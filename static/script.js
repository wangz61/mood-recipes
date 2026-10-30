(function () {
  const { api, goLogin, renderNav, el } = window.MR;

  const EXCLUDED_KEY = "moodRecipesExcluded";
  // A recipe the visitor tried to save before logging in; saved for them when they come back.
  const PENDING_KEY = "moodRecipesPendingSave";

  /** @type {Array<{id:number, slug:string, label:string, emoji:string, builtin:boolean, categories:string[], areas:string[]}>} */
  let moods = [];
  /** @type {string | null} */
  let selectedMood = null;
  /** @type {any} */
  let currentRecipe = null;
  /** meal id -> favorite */
  const favorites = new Map();
  let user = null;

  const $ = (id) => document.getElementById(id);
  const moodButtons = $("mood-buttons");
  const recipeSection = $("recipe-section");
  const recipeLoading = $("recipe-loading");
  const recipeContent = $("recipe-content");
  const recipeImage = $("recipe-image");
  const recipeTitle = $("recipe-title");
  const recipeMeta = $("recipe-meta");
  const recipeIngredients = $("recipe-ingredients");
  const recipeInstructions = $("recipe-instructions");
  const recipeYoutube = $("recipe-youtube");
  const btnAnother = $("btn-another");
  const btnFavorite = $("btn-favorite");
  const favoriteLabel = $("btn-favorite-label");
  const favoriteNote = $("favorite-note");
  const heart = $("heart");
  const errorEl = $("error");

  function readJSON(storage, key, fallback) {
    try {
      const v = JSON.parse(storage.getItem(key) ?? "null");
      return v ?? fallback;
    } catch {
      return fallback;
    }
  }

  function writeJSON(storage, key, value) {
    try {
      if (value === null) storage.removeItem(key);
      else storage.setItem(key, JSON.stringify(value));
    } catch {
      // Storage blocked: features that depend on it just don't persist.
    }
  }

  function getExcludedForMood(mood) {
    const list = readJSON(sessionStorage, EXCLUDED_KEY, {})[mood];
    return Array.isArray(list) ? list : [];
  }

  function addExcluded(mood, id) {
    const map = readJSON(sessionStorage, EXCLUDED_KEY, {});
    const cur = Array.isArray(map[mood]) ? map[mood] : [];
    if (!cur.includes(id)) cur.push(id);
    map[mood] = cur;
    writeJSON(sessionStorage, EXCLUDED_KEY, map);
  }

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.classList.remove("hidden");
  }

  function clearError() {
    errorEl.textContent = "";
    errorEl.classList.add("hidden");
  }

  function setLoading(loading) {
    recipeSection.classList.remove("hidden");
    recipeLoading.classList.toggle("hidden", !loading);
    recipeContent.classList.toggle("hidden", loading);
  }

  const moodBySlug = (slug) => moods.find((m) => m.slug === slug);
  const moodName = (m) => (m.emoji ? `${m.emoji} ${m.label}` : m.label);

  // --- Moods ---------------------------------------------------------------

  function renderMoods() {
    moodButtons.innerHTML = "";
    for (const m of moods) {
      const active = m.slug === selectedMood;
      const group = el("span", "inline-flex items-stretch");
      const btn = el(
        "button",
        "border px-4 py-2 text-sm font-medium shadow-sm transition focus:outline-none focus:ring-2 focus:ring-orange-400 " +
          (m.builtin ? "rounded-full " : "rounded-l-full border-r-0 pr-3 ") +
          (active
            ? "border-orange-300 bg-orange-100 text-orange-900 ring-2 ring-orange-500"
            : "border-slate-200 bg-white text-slate-700 hover:border-orange-300 hover:bg-orange-50"),
        moodName(m),
      );
      btn.type = "button";
      btn.setAttribute("aria-pressed", String(active));
      btn.addEventListener("click", () => selectMood(m.slug));
      group.appendChild(btn);

      if (!m.builtin) {
        const del = el(
          "button",
          "rounded-r-full border border-l border-slate-200 bg-white px-2.5 text-slate-400 shadow-sm transition hover:bg-red-50 hover:text-red-600 focus:outline-none focus:ring-2 focus:ring-red-400 " +
            (active ? "border-orange-300 bg-orange-100" : ""),
          "×",
        );
        del.type = "button";
        del.title = `Delete "${m.label}"`;
        del.setAttribute("aria-label", `Delete mood ${m.label}`);
        del.addEventListener("click", () => deleteMood(m));
        group.appendChild(del);
      }
      moodButtons.appendChild(group);
    }

    const add = el(
      "button",
      "rounded-full border border-dashed border-slate-300 px-4 py-2 text-sm font-medium text-slate-500 transition hover:border-orange-400 hover:bg-white hover:text-orange-700 focus:outline-none focus:ring-2 focus:ring-orange-400",
      "+ New mood",
    );
    add.type = "button";
    add.addEventListener("click", () => (user ? openMoodDialog() : goLogin()));
    moodButtons.appendChild(add);
  }

  async function loadMoods() {
    moods = await api("/api/moods");
    renderMoods();
  }

  async function deleteMood(m) {
    if (!window.confirm(`Delete the "${m.label}" mood? Saved recipes keep their other moods.`)) return;
    try {
      await api(`/api/moods/${m.id}`, { method: "DELETE" });
      if (selectedMood === m.slug) {
        selectedMood = null;
        recipeSection.classList.add("hidden");
      }
      await loadMoods();
      await loadFavorites();
    } catch (e) {
      showError(e.message);
    }
  }

  function selectMood(slug) {
    selectedMood = slug;
    renderMoods();
    loadRecipe(getExcludedForMood(slug));
  }

  // --- Recipe ---------------------------------------------------------------

  function renderRecipe(data) {
    currentRecipe = data;
    recipeImage.src = data.image || "";
    recipeImage.alt = data.name ? `Photo of ${data.name}` : "Recipe";
    recipeTitle.textContent = data.name || "Recipe";
    recipeMeta.textContent = [data.category, data.area].filter(Boolean).join(" · ");

    recipeIngredients.innerHTML = "";
    if (Array.isArray(data.ingredients) && data.ingredients.length) {
      recipeIngredients.appendChild(el("h4", "mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500", "Ingredients"));
      const ul = el("ul", "list-inside list-disc space-y-1 text-sm text-slate-700");
      for (const row of data.ingredients) ul.appendChild(el("li", "", `${row.measure ? `${row.measure} ` : ""}${row.ingredient}`.trim()));
      recipeIngredients.appendChild(ul);
    }

    recipeInstructions.textContent = (data.instructions || "").trim() || "No instructions listed.";

    if (data.youtube && String(data.youtube).trim()) {
      recipeYoutube.href = data.youtube;
      recipeYoutube.classList.remove("hidden");
    } else {
      recipeYoutube.classList.add("hidden");
    }
    renderFavoriteButton();
  }

  async function loadRecipe(excludeList) {
    if (!selectedMood) return;
    clearError();
    setLoading(true);
    try {
      const params = new URLSearchParams({ mood: selectedMood });
      if (excludeList.length) params.set("exclude", excludeList.join(","));
      renderRecipe(await api(`/api/recipe?${params}`));
      setLoading(false);
    } catch (e) {
      setLoading(false);
      recipeContent.classList.add("hidden");
      showError(e.message || "Could not load a recipe.");
    }
  }

  // --- Favorites ---------------------------------------------------------------

  async function loadFavorites() {
    favorites.clear();
    if (!user) return;
    for (const f of await api("/api/favorites")) favorites.set(f.meal_id, f);
    renderFavoriteButton();
  }

  function renderFavoriteButton() {
    if (!currentRecipe) return;
    const fav = favorites.get(String(currentRecipe.id));
    const mood = moodBySlug(selectedMood);
    const tagged = !!(fav && mood && fav.moods.some((t) => t.slug === mood.slug));
    btnFavorite.setAttribute("aria-pressed", String(tagged));
    for (const c of ["border-rose-300", "bg-rose-50", "text-rose-700"]) btnFavorite.classList.toggle(c, tagged);
    for (const c of ["border-slate-200", "bg-white", "text-slate-700"]) btnFavorite.classList.toggle(c, !tagged);
    heart.setAttribute("fill", fav ? "currentColor" : "none");
    favoriteLabel.textContent = tagged ? "Saved" : fav ? `Also save as ${mood ? mood.label : "this mood"}` : "Save";
    btnFavorite.title = tagged ? "Remove from favorites" : "Save to favorites";
    if (fav) {
      favoriteNote.textContent = `In your favorites under ${fav.moods.map(moodName).join(", ") || "no mood"}.`;
      favoriteNote.classList.remove("hidden");
    } else {
      favoriteNote.classList.add("hidden");
    }
  }

  async function toggleFavorite() {
    if (!currentRecipe || !selectedMood) return;
    const mealId = String(currentRecipe.id);
    if (!user) {
      writeJSON(sessionStorage, PENDING_KEY, { meal_id: mealId, mood: selectedMood, recipe: currentRecipe });
      goLogin();
      return;
    }
    const fav = favorites.get(mealId);
    const tagged = fav && fav.moods.some((t) => t.slug === selectedMood);
    btnFavorite.disabled = true;
    try {
      if (tagged) {
        await api(`/api/favorites/${fav.id}`, { method: "DELETE" });
        favorites.delete(mealId);
      } else {
        const saved = await api("/api/favorites", { method: "POST", body: { meal_id: mealId, mood: selectedMood } });
        favorites.set(mealId, saved);
      }
      renderFavoriteButton();
    } catch (e) {
      if (e.status === 401) {
        goLogin();
        return;
      }
      showError(e.message);
    } finally {
      btnFavorite.disabled = false;
    }
  }

  async function finishPendingSave() {
    const pending = readJSON(sessionStorage, PENDING_KEY, null);
    if (!pending) return;
    writeJSON(sessionStorage, PENDING_KEY, null);
    if (!user || !moodBySlug(pending.mood)) return;
    selectedMood = pending.mood;
    renderMoods();
    setLoading(false);
    try {
      const saved = await api("/api/favorites", { method: "POST", body: { meal_id: pending.meal_id, mood: pending.mood } });
      favorites.set(saved.meal_id, saved);
    } catch (e) {
      showError(e.message);
    }
    renderRecipe(pending.recipe);
  }

  // --- New mood dialog ------------------------------------------------------------

  const dialog = $("mood-dialog");
  const form = $("mood-form");
  const moodError = $("mood-error");
  const moodCount = $("mood-count");
  const saveBtn = $("mood-save");
  let filtersLoaded = false;

  function chip(name, value) {
    const label = el("label", "cursor-pointer");
    label.dataset.value = value.toLowerCase();
    const input = el("input", "chip-check sr-only");
    input.type = "checkbox";
    input.name = name;
    input.value = value;
    input.addEventListener("change", updateCount);
    label.appendChild(input);
    label.appendChild(el("span", "inline-block rounded-full border border-slate-200 bg-white px-3 py-1 text-sm text-slate-700 transition hover:border-orange-300", value));
    return label;
  }

  function checked(name) {
    return [...form.querySelectorAll(`input[name="${name}"]:checked`)].map((i) => i.value);
  }

  function updateCount() {
    const c = checked("categories").length;
    const a = checked("areas").length;
    moodCount.textContent = c || a ? `${c} ${c === 1 ? "category" : "categories"} · ${a} ${a === 1 ? "cuisine" : "cuisines"}` : "Nothing selected";
  }

  async function openMoodDialog() {
    form.reset();
    moodError.classList.add("hidden");
    updateCount();
    dialog.showModal();
    $("mood-label").focus();
    if (filtersLoaded) return;
    try {
      const { categories, areas } = await api("/api/meal-filters");
      $("mood-categories").replaceChildren(...categories.map((c) => chip("categories", c)));
      $("mood-areas").replaceChildren(...areas.map((a) => chip("areas", a)));
      filtersLoaded = true;
    } catch (e) {
      moodError.textContent = e.message;
      moodError.classList.remove("hidden");
    }
  }

  $("area-filter").addEventListener("input", (e) => {
    const q = e.target.value.trim().toLowerCase();
    for (const label of $("mood-areas").children) label.classList.toggle("hidden", !!q && !label.dataset.value.includes(q));
  });

  $("mood-cancel").addEventListener("click", () => dialog.close());

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    moodError.classList.add("hidden");
    saveBtn.disabled = true;
    try {
      const mood = await api("/api/moods", {
        method: "POST",
        body: {
          label: $("mood-label").value,
          emoji: $("mood-emoji").value,
          categories: checked("categories"),
          areas: checked("areas"),
        },
      });
      dialog.close();
      await loadMoods();
      selectMood(mood.slug);
    } catch (err) {
      moodError.textContent = err.message;
      moodError.classList.remove("hidden");
    } finally {
      saveBtn.disabled = false;
    }
  });

  // --- Start -------------------------------------------------------------------

  btnAnother.addEventListener("click", () => {
    if (!selectedMood) return;
    if (currentRecipe?.id) addExcluded(selectedMood, String(currentRecipe.id));
    loadRecipe(getExcludedForMood(selectedMood));
  });
  btnFavorite.addEventListener("click", toggleFavorite);

  (async function start() {
    user = await renderNav("home");
    try {
      await loadMoods();
      await loadFavorites();
      await finishPendingSave();
    } catch (e) {
      showError(e.message || "Could not load moods.");
    }
    const hint = $("mood-hint");
    hint.textContent = user ? "Tip: create your own mood with + New mood." : "Log in to save recipes and create your own moods.";
    hint.classList.remove("hidden");
  })();
})();
