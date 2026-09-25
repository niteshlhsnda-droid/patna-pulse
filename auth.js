/* ================================================================
   Shared login gate for all four GitHub Pages sites.
   * CHANGE THE PASSWORD on the next line, then copy this file and
     login.html into each site repo. One login unlocks all 4 sites.
   * Honest note: this is a polite front-door, NOT real security.
     The password lives in public page source, so anyone who reads
     the code can walk past it. It keeps casual visitors out.
   ================================================================ */
var SITE_PASSWORD = "changeme123";   /* <-- CHANGE THIS PASSWORD */
var LOGIN_PAGE = "/patna-pulse/login.html";
var AUTH_KEY = "all_sites_auth_ok";

(function () {
  try {
    if (localStorage.getItem(AUTH_KEY) === "1") return;
    var p = location.pathname;
    if (p.slice(-10) === "login.html") return;
    location.replace(LOGIN_PAGE + "?next=" + encodeURIComponent(p + location.search));
  } catch (e) {}
})();

function siteDoLogin(pw) {
  if (pw === SITE_PASSWORD) {
    try { localStorage.setItem(AUTH_KEY, "1"); } catch (e) {}
    return true;
  }
  return false;
}
function siteIsAuthed() {
  try { return localStorage.getItem(AUTH_KEY) === "1"; } catch (e) { return false; }
}
function siteLogout() {
  try { localStorage.removeItem(AUTH_KEY); } catch (e) {}
  location.replace(LOGIN_PAGE);
}
