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
  const frame = preview.getContext('2d');
  const drawing = element('editor-drawing');
  const ink = drawing.getContext('2d');
  const selection = element('editor-selection');
  const dropMarker = element('editor-drop-marker');
  const previewStatus = element('editor-preview-status');
  const retry = element('editor-preview-retry');
  const widgetList = element('editor-widgets');
  const palette = element('editor-palette');
  const tools = element('editor-tools');
  const brushOptions = element('editor-brush-options');
  const brush = element('editor-brush');
  const clearDrawing = element('editor-clear-drawing');
  const undo = element('editor-undo');
  const redo = element('editor-redo');
  const blank = element('editor-blank');
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
    tab.dataset.screen, {saved: null, layout: null, selection: -1, message: '', undo: [], redo: []},
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
  let paletteDrag;
  let tool = 'select';
  let loadController;
  let previewController;
  let previewTimer;
  let atlas;
  let tiles = new Map();
  let savingScreen;

  const current = () => drafts[screen];
  const widgets = (layout = current().layout) => (layout ?? schema.defaults[screen])
    .filter(widget => widget.type !== 'drawing');
  const bitmap = () => current().layout?.at(-1)?.bitmap;
  const definitions = () => schema.widgets[screen];
  const definition = (type) => definitions().find(widget => widget.type === type);
  const hasChanges = ({saved, layout}) => JSON.stringify(saved) !== JSON.stringify(layout);
  const clamp = (value, min, max) => Math.max(min, Math.min(value, max));
  const stride = () => Math.ceil(schema.width / 8);
  const layerKey = ({x, y, ...appearance}) => JSON.stringify(appearance);
  const withDrawing = (layout) => bitmap() ? [...layout, {type: 'drawing', bitmap: bitmap()}] : layout;

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
    blank.disabled = current().layout?.length === 0;
    clearDrawing.disabled = !bitmap();
    undo.disabled = current().undo.length === 0;
    redo.disabled = current().redo.length === 0;
    save.disabled = Boolean(savingScreen) || !hasChanges(current());
    setText(saveStatus, current().message);
  }

  function widgetLabel(widget, index) {
    return translate(definition(widget.type).label) + ' ' + (index + 1);
  }

  function renderPalette() {
    palette.replaceChildren(...definitions().map(item => {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.widget = item.type;
      button.textContent = translate(item.label);
      return button;
    }));
    updatePalette();
  }

  function updatePalette() {
    const full = widgets().length >= schema.maxWidgets;
    for (const button of palette.children) button.disabled = full;
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
      hitbox.tabIndex = tool === 'select' ? 0 : -1;
      widgetButtons[index].setAttribute('aria-pressed', selected);
    }
    const widget = widgets()[current().selection];
    selection.hidden = !widget || tool !== 'select';
    if (widget) position(selection, widget);
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
    updatePalette();
    updateSelection();
  }

  function selectWidget(index) {
    current().selection = index;
    updateSelection();
  }

  function clearPreview() {
    atlas?.close();
    atlas = undefined;
    tiles.clear();
    frame.clearRect(0, 0, preview.width, preview.height);
  }

  function compose() {
    if (!atlas) return;
    frame.imageSmoothingEnabled = false;
    frame.drawImage(atlas, 0, 0, 1, 1, 0, 0, schema.width, schema.height);
    for (const [index, widget] of widgets().entries()) {
      const fallback = drag?.index === index && drag.origin ? tiles.get(layerKey(drag.origin)) : undefined;
      const tile = tiles.get(layerKey(widget)) ?? fallback;
      if (tile) {
        frame.drawImage(atlas, 0, tile.y, tile.w, tile.h, widget.x, widget.y, widget.w, widget.h);
      }
    }
  }

  function drawingBytes() {
    const saved = bitmap();
    return saved
      ? Uint8Array.from(atob(saved), character => character.charCodeAt(0))
      : new Uint8Array(stride() * schema.height);
  }

  function showInk(bytes = drawingBytes()) {
    const {width, height} = schema;
    const color = document.documentElement.dataset.theme === 'dark' ? 255 : 0;
    const image = ink.createImageData(width, height);
    const rowBytes = stride();
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        if (!(bytes[y * rowBytes + (x >> 3)] & (128 >> (x & 7)))) continue;
        const offset = (y * width + x) * 4;
        image.data.fill(color, offset, offset + 3);
        image.data[offset + 3] = 255;
      }
    }
    ink.putImageData(image, 0, 0);
  }

  function storeInk(bytes) {
    const layout = widgets();
    if (bytes.some(Boolean)) layout.push({type: 'drawing', bitmap: btoa(String.fromCharCode(...bytes))});
    if (bitmap() || layout.at(-1)?.type === 'drawing') setDraft(layout);
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
    const payload = {screen, layout: widgets(), layers: true};
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
        const image = await createImageBitmap(blob);
        if (controller.signal.aborted || previewController !== controller) {
          image.close();
          return;
        }
        atlas?.close();
        atlas = image;
        tiles = new Map(payload.layout.map((widget, index) => [layerKey(widget), {
          y: 1 + index * schema.height, w: widget.w, h: widget.h,
        }]));
        compose();
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
    paletteDrag = undefined;
    dropMarker.hidden = true;
    for (const tab of tabs) {
      const active = tab.dataset.screen === screen;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      if (active) panel.setAttribute('aria-labelledby', tab.id);
    }
    clearPreview();
    renderPalette();
    renderWidgets();
    showInk();
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
          if (!hasChanges(draft) && JSON.stringify(draft.saved) !== JSON.stringify(data.layouts[name])) {
            draft.layout = data.layouts[name];
            draft.undo = [];
            draft.redo = [];
          }
          draft.saved = data.layouts[name];
          const visible = (draft.layout ?? data.defaults[name]).filter(widget => widget.type !== 'drawing');
          draft.selection = Math.min(draft.selection, visible.length - 1);
        }
        for (const canvas of [preview, drawing]) {
          canvas.width = data.width;
          canvas.height = data.height;
        }
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

  function recordHistory(previous) {
    const {undo, redo, layout} = current();
    if (JSON.stringify(previous) === JSON.stringify(layout)) return;
    undo.push(previous);
    if (undo.length > 40) undo.shift();
    redo.length = 0;
  }

  function refreshPreview() {
    if (!atlas || widgets().some(widget => !tiles.has(layerKey(widget)))) schedulePreview(80);
  }

  function setDraft(layout, structureChanged = false, remember = true) {
    const draft = current();
    const previous = draft.layout;
    const previousBitmap = bitmap();
    draft.layout = layout;
    if (remember) recordHistory(previous);
    draft.message = '';
    if (structureChanged) {
      renderWidgets();
    } else {
      const widget = widgets()[draft.selection];
      if (widget) position(hitboxes[draft.selection], widget);
      updateSelection();
    }
    if (bitmap() !== previousBitmap) showInk();
    compose();
    updateStatus();
    if (!drag) refreshPreview();
  }

  function editWidget(change, remember = true) {
    const index = current().selection;
    const layout = widgets().slice();
    const widget = layout[index];
    if (!widget || Object.entries(change).every(([name, value]) => widget[name] === value)) return;
    layout[index] = {...widget, ...change};
    setDraft(withDrawing(layout), false, remember);
  }

  function moveWidget(dx, dy, origin = widgets()[current().selection]) {
    const {x, y, w, h} = origin;
    editWidget({
      x: clamp(x + dx, 0, schema.width - w),
      y: clamp(y + dy, 0, schema.height - h),
    }, !drag);
  }

  function resizeWidget(dx, dy, {origin, corner}) {
    const {x, y, w, h} = origin;
    const [right, bottom] = [x + w, y + h];
    const left = corner.includes('w') ? clamp(x + dx, 0, right - 1) : x;
    const top = corner.includes('n') ? clamp(y + dy, 0, bottom - 1) : y;
    editWidget({
      x: left, y: top,
      w: (corner.includes('e') ? clamp(right + dx, x + 1, schema.width) : right) - left,
      h: (corner.includes('s') ? clamp(bottom + dy, y + 1, schema.height) : bottom) - top,
    }, false);
  }

  function setTool(value) {
    tool = value;
    stage.dataset.tool = value;
    brushOptions.hidden = value === 'select';
    for (const button of tools.children) {
      button.setAttribute('aria-pressed', String(button.dataset.tool === value));
    }
    setText(element('editor-move-help'), value === 'select'
      ? 'Drag widgets onto the canvas. Drag their corners to resize them.'
      : 'Draw directly on the screen. The eraser only removes your strokes.');
    updateSelection();
  }

  function stepHistory(from, to) {
    const draft = current();
    if (drag || paletteDrag || !draft[from].length) return;
    draft[to].push(draft.layout);
    const next = draft[from].pop();
    draft.selection = Math.min(draft.selection, widgets(next).length - 1);
    setDraft(next, true, false);
  }

  function canvasPoint(event) {
    const {left, top, width, height} = stage.getBoundingClientRect();
    return {
      x: (event.clientX - left) / width * schema.width,
      y: (event.clientY - top) / height * schema.height,
    };
  }

  function brushPoint(event) {
    const {x, y} = canvasPoint(event);
    return [clamp(Math.floor(x), 0, schema.width - 1), clamp(Math.floor(y), 0, schema.height - 1)];
  }

  function strokeTo(point) {
    const {bytes, radius, erase} = drag;
    let [x, y] = drag.point;
    const [endX, endY] = point;
    const dx = Math.abs(endX - x);
    const dy = -Math.abs(endY - y);
    const stepX = Math.sign(endX - x);
    const stepY = Math.sign(endY - y);
    const rowBytes = stride();
    let error = dx + dy;
    // Stamp a round brush along an integer line so rapid motions have no gaps.
    for (;;) {
      for (let py = Math.max(0, y - radius); py <= Math.min(schema.height - 1, y + radius); py++) {
        for (let px = Math.max(0, x - radius); px <= Math.min(schema.width - 1, x + radius); px++) {
          if ((px - x) ** 2 + (py - y) ** 2 > (radius + .35) ** 2) continue;
          const index = py * rowBytes + (px >> 3);
          const bit = 128 >> (px & 7);
          bytes[index] = erase ? bytes[index] & ~bit : bytes[index] | bit;
        }
      }
      if (x === endX && y === endY) break;
      const step = 2 * error;
      if (step >= dy) {
        error += dy;
        x += stepX;
      }
      if (step <= dx) {
        error += dx;
        y += stepY;
      }
    }
    drag.point = point;
    showInk(bytes);
  }

  function widgetAt(item, point) {
    const {w, h} = item.template;
    return {
      x: clamp(Math.round(point.x - w / 2), 0, schema.width - w),
      y: clamp(Math.round(point.y - h / 2), 0, schema.height - h),
      w, h,
    };
  }

  function insideCanvas({x, y}) {
    return x >= 0 && y >= 0 && x < schema.width && y < schema.height;
  }

  function addWidget(item, point) {
    if (widgets().length >= schema.maxWidgets) return;
    const widget = {...item.template, ...(point && widgetAt(item, point))};
    if (widget.type === 'text') widget.text = translate(widget.text);
    const layout = [...widgets(), widget];
    current().selection = layout.length - 1;
    setTool('select');
    setDraft(withDrawing(layout), true);
    hitboxes.at(-1).focus({preventScroll: true});
  }

  function reorder(direction) {
    const layout = widgets().slice();
    const index = current().selection;
    const target = index + direction;
    if (index < 0 || target < 0 || target >= layout.length) return;
    [layout[index], layout[target]] = [layout[target], layout[index]];
    current().selection = target;
    setDraft(withDrawing(layout), true);
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
    paletteDrag = undefined;
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
    const hitbox = event.target.closest('.editor-hitbox');
    if (event.detail === 0 && hitbox) selectWidget(Number(hitbox.dataset.index));
  });
  stage.addEventListener('pointerdown', (event) => {
    if (drag || paletteDrag || event.button !== 0) return;
    if (tool !== 'select') {
      event.preventDefault();
      const point = brushPoint(event);
      drag = {
        id: event.pointerId, point, bytes: drawingBytes(), radius: Number(brush.value) >> 1,
        erase: tool === 'erase',
      };
      stage.setPointerCapture(event.pointerId);
      strokeTo(point);
      return;
    }
    const corner = event.target.dataset.corner;
    const hitbox = event.target.closest('.editor-hitbox');
    if (!hitbox && !corner) {
      selectWidget(-1);
      return;
    }
    event.preventDefault();
    const index = hitbox ? Number(hitbox.dataset.index) : current().selection;
    hitboxes[index].focus({preventScroll: true});
    selectWidget(index);
    drag = {
      id: event.pointerId, point: canvasPoint(event), index, corner, origin: widgets()[index],
      before: current().layout,
    };
    stage.setPointerCapture(event.pointerId);
  });
  stage.addEventListener('pointermove', (event) => {
    if (drag?.id !== event.pointerId) return;
    if (drag.bytes) {
      strokeTo(brushPoint(event));
      return;
    }
    const point = canvasPoint(event);
    const dx = Math.round(point.x - drag.point.x);
    const dy = Math.round(point.y - drag.point.y);
    if (drag.corner) resizeWidget(dx, dy, drag);
    else moveWidget(dx, dy, drag.origin);
  });
  for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    stage.addEventListener(event, ({pointerId, type}) => {
      if (drag?.id !== pointerId) return;
      const {bytes, before} = drag;
      drag = undefined;
      if (bytes) {
        if (type === 'pointerup') storeInk(bytes);
        else showInk();
      } else {
        recordHistory(before);
        updateStatus();
        refreshPreview();
      }
    });
  }
  stage.addEventListener('keydown', (event) => {
    const hitbox = event.target.closest('.editor-hitbox');
    const offset = arrows[event.key];
    if (drag || tool !== 'select' || !hitbox || !Array.isArray(offset)) return;
    event.preventDefault();
    selectWidget(Number(hitbox.dataset.index));
    const step = event.shiftKey ? 10 : 1;
    moveWidget(offset[0] * step, offset[1] * step);
  });

  widgetList.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-index]');
    if (button && !drag) {
      setTool('select');
      selectWidget(Number(button.dataset.index));
    }
  });

  palette.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-widget]');
    if (event.detail === 0 && button && !drag) addWidget(definition(button.dataset.widget));
  });
  palette.addEventListener('pointerdown', (event) => {
    const button = event.target.closest('button[data-widget]');
    if (!button || button.disabled || drag || paletteDrag || event.button !== 0) return;
    event.preventDefault();
    button.focus({preventScroll: true});
    button.setPointerCapture(event.pointerId);
    paletteDrag = {id: event.pointerId, item: definition(button.dataset.widget), button};
  });
  palette.addEventListener('pointermove', (event) => {
    if (paletteDrag?.id !== event.pointerId) return;
    const point = canvasPoint(event);
    dropMarker.hidden = !insideCanvas(point);
    if (!dropMarker.hidden) position(dropMarker, widgetAt(paletteDrag.item, point));
  });
  for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    palette.addEventListener(event, (event) => {
      if (paletteDrag?.id !== event.pointerId) return;
      const {item, button} = paletteDrag;
      paletteDrag = undefined;
      dropMarker.hidden = true;
      if (event.type !== 'pointerup') return;
      const point = canvasPoint(event);
      if (insideCanvas(point)) addWidget(item, point);
      else if (button.contains(document.elementFromPoint(event.clientX, event.clientY))) addWidget(item);
    });
  }

  tools.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-tool]');
    if (button && !drag) setTool(button.dataset.tool);
  });
  undo.addEventListener('click', () => stepHistory('undo', 'redo'));
  redo.addEventListener('click', () => stepHistory('redo', 'undo'));
  clearDrawing.addEventListener('click', () => {
    if (!drag) setDraft(widgets());
  });
  dialog.addEventListener('keydown', (event) => {
    if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'z' ||
        content.hidden || event.target.matches('input, textarea, select')) return;
    event.preventDefault();
    if (event.shiftKey) stepHistory('redo', 'undo');
    else stepHistory('undo', 'redo');
  });

  moveUp.addEventListener('click', () => reorder(-1));
  moveDown.addEventListener('click', () => reorder(1));
  remove.addEventListener('click', () => {
    const layout = widgets().filter((_, index) => index !== current().selection);
    current().selection = Math.min(current().selection, layout.length - 1);
    setDraft(withDrawing(layout), true);
    (widgetButtons[current().selection] ?? palette.firstElementChild).focus();
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
  blank.addEventListener('click', () => {
    current().selection = -1;
    setDraft([], true);
    save.focus();
  });

  retry.addEventListener('click', () => schedulePreview(0));

  save.addEventListener('click', async () => {
    const draft = current();
    if (!hasChanges(draft) || savingScreen || drag || paletteDrag) return;
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

  new MutationObserver(records => {
    if (!schema || content.hidden) return;
    const root = document.documentElement;
    if (records.some(record => record.attributeName === 'lang')) {
      delete fields.variant.dataset.type;
      for (const [index, widget] of widgets().entries()) {
        hitboxes[index].setAttribute('aria-label', widgetLabel(widget, index));
        widgetButtons[index].firstElementChild.textContent = translate(definition(widget.type).label);
      }
      renderPalette();
      updateInspector();
      updateStatus();
    } else if (!records.some(record => record.oldValue !== root.getAttribute('data-theme'))) {
      return;
    }
    showInk(drag?.bytes);
    schedulePreview();
  }).observe(document.documentElement, {attributeOldValue: true, attributeFilter: ['lang', 'data-theme']});
}
