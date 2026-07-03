import asyncio
import json
import os
import sys
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load env variables from .env if present
load_dotenv()

app = FastAPI(title="RecipeLab API")

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Resolve paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_STORE_FILE = os.path.join(BASE_DIR, "mock_user_store.json")
RECIPES_FILE = os.path.join(BASE_DIR, "mock_recipes.json")

class ChatRequest(BaseModel):
    message: str
    api_key: Optional[str] = None

class PantryRequest(BaseModel):
    ingredients: List[str]

class RestrictionsRequest(BaseModel):
    restrictions: List[str]

class ApiKeyRequest(BaseModel):
    api_key: str

def get_stored_profile() -> Dict[str, Any]:
    if not os.path.exists(USER_STORE_FILE):
        return {"pantry": [], "restrictions": [], "shopping_list": [], "favorites": []}
    with open(USER_STORE_FILE, "r") as f:
        return json.load(f)

def save_stored_profile(profile: Dict[str, Any]) -> None:
    with open(USER_STORE_FILE, "w") as f:
        json.dump(profile, f, indent=2)

@app.get("/api/profile")
async def get_profile():
    return get_stored_profile()

class SettingsRequest(BaseModel):
    spoonacular_key: str

@app.get("/api/settings")
async def get_settings():
    return {"spoonacular_key": os.environ.get("SPOONACULAR_API_KEY") or ""}

@app.post("/api/settings")
async def save_settings(req: SettingsRequest):
    os.environ["SPOONACULAR_API_KEY"] = req.spoonacular_key
    env_path = os.path.join(BASE_DIR, ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
            
    updated = False
    for i, line in enumerate(lines):
        if line.strip().startswith("SPOONACULAR_API_KEY="):
            lines[i] = f"SPOONACULAR_API_KEY={req.spoonacular_key}\n"
            updated = True
            break
            
    if not updated:
        lines.append(f"SPOONACULAR_API_KEY={req.spoonacular_key}\n")
        
    with open(env_path, "w") as f:
        f.writelines(lines)
        
    return {"status": "success"}


@app.post("/api/pantry")
async def update_pantry(req: PantryRequest):
    profile = get_stored_profile()
    profile["pantry"] = req.ingredients
    save_stored_profile(profile)
    return {"status": "success", "pantry": profile["pantry"]}

@app.post("/api/restrictions")
async def update_restrictions(req: RestrictionsRequest):
    profile = get_stored_profile()
    profile["restrictions"] = req.restrictions
    save_stored_profile(profile)
    return {"status": "success", "restrictions": profile["restrictions"]}

@app.post("/api/shopping_list/clear")
async def clear_shopping_list():
    profile = get_stored_profile()
    profile["shopping_list"] = []
    save_stored_profile(profile)
    return {"status": "success", "shopping_list": []}

class ShoppingListSetRequest(BaseModel):
    items: List[str]

@app.post("/api/shopping_list/set")
async def set_shopping_list(req: ShoppingListSetRequest):
    """Replace the shopping list with exactly the provided items."""
    profile = get_stored_profile()
    profile["shopping_list"] = [i.strip() for i in req.items if i.strip()]
    save_stored_profile(profile)
    return {"status": "success", "shopping_list": profile["shopping_list"]}

class ShoppingListAddRequest(BaseModel):
    ingredients: List[str]

@app.post("/api/shopping_list/add")
async def add_to_shopping_list(req: ShoppingListAddRequest):
    profile = get_stored_profile()
    shopping_list = profile.get("shopping_list", [])
    added = []
    for item in req.ingredients:
        item_clean = item.strip().lower()
        if not item_clean:
            continue
        if item_clean not in [x.lower() for x in shopping_list] and item_clean not in [x.lower() for x in profile.get("pantry", [])]:
            shopping_list.append(item.strip())
            added.append(item.strip())
    profile["shopping_list"] = shopping_list
    save_stored_profile(profile)
    return {"status": "success", "added": added, "shopping_list": shopping_list}

class FavoriteToggleRequest(BaseModel):
    recipe_id: str
    is_starred: bool

@app.post("/api/favorites/toggle")
async def toggle_favorite(req: FavoriteToggleRequest):
    profile = get_stored_profile()
    favorites = profile.get("favorites", [])
    if req.is_starred:
        if req.recipe_id not in favorites:
            favorites.append(req.recipe_id)
    else:
        if req.recipe_id in favorites:
            favorites.remove(req.recipe_id)
    profile["favorites"] = favorites
    save_stored_profile(profile)
    return {"status": "success", "favorites": favorites}

# ---------------------------------------------------------------------------
# Recipes API
# ---------------------------------------------------------------------------

def load_recipes() -> List[Dict[str, Any]]:
    if not os.path.exists(RECIPES_FILE):
        return []
    with open(RECIPES_FILE, "r") as f:
        return json.load(f)

@app.get("/api/recipes")
async def get_all_recipes():
    """Return the full recipe database."""
    return load_recipes()

@app.get("/api/recipes/search")
async def search_recipes(
    ingredients: str = "",
    strict: bool = False,
    diet: str = ""
):
    """
    Search recipes by ingredient keywords and optional diet filters.
    - ingredients: comma-separated list (e.g. "eggs,spinach")
    - strict: if true, only return recipes where ALL ingredients are covered
    - diet: comma-separated restrictions (e.g. "Vegetarian,Gluten-Free")
    """
    recipes = load_recipes()
    profile = get_stored_profile()

    # Parse inputs
    ing_list = [i.strip().lower() for i in ingredients.split(",") if i.strip()]
    diet_list = [d.strip().lower() for d in diet.split(",") if d.strip()]

    # If no ingredient query, use the user's pantry
    if not ing_list:
        ing_list = [i.lower() for i in profile.get("pantry", [])]

    results = []
    for r in recipes:
        recipe_ings = [i.strip().lower() for i in r["ingredients"]]
        missing = [i for i in recipe_ings if i not in ing_list]
        matched = len(recipe_ings) - len(missing)
        pct = round((matched / len(recipe_ings)) * 100, 1) if recipe_ings else 0.0

        if strict and missing:
            continue
        if not strict and pct < 30 and len(recipe_ings) > 1:
            continue

        # Diet filtering
        skip = False
        for restriction in diet_list:
            if "gluten" in restriction and not r.get("is_gluten_free"):
                skip = True; break
            if "dairy" in restriction and not r.get("is_dairy_free"):
                skip = True; break
            if restriction == "vegan" and not r.get("is_vegan"):
                skip = True; break
            if "vegetarian" in restriction and not r.get("is_vegetarian"):
                skip = True; break
        if skip:
            continue

        results.append({**r, "missing_ingredients": missing, "match_percentage": pct, "source": "local"})

    results.sort(key=lambda x: x["match_percentage"], reverse=True)

    # Check if best match is < 95.0%
    best_match = results[0]["match_percentage"] if results else 0.0
    if best_match < 95.0 and ing_list:
        from recipe_db_mcp import fetch_internet_recipes
        internet_recipes = await fetch_internet_recipes(ing_list)
        for r in internet_recipes:
            recipe_ings = [i.strip().lower() for i in r["ingredients"]]
            missing = [i for i in recipe_ings if i not in ing_list]
            matched = len(recipe_ings) - len(missing)
            pct = round((matched / len(recipe_ings)) * 100, 1) if recipe_ings else 0.0

            if strict and missing:
                continue
            if not strict and pct < 30 and len(recipe_ings) > 1:
                continue

            # Diet filtering
            skip = False
            for restriction in diet_list:
                if "gluten" in restriction and not r.get("is_gluten_free"):
                    skip = True; break
                if "dairy" in restriction and not r.get("is_dairy_free"):
                    skip = True; break
                if restriction == "vegan" and not r.get("is_vegan"):
                    skip = True; break
                if "vegetarian" in restriction and not r.get("is_vegetarian"):
                    skip = True; break
            if skip:
                continue

            results.append({
                **r,
                "missing_ingredients": missing,
                "match_percentage": pct
            })

        # Re-sort combined list
        results.sort(key=lambda x: x["match_percentage"], reverse=True)

    return results

@app.get("/api/recipes/{recipe_id}")
async def get_recipe(recipe_id: str):
    """Return a single recipe by ID."""
    recipes = load_recipes()
    for r in recipes:
        if r["id"] == recipe_id:
            return r
            
    # Lookup internet recipe by prefix if not in local db
    if recipe_id.startswith("internet_spoonacular_"):
        spoon_id = recipe_id.replace("internet_spoonacular_", "")
        api_key = os.environ.get("SPOONACULAR_API_KEY") or ""
        if api_key.strip():
            import httpx
            url = f"https://api.spoonacular.com/recipes/{spoon_id}/information"
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params={"apiKey": api_key.strip()}, timeout=10.0)
                if response.status_code == 200:
                    r = response.json()
                    recipe_ings = [ing.get("name", "") for ing in r.get("extendedIngredients", []) if ing.get("name")]
                    steps = []
                    if r.get("analyzedInstructions"):
                        for inst in r["analyzedInstructions"]:
                            for step in inst.get("steps", []):
                                num = step.get("number", "")
                                desc = step.get("step", "")
                                steps.append(f"{num}. {desc}" if num else desc)
                    instructions = "\n".join(steps) or r.get("summary", "No instructions available.")
                    return {
                        "id": recipe_id,
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
                    }
                    
    elif recipe_id.startswith("internet_mealdb_"):
        meal_id = recipe_id.replace("internet_mealdb_", "")
        import httpx
        from recipe_db_mcp import infer_dietary_tags
        url = f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={meal_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
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
                    return {
                        "id": recipe_id,
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
                    }
                    
    raise HTTPException(status_code=404, detail=f"Recipe '{recipe_id}' not found.")

# ---------------------------------------------------------------------------
# Pantry – add a single item
# ---------------------------------------------------------------------------

class PantryAddRequest(BaseModel):
    ingredient: str

@app.post("/api/pantry/add")
async def add_pantry_item(req: PantryAddRequest):
    """Add a single ingredient to the pantry."""
    profile = get_stored_profile()
    item = req.ingredient.strip()
    if not item:
        raise HTTPException(status_code=400, detail="Ingredient name cannot be empty.")
    if item.lower() not in [i.lower() for i in profile.get("pantry", [])]:
        profile.setdefault("pantry", []).append(item)
        save_stored_profile(profile)
    return {"status": "success", "pantry": profile["pantry"]}

# ---------------------------------------------------------------------------
# Shopping list – remove a single item
# ---------------------------------------------------------------------------

@app.delete("/api/shopping_list/{item}")
async def remove_shopping_item(item: str):
    """Remove a specific item from the shopping list."""
    profile = get_stored_profile()
    before = profile.get("shopping_list", [])
    after = [x for x in before if x.lower() != item.lower()]
    profile["shopping_list"] = after
    save_stored_profile(profile)
    return {"status": "success", "shopping_list": after}



async def execute_mock_fallback(message: str) -> str:
    msg_lower = message.lower()
    profile = get_stored_profile()
    pantry = profile.get("pantry", [])
    restrictions = profile.get("restrictions", [])
    
    # 1. Intent: Star / Favorite
    if "star" in msg_lower or "favorite" in msg_lower or "starred" in msg_lower:
        with open(RECIPES_FILE, "r") as f:
            recipes = json.load(f)
        
        matched_recipe = None
        for r in recipes:
            if r["name"].lower() in msg_lower or r["id"].lower() in msg_lower:
                matched_recipe = r
                break
        
        if matched_recipe:
            is_starred = "unstar" not in msg_lower and "remove" not in msg_lower
            from user_profile_mcp import toggle_favorite_recipe
            res_msg = toggle_favorite_recipe(matched_recipe["id"], is_starred)
            return (
                f"🤖 **[Local Orchestrator Fallback]**\n\n"
                f"I detected that you want to star/favorite a recipe. "
                f"I delegated this to the **Preferences Agent**.\n\n"
                f"*Preferences Agent response:*\n"
                f"\"I have updated your favorites for **{matched_recipe['name']}**. {res_msg}\""
            )
        else:
            return (
                f"🤖 **[Local Orchestrator Fallback]**\n\n"
                f"I detected you want to manage starred recipes, but I couldn't identify the recipe name in your query. "
                f"Please specify the name of the recipe (e.g., 'Star Spinach Tomato Omelette')."
            )

    # 2. Intent: Add missing to shopping list
    if "add" in msg_lower and ("shopping" in msg_lower or "list" in msg_lower or "buy" in msg_lower):
        with open(RECIPES_FILE, "r") as f:
            recipes = json.load(f)
            
        matched_recipe = None
        for r in recipes:
            if r["name"].lower() in msg_lower:
                matched_recipe = r
                break
                
        if matched_recipe:
            user_ing = {i.lower() for i in pantry}
            missing = [i for i in matched_recipe["ingredients"] if i.lower() not in user_ing]
            if missing:
                from user_profile_mcp import add_to_shopping_list
                res_msg = add_to_shopping_list(missing)
                return (
                    f"🤖 **[Local Orchestrator Fallback]**\n\n"
                    f"I detected that you want to add ingredients for **{matched_recipe['name']}** to your shopping list. "
                    f"I delegated this to the **List Manager Agent**.\n\n"
                    f"*List Manager Agent response:*\n"
                    f"\"Calculated missing ingredients: {', '.join(missing)}.\n"
                    f"{res_msg}\""
                )
            else:
                return (
                    f"🤖 **[Local Orchestrator Fallback]**\n\n"
                    f"I analyzed **{matched_recipe['name']}** and verified that you already have all the ingredients in your pantry! No shopping is needed."
                )

    # 3. Intent: Search Recipes
    search_ingredients = []
    with open(RECIPES_FILE, "r") as f:
        recipes = json.load(f)
    all_known_ingredients = set()
    for r in recipes:
        for ing in r["ingredients"]:
            all_known_ingredients.add(ing.lower())

    # Normalize the message: remove punctuation for matching
    clean_msg = msg_lower.replace(",", " ").replace(".", " ").replace(";", " ")

    # First pass: match multi-word ingredients (e.g. "sour cream", "baking soda", "olive oil")
    multi_word_ings = sorted(
        [ing for ing in all_known_ingredients if " " in ing],
        key=lambda x: -len(x)  # longest first so "baking soda" wins over "soda"
    )
    remaining_msg = clean_msg
    for ing in multi_word_ings:
        if ing in remaining_msg:
            search_ingredients.append(ing)
            remaining_msg = remaining_msg.replace(ing, " ")  # consume matched text

    # Second pass: single-word ingredients from what's left
    single_word_ings = {ing for ing in all_known_ingredients if " " not in ing}
    for word in remaining_msg.split():
        if word in single_word_ings:
            search_ingredients.append(word)

    # Deduplicate while preserving order
    seen = set()
    unique_ingredients = []
    for ing in search_ingredients:
        if ing not in seen:
            seen.add(ing)
            unique_ingredients.append(ing)
    search_ingredients = unique_ingredients

    # Synonym/shorthand expansion: map common short forms to known DB ingredient names
    SYNONYMS = {
        "soda": "baking soda",
        "baking": "baking soda",
        "lemon": "lemon juice",
        "chili": "chili flakes",
        "cheddar": "cheddar cheese",
    }
    for word in clean_msg.split():
        if word in SYNONYMS:
            candidate = SYNONYMS[word]
            if candidate in all_known_ingredients and candidate not in search_ingredients:
                search_ingredients.append(candidate)

    used_pantry = False
    if not search_ingredients:
        search_ingredients = pantry
        used_pantry = True
        
    strict_mode = "only" in msg_lower or "strict" in msg_lower
    
    from recipe_db_mcp import search_recipes_by_ingredients, filter_by_diet
    raw_results = await search_recipes_by_ingredients(search_ingredients, strict_mode)
    filtered_results = filter_by_diet(raw_results, restrictions)
    
    if not filtered_results:
        return (
            f"🤖 **[Local Orchestrator Fallback]**\n\n"
            f"I delegated the recipe search to the **Recipe Finder Agent** using ingredients: "
            f"*{', '.join(search_ingredients)}* (Strict: {strict_mode}, Restrictions: {', '.join(restrictions) if restrictions else 'None'}).\n\n"
            f"**Recipe Finder Agent response:**\n"
            f"\"No matching recipes found in the database. Try adjusting your pantry items or dietary restrictions.\""
        )
        
    response_lines = [
        f"🤖 **[Local Orchestrator Fallback]**\n\n"
        f"I delegated the recipe search to the **Recipe Finder Agent**.\n\n"
        f"**Recipe Finder Agent response:**\n"
        f"\"Here are the best matches for your request using "
        f"{'your pantry ingredients' if used_pantry else 'the specified ingredients'}: {', '.join(search_ingredients)} "
        f"(Strict: {strict_mode}, Restrictions: {', '.join(restrictions) if restrictions else 'None'}).\"\n"
    ]
    
    for r in filtered_results:
        pct = r["match_percentage"]
        badge = "✅ STRICT MATCH" if pct == 100 else f"⚠️ LOOSE MATCH ({pct}% matching)"
        
        response_lines.append(f"### {r['name']}")
        response_lines.append(f"*{badge}*")
        response_lines.append(f"**Ingredients:** {', '.join(r['ingredients'])}")
        
        if r["missing_ingredients"]:
            response_lines.append(f"❌ **Missing:** {', '.join(r['missing_ingredients'])}")
            
        response_lines.append(f"**Instructions:** {r['instructions']}")
        response_lines.append("---")
        
    return "\n".join(response_lines)

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    # Determine the API key to use
    api_key = req.api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Gemini API Key is missing. Please provide it in the request or set it in the backend configuration."
        )

    # Import google.antigravity here to ensure we capture any dynamically set env vars
    try:
        from google.antigravity import Agent, LocalAgentConfig, types
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to import google-antigravity SDK: {str(e)}"
        )

    # Resolve python interpreter path to run our MCP servers
    python_interpreter = sys.executable

    # Configure the MCP servers
    mcp_servers = [
        types.McpStdioServer(
            name="recipe_db",
            command=python_interpreter,
            args=[os.path.join(BASE_DIR, "recipe_db_mcp.py")],
        ),
        types.McpStdioServer(
            name="user_profile",
            command=python_interpreter,
            args=[os.path.join(BASE_DIR, "user_profile_mcp.py")],
        )
    ]

    # Create the Concierge Agent config
    system_instructions = (
        "You are an elite culinary concierge. Guide the user through meal planning, "
        "track their pantry, and coordinate with specialized sub-agents.\n\n"
        "Available sub-agents you can spawn using the `start_subagent` tool:\n"
        "1. Recipe Finder Agent: Matches ingredients against recipes and strictly filters by diet restrictions.\n"
        "2. Preferences Agent: Handles favoriting/starring recipes and saving profiles.\n"
        "3. List Manager Agent: Manages the shopping list for missing ingredients.\n\n"
        "CRITICAL RULES & WORKFLOWS:\n"
        "- ALWAYS inspect the user's profile first using `get_user_profile` to know their pantry and restrictions.\n"
        "- When the user MENTIONS specific ingredients in their message (e.g. 'I have eggs, flour, sour cream'), "
        "  use THOSE ingredients as the search query — NOT the pantry. "
        "  Extract all ingredients listed in the message and pass them as the `ingredients` list to the Recipe Finder Agent.\n"
        "- When asked to find recipes:\n"
        "  1. Extract any ingredients explicitly mentioned by the user in the message. If none are mentioned, use the pantry.\n"
        "  2. Spawn a 'Recipe Finder Agent' subagent to run `search_recipes_by_ingredients` with those ingredients "
        "     (use strict_mode=True if requested to ONLY use those ingredients, otherwise strict_mode=False).\n"
        "  3. Direct the subagent to run `filter_by_diet` on those recipes using the user's dietary restrictions.\n"
        "  4. Enforce the dietary guardrails strictly. If a user is Vegetarian, Gluten-Free, Vegan, or Dairy-Free, "
        "     filter out any recipe violating these tags. Do not show them under any circumstances.\n"
        "- When asked to star or favorite a recipe:\n"
        "  - Spawn a 'Preferences Agent' subagent to run `toggle_favorite_recipe`.\n"
        "- When asked to save missing ingredients to buy or update the shopping list:\n"
        "  - Spawn a 'List Manager Agent' subagent to run `add_to_shopping_list`.\n"
        "- Keep the user updated on which sub-agent is performing which action. Show that you are delegating to them!"
    )

    config = LocalAgentConfig(
        api_key=api_key,
        model="gemini-2.0-flash",
        system_instructions=system_instructions,
        mcp_servers=mcp_servers,
        capabilities=types.CapabilitiesConfig(
            enable_subagents=True,
        )
    )

    AGENT_TIMEOUT_SECONDS = 90  # give the real agent up to 90 seconds to respond

    async def run_agent():
        """Run the real agent and return streamed chunks as a list."""
        chunks = []
        async with Agent(config) as agent:
            response = await agent.chat(req.message)
            try:
                async for thought in response.thoughts:
                    chunks.append(("thought", thought))
            except Exception:
                pass
            async for chunk in response:
                chunks.append(("text", chunk))
        return chunks

    async def event_generator():
        try:
            # Give the agent a bounded window; on timeout, fall through to fallback
            agent_chunks = await asyncio.wait_for(run_agent(), timeout=AGENT_TIMEOUT_SECONDS)
            for kind, content in agent_chunks:
                yield f"data: {json.dumps({'type': kind, 'content': content})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            # Covers asyncio.TimeoutError, 503s, connection errors, quota errors, etc.
            err_str = str(e)
            is_quota = "429" in err_str or "quota" in err_str.lower() or "RESOURCE_EXHAUSTED" in err_str
            is_timeout = isinstance(e, asyncio.TimeoutError)

            if is_quota:
                reason = "API quota exceeded"
            elif is_timeout:
                reason = "Agent timeout"
            else:
                reason = type(e).__name__

            print(f"Agent unavailable ({reason}): {e}. Running local fallback...")
            notice = f"Agent unavailable ({reason}) — switching to instant local Recipe Engine...\n"
            yield f"data: {json.dumps({'type': 'thought', 'content': notice})}\n\n"
            await asyncio.sleep(0.3)

            try:
                fallback_text = await execute_mock_fallback(req.message)
            except Exception as fe:
                fallback_text = f"🤖 **[Local Engine]**\n\nCould not process request: {str(fe)}"

            # Stream words in small chunks for a typing effect
            words = fallback_text.split(" ")
            for i in range(0, len(words), 4):
                chunk = " ".join(words[i:i+4]) + " "
                yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
                await asyncio.sleep(0.03)

            yield f"data: {json.dumps({'type': 'done'})}\n\n"


    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Serve the static files from the 'frontend' directory at root
# Note: we will mount static files after implementing frontend
if os.path.exists(os.path.join(BASE_DIR, "frontend")):
    app.mount("/", StaticFiles(directory=os.path.join(BASE_DIR, "frontend"), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
