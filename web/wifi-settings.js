(() => {
  const controls = document.querySelector('#wifi-network-controls');
  const nearby = document.querySelector('#wifi-nearby');
  const saved = document.querySelector('#wifi-saved');
  const status = document.querySelector('#wifi-status');
  const refresh = document.querySelector('#wifi-refresh');
  const other = document.querySelector('#wifi-other');
  const connectDialog = document.querySelector('#wifi-connect-dialog');
  const connectForm = document.querySelector('#wifi-connect-form');
  const connectStatus = document.querySelector('#wifi-connect-status');
  const forgetDialog = document.querySelector('#wifi-forget-dialog');
  const busyStates = new Set(['joining', 'forgetting']);
  const lostContact = 'The Pi is no longer reachable at this address. Join its network and open the address on its display.';
  let networks;
  let loading = false;
  let changing = false;
  let forgetTarget;

  async function request(path, payload, timeout = 7000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      return await api(path, payload, controller.signal);
    } finally {
      clearTimeout(timer);
    }
  }

  function updateControls() {
    controls.disabled = loading || changing;
    controls.setAttribute('aria-busy', String(loading || changing));
    other.disabled = !networks?.canManage;
  }

  function button(message, ssid, work, disabled = false) {
    const item = document.createElement('button');
    item.type = 'button';
    item.textContent = translate(message);
    item.setAttribute('aria-label', translate(message) + ' · ' + ssid);
    item.disabled = disabled || !networks.canManage;
    item.addEventListener('click', work);
    return item;
  }

  function showRows(list, items, savedList) {
    list.replaceChildren();
    if (!items.length) {
      const empty = document.createElement('li');
      empty.textContent = translate(savedList ? 'No saved networks.' : 'No nearby networks found.');
      list.append(empty);
      return;
    }
    for (const item of items) {
      const row = document.createElement('li');
      const details = document.createElement('div');
      details.className = 'wifi-network-details';
      const name = document.createElement('strong');
      name.textContent = item.ssid;
      const info = document.createElement('small');
      const labels = item.connected ? [translate('Connected')] : [];
      if (!savedList) labels.push(item.signal + '%', item.security || translate('Open network'));
      else if (item.name !== item.ssid) labels.push(item.name);
      info.textContent = labels.join(' · ');
      details.append(name, info);
      const actions = document.createElement('div');
      actions.className = 'wifi-network-actions';
      if (!item.connected) {
        const profile = savedList ? item : null;
        const supported = profile || !item.security || /WPA/.test(item.security) && !/802\.1X|EAP/.test(item.security);
        actions.append(button('Connect', item.ssid, () => profile
          ? runChange('connect', {uuid: profile.uuid}) : openConnect(item), !supported));
        if (!supported) info.textContent += ' · ' + translate('Use a saved connection for this network.');
      }
      if (savedList) actions.append(button('Forget network', item.ssid, () => {
        forgetTarget = item;
        document.querySelector('#wifi-forget-name').textContent = item.ssid;
        document.querySelector('#wifi-forget-active').hidden = !item.connected;
        forgetDialog.showModal();
      }));
      row.append(details, actions);
      list.append(row);
    }
  }

  function render() {
    if (!networks) return;
    showRows(nearby, networks.available, false);
    showRows(saved, networks.saved, true);
    document.querySelector('#wifi-support').hidden = networks.canManage;
    updateControls();
  }

  async function loadNetworks(rescan = false, keepStatus = false) {
    if (loading || changing) return;
    loading = true;
    updateControls();
    if (!keepStatus) setText(status, rescan ? 'Searching for Wi-Fi networks…' : 'Loading Wi-Fi networks…');
    try {
      networks = await request('/api/wifi-networks', rescan ? {} : undefined, 30000);
      render();
      if (!keepStatus) setText(status, networks.scanError
        ? 'Could not scan nearby networks. Saved networks are still available.' : '');
    } catch (error) {
      if (!keepStatus) setText(status, error.name === 'AbortError' ? 'The Pi did not respond.' : error.message);
    } finally {
      loading = false;
      updateControls();
    }
  }

  function openConnect(network) {
    connectForm.reset();
    setText(connectStatus, '');
    connectForm.elements.ssid.value = network?.ssid ?? '';
    connectForm.elements.ssid.readOnly = Boolean(network);
    const open = network && !network.security;
    connectForm.elements.password.required = Boolean(network && !open);
    document.querySelector('#wifi-password-label').hidden = Boolean(open);
    connectDialog.showModal();
    (network && !open ? connectForm.elements.password : connectForm.elements.ssid).focus();
  }

  async function watch(operation) {
    const deadline = Date.now() + 100000;
    let data = operation;
    while (busyStates.has(data.status) && Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      try {
        data = await request('/api/wifi-status');
      } catch (error) {
        if (error instanceof TypeError || error.name === 'AbortError') throw new Error(lostContact);
        throw error;
      }
      if (data.id !== operation.id) throw new Error('A Wi-Fi change is already in progress.');
    }
    if (busyStates.has(data.status)) throw new Error('The Wi-Fi change is still running. Refresh networks shortly.');
    if (data.status === 'failed') throw new Error(operation.operation === 'forget'
      ? 'Could not forget the Wi-Fi network. Try again.'
      : 'Could not join that network. Check its name and password, then try again.');
    setText(status, data.status === 'forgotten' ? 'Wi-Fi network forgotten.' : 'Wi-Fi connected.');
  }

  async function runChange(action, payload) {
    if (changing || loading) return;
    changing = true;
    updateControls();
    setText(status, action === 'forget' ? 'Forgetting Wi-Fi network…' : 'Connecting to Wi-Fi…');
    const submit = connectForm.querySelector('[type="submit"]');
    submit.disabled = true;
    let accepted = false;
    let reachable = true;
    try {
      const operation = await request('/api/wifi-' + action, payload);
      accepted = true;
      connectForm.elements.password.value = '';
      connectDialog.close();
      await watch(operation);
    } catch (error) {
      const message = error instanceof TypeError || error.name === 'AbortError' ? lostContact : error.message;
      reachable = message !== lostContact;
      setText(status, message);
      if (connectDialog.open) setText(connectStatus, message);
    } finally {
      changing = false;
      submit.disabled = false;
      updateControls();
      if (accepted && reachable) await loadNetworks(false, true);
    }
  }

  refresh.addEventListener('click', () => loadNetworks(true));
  other.addEventListener('click', () => openConnect());
  document.querySelector('#wifi-connect-cancel').addEventListener('click', () => connectDialog.close());
  connectDialog.addEventListener('close', () => { connectForm.elements.password.value = ''; });
  connectForm.addEventListener('submit', event => {
    event.preventDefault();
    runChange('connect', {ssid: connectForm.elements.ssid.value, password: connectForm.elements.password.value});
  });
  document.querySelector('#wifi-forget-cancel').addEventListener('click', () => forgetDialog.close());
  document.querySelector('#wifi-forget-confirm').addEventListener('click', () => {
    const target = forgetTarget;
    forgetDialog.close();
    if (target) runChange('forget', {uuid: target.uuid});
  });
  document.addEventListener('languagechange', render);
  if (!document.querySelector('#setup-fields').hidden) loadNetworks();
  else document.addEventListener('settings-loaded', () => loadNetworks(), {once: true});
})();
