import json
import os
from typing import List, Dict, Any
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("UserProfile")

# Resolve absolute path to the user store database
STORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_user_store.json")

def load_store() -> Dict[str, Any]:
    if not os.path.exists(STORE_FILE):
        return {
            "pantry": [],
            "restrictions": [],
            "shopping_list": [],
            "favorites": []
        }
    with open(STORE_FILE, "r") as f:
        return json.load(f)

def save_store(store: Dict[str, Any]) -> None:
    with open(STORE_FILE, "w") as f:
        json.dump(store, f, indent=2)

@mcp.tool()
def get_user_profile() -> Dict[str, Any]:
    """Fetches the user's profile, including pantry items, dietary restrictions,

    shopping list, and favorite recipes.
    """
    return load_store()

@mcp.tool()
def add_to_shopping_list(ingredients: List[str]) -> str:
    """Adds missing ingredients to the user's shopping list.

    Args:
        ingredients: A list of ingredient names to add to the shopping list.
    """
    store = load_store()
    shopping_list = store.get("shopping_list", [])
    
    added_items = []
    for item in ingredients:
        item_clean = item.strip().lower()
        if not item_clean:
            continue
        # Check if already in shopping list or pantry to avoid redundancy
        if item_clean not in [x.lower() for x in shopping_list] and item_clean not in [x.lower() for x in store.get("pantry", [])]:
            shopping_list.append(item.strip())
            added_items.append(item.strip())
            
    store["shopping_list"] = shopping_list
    save_store(store)
    
    if added_items:
        return f"Successfully added to shopping list: {', '.join(added_items)}"
    return "All items are already in your pantry or shopping list."

@mcp.tool()
def toggle_favorite_recipe(recipe_id: str, is_starred: bool) -> str:
    """Favorites or unfavorites a recipe.

    Args:
        recipe_id: The unique ID of the recipe (e.g. "recipe_1").
        is_starred: True to add to favorites/star, False to remove.
    """
    store = load_store()
    favorites = store.get("favorites", [])
    
    if is_starred:
        if recipe_id not in favorites:
            favorites.append(recipe_id)
            msg = f"Recipe {recipe_id} added to favorites."
        else:
            msg = f"Recipe {recipe_id} is already in favorites."
    else:
        if recipe_id in favorites:
            favorites.remove(recipe_id)
            msg = f"Recipe {recipe_id} removed from favorites."
        else:
            msg = f"Recipe {recipe_id} was not in favorites."
            
    store["favorites"] = favorites
    save_store(store)
    return msg

# Add helper tools for API convenience (so frontend/backend can directly edit pantry or restrictions)
@mcp.tool()
def update_pantry(ingredients: List[str]) -> str:
    """Directly updates the user's pantry ingredients.

    Args:
        ingredients: The full list of ingredients currently in the pantry.
    """
    store = load_store()
    store["pantry"] = [i.strip() for i in ingredients if i.strip()]
    save_store(store)
    return "Pantry updated successfully."

@mcp.tool()
def update_restrictions(restrictions: List[str]) -> str:
    """Directly updates the user's dietary restrictions.

    Args:
        restrictions: The full list of dietary restrictions (e.g. ["Vegetarian"]).
    """
    store = load_store()
    store["restrictions"] = [r.strip() for r in restrictions if r.strip()]
    save_store(store)
    return "Dietary restrictions updated successfully."

if __name__ == "__main__":
    mcp.run()
