// Dark-mode toggle. The no-flash inline script in <head> already applied
// any stored preference before first paint; this just handles clicks on
// the nav bar's toggle button and keeps localStorage in sync. Runs
// wherever it's included, after the nav bar it targets already exists.
function toggleTheme() {
  var isDark = document.documentElement.getAttribute("data-theme")
    ? document.documentElement.getAttribute("data-theme") === "dark"
    : window.matchMedia("(prefers-color-scheme: dark)").matches;
  var next = isDark ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try {
    localStorage.setItem("theme", next);
  } catch (e) {}
}
