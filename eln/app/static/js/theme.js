// Theme früh setzen (verhindert Aufblitzen). Separate Datei wegen Content-Security-Policy.
(function () {
  try {
    var t = localStorage.getItem('eln-theme');
    if (!t) { t = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'; }
    document.documentElement.setAttribute('data-theme', t);
  } catch (e) { document.documentElement.setAttribute('data-theme', 'light'); }
})();
