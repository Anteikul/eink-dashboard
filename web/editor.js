{
  const element = (id) => document.getElementById(id);
  const dialog = element('layout-editor');
  const openButton = element('open-editor');
  const closeButton = element('editor-close');
  const unlock = element('editor-unlock');
  const codeField = element('editor-code');
  const accessStatus = element('editor-access-status');
  const content = element('editor-content');
  const panel = element('editor-panel');
  const tabs = [...dialog.querySelectorAll('[role=tab]')];
  const stage = element('editor-stage');
  const preview = element('editor-image');
  const previewStatus = element('editor-preview-status');
  const retry = element('editor-preview-retry');
  const widgetList = element('editor-widgets');
  const addType = element('editor-add-type');
  const add = element('editor-add');
  const properties = element('editor-properties');
  const fields = Object.fromEntries(
    [...properties.querySelectorAll('[data-property]')].map(field => [field.dataset.property, field]),
  );
  const moveUp = element('editor-move-up');
  const moveDown = element('editor-move-down');
  const remove = element('editor-remove');
  const reset = element('editor-reset');
  const save = element('editor-save');
  const dirtyMessage = element('editor-dirty');
  const saveStatus = element('editor-save-status');
  const drafts = Object.fromEntries(tabs.map(tab => [
    tab.dataset.screen, {saved: null, layout: null, selection: -1, message: ''},
  ]));
  const arrows = {
    ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1],
  };
  const badCode = 'Check the device setup code.';

  let schema;
  let screen = 'dashboard';
  let hitboxes = [];
  let widgetButtons = [];
  let drag;
  let loadController;
  let previewController;
  let previewTimer;
  let previewURL;
  let savingScreen;

  const current = () => drafts[screen];
  const widgets = () => current().layout ?? schema.defaults[screen];
  const definitions = () => schema.widgets[screen];
  const definition = (type) => definitions().find(widget => widget.type === type);
  const hasChanges = ({saved, layout}) => JSON.stringify(saved) !== JSON.stringify(layout);
  const clamp = (value, min, max) => Math.max(min, Math.min(value, max));

  async function request(path, {code = setupCode, payload, signal, fallback} = {}) {
    const headers = {'X-Setup-Code': code};
    const options = {headers, signal};
    if (payload !== undefined) {
      headers['Content-Type'] = 'application/json';
      options.method = 'POST';
      options.body = JSON.stringify(payload);
    }
    const response = await fetch(path, options);
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || fallback);
    }
    return response;
  }

  function updateStatus() {
    for (const tab of tabs) {
      const dirty = hasChanges(drafts[tab.dataset.screen]);
      tab.querySelector('.editor-tab-dirty').hidden = !dirty;
      if (dirty) {
        const title = tab.firstElementChild.textContent;
        tab.setAttribute('aria-label', title + ' (' + translate('Unsaved changes') + ')');
      } else {
        tab.removeAttribute('aria-label');
      }
    }
    dirtyMessage.hidden = !Object.values(drafts).some(hasChanges);
    reset.disabled = current().layout === null;
    save.disabled = Boolean(savingScreen) || !hasChanges(current());
    setText(saveStatus, current().message);
  }

  function widgetLabel(widget, index) {
    return translate(definition(widget.type).label) + ' ' + (index + 1);
  }

  function renderAddOptions() {
    const previous = addType.value;
    addType.replaceChildren(...definitions().map(item => new Option(translate(item.label), item.type)));
    if (definitions().some(item => item.type === previous)) addType.value = previous;
  }

  function updateInspector() {
    const widget = widgets()[current().selection];
    properties.hidden = !widget;
    element('editor-no-selection').hidden = Boolean(widget);
    if (!widget) return;

    const item = definition(widget.type);
    element('editor-selected-widget').textContent = widgetLabel(widget, current().selection);
    element('editor-variant-label').hidden = item.variants.length === 0;
    element('editor-text-style').hidden = !item.textStyle || (
      (widget.type === 'clock' && widget.variant === 'analog') ||
      (widget.type === 'weather' && widget.variant === 'icon-only')
    );
    element('editor-text-label').hidden = widget.type !== 'text';

    if (fields.variant.dataset.type !== widget.type) {
      fields.variant.replaceChildren(...item.variants.map(variant =>
        new Option(translate(variant.label), variant.value)));
      fields.variant.dataset.type = widget.type;
    }

    fields.x.max = schema.width - widget.w;
    fields.y.max = schema.height - widget.h;
    fields.w.max = schema.width - widget.x;
    fields.h.max = schema.height - widget.y;
    for (const [name, field] of Object.entries(fields)) {
      const value = String(widget[name] ?? '');
      if (field.value !== value) field.value = value;
    }
    moveUp.disabled = current().selection === 0;
    moveDown.disabled = current().selection === widgets().length - 1;
  }

  function updateSelection() {
    for (const [index, hitbox] of hitboxes.entries()) {
      const selected = String(index === current().selection);
      hitbox.setAttribute('aria-pressed', selected);
      widgetButtons[index].setAttribute('aria-pressed', selected);
    }
    updateInspector();
  }

  function position(hitbox, {x, y, w, h}) {
    hitbox.style.left = (x / schema.width * 100) + '%';
    hitbox.style.top = (y / schema.height * 100) + '%';
    hitbox.style.width = (w / schema.width * 100) + '%';
    hitbox.style.height = (h / schema.height * 100) + '%';
  }

  function renderWidgets() {
    for (const hitbox of hitboxes) hitbox.remove();
    hitboxes = [];
    widgetButtons = [];
    const list = document.createDocumentFragment();
    for (const [index, widget] of widgets().entries()) {
      const label = widgetLabel(widget, index);
      const hitbox = document.createElement('button');
      hitbox.type = 'button';
      hitbox.className = 'editor-hitbox';
      hitbox.dataset.index = index;
      hitbox.setAttribute('aria-label', label);
      position(hitbox, widget);
      stage.append(hitbox);
      hitboxes.push(hitbox);

      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.index = index;
      const name = document.createElement('span');
      name.textContent = translate(definition(widget.type).label);
      const number = document.createElement('span');
      number.className = 'editor-position';
      number.textContent = index + 1;
      button.append(name, number);
      const row = document.createElement('li');
      row.append(button);
      list.append(row);
      widgetButtons.push(button);
    }
    widgetList.replaceChildren(list);
    add.disabled = widgets().length >= (schema.maxWidgets ?? 18);
    updateSelection();
  }

  function selectWidget(index) {
    current().selection = index;
    updateSelection();
  }

  function clearPreview() {
    preview.hidden = true;
    preview.removeAttribute('src');
    if (previewURL) URL.revokeObjectURL(previewURL);
    previewURL = undefined;
  }

  function stopPreview() {
    clearTimeout(previewTimer);
    previewController?.abort();
    previewController = undefined;
  }

  function askForCode(message) {
    stopPreview();
    clearPreview();
    content.hidden = true;
    unlock.hidden = false;
    setText(accessStatus, message);
    codeField.focus();
  }

  function schedulePreview(delay = 160) {
    stopPreview();
    retry.hidden = true;
    setText(previewStatus, '');
    const payload = {screen, layout: current().layout};
    const code = setupCode;
    const controller = new AbortController();
    previewController = controller;
    previewTimer = setTimeout(async () => {
      try {
        const response = await request('/api/layout-preview', {
          code, payload, signal: controller.signal, fallback: 'Could not load the sample preview.',
        });
        const blob = await response.blob();
        if (controller.signal.aborted || previewController !== controller) return;
        if (blob.type !== 'image/png') throw new Error('Could not load the sample preview.');
        const url = URL.createObjectURL(blob);
        if (previewURL) URL.revokeObjectURL(previewURL);
        previewURL = url;
        preview.src = url;
        preview.hidden = false;
      } catch (error) {
        if (controller.signal.aborted || previewController !== controller) return;
        if (error.message === badCode) {
          askForCode(error.message);
          return;
        }
        setText(previewStatus, error instanceof TypeError ? 'The Pi did not respond.' : error.message);
        retry.hidden = false;
      }
    }, delay);
  }

  function showScreen() {
    drag = undefined;
    for (const tab of tabs) {
      const active = tab.dataset.screen === screen;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      if (active) panel.setAttribute('aria-labelledby', tab.id);
    }
    clearPreview();
    renderAddOptions();
    renderWidgets();
    updateStatus();
    schedulePreview(0);
  }

  async function loadLayouts(code, focusTab) {
    loadController?.abort();
    const controller = new AbortController();
    loadController = controller;
    const unlockButton = unlock.querySelector('button');
    unlockButton.disabled = true;
    setText(accessStatus, 'Loading layouts…');
    try {
      // Keep the in-flight save as the source of truth when reopening the editor.
      if (!savingScreen || !schema || focusTab) {
        const response = await request('/api/layouts', {
          code, signal: controller.signal, fallback: 'Could not load the layouts.',
        });
        const data = await response.json();
        if (controller.signal.aborted) return;
        schema = data;
        for (const [name, draft] of Object.entries(drafts)) {
          if (!hasChanges(draft)) draft.layout = data.layouts[name];
          draft.saved = data.layouts[name];
          const visible = draft.layout ?? data.defaults[name];
          draft.selection = Math.min(draft.selection, visible.length - 1);
        }
        preview.width = data.width;
        preview.height = data.height;
        stage.style.aspectRatio = data.width + ' / ' + data.height;
        element('editor-resolution').textContent = data.width + ' × ' + data.height + ' px';
      }
      setupCode = code;
      for (const draft of Object.values(drafts)) {
        if (draft.message === badCode) draft.message = '';
      }
      unlock.reset();
      unlock.hidden = true;
      content.hidden = false;
      setText(accessStatus, '');
      showScreen();
      if (focusTab) tabs.find(tab => tab.dataset.screen === screen).focus();
    } catch (error) {
      if (controller.signal.aborted) return;
      askForCode(error instanceof TypeError ? 'The Pi did not respond.' : error.message);
    } finally {
      if (loadController === controller) unlockButton.disabled = false;
    }
  }

  function setDraft(layout, structureChanged = false) {
    const draft = current();
    draft.layout = layout;
    draft.message = '';
    if (structureChanged) {
      renderWidgets();
    } else {
      position(hitboxes[draft.selection], layout[draft.selection]);
      updateInspector();
    }
    updateStatus();
    schedulePreview();
  }

  function editWidget(change) {
    const index = current().selection;
    const layout = widgets().slice();
    const widget = layout[index];
    if (!widget || Object.entries(change).every(([name, value]) => widget[name] === value)) return;
    layout[index] = {...widget, ...change};
    setDraft(layout);
  }

  function moveWidget(dx, dy, origin = widgets()[current().selection]) {
    const {x, y, w, h} = origin;
    editWidget({
      x: clamp(x + dx, 0, schema.width - w),
      y: clamp(y + dy, 0, schema.height - h),
    });
  }

  function reorder(direction) {
    const layout = widgets().slice();
    const index = current().selection;
    const target = index + direction;
    if (index < 0 || target < 0 || target >= layout.length) return;
    [layout[index], layout[target]] = [layout[target], layout[index]];
    current().selection = target;
    setDraft(layout, true);
    if (document.activeElement === document.body) widgetButtons[target].focus();
  }

  openButton.addEventListener('click', () => {
    dialog.showModal();
    content.hidden = true;
    unlock.hidden = true;
    if (setupCode) {
      loadLayouts(setupCode, false);
    } else {
      askForCode('');
    }
  });

  dialog.addEventListener('close', () => {
    loadController?.abort();
    loadController = undefined;
    unlock.querySelector('button').disabled = false;
    unlock.reset();
    drag = undefined;
    stopPreview();
    clearPreview();
    openButton.focus();
  });

  unlock.addEventListener('submit', (event) => {
    event.preventDefault();
    const code = codeField.value.trim();
    if (code) loadLayouts(code, true);
    else setText(accessStatus, badCode);
  });

  for (const [index, tab] of tabs.entries()) {
    tab.addEventListener('click', () => {
      if (tab.dataset.screen === screen) return;
      screen = tab.dataset.screen;
      showScreen();
    });
    tab.addEventListener('keydown', (event) => {
      const indices = {ArrowLeft: index - 1, ArrowRight: index + 1, Home: 0, End: tabs.length - 1};
      const next = indices[event.key];
      if (!Number.isInteger(next)) return;
      event.preventDefault();
      const target = tabs[(next + tabs.length) % tabs.length];
      target.click();
      target.focus();
    });
  }

  stage.addEventListener('click', (event) => {
    selectWidget(event.target === stage ? -1 : Number(event.target.dataset.index));
  });
  stage.addEventListener('pointerdown', (event) => {
    const hitbox = event.target.closest('.editor-hitbox');
    if (!hitbox || drag || event.button !== 0) return;
    event.preventDefault();
    hitbox.focus({preventScroll: true});
    selectWidget(Number(hitbox.dataset.index));
    const {width, height} = stage.getBoundingClientRect();
    drag = {
      id: event.pointerId, startX: event.clientX, startY: event.clientY,
      width, height, origin: widgets()[current().selection],
    };
    hitbox.setPointerCapture(event.pointerId);
  });
  stage.addEventListener('pointermove', (event) => {
    if (drag?.id !== event.pointerId) return;
    moveWidget(
      Math.round((event.clientX - drag.startX) / drag.width * schema.width),
      Math.round((event.clientY - drag.startY) / drag.height * schema.height),
      drag.origin,
    );
  });
  for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    stage.addEventListener(event, ({pointerId}) => {
      if (drag?.id === pointerId) drag = undefined;
    });
  }
  stage.addEventListener('keydown', (event) => {
    const hitbox = event.target.closest('.editor-hitbox');
    const offset = arrows[event.key];
    if (!hitbox || !Array.isArray(offset)) return;
    event.preventDefault();
    selectWidget(Number(hitbox.dataset.index));
    const step = event.shiftKey ? 10 : 1;
    moveWidget(offset[0] * step, offset[1] * step);
  });

  widgetList.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-index]');
    if (button) selectWidget(Number(button.dataset.index));
  });

  add.addEventListener('click', () => {
    const item = definition(addType.value);
    if (!item || add.disabled) return;
    const widget = {...item.template};
    if (widget.type === 'text') widget.text = translate(widget.text);
    const layout = [...widgets(), widget];
    current().selection = layout.length - 1;
    setDraft(layout, true);
    widgetButtons.at(-1).focus({preventScroll: true});
    widgetButtons.at(-1).scrollIntoView({block: 'nearest'});
  });

  moveUp.addEventListener('click', () => reorder(-1));
  moveDown.addEventListener('click', () => reorder(1));
  remove.addEventListener('click', () => {
    const layout = widgets().filter((_, index) => index !== current().selection);
    current().selection = Math.min(current().selection, layout.length - 1);
    setDraft(layout, true);
    (widgetButtons[current().selection] ?? addType).focus();
  });

  properties.addEventListener('change', (event) => {
    const field = event.target;
    const name = field.dataset.property;
    if (!name || name === 'text') return;
    if (field.type === 'number') {
      if (!Number.isFinite(field.valueAsNumber)) {
        updateInspector();
        return;
      }
      const value = clamp(Math.round(field.valueAsNumber), Number(field.min), Number(field.max));
      field.value = value;
      editWidget({[name]: value});
    } else {
      editWidget({[name]: field.value});
    }
  });
  for (const event of ['input', 'compositionend']) {
    fields.text.addEventListener(event, ({isComposing}) => {
      if (isComposing) return;
      const text = [...fields.text.value].slice(0, 120).join('');
      if (fields.text.value !== text) fields.text.value = text;
      editWidget({text});
    });
  }

  reset.addEventListener('click', () => {
    current().selection = -1;
    setDraft(null, true);
    (save.disabled ? closeButton : save).focus();
  });

  retry.addEventListener('click', () => schedulePreview(0));

  save.addEventListener('click', async () => {
    const draft = current();
    if (!hasChanges(draft) || savingScreen) return;
    const payload = {screen, layout: draft.layout};
    const code = setupCode;
    savingScreen = screen;
    draft.message = 'Saving layout…';
    updateStatus();
    try {
      const response = await request('/api/layouts', {code, payload, fallback: 'Could not save the layout.'});
      const data = await response.json();
      if (draft.layout === payload.layout) draft.layout = data.layout;
      draft.saved = data.layout;
      draft.message = 'Layout saved. The display will refresh shortly.';
    } catch (error) {
      draft.message = error instanceof TypeError ? 'The Pi did not respond.' : error.message;
      if (dialog.open && code === setupCode && draft.message === badCode) askForCode(draft.message);
    } finally {
      savingScreen = undefined;
      updateStatus();
    }
  });

  new MutationObserver(() => {
    if (!schema || content.hidden) return;
    delete fields.variant.dataset.type;
    for (const [index, widget] of widgets().entries()) {
      hitboxes[index].setAttribute('aria-label', widgetLabel(widget, index));
      widgetButtons[index].firstElementChild.textContent = translate(definition(widget.type).label);
    }
    renderAddOptions();
    updateInspector();
    updateStatus();
    schedulePreview();
  }).observe(document.documentElement, {attributes: true, attributeFilter: ['lang']});
}
