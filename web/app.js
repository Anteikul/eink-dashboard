const controls = document.querySelector('fieldset');
const buttons = [...controls.querySelectorAll('button')];
const status = document.querySelector('#status');
const image = document.querySelector('#preview');
const placeholder = document.querySelector('#placeholder');
const trackLink = document.querySelector('#track-link');
let revision = null;
let saving = false;
let saveError = '';

image.addEventListener('load', () => {
  placeholder.hidden = true;
  image.hidden = false;
});

function show(data) {
  applyLanguage(data.language);
  const applied = data.appliedTheme === data.theme;
  trackLink.hidden = !data.trackUrl;
  if (data.trackUrl) trackLink.querySelector('a').href = data.trackUrl;
  document.documentElement.dataset.theme = data.appliedTheme || data.theme;
  for (const button of buttons) {
    button.setAttribute('aria-pressed', String(button.dataset.theme === data.theme));
  }
  if (data.revision && data.revision !== revision) {
    revision = data.revision;
    image.src = '/screen.png?frame=' + revision;
  }
  controls.disabled = false;
  setText(status, saveError || (applied ? 'Shown on the display.' : 'Refreshing the display…'));
}

async function read() {
  if (saving) return;
  try {
    const response = await fetch('/api/state');
    if (!response.ok) throw new Error();
    const data = await response.json();
    if (!saving) show(data);
  } catch {
    setText(status, 'Connection to the Pi lost. Reconnecting…');
    controls.disabled = true;
  }
}

for (const button of buttons) {
  button.addEventListener('click', async () => {
    if (saving || button.getAttribute('aria-pressed') === 'true') return;
    saving = true;
    saveError = '';
    setText(status, 'Saving theme…');
    try {
      const response = await fetch('/api/theme', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({theme: button.dataset.theme}),
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
