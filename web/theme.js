{
  const key = 'eink-web-theme';
  const systemTheme = matchMedia('(prefers-color-scheme: dark)');
  const themeColor = document.querySelector('meta[name="theme-color"]');
  let preference = 'system';
  let chooser;

  function applyTheme() {
    const dark = preference === 'dark' || (preference === 'system' && systemTheme.matches);
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    if (themeColor) themeColor.content = dark ? '#1d221e' : '#eeece5';
    if (chooser) chooser.value = preference;
  }

  function loadTheme() {
    try {
      const saved = localStorage.getItem(key);
      preference = saved === 'light' || saved === 'dark' ? saved : 'system';
    } catch {
      // Keep the current choice when browser storage is unavailable.
    }
    applyTheme();
  }

  loadTheme();
  systemTheme.addEventListener('change', applyTheme);
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) loadTheme();
  });
  window.addEventListener('pageshow', event => {
    if (event.persisted) loadTheme();
  });
  document.addEventListener('DOMContentLoaded', () => {
    chooser = document.querySelector('#web-theme');
    if (!chooser) return;
    chooser.value = preference;
    chooser.addEventListener('change', () => {
      preference = chooser.value;
      try {
        localStorage.setItem(key, preference);
      } catch {
        // Apply the choice for this page even without browser storage.
      }
      applyTheme();
    });
  });
}
