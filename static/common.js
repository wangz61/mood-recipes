/* Shared helpers for every page: API calls, the current user and the top navigation. */
(function () {
  /** Calls the JSON API. Throws an Error with the server's `detail` message and a `status`. */
  async function api(path, { method = "GET", body } = {}) {
    const res = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.status === 204) return null;
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      let detail = data.detail ?? res.statusText;
      if (typeof detail !== "string") detail = "Something went wrong. Please try again.";
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  let mePromise = null;
  /** The logged-in user, or null. Fetched once per page. */
  function me() {
    mePromise ??= api("/api/auth/me").catch(() => null);
    return mePromise;
  }

  function loginUrl(view) {
    const next = encodeURIComponent(location.pathname + location.search);
    return `/login.html?next=${next}${view ? `#${view}` : ""}`;
  }

  function goLogin(view) {
    location.href = loginUrl(view);
  }

  const linkClass =
    "rounded-full px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:bg-white/70 hover:text-slate-900 focus:outline-none focus:ring-2 focus:ring-orange-400";

  /** Fills the page's <nav id="nav"> for the current user. */
  async function renderNav(current) {
    const nav = document.getElementById("nav");
    if (!nav) return null;
    const user = await me();
    nav.innerHTML = "";
    const add = (el) => nav.appendChild(el);
    const link = (href, text, active) => {
      const a = document.createElement("a");
      a.href = href;
      a.textContent = text;
      a.className = linkClass + (active ? " bg-white/80 text-slate-900 shadow-sm" : "");
      if (active) a.setAttribute("aria-current", "page");
      return a;
    };

    add(link("/", "Recipes", current === "home"));
    if (user) {
      add(link("/favorites.html", "Favorites", current === "favorites"));
      const spacer = document.createElement("span");
      spacer.className = "flex-1";
      add(spacer);
      const who = document.createElement("span");
      who.className = "hidden truncate text-sm text-slate-500 sm:inline max-w-[14rem]";
      who.textContent = user.email;
      who.title = user.email;
      add(who);
      const out = document.createElement("button");
      out.type = "button";
      out.textContent = "Log out";
      out.className = linkClass;
      out.addEventListener("click", async () => {
        await api("/api/auth/logout", { method: "POST" }).catch(() => {});
        location.href = "/";
      });
      add(out);
    } else {
      const spacer = document.createElement("span");
      spacer.className = "flex-1";
      add(spacer);
      add(link(loginUrl(), "Log in"));
      const reg = link(loginUrl("register"), "Register");
      reg.className =
        "rounded-full bg-slate-900 px-4 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-orange-400";
      add(reg);
    }
    return user;
  }

  /** Text helper so user content never goes through innerHTML. */
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  window.MR = { api, me, goLogin, loginUrl, renderNav, el };
})();
