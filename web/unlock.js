const unlockForm = document.querySelector('#unlock-form');
const codeField = document.querySelector('#unlock-code');
const unlockStatus = document.querySelector('#unlock-status');
const submit = unlockForm.querySelector('button');
const nextPage = new URLSearchParams(window.location.search).get('next');
const destination = nextPage === 'layouts' ? '/#saved-layouts' : nextPage === 'editor' ? '/editor' : '/settings';

unlockForm.addEventListener('submit', async event => {
  event.preventDefault();
  if (submit.disabled) return;
  const code = codeField.value.trim();
  if (!code) {
    setText(unlockStatus, 'Check the device setup code.');
    codeField.focus();
    return;
  }
  submit.disabled = true;
  setText(unlockStatus, '');
  try {
    const response = await fetch('/api/unlock', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({code}),
    });
    if (!response.ok) {
      const result = await response.json();
      throw new Error(result.error || 'Could not sign in.');
    }
    unlockForm.reset();
    window.location.replace(destination);
  } catch (error) {
    setText(unlockStatus, error.message);
    codeField.focus();
    codeField.select();
  } finally {
    submit.disabled = false;
  }
});

fetch('/api/state').then(response => response.ok ? response.json() : null).then(data => {
  if (!data) return;
  document.documentElement.dataset.theme = data.appliedTheme || data.theme;
  applyLanguage(data.language);
}).catch(() => {});
