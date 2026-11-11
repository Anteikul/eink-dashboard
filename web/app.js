const controls = [...document.querySelectorAll('fieldset[data-control]')];
const buttons = controls.flatMap(group => [...group.querySelectorAll('button')]);
const status = document.querySelector('#status');
const image = document.querySelector('#preview');
const placeholder = document.querySelector('#placeholder');
const trackLink = document.querySelector('#track-link');
let revision = null;
let saving = false;
let saveError = '';
let reading = false;
let change = 0;

image.addEventListener('load', () => {
  placeholder.hidden = true;
  image.hidden = false;
});

function show(data) {
  applyLanguage(data.language);
  const applied = data.appliedTheme === data.theme && data.page && (data.mode === 'auto' || data.page === data.mode);
  trackLink.hidden = !data.trackUrl;
  if (data.trackUrl) trackLink.querySelector('a').href = data.trackUrl;
  document.documentElement.dataset.theme = data.appliedTheme || data.theme;
  for (const button of buttons) {
    const key = button.closest('fieldset').dataset.control;
    button.setAttribute('aria-pressed', String(button.dataset[key] === data[key]));
  }
  if (data.revision && data.revision !== revision) {
    revision = data.revision;
    image.src = '/screen.png?frame=' + revision;
  }
  for (const group of controls) group.disabled = false;
  setText(status, saveError || (applied ? '' : 'Refreshing the display…'));
}

async function read() {
  if (saving || reading) return;
  reading = true;
  const previous = change;
  try {
    const response = await fetch('/api/state');
    if (!response.ok) throw new Error();
    const data = await response.json();
    if (previous === change) show(data);
  } catch {
    if (previous === change) {
      setText(status, 'Connection to the Pi lost. Reconnecting…');
      for (const group of controls) group.disabled = true;
    }
  } finally {
    reading = false;
  }
}

for (const button of buttons) {
  button.addEventListener('click', async () => {
    if (saving || button.getAttribute('aria-pressed') === 'true') return;
    saving = true;
    change++;
    saveError = '';
    const key = button.closest('fieldset').dataset.control;
    const theme = key === 'theme';
    setText(status, theme ? 'Saving theme…' : 'Switching display mode…');
    try {
      const response = await fetch(theme ? '/api/theme' : '/api/display-mode', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({[key]: button.dataset[key]}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      show(data);
    } catch (error) {
      saveError = error instanceof TypeError ? 'The Pi did not respond.' : error.message;
      setText(status, saveError);
    } finally {
      saving = false;
    }
  });
}

read();
setInterval(read, 2000);
