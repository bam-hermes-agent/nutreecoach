"""
NutreeCoach — Service d'accès aux bases de données alimentaires
"""

import json
import logging
import os

import httpx
from models.database import db

logger = logging.getLogger(__name__)

# ── OpenFoodFacts (gratuit, excellent couverture FR/EU) ─

OFF_API = "https://world.openfoodfacts.net/api/v2"


async def search_food(query: str, limit: int = 5) -> list[dict]:
    """Recherche un aliment par texte dans OpenFoodFacts."""
    params = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "page_size": limit,
        "json": 1,
        "lc": "fr",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{OFF_API}/search", params=params)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logger.warning(f"OpenFoodFacts search failed: {e}")
        return await _fallback_nutrition_search(query)

    products = data.get("products", [])
    results = []
    for p in products:
        if not p.get("product_name"):
            continue
        nutriments = p.get("nutriments", {})
        results.append({
            "name": p.get("product_name", "Inconnu"),
            "brand": p.get("brands", ""),
            "barcode": p.get("code", ""),
            "kcal_per_100g": nutriments.get("energy-kcal_100g", 0) or 0,
            "protein_per_100g": nutriments.get("proteins_100g", 0) or 0,
            "carbs_per_100g": nutriments.get("carbohydrates_100g", 0) or 0,
            "fat_per_100g": nutriments.get("fat_100g", 0) or 0,
        })

    return results[:limit]


async def search_by_barcode(barcode: str) -> dict | None:
    """Recherche un produit par code-barres."""
    # Vérifier le cache local d'abord
    cached = await db.get_food_by_barcode(barcode)
    if cached:
        return dict(cached)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{OFF_API}/product/{barcode}.json")
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logger.warning(f"Barcode lookup failed for {barcode}: {e}")
        return None

    product = data.get("product")
    if not product:
        return None

    nutriments = product.get("nutriments", {})
    result = {
        "name": product.get("product_name", "Inconnu"),
        "brand": product.get("brands", ""),
        "barcode": barcode,
        "kcal_per_100g": nutriments.get("energy-kcal_100g", 0) or 0,
        "protein_per_100g": nutriments.get("proteins_100g", 0) or 0,
        "carbs_per_100g": nutriments.get("carbohydrates_100g", 0) or 0,
        "fat_per_100g": nutriments.get("fat_100g", 0) or 0,
    }

    # Mettre en cache
    await db.cache_food(
        barcode=barcode,
        name=result["name"],
        brand=result["brand"],
        kcal=result["kcal_per_100g"],
        protein=result["protein_per_100g"],
        carbs=result["carbs_per_100g"],
        fat=result["fat_per_100g"],
    )

    return result


# ── Fallback simple ─────────────────────────────────────

COMMON_FOODS = {
    "riz": {"kcal": 130, "protein": 2.7, "carbs": 28, "fat": 0.3},
    "poulet": {"kcal": 165, "protein": 31, "carbs": 0, "fat": 3.6},
    "pâtes": {"kcal": 131, "protein": 5, "carbs": 25, "fat": 1.1},
    "pain": {"kcal": 265, "protein": 9, "carbs": 49, "fat": 3.2},
    "œuf": {"kcal": 155, "protein": 13, "carbs": 1.1, "fat": 11},
    "avocat": {"kcal": 160, "protein": 2, "carbs": 8.5, "fat": 14.7},
    "saumon": {"kcal": 208, "protein": 20, "carbs": 0, "fat": 13},
    "banane": {"kcal": 89, "protein": 1.1, "carbs": 23, "fat": 0.3},
    "pomme": {"kcal": 52, "protein": 0.3, "carbs": 14, "fat": 0.2},
    "brocoli": {"kcal": 34, "protein": 2.8, "carbs": 7, "fat": 0.4},
    "patate douce": {"kcal": 86, "protein": 1.6, "carbs": 20, "fat": 0.1},
    "yaourt": {"kcal": 63, "protein": 5.3, "carbs": 4.7, "fat": 3.3},
    "fromage": {"kcal": 402, "protein": 25, "carbs": 1.3, "fat": 33},
    "beurre": {"kcal": 717, "protein": 0.9, "carbs": 0.1, "fat": 81},
    "huile olive": {"kcal": 884, "protein": 0, "carbs": 0, "fat": 100},
    "lentilles": {"kcal": 116, "protein": 9, "carbs": 20, "fat": 0.4},
    "thon": {"kcal": 184, "protein": 30, "carbs": 0, "fat": 7},
    "tofu": {"kcal": 76, "protein": 8, "carbs": 1.9, "fat": 4.8},
}


async def _fallback_nutrition_search(query: str) -> list[dict]:
    """Fallback si OpenFoodFacts est indisponible."""
    query_lower = query.lower()
    results = []

    for name, data in COMMON_FOODS.items():
        if name in query_lower:
            results.append({
                "name": name.capitalize(),
                "brand": "",
                "barcode": "",
                "kcal_per_100g": data["kcal"],
                "protein_per_100g": data["protein"],
                "carbs_per_100g": data["carbs"],
                "fat_per_100g": data["fat"],
            })

    return results[:5]


async def parse_meal_with_llm(text: str) -> list[dict]:
    """
    Utilise DeepSeek pour parser un texte de repas en aliments structurés.
    Retourne [{\"food\": \"poulet\", \"quantity_g\": 300}, ...]
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return _fallback_parse_meal(text)

    prompt = (
        "Tu aides à parser des descriptions de repas. "
        "Extrais les aliments et leurs quantités. "
        "Réponds UNIQUEMENT avec un tableau JSON valide, rien d'autre.\n\n"
        f'Message: "{text}"\n\n'
        "Format: [{\"food\": \"nom_aliment\", \"quantity_g\": nombre_en_grammes}]\n\n"
        "Règles:\n"
        "- quantity_g est TOUJOURS en grammes (2 oeufs ≈ 100g, 1 filet de poulet ≈ 150g)\n"
        "- Si pas de quantité, mets 100 par défaut\n"
        "- Extrais TOUS les aliments listés\n"
        "- Le nom d'aliment doit être court et générique (ex: 'poulet' pas 'poulet rôti au four')"
    )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "Tu réponds uniquement en JSON valide, sans aucun commentaire."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()

            # Nettoyer le JSON (le LLM peut ajouter des ``` markdown)
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                content = content.rsplit("```", 1)[0].strip()

            items = json.loads(content)
            if isinstance(items, list):
                return [
                    {"food": item["food"], "quantity_g": int(item["quantity_g"])}
                    for item in items
                ]
    except Exception as e:
        logger.warning(f"LLM meal parsing failed: {e}")

    return _fallback_parse_meal(text)


def _fallback_parse_meal(text: str) -> list[dict]:
    """Fallback regex si l'API DeepSeek est indisponible."""
    import re

    lines = re.split(r'[,;\n\r]+', text.strip())
    items = []
    for line in lines:
        line = line.strip().lstrip("-*•").strip()
        if not line:
            continue
        m = re.match(r"(\d+)\s*g\s*(?:de|d'|)\s*(.+)", line)
        if m:
            items.append({"food": m.group(2).strip(), "quantity_g": int(m.group(1))})
        else:
            items.append({"food": line, "quantity_g": 100})
    return items
