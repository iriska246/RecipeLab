document.addEventListener("DOMContentLoaded", () => {
    // UI State
    let state = {
        pantry: [],
        restrictions: [],
        shopping_list: [],
        favorites: []
    };

    // DOM Elements
    const chatMessages = document.getElementById("chatMessages");
    const chatForm = document.getElementById("chatForm");
    const userInput = document.getElementById("userInput");
    const thoughtIndicator = document.getElementById("thoughtIndicator");
    const thoughtText = document.getElementById("thoughtText");
    const pantryList = document.getElementById("pantryList");
    const addPantryItemBtn = document.getElementById("addPantryItemBtn");
    const shoppingList = document.getElementById("shoppingList");
    const clearShoppingListBtn = document.getElementById("clearShoppingListBtn");
    const favoritesList = document.getElementById("favoritesList");
    const dietCheckboxes = document.querySelectorAll(".diet-checkbox");

    // API Key management
    const apiKeyInput = document.getElementById("apiKeyInput");
    const saveApiKeyBtn = document.getElementById("saveApiKeyBtn");
    const apiKeyStatus = document.getElementById("apiKeyStatus");

    const spoonKeyInput = document.getElementById("spoonKeyInput");
    const saveSpoonKeyBtn = document.getElementById("saveSpoonKeyBtn");
    const spoonKeyStatus = document.getElementById("spoonKeyStatus");

    // Load saved API key from localStorage
    const savedKey = localStorage.getItem("gemini_api_key");
    if (savedKey) {
        apiKeyInput.value = savedKey;
        apiKeyStatus.textContent = "✓ Key saved";
        apiKeyStatus.style.color = "#4ade80";
    }

    saveApiKeyBtn.addEventListener("click", () => {
        const key = apiKeyInput.value.trim();
        if (key) {
            localStorage.setItem("gemini_api_key", key);
            apiKeyStatus.textContent = "✓ Key saved";
            apiKeyStatus.style.color = "#4ade80";
        } else {
            localStorage.removeItem("gemini_api_key");
            apiKeyStatus.textContent = "Key cleared";
            apiKeyStatus.style.color = "var(--text-muted)";
        }
    });

    // Load saved Spoonacular key from Backend
    async function loadSpoonKey() {
        try {
            const res = await fetch("/api/settings");
            const data = await res.json();
            if (data.spoonacular_key) {
                spoonKeyInput.value = data.spoonacular_key;
                spoonKeyStatus.textContent = "✓ Key active";
                spoonKeyStatus.style.color = "#4ade80";
            }
        } catch (err) {
            console.error("Failed to load Spoonacular key", err);
        }
    }
    loadSpoonKey();

    saveSpoonKeyBtn.addEventListener("click", async () => {
        const key = spoonKeyInput.value.trim();
        try {
            const response = await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ spoonacular_key: key })
            });
            if (response.ok) {
                if (key) {
                    spoonKeyStatus.textContent = "✓ Key saved";
                    spoonKeyStatus.style.color = "#4ade80";
                } else {
                    spoonKeyStatus.textContent = "Key cleared";
                    spoonKeyStatus.style.color = "var(--text-muted)";
                }
            } else {
                spoonKeyStatus.textContent = "Error saving";
                spoonKeyStatus.style.color = "var(--danger)";
            }
        } catch (err) {
            console.error("Failed to save Spoonacular key", err);
            spoonKeyStatus.textContent = "Error saving";
            spoonKeyStatus.style.color = "var(--danger)";
        }
    });


    // Tab Switching Logic
    const tabButtons = document.querySelectorAll(".tab-btn");
    const tabContents = document.querySelectorAll(".tab-content");
    
    tabButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            tabButtons.forEach(b => b.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));
            
            btn.classList.add("active");
            const tabId = btn.getAttribute("data-tab");
            document.getElementById(tabId).classList.add("active");
        });
    });

    // Fetch User Profile
    async function fetchProfile() {
        try {
            const response = await fetch("/api/profile");
            const data = await response.json();
            state.pantry = data.pantry || [];
            state.restrictions = data.restrictions || [];
            state.shopping_list = data.shopping_list || [];
            state.favorites = data.favorites || [];
            
            renderPantry();
            renderRestrictions();
            renderShoppingList();
            renderFavorites();
        } catch (err) {
            console.error("Error fetching profile:", err);
        }
    }

    // Render Pantry
    function renderPantry() {
        pantryList.innerHTML = "";
        if (state.pantry.length === 0) {
            pantryList.innerHTML = `<span class="text-muted" style="font-size:0.85rem;">Your pantry is empty. Click + Add to start stocking ingredients!</span>`;
            return;
        }
        
        state.pantry.forEach(item => {
            const div = document.createElement("div");
            div.className = "pantry-item";
            div.innerHTML = `
                <span>${item}</span>
                <span class="remove-btn" data-item="${item}">×</span>
            `;
            pantryList.appendChild(div);
        });

        // Add event listeners to remove buttons
        document.querySelectorAll(".pantry-item .remove-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                const itemToRemove = e.target.getAttribute("data-item");
                const newPantry = state.pantry.filter(i => i !== itemToRemove);
                await updatePantryBackend(newPantry);
            });
        });
    }

    // Render Restrictions Checkboxes
    function renderRestrictions() {
        dietCheckboxes.forEach(cb => {
            cb.checked = state.restrictions.includes(cb.value);
        });
    }

    // Render Shopping List
    function renderShoppingList() {
        shoppingList.innerHTML = "";
        if (state.shopping_list.length === 0) {
            shoppingList.innerHTML = `<li class="text-muted" style="font-size:0.85rem; padding: 0.5rem 0;">No missing items! All set to cook.</li>`;
            return;
        }

        state.shopping_list.forEach(item => {
            const li = document.createElement("li");
            li.className = "shopping-item";
            li.innerHTML = `
                <label class="shopping-item-check">
                    <input type="checkbox" data-item="${item}" class="shopping-check-btn">
                    <span>${item}</span>
                </label>
            `;
            shoppingList.appendChild(li);
        });

        // Add event listeners to mark items as purchased (add to pantry)
        document.querySelectorAll(".shopping-check-btn").forEach(cb => {
            cb.addEventListener("change", async (e) => {
                if (e.target.checked) {
                    const itemBought = e.target.getAttribute("data-item");
                    // Move from shopping list to pantry
                    const newShopping = state.shopping_list.filter(i => i !== itemBought);
                    const newPantry = [...state.pantry, itemBought];
                    
                    // Sync both
                    await updatePantryBackend(newPantry);
                    await updateShoppingBackend(newShopping);
                }
            });
        });
    }

    // Render Favorites list
    async function renderFavorites() {
        favoritesList.innerHTML = "";
        if (state.favorites.length === 0) {
            favoritesList.innerHTML = `<span style="font-size:0.85rem; color: var(--text-muted);">You haven't starred any recipes yet. Ask the assistant to star some!</span>`;
            return;
        }

        favoritesList.innerHTML = `<span style="font-size:0.85rem; color: var(--text-muted);">Loading...</span>`;

        try {
            // Resolve each favorited ID to a full recipe object via the backend
            const recipePromises = state.favorites.map(id =>
                fetch(`/api/recipes/${id}`).then(r => r.ok ? r.json() : null)
            );
            const recipes = (await Promise.all(recipePromises)).filter(Boolean);

            favoritesList.innerHTML = "";

            if (recipes.length === 0) {
                favoritesList.innerHTML = `<span style="font-size:0.85rem; color: var(--text-muted);">No starred recipes found.</span>`;
                return;
            }

            recipes.forEach(recipe => {
                const div = document.createElement("div");
                div.className = "recipe-card";
                
                const isInternet = recipe.source === 'internet';
                const badgeHtml = isInternet 
                    ? `<span class="recipe-badge" style="background: rgba(99, 102, 241, 0.15); color: #a5b4fc; border: 1px solid rgba(99, 102, 241, 0.3); font-size: 0.7rem; padding: 0.1rem 0.3rem; border-radius: 4px; margin-left: 0.5rem; display: inline-flex; align-items: center; gap: 2px;">🌐 Internet</span>` 
                    : ``;
                const linkHtml = isInternet && recipe.source_url
                    ? `<div style="margin-top: 0.5rem;"><a href="${recipe.source_url}" target="_blank" style="color: #818cf8; text-decoration: none; font-size: 0.8rem; font-weight: 500; display: inline-flex; align-items: center; gap: 4px;">View Full Recipe ↗</a></div>`
                    : ``;
                
                div.innerHTML = `
                    <div class="recipe-header">
                        <span class="recipe-title">${recipe.name} ${badgeHtml}</span>
                        <button class="fav-btn remove-fav" data-id="${recipe.id}" title="Remove from favorites">⭐</button>
                    </div>
                    <div class="recipe-details">${recipe.instructions}</div>
                    ${linkHtml}
                `;
                favoritesList.appendChild(div);
            });

            // Un-star button handlers
            document.querySelectorAll(".remove-fav").forEach(btn => {
                btn.addEventListener("click", async (e) => {
                    const id = e.target.closest("[data-id]").getAttribute("data-id");
                    try {
                        const res = await fetch("/api/favorites/toggle", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ recipe_id: id, is_starred: false })
                        });
                        if ((await res.json()).status === "success") fetchProfile();
                    } catch (err) {
                        console.error("Failed to toggle favorite:", err);
                    }
                });
            });
        } catch (e) {
            favoritesList.innerHTML = `<span style="color: var(--danger); font-size:0.85rem;">Failed to load favorites.</span>`;
            console.error("renderFavorites error:", e);
        }
    }

    // Update Pantry on Backend
    async function updatePantryBackend(newPantry) {
        try {
            const response = await fetch("/api/pantry", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ ingredients: newPantry })
            });
            const data = await response.json();
            state.pantry = data.pantry;
            renderPantry();
        } catch (err) {
            console.error("Failed to update pantry:", err);
        }
    }

    // Update Diet Restrictions on Backend
    async function updateRestrictionsBackend(newRestrictions) {
        try {
            const response = await fetch("/api/restrictions", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ restrictions: newRestrictions })
            });
            const data = await response.json();
            state.restrictions = data.restrictions;
            renderRestrictions();
        } catch (err) {
            console.error("Failed to update restrictions:", err);
        }
    }

    // Update Shopping List (replace the full list on the backend)
    async function updateShoppingBackend(newShopping) {
        try {
            const response = await fetch("/api/shopping_list/set", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ items: newShopping })
            });
            const data = await response.json();
            state.shopping_list = data.shopping_list || [];
            renderShoppingList();
        } catch (err) {
            console.error("Failed to update shopping list:", err);
            setTimeout(fetchProfile, 300); // fallback: re-fetch profile
        }
    }

    // Add Pantry Item Event
    addPantryItemBtn.addEventListener("click", () => {
        const item = prompt("Enter ingredient name (e.g. 'mushrooms', 'garlic'):");
        if (item && item.trim()) {
            const newPantry = [...state.pantry, item.trim()];
            updatePantryBackend(newPantry);
        }
    });

    // Clear Shopping List Event
    clearShoppingListBtn.addEventListener("click", async () => {
        try {
            await fetch("/api/shopping_list/clear", { method: "POST" });
            state.shopping_list = [];
            renderShoppingList();
        } catch (err) {
            console.error(err);
        }
    });

    // Diet Checklist Events
    dietCheckboxes.forEach(cb => {
        cb.addEventListener("change", () => {
            const newRestrictions = [];
            dietCheckboxes.forEach(item => {
                if (item.checked) newRestrictions.push(item.value);
            });
            updateRestrictionsBackend(newRestrictions);
        });
    });

    // Format Markdown Helper
    function formatMessage(text) {
        // Very basic markdown formatting for presentation
        let formatted = text
            .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
            .replace(/\*(.*?)\*/g, "<em>$1</em>")
            .replace(/`([^`]+)`/g, "<code>$1</code>")
            .replace(/\n/g, "<br>");
            
        // Lists formatting
        formatted = formatted.replace(/- (.*?)<br>/g, "<li>$1</li>");
        formatted = formatted.replace(/(<li>.*?<\/li>)/g, "<ul>$1</ul>");
        // Clean up redundant ul nesting
        formatted = formatted.replace(/<\/ul><ul>/g, "");
        
        return formatted;
    }

    // Append Message to UI
    function appendMessage(sender, text) {
        const div = document.createElement("div");
        div.className = `message ${sender}`;
        div.innerHTML = `
            <div class="message-content">
                ${sender === 'assistant' ? formatMessage(text) : `<p>${escapeHTML(text)}</p>`}
            </div>
        `;
        chatMessages.appendChild(div);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function addSystemMessage(text) {
        const div = document.createElement("div");
        div.className = "message assistant";
        div.innerHTML = `
            <div class="message-content" style="border-color: rgba(99,102,241,0.3); background: rgba(99,102,241,0.02)">
                <p style="color: #a5b4fc; font-weight: 500;">⚙️ System Update</p>
                <p>${text}</p>
            </div>
        `;
        chatMessages.appendChild(div);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function escapeHTML(str) {
        return str.replace(/[&<>'"]/g, 
            tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
        );
    }

    // Submit Chat
    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const msg = userInput.value.trim();
        if (!msg) return;


        // Add user message to screen
        appendMessage("user", msg);
        userInput.value = "";

        // Show thinking indicator
        thoughtIndicator.classList.remove("hidden");
        thoughtText.textContent = "";

        // Create Assistant message placeholder
        const messageDiv = document.createElement("div");
        messageDiv.className = "message assistant";
        const contentDiv = document.createElement("div");
        contentDiv.className = "message-content";
        messageDiv.appendChild(contentDiv);
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        let assistantResponse = "";

        try {
            // Trigger streaming API – send API key if user provided one
            const storedApiKey = localStorage.getItem("gemini_api_key") || "";
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: msg, api_key: storedApiKey || undefined })
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || "Server error");
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n\n");
                // Save the last incomplete line back into the buffer
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        const jsonStr = line.slice(6).trim();
                        if (!jsonStr) continue;

                        try {
                            const data = JSON.parse(jsonStr);
                            
                            if (data.type === "thought") {
                                thoughtText.textContent += data.content;
                                thoughtIndicator.classList.remove("hidden");
                            } else if (data.type === "text") {
                                assistantResponse += data.content;
                                contentDiv.innerHTML = formatMessage(assistantResponse);
                                chatMessages.scrollTop = chatMessages.scrollHeight;
                            } else if (data.type === "error") {
                                throw new Error(data.content);
                            } else if (data.type === "done") {
                                thoughtIndicator.classList.add("hidden");
                                // Trigger profile refresh after agent completes to keep pantry/list in sync
                                fetchProfile();
                            }
                        } catch (parseErr) {
                            console.error("Error parsing SSE line:", parseErr, line);
                        }
                    }
                }
            }
        } catch (err) {
            thoughtIndicator.classList.add("hidden");
            contentDiv.innerHTML = `<p style="color: var(--danger);"><strong>Error:</strong> ${escapeHTML(err.message)}</p>`;
            chatMessages.scrollTop = chatMessages.scrollHeight;
            

        }
    });

    // Initial Load
    fetchProfile();
});
