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
let setupCode = '';
let foundPlaces = [];

openSettings.addEventListener('click', () => settingsDialog.showModal());
settingsDialog.addEventListener('close', () => openSettings.focus());

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
  setupStatus.textContent = '';
  try {
    await work();
  } catch (error) {
    setupStatus.textContent = error.message;
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
  document.querySelector('#redirect-uri').textContent = data.redirectUri;
  document.querySelector('#spotify-status').textContent = data.spotifyConnected
    ? 'Your account is connected.' : 'Connect your Spotify account to show music.';
  spotifyForm.hidden = data.spotifyConnected;
  if (data.spotifyConnected) finishForm.hidden = true;
  disconnect.hidden = !data.spotifyConnected;
}

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
  places.replaceChildren(new Option('Select a location', ''));
  for (const [index, place] of foundPlaces.entries()) places.add(new Option(place.label, index));
  places.hidden = !foundPlaces.length;
  setupStatus.textContent = foundPlaces.length ? 'Select a location from the list.' : 'No matching locations found.';
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
    setupStatus.textContent = 'Settings saved. The display will refresh shortly.';
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
    setupStatus.textContent = 'Spotify connected. The display will refresh shortly.';
  });
});

disconnect.addEventListener('click', () => action(async () => {
  showSettings(await api('/api/spotify/disconnect', {}));
  finishForm.reset();
  finishForm.hidden = true;
  spotifyForm.elements.clientId.focus();
  setupStatus.textContent = 'Spotify disconnected.';
}));
