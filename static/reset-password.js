(function () {
  const { api } = window.MR;
  const $ = (id) => document.getElementById(id);
  const form = $("reset-form");
  const submit = $("submit");
  const message = $("message");
  const token = new URLSearchParams(location.search).get("token");

  function say(text, tone) {
    message.textContent = text;
    message.className =
      "mb-5 rounded-xl px-4 py-3 text-[14px] font-medium " + (tone === "error" ? "bg-[#4c0519]/45 text-white" : "bg-white/20 text-white");
    message.classList.toggle("hidden", !text);
  }

  if (!token) {
    say("This page needs the link from your reset email. Ask for a new one below.", "error");
    submit.disabled = true;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const password = $("password").value;
    if (password.length < 8) return say("Password must be at least 8 characters.", "error");
    if (password !== $("confirm").value) return say("The two passwords don't match.", "error");
    submit.disabled = true;
    submit.textContent = "Saving…";
    try {
      await api("/api/auth/reset-password", { method: "POST", body: { token, password } });
      location.href = "/login.html?notice=reset";
      return;
    } catch (err) {
      say(err.message, "error");
    }
    submit.disabled = false;
    submit.textContent = "Save password";
  });
})();
