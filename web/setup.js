const openSettings = document.querySelector('#open-settings');
const settingsDialog = document.querySelector('#settings-dialog');
const unlockForm = document.querySelector('#unlock-form');
const deviceForm = document.querySelector('#device-form');
const spotifyForm = document.querySelector('#spotify-form');
const finishForm = document.querySelector('#spotify-finish');
const setupFields = document.querySelector('#setup-fields');
const setupStatus = document.querySelector('#setup-status');
const places = document.querySelector('#places');
const disconnect = document.querySelector('#spotify-disconnect');
const setupCodeForm = document.querySelector('#setup-code-form');
const setupCodeStatus = document.querySelector('#setup-code-status');
const localName = document.querySelector('#local-name');
const localNameStatus = document.querySelector('#local-name-status');
let setupCode = '';
let foundPlaces = [];

openSettings.addEventListener('click', () => settingsDialog.showModal());
settingsDialog.addEventListener('close', () => openSettings.focus());

languageSelect.addEventListener('change', async () => {
  const status = document.querySelector('#language-status');
  languageSelect.dataset.saving = 'true';
  languageSelect.disabled = true;
  setText(status, '');
  try {
    const data = await api('/api/language', {language: languageSelect.value});
    applyLanguage(data.language);
  } catch (error) {
    setText(status, error.message);
  } finally {
    delete languageSelect.dataset.saving;
    applyLanguage(document.documentElement.lang);
  }
});

async function api(path, payload) {
  const headers = {'X-Setup-Code': setupCode};
  const options = {headers};
  if (payload !== undefined) {
    options.method = 'POST';
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(payload);
  }
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Could not load settings.');
  return data;
}

async function action(work) {
  setText(setupStatus, '');
  try {
    await work();
  } catch (error) {
    setText(setupStatus, error.message);
  }
}

function fillDevice(settings) {
  for (const [key, value] of Object.entries(settings)) {
    const field = deviceForm.elements.namedItem(key);
    if (field) field.value = value;
  }
}

function showSettings(data) {
  fillDevice(data.settings);
  if (!localName.disabled) localName.checked = data.settings.local_name;
  document.querySelector('#redirect-uri').textContent = data.redirectUri;
  setText(document.querySelector('#spotify-status'), data.spotifyConnected
    ? 'Your account is connected.' : 'Connect your Spotify account to show music.');
  spotifyForm.hidden = data.spotifyConnected;
  if (data.spotifyConnected) finishForm.hidden = true;
  disconnect.hidden = !data.spotifyConnected;
}

localName.addEventListener('change', async () => {
  const enabled = localName.checked;
  localName.disabled = true;
  setText(localNameStatus, '');
  try {
    const data = await api('/api/local-name', {enabled});
    localName.checked = data.enabled;
    if (!data.enabled && window.location.hostname === 'eink.local') {
      window.location.replace(data.ipUrl);
      return;
    }
    setText(localNameStatus, data.enabled ? 'Local address enabled.' : 'Local address disabled.');
  } catch (error) {
    localName.checked = !enabled;
    setText(localNameStatus, error.message);
  } finally {
    localName.disabled = false;
  }
});

unlockForm.addEventListener('submit', (event) => {
  event.preventDefault();
  action(async () => {
    setupCode = document.querySelector('#setup-code').value.trim();
    showSettings(await api('/api/settings'));
    unlockForm.reset();
    unlockForm.hidden = true;
    setupFields.hidden = false;
    document.querySelector('#city').focus();
  });
});

document.querySelector('#find-city').addEventListener('click', () => action(async () => {
  const data = await api('/api/places', {name: deviceForm.elements.location.value});
  foundPlaces = data.places;
  if (places.options.length) dynamicText.delete(places.options[0]);
  const placeholder = new Option('', '');
  setText(placeholder, 'Select a location');
  places.replaceChildren(placeholder);
  for (const [index, place] of foundPlaces.entries()) places.add(new Option(place.label, index));
  places.hidden = !foundPlaces.length;
  setText(setupStatus, foundPlaces.length ? 'Select a location from the list.' : 'No matching locations found.');
}));

places.addEventListener('change', () => {
  if (places.value !== '') fillDevice(foundPlaces[Number(places.value)]);
});

deviceForm.addEventListener('submit', (event) => {
  event.preventDefault();
  action(async () => {
    const form = Object.fromEntries(new FormData(deviceForm));
    for (const key of ['latitude', 'longitude', 'rotation']) form[key] = Number(form[key]);
    showSettings(await api('/api/settings', form));
    setText(setupStatus, 'Settings saved. The display will refresh shortly.');
  });
});

spotifyForm.addEventListener('submit', (event) => {
  event.preventDefault();
  action(async () => {
    const data = await api('/api/spotify/start', {clientId: spotifyForm.elements.clientId.value.trim()});
    document.querySelector('#spotify-auth').href = data.url;
    finishForm.hidden = false;
    document.querySelector('#spotify-auth').focus();
  });
});

finishForm.addEventListener('submit', (event) => {
  event.preventDefault();
  action(async () => {
    showSettings(await api('/api/spotify/finish', {callback: finishForm.elements.callback.value}));
    finishForm.reset();
    disconnect.focus();
    setText(setupStatus, 'Spotify connected. The display will refresh shortly.');
  });
});

disconnect.addEventListener('click', () => action(async () => {
  showSettings(await api('/api/spotify/disconnect', {}));
  finishForm.reset();
  finishForm.hidden = true;
  spotifyForm.elements.clientId.focus();
  setText(setupStatus, 'Spotify disconnected.');
}));

setupCodeForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const newCode = setupCodeForm.elements.newCode.value;
  if (newCode !== setupCodeForm.elements.confirmCode.value) {
    setText(setupCodeStatus, 'The new codes do not match.');
    return;
  }
  const button = setupCodeForm.querySelector('button');
  button.disabled = true;
  setText(setupCodeStatus, '');
  try {
    await api('/api/setup-code', {newCode});
    setupCode = newCode;
    setupCodeForm.reset();
    setText(setupCodeStatus, 'Setup code changed.');
  } catch (error) {
    setText(setupCodeStatus, error.message);
  } finally {
    button.disabled = false;
  }
});
