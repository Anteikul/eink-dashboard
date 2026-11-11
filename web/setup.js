const deviceForm = document.querySelector('#device-form');
const spotifyForm = document.querySelector('#spotify-form');
const finishForm = document.querySelector('#spotify-finish');
const setupFields = document.querySelector('#setup-fields');
const setupStatus = document.querySelector('#setup-status');
const signIn = document.querySelector('#settings-sign-in');
const deviceStatus = document.querySelector('#device-status');
const spotifyActionStatus = document.querySelector('#spotify-action-status');
const spotifyCheck = document.querySelector('#spotify-check');
const spotifyVerified = document.querySelector('#spotify-verified');
const spotifyCheckStatus = document.querySelector('#spotify-check-status');
const spotifyCheckButton = document.querySelector('#spotify-check-button');
const city = document.querySelector('#city');
const cityStatus = document.querySelector('#city-status');
const places = document.querySelector('#places');
const disconnect = document.querySelector('#spotify-disconnect');
const setupCodeForm = document.querySelector('#setup-code-form');
const setupCodeStatus = document.querySelector('#setup-code-status');
const passwordRequired = document.querySelector('#password-required');
const passwordProtectionStatus = document.querySelector('#password-protection-status');
const localName = document.querySelector('#local-name');
const localHostname = document.querySelector('#local-hostname');
const localNameForm = document.querySelector('#local-name-form');
const localNameStatus = document.querySelector('#local-name-status');
const updateButton = document.querySelector('#check-update');
const installButton = document.querySelector('#install-update');
const updateStatus = document.querySelector('#update-status');
const installedVersion = document.querySelector('#installed-version');
const availableVersion = document.querySelector('#available-version');
const updatingStates = new Set(['checking', 'downloading', 'restarting']);
const updateMessages = {
  checking: 'Checking GitHub for updates…',
  current: 'The dashboard is up to date.',
  available: 'An update is available.',
  downloading: 'Downloading and checking the update…',
  restarting: 'Restarting the dashboard…',
  rolled_back: 'The update did not start. The previous version was restored.',
  failed: 'Could not check for updates. Try again.',
  install_failed: 'Could not install the update. Try again.',
  unavailable: 'Updates are available when the dashboard runs on the Pi.',
};
let foundPlaces = [];
let selectedPlace = -1;
let placeTimer;
let placeRequest;
let spotifyCheckRequest;
let checkingUpdate = false;
let offeredRevision = null;

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
  const options = {signal};
  if (payload !== undefined) {
    options.method = 'POST';
    options.headers = {'Content-Type': 'application/json'};
    options.body = JSON.stringify(payload);
  }
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    if (data.error === 'Check the device setup code.') {
      signIn.hidden = false;
      throw new Error('Sign in again to continue.');
    }
    throw new Error(data.error || 'Could not load settings.');
  }
  if (path !== '/api/state' && path !== '/api/language') signIn.hidden = true;
  return data;
}

async function action(work, status = setupStatus) {
  setText(status, '');
  try {
    await work();
  } catch (error) {
    setText(status, error.message);
  }
}

function fillDevice(settings) {
  for (const [key, value] of Object.entries(settings)) {
    const field = deviceForm.elements.namedItem(key);
    if (field?.type === 'checkbox') field.checked = value;
    else if (field) field.value = value;
  }
}

function showSettings(data) {
  clearPlaces();
  fillDevice(data.settings);
  for (const [key, [min, max]] of Object.entries(data.ranges)) {
    const field = deviceForm.elements.namedItem(key);
    field.min = min;
    field.max = max;
  }
  localName.checked = data.settings.local_name;
  localHostname.value = data.settings.local_hostname;
  passwordRequired.checked = data.settings.password_required;
  showSpotify(data);
}

function showSpotify(data) {
  document.querySelector('#redirect-uri').textContent = data.redirectUri;
  setText(document.querySelector('#spotify-status'), data.spotifyConnected
    ? '' : 'Connect your Spotify account to show music.');
  spotifyForm.hidden = data.spotifyConnected;
  if (data.spotifyConnected) finishForm.hidden = true;
  disconnect.hidden = !data.spotifyConnected;
  spotifyCheckRequest?.abort();
  spotifyCheck.hidden = !data.spotifyConnected;
  spotifyVerified.hidden = true;
  spotifyCheckButton.disabled = false;
  if (data.spotifyConnected) verifySpotify();
}

async function verifySpotify() {
  const controller = new AbortController();
  spotifyCheckRequest = controller;
  spotifyCheckButton.disabled = true;
  spotifyVerified.hidden = true;
  setText(spotifyCheckStatus, 'Checking Spotify API…');
  try {
    const result = await api('/api/spotify/check', {}, controller.signal);
    if (!result.verified) throw new Error('Could not verify Spotify API.');
    if (!controller.signal.aborted) {
      spotifyVerified.hidden = false;
      setText(spotifyCheckStatus, '');
    }
  } catch (error) {
    if (!controller.signal.aborted) setText(spotifyCheckStatus, error.message);
  } finally {
    if (spotifyCheckRequest === controller) spotifyCheckButton.disabled = false;
  }
}

spotifyCheckButton.addEventListener('click', verifySpotify);

localNameForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = localNameForm.querySelector('button');
  button.disabled = true;
  setText(localNameStatus, '');
  try {
    const data = await api('/api/local-name', {enabled: localName.checked, hostname: localHostname.value});
    localName.checked = data.enabled;
    localHostname.value = data.hostname;
    const host = window.location.hostname;
    if (host.endsWith('.local') && (!data.enabled || host !== data.hostname)) {
      window.location.replace(new URL('/settings', data.ipUrl));
      return;
    }
    setText(localNameStatus, data.enabled ? 'Local address enabled.' : 'Local address disabled.');
  } catch (error) {
    setText(localNameStatus, error.message);
  } finally {
    button.disabled = false;
  }
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
    for (const field of deviceForm.querySelectorAll('input[type="number"]')) form[field.name] = field.valueAsNumber;
    for (const field of deviceForm.querySelectorAll('input[type="checkbox"]')) form[field.name] = field.checked;
    form.rotation = Number(form.rotation);
    const data = await api('/api/settings', form);
    clearPlaces();
    fillDevice(data.settings);
    setText(deviceStatus, 'Settings saved. The display will refresh shortly.');
  }, deviceStatus);
});

spotifyForm.addEventListener('submit', (event) => {
  event.preventDefault();
  action(async () => {
    const data = await api('/api/spotify/start', {clientId: spotifyForm.elements.clientId.value.trim()});
    document.querySelector('#spotify-auth').href = data.url;
    finishForm.hidden = false;
    document.querySelector('#spotify-auth').focus();
  }, spotifyActionStatus);
});

finishForm.addEventListener('submit', (event) => {
  event.preventDefault();
  action(async () => {
    showSpotify(await api('/api/spotify/finish', {callback: finishForm.elements.callback.value}));
    finishForm.reset();
    disconnect.focus();
    setText(spotifyActionStatus, 'Spotify connected. The display will refresh shortly.');
  }, spotifyActionStatus);
});

disconnect.addEventListener('click', () => action(async () => {
  showSpotify(await api('/api/spotify/disconnect', {}));
  finishForm.reset();
  finishForm.hidden = true;
  spotifyForm.elements.clientId.focus();
  setText(spotifyActionStatus, 'Spotify disconnected.');
}, spotifyActionStatus));

passwordRequired.addEventListener('change', async () => {
  const required = passwordRequired.checked;
  passwordRequired.disabled = true;
  setText(passwordProtectionStatus, '');
  try {
    const data = await api('/api/password-protection', {required});
    passwordRequired.checked = data.required;
    setText(passwordProtectionStatus, data.required ? 'Web password enabled.' : 'Web password disabled.');
  } catch (error) {
    passwordRequired.checked = !required;
    setText(passwordProtectionStatus, error.message);
  } finally {
    passwordRequired.disabled = false;
  }
});

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
    setupCodeForm.elements.newCode.value = '';
    setupCodeForm.elements.confirmCode.value = '';
    setText(setupCodeStatus, 'Setup code changed.');
  } catch (error) {
    setText(setupCodeStatus, error.message);
  } finally {
    button.disabled = false;
  }
});

function showUpdate(data) {
  installedVersion.hidden = !data.version;
  installedVersion.textContent = data.version?.slice(0, 7) ?? '';
  offeredRevision = data.availableVersion ?? null;
  installButton.hidden = !offeredRevision;
  availableVersion.textContent = offeredRevision?.slice(0, 7) ?? '';
  setText(updateStatus, updateMessages[data.state] ?? '');
}

async function runUpdate(path, payload, initialState) {
  if (checkingUpdate) return;
  checkingUpdate = updateButton.disabled = installButton.disabled = true;
  let data;
  try {
    setText(updateStatus, updateMessages[initialState]);
    data = await api(path, payload);
    const previous = data.version;
    const deadline = Date.now() + 120000;
    showUpdate(data);
    while (updatingStates.has(data.state) && Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      try {
        data = await api('/api/update');
      } catch (error) {
        if (!(error instanceof TypeError)) throw error;
        continue;
      }
      if (data.version && data.version !== previous && !updatingStates.has(data.state)) {
        window.location.reload();
        return;
      }
      showUpdate(data);
    }
    if (updatingStates.has(data.state)) setText(updateStatus, 'The update is still running. Check again shortly.');
  } catch (error) {
    setText(updateStatus, error instanceof TypeError ? 'The Pi did not respond.' : error.message);
  } finally {
    checkingUpdate = false;
    updateButton.disabled = data?.state === 'unavailable';
    installButton.disabled = !offeredRevision || updatingStates.has(data?.state);
  }
}

function checkUpdate() {
  return runUpdate('/api/update', {}, 'checking');
}

updateButton.addEventListener('click', checkUpdate);
installButton.addEventListener('click', () => {
  if (offeredRevision) runUpdate('/api/update/install', {version: offeredRevision}, 'downloading');
});
window.addEventListener('pageshow', event => {
  if (event.persisted && !setupFields.hidden) checkUpdate();
});

api('/api/state').then(data => {
  applyLanguage(data.language);
  document.documentElement.dataset.theme = data.appliedTheme || data.theme;
}).catch(error => setText(document.querySelector('#language-status'), error.message));

action(async () => {
  showSettings(await api('/api/settings'));
  setupFields.hidden = false;
  checkUpdate();
});
