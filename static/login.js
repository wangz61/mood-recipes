(function () {
  const { api, me } = window.MR;

  const VIEWS = {
    login: { title: "Login", submit: "Log in", busy: "Logging in…" },
    register: { title: "Register", submit: "Create account", busy: "Creating account…" },
    forgot: { title: "Forget Password", submit: "Send reset link", busy: "Sending…" },
  };

  const $ = (id) => document.getElementById(id);
  const form = $("auth-form");
  const email = $("email");
  const password = $("password");
  const remember = $("remember");
  const submit = $("submit");
  const message = $("message");

  /** Only same-site paths, so ?next= can't send people to another website. */
  function nextUrl() {
    const next = new URLSearchParams(location.search).get("next") || "/";
    return next.startsWith("/") && !next.startsWith("//") ? next : "/";
  }

  function currentView() {
    const v = location.hash.slice(1);
    return v in VIEWS ? v : "login";
  }

  function say(text, tone) {
    message.textContent = text;
    message.className =
      "mb-5 rounded-xl px-4 py-3 text-[14px] font-medium " +
      (tone === "error" ? "bg-[#4c0519]/45 text-white" : "bg-white/20 text-white");
    message.classList.toggle("hidden", !text);
  }

  function show(view) {
    const cfg = VIEWS[view];
    $("title").textContent = cfg.title;
    submit.textContent = cfg.submit;
    document.title = `${cfg.title} · Mood Recipes`;
    for (const node of document.querySelectorAll("[data-views]")) {
      node.classList.toggle("hidden", !node.dataset.views.split(" ").includes(view));
    }
    password.required = view !== "forgot";
    password.autocomplete = view === "register" ? "new-password" : "current-password";
    say("");
    email.focus();
  }

  $("reveal").addEventListener("click", (e) => {
    const showing = password.type === "text";
    password.type = showing ? "password" : "text";
    e.currentTarget.textContent = showing ? "Show" : "Hide";
    e.currentTarget.setAttribute("aria-pressed", String(!showing));
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const view = currentView();
    if (!email.value.trim()) return say("Enter your email address.", "error");
    if (view !== "forgot" && !password.value) return say("Enter your password.", "error");
    if (view === "register" && password.value.length < 8) return say("Password must be at least 8 characters.", "error");

    submit.disabled = true;
    submit.textContent = VIEWS[view].busy;
    try {
      if (view === "forgot") {
        const res = await api("/api/auth/forgot-password", { method: "POST", body: { email: email.value.trim() } });
        say(res.message, "ok");
      } else {
        await api(`/api/auth/${view === "register" ? "register" : "login"}`, {
          method: "POST",
          body: { email: email.value.trim(), password: password.value, remember: remember.checked },
        });
        location.href = nextUrl();
        return;
      }
    } catch (err) {
      say(err.message, "error");
    }
    submit.disabled = false;
    submit.textContent = VIEWS[view].submit;
  });

  window.addEventListener("hashchange", () => show(currentView()));

  (async function start() {
    // Already logged in: nothing to do here.
    if (await me()) {
      location.replace(nextUrl());
      return;
    }
    show(currentView());
    const notice = new URLSearchParams(location.search).get("notice");
    if (notice === "reset") say("Password updated. Log in with your new password.", "ok");
  })();
})();
