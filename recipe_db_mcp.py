import json
import os
from typing import List, Dict, Any
from mcp.server.fastmcp import FastMCP
import httpx
from dotenv import load_dotenv

# Load env variables from .env if present
load_dotenv()

mcp = FastMCP("RecipeDB")

# Resolve absolute path to the recipes database
RECIPES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_recipes.json")

def load_recipes() -> List[Dict[str, Any]]:
    if not os.path.exists(RECIPES_FILE):
        return []
    with open(RECIPES_FILE, "r") as f:
        return json.load(f)

# Helper to infer dietary tags for database/internet recipes if missing
MEATS_AND_FISH = {
    "chicken", "beef", "pork", "shrimp", "prawn", "salmon", "tuna", "lamb", "bacon", 
    "sausage", "turkey", "ham", "fish", "crab", "lobster", "duck", "meat", "steak", 
    "pepperoni", "gelatin", "anchovies", "cod", "pork chop", "sirloin"
}
ANIMAL_PRODUCTS = MEATS_AND_FISH.union({
    "egg", "eggs", "milk", "butter", "cheese", "cream", "yogurt", "honey", "mayonnaise", "parmesan"
})
DAIRY_ITEMS = {
    "milk", "butter", "cheese", "cream", "yogurt", "sour cream", "ghee", "parmesan"
}
GLUTEN_ITEMS = {
    "flour", "bread", "pasta", "wheat", "barley", "rye", "semolina", "couscous", "noodle"
}

def infer_dietary_tags(ingredients: List[str]) -> Dict[str, bool]:
    is_vegetarian = True
    is_vegan = True
    is_dairy_free = True
    is_gluten_free = True
    
    for ing in ingredients:
        ing_lower = ing.lower()
        if any(meat in ing_lower for meat in MEATS_AND_FISH):
            is_vegetarian = False
            is_vegan = False
        if any(animal in ing_lower for animal in ANIMAL_PRODUCTS):
            is_vegan = False
        if any(dairy in ing_lower for dairy in DAIRY_ITEMS):
            is_dairy_free = False
        if any(gluten in ing_lower for gluten in GLUTEN_ITEMS):
            is_gluten_free = False
            
    return {
        "is_vegetarian": is_vegetarian,
        "is_vegan": is_vegan,
        "is_dairy_free": is_dairy_free,
        "is_gluten_free": is_gluten_free
    }

async def fetch_internet_recipes(ingredients: List[str]) -> List[Dict[str, Any]]:
    if not ingredients:
        return []
        
    api_key = os.environ.get("SPOONACULAR_API_KEY") or ""
    results = []
    
    # 1. Try Spoonacular if key is provided
    if api_key.strip():
        try:
            ingredients_str = ",".join(ingredients)
            url = "https://api.spoonacular.com/recipes/complexSearch"
            params = {
                "includeIngredients": ingredients_str,
                "fillIngredients": "true",
                "addRecipeInformation": "true",
                "instructionsRequired": "true",
                "number": "5",
                "apiKey": api_key.strip()
            }
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=10.0)
                if response.status_code == 200:
                    data = response.json()
                    for r in data.get("results", []):
                        recipe_ings = [ing.get("name", "") for ing in r.get("extendedIngredients", []) if ing.get("name")]
                        
                        steps = []
                        if r.get("analyzedInstructions"):
                            for inst in r["analyzedInstructions"]:
                                for step in inst.get("steps", []):
                                    num = step.get("number", "")
                                    desc = step.get("step", "")
                                    steps.append(f"{num}. {desc}" if num else desc)
                        instructions = "\n".join(steps)
                        if not instructions:
                            instructions = r.get("summary", "No instructions available.")
                            
                        results.append({
                            "id": f"internet_spoonacular_{r.get('id')}",
                            "name": r.get("title", "Unnamed Recipe"),
                            "ingredients": recipe_ings,
                            "instructions": instructions,
                            "is_gluten_free": r.get("glutenFree", False),
                            "is_dairy_free": r.get("dairyFree", False),
                            "is_vegetarian": r.get("vegetarian", False),
                            "is_vegan": r.get("vegan", False),
                            "source": "internet",
                            "source_url": r.get("sourceUrl", ""),
                            "image": r.get("image", "")
                        })
        except Exception as e:
            print(f"Error fetching from Spoonacular API: {e}")
            
    # 2. Fall back to TheMealDB if no Spoonacular key or no results
    if not results:
        try:
            async with httpx.AsyncClient() as client:
                meal_ids_seen = set()
                meals_to_lookup = []
                
                # Search by first 3 ingredients
                for ing in ingredients[:3]:
                    if len(meals_to_lookup) >= 5:
                        break
                    url = f"https://www.themealdb.com/api/json/v1/1/filter.php?i={ing}"
                    response = await client.get(url, timeout=5.0)
                    if response.status_code == 200:
                        data = response.json()
                        meals = data.get("meals")
                        if meals:
                            for m in meals:
                                if m["idMeal"] not in meal_ids_seen:
                                    meal_ids_seen.add(m["idMeal"])
                                    meals_to_lookup.append(m["idMeal"])
                                    if len(meals_to_lookup) >= 5:
                                        break
                                        
                # If still nothing, search by ingredients as name query
                if not meals_to_lookup:
                    for ing in ingredients[:2]:
                        url = f"https://www.themealdb.com/api/json/v1/1/search.php?s={ing}"
                        response = await client.get(url, timeout=5.0)
                        if response.status_code == 200:
                            data = response.json()
                            meals = data.get("meals")
                            if meals:
                                for m in meals:
                                    if m["idMeal"] not in meal_ids_seen:
                                        meal_ids_seen.add(m["idMeal"])
                                        meals_to_lookup.append(m["idMeal"])
                                        if len(meals_to_lookup) >= 5:
                                            break
                                            
                # Lookup details for collected meal IDs
                for meal_id in meals_to_lookup[:5]:
                    lookup_url = f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={meal_id}"
                    response = await client.get(lookup_url, timeout=5.0)
                    if response.status_code == 200:
                        data = response.json()
                        meal_details_list = data.get("meals")
                        if meal_details_list:
                            meal = meal_details_list[0]
                            
                            recipe_ings = []
                            for i in range(1, 21):
                                ing_name = meal.get(f"strIngredient{i}")
                                if ing_name and ing_name.strip():
                                    recipe_ings.append(ing_name.strip())
                                    
                            diet_tags = infer_dietary_tags(recipe_ings)
                            
                            results.append({
                                "id": f"internet_mealdb_{meal.get('idMeal')}",
                                "name": meal.get("strMeal", "Unnamed Meal"),
                                "ingredients": recipe_ings,
                                "instructions": meal.get("strInstructions", "No instructions available."),
                                "is_gluten_free": diet_tags["is_gluten_free"],
                                "is_dairy_free": diet_tags["is_dairy_free"],
                                "is_vegetarian": diet_tags["is_vegetarian"],
                                "is_vegan": diet_tags["is_vegan"],
                                "source": "internet",
                                "source_url": meal.get("strSource") or f"https://www.themealdb.com/meal/{meal.get('idMeal')}",
                                "image": meal.get("strMealThumb", "")
                            })
        except Exception as e:
            print(f"Error fetching from TheMealDB: {e}")
            
    return results

@mcp.tool()
async def search_recipes_by_ingredients(ingredients: List[str], strict_mode: bool = False) -> List[Dict[str, Any]]:
    """Search recipes in the database based on available ingredients.
    
    If the best match percentage is less than 95%, it automatically queries the internet
    (Spoonacular/TheMealDB) to fetch additional recipe suggestions.

    Args:
        ingredients: A list of ingredients available (e.g. ["eggs", "spinach"]).
        strict_mode: If True, returns only recipes that can be made entirely with the provided ingredients.
                     If False, returns recipes where most ingredients are available and details what is missing.
    """
    recipes = load_recipes()
    results = []
    
    # Normalize input ingredients for comparison
    user_ingredients = {i.strip().lower() for i in ingredients if i}
    
    for r in recipes:
        recipe_ingredients = [i.strip().lower() for i in r["ingredients"]]
        recipe_ing_set = set(recipe_ingredients)
        
        # Missing ingredients are ingredients in the recipe that the user does not have
        missing = [i for i in recipe_ingredients if i not in user_ingredients]
        
        # If strict mode, user must have ALL ingredients (missing list is empty)
        if strict_mode and len(missing) > 0:
            continue
            
        match_count = len(recipe_ing_set) - len(missing)
        match_percentage = (match_count / len(recipe_ing_set)) * 100 if recipe_ing_set else 0
        
        # For loose search, let's return recipes if the user has at least 30% of the ingredients
        # or if the recipe is very simple.
        if not strict_mode and match_percentage < 30:
            continue
            
        results.append({
            "id": r["id"],
            "name": r["name"],
            "ingredients": r["ingredients"],
            "instructions": r["instructions"],
            "is_gluten_free": r.get("is_gluten_free", False),
            "is_dairy_free": r.get("is_dairy_free", False),
            "is_vegetarian": r.get("is_vegetarian", False),
            "is_vegan": r.get("is_vegan", False),
            "missing_ingredients": missing,
            "match_percentage": round(match_percentage, 1),
            "source": "local"
        })
        
    # Sort results by match percentage (highest match first)
    results.sort(key=lambda x: x["match_percentage"], reverse=True)
    
    # Check if the best match is < 95% (or no local results at all)
    best_match = results[0]["match_percentage"] if results else 0.0
    
    if best_match < 95.0 and ingredients:
        internet_recipes = await fetch_internet_recipes(ingredients)
        for r in internet_recipes:
            recipe_ingredients = [i.strip().lower() for i in r["ingredients"]]
            recipe_ing_set = set(recipe_ingredients)
            
            missing = [i for i in recipe_ingredients if i not in user_ingredients]
            
            if strict_mode and len(missing) > 0:
                continue
                
            match_count = len(recipe_ing_set) - len(missing)
            match_percentage = (match_count / len(recipe_ing_set)) * 100 if recipe_ing_set else 0
            
            if not strict_mode and match_percentage < 30:
                continue
                
            results.append({
                "id": r["id"],
                "name": r["name"],
                "ingredients": r["ingredients"],
                "instructions": r["instructions"],
                "is_gluten_free": r["is_gluten_free"],
                "is_dairy_free": r["is_dairy_free"],
                "is_vegetarian": r["is_vegetarian"],
                "is_vegan": r["is_vegan"],
                "missing_ingredients": missing,
                "match_percentage": round(match_percentage, 1),
                "source": "internet",
                "source_url": r.get("source_url", ""),
                "image": r.get("image", "")
            })
            
        # Re-sort combined list
        results.sort(key=lambda x: x["match_percentage"], reverse=True)
        
    return results

@mcp.tool()
def filter_by_diet(recipes: List[Dict[str, Any]], restrictions: List[str]) -> List[Dict[str, Any]]:
    """Filters a list of recipes according to dietary restrictions.

    Args:
        recipes: A list of recipe dictionaries (as returned by search_recipes_by_ingredients).
        restrictions: A list of dietary restrictions (e.g. ["Vegetarian", "Gluten-Free"]).
                      Valid values: "Dairy-Free", "Gluten-Free", "Vegetarian", "Vegan".
    """
    if not restrictions:
        return recipes
        
    filtered = []
    # Normalize restrictions to lower case
    normalized_restrictions = {r.strip().lower() for r in restrictions if r}
    
    for r in recipes:
        keep = True
        for restriction in normalized_restrictions:
            if "gluten-free" in restriction and not r.get("is_gluten_free", False):
                keep = False
                break
            if "dairy-free" in restriction and not r.get("is_dairy_free", False):
                keep = False
                break
            if "vegetarian" in restriction and not r.get("is_vegetarian", False):
                keep = False
                break
            if "vegan" in restriction and not r.get("is_vegan", False):
                keep = False
                break
        if keep:
            filtered.append(r)
            
    return filtered

if __name__ == "__main__":
    mcp.run()
