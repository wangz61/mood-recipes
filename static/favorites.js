(function () {
  const { api, goLogin, renderNav, el } = window.MR;
  const $ = (id) => document.getElementById(id);

  /** @type {Array<any>} */
  let favorites = [];
  /** Mood slug to show, or null for all. */
  let filter = null;

  const moodName = (m) => (m.emoji ? `${m.emoji} ${m.label}` : m.label);
  const dateFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });
  // The API sends naive UTC timestamps.
  const savedOn = (iso) => dateFmt.format(new Date(iso.endsWith("Z") ? iso : `${iso}Z`));

  function showError(msg) {
    $("error").textContent = msg;
    $("error").classList.toggle("hidden", !msg);
  }

  function moodTag(m) {
    return el("span", "rounded-full bg-orange-100 px-2.5 py-0.5 text-xs font-medium text-orange-900", moodName(m));
  }

  function renderFilters() {
    const box = $("filters");
    box.replaceChildren();
    if (!favorites.length) return;
    const counts = new Map();
    for (const f of favorites) for (const m of f.moods) counts.set(m.slug, { mood: m, n: (counts.get(m.slug)?.n ?? 0) + 1 });
    if (filter && !counts.has(filter)) filter = null;

    const pill = (label, value, n) => {
      const active = filter === value;
      const b = el(
        "button",
        "rounded-full border px-3.5 py-1.5 text-sm font-medium shadow-sm transition focus:outline-none focus:ring-2 focus:ring-orange-400 " +
          (active ? "border-orange-300 bg-orange-100 text-orange-900" : "border-slate-200 bg-white text-slate-700 hover:border-orange-300 hover:bg-orange-50"),
      );
      b.type = "button";
      b.setAttribute("aria-pressed", String(active));
      b.append(label, el("span", "ml-1.5 text-xs text-slate-500", String(n)));
      b.addEventListener("click", () => {
        filter = value;
        render();
      });
      return b;
    };
    box.appendChild(pill("All", null, favorites.length));
    for (const { mood, n } of counts.values()) box.appendChild(pill(moodName(mood), mood.slug, n));
  }

  function card(f) {
    const li = el("li", "group flex flex-col overflow-hidden rounded-2xl border border-white/60 bg-white/85 shadow-lg shadow-orange-900/5");
    const open = el("button", "block text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-400");
    open.type = "button";
    open.setAttribute("aria-label", `View ${f.name}`);
    const img = el("img", "aspect-video w-full bg-slate-100 object-cover transition group-hover:brightness-95");
    img.src = f.image ? `${f.image}/medium` : "";
    img.alt = "";
    img.loading = "lazy";
    img.addEventListener("error", () => (img.src = f.image), { once: true });
    open.appendChild(img);
    open.addEventListener("click", () => showDetail(f));
    li.appendChild(open);

    const body = el("div", "flex flex-1 flex-col gap-2 p-4");
    body.appendChild(el("h2", "font-display text-lg font-semibold leading-snug text-slate-900", f.name));
    body.appendChild(el("p", "text-xs text-slate-500", [f.category, f.area].filter(Boolean).join(" · ")));
    const tags = el("div", "flex flex-wrap gap-1.5");
    if (f.moods.length) f.moods.forEach((m) => tags.appendChild(moodTag(m)));
    else tags.appendChild(el("span", "text-xs text-slate-400", "No mood"));
    body.appendChild(tags);

    const foot = el("div", "mt-auto flex items-center justify-between pt-2");
    foot.appendChild(el("span", "text-xs text-slate-400", `Saved ${savedOn(f.created_at)}`));
    const remove = el(
      "button",
      "rounded-lg px-2.5 py-1 text-xs font-medium text-slate-500 transition hover:bg-red-50 hover:text-red-700 focus:outline-none focus:ring-2 focus:ring-red-300",
      "Remove",
    );
    remove.type = "button";
    remove.setAttribute("aria-label", `Remove ${f.name} from favorites`);
    remove.addEventListener("click", () => removeFavorite(f, remove));
    foot.appendChild(remove);
    body.appendChild(foot);
    li.appendChild(body);
    return li;
  }

  function render() {
    renderFilters();
    const shown = filter ? favorites.filter((f) => f.moods.some((m) => m.slug === filter)) : favorites;
    $("grid").replaceChildren(...shown.map(card));
    $("empty").classList.toggle("hidden", favorites.length > 0);
    const n = favorites.length;
    $("summary").textContent = n ? `${n} saved ${n === 1 ? "recipe" : "recipes"}${filter ? ` · showing ${shown.length}` : ""}` : "Nothing saved yet.";
  }

  async function removeFavorite(f, button) {
    button.disabled = true;
    try {
      await api(`/api/favorites/${f.id}`, { method: "DELETE" });
      favorites = favorites.filter((x) => x.id !== f.id);
      render();
    } catch (e) {
      button.disabled = false;
      showError(e.message);
    }
  }

  // --- Detail dialog -------------------------------------------------------------

  const dialog = $("detail");
  $("detail-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (e) => {
    if (e.target === dialog) dialog.close();
  });

  async function showDetail(f) {
    $("detail-image").src = f.image || "";
    $("detail-image").alt = `Photo of ${f.name}`;
    $("detail-title").textContent = f.name;
    $("detail-meta").textContent = [f.category, f.area].filter(Boolean).join(" · ");
    $("detail-moods").replaceChildren(...f.moods.map(moodTag));
    const bodyEl = $("detail-body");
    bodyEl.replaceChildren(el("p", "text-slate-500", "Loading the recipe…"));
    dialog.showModal();
    try {
      const meal = await api(`/api/recipes/${encodeURIComponent(f.meal_id)}`);
      const parts = [];
      if (meal.ingredients?.length) {
        parts.push(el("h3", "mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500", "Ingredients"));
        const ul = el("ul", "mb-4 list-inside list-disc space-y-1");
        meal.ingredients.forEach((r) => ul.appendChild(el("li", "", `${r.measure ? `${r.measure} ` : ""}${r.ingredient}`)));
        parts.push(ul);
      }
      parts.push(el("h3", "mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500", "Instructions"));
      parts.push(el("p", "whitespace-pre-wrap leading-relaxed", (meal.instructions || "").trim() || "No instructions listed."));
      if (meal.youtube) {
        const a = el(
          "a",
          "mt-4 inline-block rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50",
          "Watch video",
        );
        a.href = meal.youtube;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        parts.push(a);
      }
      bodyEl.replaceChildren(...parts);
    } catch (e) {
      bodyEl.replaceChildren(el("p", "text-red-700", e.message));
    }
  }

  (async function start() {
    const user = await renderNav("favorites");
    if (!user) {
      goLogin();
      return;
    }
    try {
      favorites = await api("/api/favorites");
      render();
    } catch (e) {
      if (e.status === 401) goLogin();
      else showError(e.message);
    }
  })();
})();
