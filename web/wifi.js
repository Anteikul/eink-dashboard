const form = document.querySelector('#wifi-form');
const submit = form.querySelector('button[type=submit]');
const message = document.querySelector('#setup-status');

async function refresh() {
  try {
    const response = await fetch('/api/wifi');
    if (!response.ok) return;
    const data = await response.json();
    applyLanguage(data.language);
    if (data.status === 'failed') {
      submit.disabled = false;
      setText(message, 'Could not join that network. Check its name and password, then try again.');
    } else if (data.status === 'joining') {
      submit.disabled = true;
      setText(message, 'The Pi is trying to connect. If this hotspot disappears and comes back, reconnect to it and reopen this page.');
    }
  } catch {
    // The hotspot is temporarily unavailable while the Pi tries the new network.
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  submit.disabled = true;
  setText(message, 'Sending network details…');
  try {
    const response = await fetch('/api/wifi', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    form.elements.password.value = '';
    setText(message, 'The Pi will now try to connect. If it succeeds, this hotspot closes and the dashboard returns to the e-paper display. If the hotspot comes back, reconnect to it and reopen this page.');
  } catch (error) {
    setText(message, error.message);
    submit.disabled = false;
  }
});

refresh();
setInterval(() => {
  if (submit.disabled) refresh();
}, 2000);
