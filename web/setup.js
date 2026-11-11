const openSettings = document.querySelector('#open-settings');
const settingsDialog = document.querySelector('#settings-dialog');
const unlockForm = document.querySelector('#unlock-form');
const deviceForm = document.querySelector('#device-form');
const spotifyForm = document.querySelector('#spotify-form');
const finishForm = document.querySelector('#spotify-finish');
const setupFields = document.querySelector('#setup-fields');
const setupStatus = document.querySelector('#setup-status');
const city = document.querySelector('#city');
const cityStatus = document.querySelector('#city-status');
const places = document.querySelector('#places');
const disconnect = document.querySelector('#spotify-disconnect');
const setupCodeForm = document.querySelector('#setup-code-form');
const setupCodeStatus = document.querySelector('#setup-code-status');
const localName = document.querySelector('#local-name');
const localNameStatus = document.querySelector('#local-name-status');
let setupCode = '';
let foundPlaces = [];
let selectedPlace = -1;
let placeTimer;
let placeRequest;

openSettings.addEventListener('click', () => settingsDialog.showModal());
settingsDialog.addEventListener('close', () => {
  clearPlaces();
  openSettings.focus();
});

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

async function api(path, payload, signal) {
  const headers = {'X-Setup-Code': setupCode};
  const options = {headers, signal};
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
  clearPlaces();
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
    city.focus();
  });
});

function clearPlaces() {
  clearTimeout(placeTimer);
  placeRequest?.abort();
  placeRequest = undefined;
  foundPlaces = [];
  selectedPlace = -1;
  places.replaceChildren();
  places.hidden = true;
  city.setAttribute('aria-expanded', 'false');
  city.removeAttribute('aria-activedescendant');
  setText(cityStatus, '');
}

function searchPlaces(event) {
  if (event.isComposing) return;
  clearPlaces();
  const name = city.value.trim();
  if (name.length < 2 || name.length > 80) return;
  const controller = new AbortController();
  placeRequest = controller;
  placeTimer = setTimeout(async () => {
    try {
      const {places: matches} = await api('/api/places', {name}, controller.signal);
      if (controller.signal.aborted) return;
      foundPlaces = matches;
      places.replaceChildren(...matches.map((place, index) => {
        const option = document.createElement('li');
        option.id = 'place-' + index;
        option.dataset.index = index;
        option.setAttribute('role', 'option');
        option.setAttribute('aria-selected', 'false');
        option.textContent = place.label;
        return option;
      }));
      places.hidden = !matches.length;
      city.setAttribute('aria-expanded', String(!places.hidden));
      if (!matches.length) setText(cityStatus, 'No matching locations found.');
    } catch (error) {
      if (!controller.signal.aborted) setText(cityStatus, error.message);
    }
  }, 300);
}

function choosePlace(index) {
  const place = foundPlaces[index];
  if (!place) return;
  clearPlaces();
  fillDevice(place);
  city.focus();
}

city.addEventListener('input', searchPlaces);
city.addEventListener('compositionend', searchPlaces);
city.addEventListener('blur', clearPlaces);
city.addEventListener('keydown', (event) => {
  if (event.isComposing) return;
  if (event.key === 'Escape' && (placeRequest || !places.hidden)) {
    event.preventDefault();
    clearPlaces();
    return;
  }
  if (places.hidden) return;
  if (event.key === 'Enter') {
    event.preventDefault();
    choosePlace(Math.max(0, selectedPlace));
  } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();
    const next = event.key === 'ArrowDown' ? selectedPlace + 1
      : selectedPlace < 0 ? foundPlaces.length - 1 : selectedPlace - 1;
    places.children[selectedPlace]?.setAttribute('aria-selected', 'false');
    selectedPlace = (next + foundPlaces.length) % foundPlaces.length;
    const option = places.children[selectedPlace];
    option.setAttribute('aria-selected', 'true');
    city.setAttribute('aria-activedescendant', option.id);
    option.scrollIntoView({block: 'nearest'});
  }
});
places.addEventListener('mousedown', (event) => event.preventDefault());
places.addEventListener('click', (event) => {
  const option = event.target.closest('[data-index]');
  if (option) choosePlace(Number(option.dataset.index));
});

deviceForm.addEventListener('submit', (event) => {
  event.preventDefault();
  action(async () => {
    const form = Object.fromEntries(new FormData(deviceForm));
    for (const key of ['latitude', 'longitude', 'rotation', 'display_width', 'display_height']) {
      form[key] = Number(form[key]);
    }
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
