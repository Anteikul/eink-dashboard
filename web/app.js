const controls = [...document.querySelectorAll('fieldset[data-control]')];
const buttons = controls.flatMap(group => [...group.querySelectorAll('button')]);
const status = document.querySelector('#status');
const image = document.querySelector('#preview');
const bezel = image.closest('.bezel');
const placeholder = document.querySelector('#placeholder');
const trackLink = document.querySelector('#track-link');
const layoutPicker = document.querySelector('#saved-layouts');
const activeLayoutLabel = document.querySelector('#active-layout');
const layoutOptions = document.querySelector('#quick-layout-options');
const layoutStatus = document.querySelector('#quick-layout-status');
const layoutSections = [...layoutOptions.querySelectorAll('[data-screen]')];
let revision = null;
let saving = false;
let saveError = '';
let reading = false;
let change = 0;
let loadingLayouts = false;
let activeLayout;
let selectedLayouts = {};

image.addEventListener('load', () => {
  bezel.toggleAttribute('data-portrait', image.naturalHeight > image.naturalWidth);
  placeholder.hidden = true;
  image.hidden = false;
});

function showActiveLayout() {
  if (!activeLayout) return;
  const {kind, name} = activeLayout;
  const title = name ?? translate(kind === 'default' ? 'Default layout' : 'Custom layout');
  activeLayoutLabel.textContent = '· ' + title;
  activeLayoutLabel.hidden = false;
  for (const section of layoutSections) {
    const selection = selectedLayouts[section.dataset.screen];
    let matched = false;
    for (const button of section.querySelectorAll('button[data-layout]')) {
      const selected = Boolean(selection && selection.kind !== 'custom' && button.dataset.layout === (selection.name ?? ''));
      matched ||= selected;
      button.setAttribute('aria-pressed', String(selected));
    }
    const current = section.querySelector('[data-current-layout]');
    current.hidden = !selection || matched;
    if (!current.hidden) current.textContent = selection.name ?? translate('Custom layout');
  }
}

function show(data) {
  applyLanguage(data.language);
  activeLayout = data.activeLayout;
  selectedLayouts = data.selectedLayouts ?? {};
  showActiveLayout();
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

async function request(path, payload, fallback) {
  const options = payload === undefined ? undefined : {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  };
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || fallback);
  return data;
}

function message(error) {
  return error instanceof TypeError ? 'The Pi did not respond.' : error.message;
}

async function saveDisplay(path, payload, pending, fallback) {
  saving = true;
  change++;
  saveError = '';
  setText(status, pending);
  try {
    show(await request(path, payload, fallback));
  } finally {
    saving = false;
  }
}

for (const button of buttons) {
  button.addEventListener('click', async () => {
    if (saving || button.getAttribute('aria-pressed') === 'true') return;
    const key = button.closest('fieldset').dataset.control;
    const theme = key === 'theme';
    try {
      await saveDisplay(theme ? '/api/theme' : '/api/display-mode', {[key]: button.dataset[key]},
        theme ? 'Saving theme…' : 'Switching display mode…', 'Could not apply the change. Try again.');
    } catch (error) {
      saveError = message(error);
      setText(status, saveError);
    }
  });
}

function reportLayoutError(error) {
  if (error.message === 'Check the device setup code.') {
    window.location.assign('/unlock?next=layouts');
  } else {
    setText(layoutStatus, message(error));
  }
}

async function loadQuickLayouts() {
  if (loadingLayouts) return;
  loadingLayouts = true;
  layoutOptions.hidden = true;
  setText(layoutStatus, 'Loading layouts…');
  try {
    const lists = await Promise.all(layoutSections.map(section => request(
      '/api/layout-library?' + new URLSearchParams({screen: section.dataset.screen}), undefined,
      'Could not open the layout library.',
    )));
    for (const [index, section] of layoutSections.entries()) {
      const buttons = lists[index].names.map(name => {
        const button = document.createElement('button');
        button.type = 'button';
        button.dataset.layout = name;
        button.textContent = name;
        return button;
      });
      section.querySelector('[data-saved-names]').replaceChildren(...buttons);
    }
    showActiveLayout();
    layoutOptions.hidden = false;
    layoutOptions.disabled = false;
    setText(layoutStatus, '');
  } catch (error) {
    reportLayoutError(error);
  } finally {
    loadingLayouts = false;
  }
}

layoutPicker.addEventListener('toggle', () => {
  if (layoutPicker.open) loadQuickLayouts();
});

layoutOptions.addEventListener('click', async event => {
  const button = event.target.closest('button[data-layout]');
  if (!button || saving) return;
  const screen = button.closest('[data-screen]').dataset.screen;
  layoutOptions.disabled = true;
  setText(layoutStatus, '');
  try {
    await saveDisplay('/api/layout-library/apply', {screen, name: button.dataset.layout || null},
      'Applying layout…', 'Could not apply the layout.');
    setText(layoutStatus, 'Layout applied.');
  } catch (error) {
    setText(status, '');
    reportLayoutError(error);
  } finally {
    layoutOptions.disabled = false;
  }
});

if (window.location.hash === '#saved-layouts') layoutPicker.open = true;
read();
setInterval(read, 2000);
