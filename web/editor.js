{
  const element = (id) => document.getElementById(id);
  const editor = element('layout-editor');
  const back = element('editor-back');
  const unlock = element('editor-unlock');
  const codeField = element('editor-code');
  const accessStatus = element('editor-access-status');
  const content = element('editor-content');
  const panel = element('editor-panel');
  const tabs = [...editor.querySelectorAll('[role=tab]')];
  const stage = element('editor-stage');
  const preview = element('editor-image');
  const frame = preview.getContext('2d');
  const drawing = document.createElement('canvas');
  const ink = drawing.getContext('2d');
  const selection = element('editor-selection');
  const dropMarker = element('editor-drop-marker');
  const guides = {x: element('editor-guide-x'), y: element('editor-guide-y')};
  const magnet = element('editor-snap');
  const inlineText = element('editor-inline-text');
  const previewStatus = element('editor-preview-status');
  const retry = element('editor-preview-retry');
  const widgetList = element('editor-widgets');
  const palette = element('editor-palette');
  const tools = element('editor-tools');
  const brush = element('editor-brush');
  const clearDrawing = element('editor-clear-drawing');
  const drawingProperties = element('editor-drawing-properties');
  const undo = element('editor-undo');
  const redo = element('editor-redo');
  const blank = element('editor-blank');
  const properties = element('editor-properties');
  const fields = Object.fromEntries(
    [...properties.querySelectorAll('[data-property]')].map(field => [field.dataset.property, field]),
  );
  const scaleField = element('editor-scale');
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
  const icons = {
    clock: 'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0ZM12 6v6l4 2',
    date: 'M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2ZM7 3v4m10-4v4M3 10h18M8 15h2m4 0h2',
    weather: 'M7 19a4 4 0 1 1 .4-8 5 5 0 0 1 9.6-1.4 4.7 4.7 0 1 1 .3 9.4Z',
    text: 'M4 7V4h16v3M12 4v16m-4 0h8',
    divider: 'M3 12h18M8 5h8M8 19h8',
    title: 'M3 7h10m-10 5h6m-6 5h6m5-9v10a3 3 0 1 1-3-3h3m0-7 7-3v4l-7 3',
    artist: 'M16 8a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-2a8 5 0 0 1 16 0v2Z',
    cover: 'M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2ZM3 17l6-6 4 4 3-3 5 5M16 8h.01',
    progress: 'M3 9h18v6H3Zm0 3h11',
    'playback-time': 'M4 4h16v16H4Zm5 5 6 3-6 3Z',
    drawing: 'm4 15 10-10 4 4L8 19l-5 1 1-5Zm10-10 2-2a1.5 1.5 0 0 1 2 0l3 3a1.5 1.5 0 0 1 0 2l-2 2M13 21h8',
    grip: 'M8 5h.01m8 0h.01M8 12h.01m8 0h.01M8 19h.01m8 0h.01',
  };
  const badCode = 'Check the device setup code.';

  let schema;
  let setupCode = '';
  let screen = 'dashboard';
  let hitboxes = [];
  let widgetButtons = [];
  let drag;
  let paletteDrag;
  let layerDrag;
  let inkBounds;
  let textEditing;
  let tool = 'select';
  let loadController;
  let previewController;
  let previewTimer;
  let atlas;
  let tiles = new Map();
  let savingScreen;

  const current = () => drafts[screen];
  const layers = (layout = current().layout) => layout ?? schema.defaults[screen];
  const widgets = () => layers().filter(layer => layer.type !== 'drawing');
  const bitmap = () => layers().find(layer => layer.type === 'drawing')?.bitmap;
  const definitions = () => schema.widgets[screen];
  const definition = (type) => definitions().find(widget => widget.type === type);
  const hasChanges = ({saved, layout}) => JSON.stringify(saved) !== JSON.stringify(layout);
  const clamp = (value, min, max) => Math.max(min, Math.min(value, max));
  const stride = () => Math.ceil(schema.width / 8);
  const layerKey = ({x, y, ...appearance}) => JSON.stringify(appearance);

  function icon(type) {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', icons[type]);
    svg.append(path);
    return svg;
  }

  function boundsOf(layer) {
    if (layer?.type !== 'drawing') return layer;
    if (!inkBounds) return null;
    return {...inkBounds, x: inkBounds.x + (drag?.inkOffset?.x ?? 0),
      y: inkBounds.y + (drag?.inkOffset?.y ?? 0)};
  }

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

  function layerName(layer) {
    return translate(layer.type === 'drawing' ? 'Drawing' : definition(layer.type).label);
  }

  function widgetLabel(widget, index) {
    return layerName(widget) + ' ' + (layers().length - index);
  }

  function renderPalette() {
    palette.replaceChildren(...definitions().map(item => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'editor-icon';
      button.dataset.widget = item.type;
      button.setAttribute('aria-label', translate(item.label));
      button.append(icon(item.type));
      return button;
    }));
    updatePalette();
  }

  function updatePalette() {
    const full = widgets().length >= schema.maxWidgets;
    for (const button of palette.children) button.disabled = full;
  }

  function updateInspector() {
    const widget = layers()[current().selection];
    const isDrawing = widget?.type === 'drawing';
    properties.hidden = !widget || isDrawing;
    drawingProperties.hidden = !isDrawing;
    element('editor-no-selection').hidden = Boolean(widget);
    if (!widget || isDrawing) return;

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
    const size = Math.max(widget.w, widget.h);
    scaleField.max = Math.floor(Math.min(
      (schema.width - widget.x) * size / widget.w,
      (schema.height - widget.y) * size / widget.h,
    ));
    scaleField.value = size;
  }

  function updateSelection() {
    for (const [index, button] of widgetButtons.entries()) {
      const selected = String(index === current().selection);
      hitboxes[index]?.setAttribute('aria-pressed', selected);
      if (hitboxes[index]) hitboxes[index].tabIndex = tool === 'select' ? 0 : -1;
      button.setAttribute('aria-pressed', selected);
    }
    const layer = layers()[current().selection];
    const bounds = boundsOf(layer);
    selection.hidden = !bounds || tool !== 'select';
    selection.dataset.kind = layer?.type === 'drawing' ? 'drawing' : 'widget';
    if (bounds) position(selection, bounds);
    updateInspector();
  }

  function position(hitbox, {x, y, w, h}) {
    hitbox.style.left = (x / schema.width * 100) + '%';
    hitbox.style.top = (y / schema.height * 100) + '%';
    hitbox.style.width = (w / schema.width * 100) + '%';
    hitbox.style.height = (h / schema.height * 100) + '%';
  }

  function renderWidgets() {
    for (const hitbox of hitboxes) hitbox?.remove();
    hitboxes = [];
    widgetButtons = [];
    const list = document.createDocumentFragment();
    for (const [index, widget] of layers().entries()) {
      const label = widgetLabel(widget, index);
      let hitbox;
      const bounds = boundsOf(widget);
      if (bounds) {
        hitbox = document.createElement('button');
        hitbox.type = 'button';
        hitbox.className = 'editor-hitbox';
        hitbox.dataset.index = index;
        hitbox.setAttribute('aria-label', label);
        position(hitbox, bounds);
        stage.append(hitbox);
      }
      hitboxes.push(hitbox);

      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.index = index;
      button.setAttribute('aria-label', label);
      const name = document.createElement('span');
      name.textContent = layerName(widget);
      const grip = icon('grip');
      grip.classList.add('editor-grip');
      button.append(icon(widget.type), name, grip);
      const row = document.createElement('li');
      row.append(button);
      list.prepend(row);
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
    for (const [index, widget] of layers().entries()) {
      if (widget.type === 'drawing') {
        frame.drawImage(drawing, drag?.inkOffset?.x ?? 0, drag?.inkOffset?.y ?? 0);
        continue;
      }
      const fallback = drag?.index === index && drag.origin ? tiles.get(layerKey(drag.origin)) : undefined;
      const tile = tiles.get(layerKey(widget)) ?? fallback;
      if (tile) {
        frame.drawImage(atlas, 0, tile.y, tile.w, tile.h, widget.x, widget.y, widget.w, widget.h);
      }
    }
    if (!bitmap() && drag?.bytes) frame.drawImage(drawing, 0, 0);
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
    let left = width, top = height, right = -1, bottom = -1;
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        if (!(bytes[y * rowBytes + (x >> 3)] & (128 >> (x & 7)))) continue;
        left = Math.min(left, x);
        right = Math.max(right, x);
        top = Math.min(top, y);
        bottom = y;
        const offset = (y * width + x) * 4;
        image.data.fill(color, offset, offset + 3);
        image.data[offset + 3] = 255;
      }
    }
    inkBounds = right < 0 ? null : {x: left, y: top, w: right - left + 1, h: bottom - top + 1};
    ink.putImageData(image, 0, 0);
  }

  function storeInk(bytes) {
    const layout = layers().slice();
    const index = layout.findIndex(layer => layer.type === 'drawing');
    if (bytes.some(Boolean)) {
      const next = btoa(String.fromCharCode(...bytes));
      if (next === bitmap()) return;
      const layer = {type: 'drawing', bitmap: next};
      if (index < 0) layout.push(layer);
      else layout[index] = layer;
      setDraft(layout, index < 0 || !hitboxes[index]);
    } else if (index >= 0) {
      removeLayer(index);
    }
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
    finishText(false);
    drag = undefined;
    paletteDrag = undefined;
    cancelLayerDrag();
    showGuides();
    dropMarker.hidden = true;
    for (const tab of tabs) {
      const active = tab.dataset.screen === screen;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      if (active) panel.setAttribute('aria-labelledby', tab.id);
    }
    clearPreview();
    renderPalette();
    showInk();
    renderWidgets();
    updateStatus();
    schedulePreview(0);
  }

  async function loadLayouts(code) {
    loadController?.abort();
    const controller = new AbortController();
    loadController = controller;
    const unlockButton = unlock.querySelector('button');
    unlockButton.disabled = true;
    setText(accessStatus, 'Loading layouts…');
    try {
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
        const visible = draft.layout ?? data.defaults[name];
        draft.selection = Math.min(draft.selection, visible.length - 1);
      }
      for (const canvas of [preview, drawing]) {
        canvas.width = data.width;
        canvas.height = data.height;
      }
      stage.style.aspectRatio = data.width + ' / ' + data.height;
      element('editor-resolution').textContent = data.width + ' × ' + data.height + ' px';
      setupCode = code;
      for (const draft of Object.values(drafts)) {
        if (draft.message === badCode) draft.message = '';
      }
      unlock.reset();
      unlock.hidden = true;
      content.hidden = false;
      setText(accessStatus, '');
      showScreen();
      tabs.find(tab => tab.dataset.screen === screen).focus();
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
    if (bitmap() !== previousBitmap) showInk();
    if (structureChanged) {
      renderWidgets();
    } else {
      for (const [index, layer] of layers().entries()) {
        const bounds = boundsOf(layer);
        if (bounds && hitboxes[index]) position(hitboxes[index], bounds);
      }
      updateSelection();
    }
    compose();
    updateStatus();
    if (!drag) refreshPreview();
  }

  function editWidget(change, remember = true) {
    const index = current().selection;
    const layout = layers().slice();
    const widget = layout[index];
    if (!widget || Object.entries(change).every(([name, value]) => widget[name] === value)) return;
    layout[index] = {...widget, ...change};
    setDraft(layout, false, remember);
  }

  function moveWidget(dx, dy, origin = boundsOf(layers()[current().selection]), snap = false) {
    const {x, y, w, h} = origin;
    const next = {
      x: clamp(x + dx, 0, schema.width - w),
      y: clamp(y + dy, 0, schema.height - h),
      w, h,
    };
    if (snap) snapPosition(next, current().selection);
    if (layers()[current().selection].type === 'drawing') {
      const offset = {x: next.x - x, y: next.y - y};
      if (drag) {
        drag.inkOffset = offset;
        position(hitboxes[current().selection], next);
        updateSelection();
        compose();
      } else {
        translateInk(offset);
      }
      return;
    }
    editWidget({x: next.x, y: next.y}, !drag);
  }

  function translateInk({x: dx, y: dy}) {
    if (dx === 0 && dy === 0) return;
    const source = drawingBytes();
    const destination = new Uint8Array(source.length);
    const rowBytes = stride();
    for (let y = inkBounds.y; y < inkBounds.y + inkBounds.h; y++) {
      for (let x = inkBounds.x; x < inkBounds.x + inkBounds.w; x++) {
        if (source[y * rowBytes + (x >> 3)] & (128 >> (x & 7))) {
          destination[(y + dy) * rowBytes + ((x + dx) >> 3)] |= 128 >> ((x + dx) & 7);
        }
      }
    }
    storeInk(destination);
  }

  function resizeWidget(dx, dy, {origin, corner}, free) {
    const {x, y, w, h} = origin;
    const [right, bottom] = [x + w, y + h];
    const west = corner.includes('w');
    const north = corner.includes('n');
    const anchorX = west ? right : x;
    const anchorY = north ? bottom : y;
    const signX = west ? -1 : 1;
    const signY = north ? -1 : 1;
    const maxW = west ? right : schema.width - x;
    const maxH = north ? bottom : schema.height - y;
    const rawW = w + signX * dx;
    const rawH = h + signY * dy;
    let width, height, guideX, guideY;
    const snapEdge = (axis, anchor, sign, span, min, max) => {
      const first = anchor + sign * min;
      const last = anchor + sign * max;
      const result = snapAxis(axis, anchor + sign * span, 0, Math.min(first, last),
        Math.max(first, last), current().selection);
      return {size: sign * (result.position - anchor), guide: result.guide};
    };
    if (free) {
      ({size: width, guide: guideX} = snapEdge('x', anchorX, signX, rawW, 1, maxW));
      ({size: height, guide: guideY} = snapEdge('y', anchorY, signY, rawH, 1, maxH));
    } else {
      const minScale = Math.max(1 / w, 1 / h);
      const maxScale = Math.min(maxW / w, maxH / h);
      let scale = clamp((rawW * w + rawH * h) / (w * w + h * h), minScale, maxScale);
      const movedX = snapEdge('x', anchorX, signX, Math.round(w * scale),
        Math.round(w * minScale), Math.round(w * maxScale));
      const movedY = snapEdge('y', anchorY, signY, Math.round(h * scale),
        Math.round(h * minScale), Math.round(h * maxScale));
      const distanceX = movedX.guide === undefined ? Infinity : Math.abs(movedX.size - w * scale);
      const distanceY = movedY.guide === undefined ? Infinity : Math.abs(movedY.size - h * scale);
      if (distanceX < Infinity && distanceX <= distanceY) {
        scale = clamp(movedX.size / w, minScale, maxScale);
        guideX = movedX.guide;
      } else if (distanceY < Infinity) {
        scale = clamp(movedY.size / h, minScale, maxScale);
        guideY = movedY.guide;
      }
      width = Math.round(w * scale);
      height = Math.round(h * scale);
    }
    showGuides(guideX, guideY);
    editWidget({
      x: west ? right - width : x, y: north ? bottom - height : y,
      w: width, h: height,
    }, false);
  }

  function setTool(value) {
    tool = value;
    stage.dataset.tool = value;
    for (const button of tools.querySelectorAll('[data-tool]')) {
      button.setAttribute('aria-pressed', String(button.dataset.tool === value));
    }
    updateSelection();
  }

  function stepHistory(from, to) {
    const draft = current();
    if (drag || paletteDrag || layerDrag || !draft[from].length) return;
    draft[to].push(draft.layout);
    const next = draft[from].pop();
    draft.selection = Math.min(draft.selection, layers(next).length - 1);
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
    compose();
  }

  function showGuides(x, y) {
    guides.x.hidden = x === undefined;
    guides.y.hidden = y === undefined;
    if (x !== undefined) guides.x.style.left = (x / schema.width * 100) + '%';
    if (y !== undefined) guides.y.style.top = (y / schema.height * 100) + '%';
  }

  function snapAxis(axis, raw, size, min, max, selected) {
    const position = clamp(raw, min, max);
    if (magnet.getAttribute('aria-pressed') !== 'true') return {position};
    const horizontal = axis === 'x';
    const dimension = horizontal ? schema.width : schema.height;
    const targets = [dimension / 2, 0, dimension];
    for (const [index, layer] of layers().entries()) {
      if (index === selected) continue;
      const bounds = boundsOf(layer);
      if (!bounds) continue;
      const start = bounds[axis];
      const span = horizontal ? bounds.w : bounds.h;
      targets.push(start, start + span, start + span / 2);
    }
    let best = {position};
    let distance = 3;
    for (const target of targets) {
      for (const anchor of size ? [size / 2, 0, size] : [0]) {
        const candidate = Math.round(target - anchor);
        const gap = Math.abs(candidate - position);
        if (gap > distance || (gap === distance && best.guide !== undefined) ||
            candidate < min || candidate > max) continue;
        distance = gap;
        best = {position: candidate, guide: target};
      }
    }
    return best;
  }

  function snapPosition(box, index) {
    const x = snapAxis('x', box.x, box.w, 0, schema.width - box.w, index);
    const y = snapAxis('y', box.y, box.h, 0, schema.height - box.h, index);
    box.x = x.position;
    box.y = y.position;
    showGuides(x.guide, y.guide);
    return box;
  }

  function widgetAt(item, point) {
    const {w, h} = item.template;
    return snapPosition({
      x: clamp(Math.round(point.x - w / 2), 0, schema.width - w),
      y: clamp(Math.round(point.y - h / 2), 0, schema.height - h),
      w, h,
    }, -1);
  }

  function insideCanvas({x, y}) {
    return x >= 0 && y >= 0 && x < schema.width && y < schema.height;
  }

  function addWidget(item, point) {
    if (widgets().length >= schema.maxWidgets) return;
    const widget = {...item.template, ...(point && widgetAt(item, point))};
    if (widget.type === 'text') widget.text = translate(widget.text);
    const layout = [...layers(), widget];
    current().selection = layout.length - 1;
    setTool('select');
    setDraft(layout, true);
    showGuides();
    hitboxes.at(-1).focus({preventScroll: true});
  }

  function reorder(index, target) {
    const layout = layers().slice();
    if (index < 0 || target < 0 || target >= layout.length || target === index) return;
    layout.splice(target, 0, layout.splice(index, 1)[0]);
    current().selection = target;
    setDraft(layout, true);
    widgetButtons[target].focus({preventScroll: true});
    widgetButtons[target].scrollIntoView({block: 'nearest'});
  }

  function removeLayer(index) {
    if (index < 0) return;
    const draft = current();
    const layout = layers().filter((_, position) => position !== index);
    if (draft.selection > index) draft.selection--;
    else if (draft.selection === index) draft.selection = Math.min(index, layout.length - 1);
    setDraft(layout, true);
  }

  function startText(index) {
    const widget = layers()[index];
    if (tool !== 'select' || widget?.type !== 'text' || textEditing) return;
    selectWidget(index);
    const {width, height} = stage.getBoundingClientRect();
    const w = Math.min(schema.width, Math.max(widget.w, 80 / width * schema.width));
    const h = Math.min(schema.height, Math.max(widget.h, 40 / height * schema.height));
    position(inlineText, {x: Math.min(widget.x, schema.width - w),
      y: Math.min(widget.y, schema.height - h), w, h});
    inlineText.style.fontSize = clamp(widget.size * width / schema.width, 16, 38) + 'px';
    inlineText.style.fontFamily = widget.font === 'mono' ? 'var(--mono)' : '';
    inlineText.style.fontWeight = widget.font === 'bold' ? '700' : '';
    inlineText.style.textAlign = widget.align;
    inlineText.value = widget.text;
    inlineText.hidden = false;
    textEditing = {index, screen};
    inlineText.focus({preventScroll: true});
    inlineText.select();
  }

  function finishText(apply, refocus = false) {
    if (!textEditing) return;
    const {index, screen: editedScreen} = textEditing;
    const text = [...inlineText.value].slice(0, 120).join('');
    textEditing = undefined;
    inlineText.hidden = true;
    if (editedScreen !== screen || current().selection !== index) return;
    if (apply) editWidget({text});
    if (refocus) hitboxes[index]?.focus({preventScroll: true});
  }

  function layerDropSlot(x, y) {
    const bounds = widgetList.getBoundingClientRect();
    if (x < bounds.left || x > bounds.right || y < bounds.top || y > bounds.bottom) return -1;
    const rows = [...widgetList.children];
    const slot = rows.findIndex(row => {
      const {top, height} = row.getBoundingClientRect();
      return y < top + height / 2;
    });
    return slot < 0 ? rows.length : slot;
  }

  function updateLayerDrop() {
    if (!layerDrag?.moved) return;
    const {x, y} = layerDrag;
    const slot = layerDropSlot(x, y);
    layerDrag.marker?.removeAttribute('data-drop');
    const rows = widgetList.children;
    layerDrag.marker = slot < 0 ? undefined : rows[Math.min(slot, rows.length - 1)];
    if (layerDrag.marker) layerDrag.marker.dataset.drop = slot === rows.length ? 'after' : 'before';
    const {top, bottom} = widgetList.getBoundingClientRect();
    if (slot >= 0) {
      const previous = widgetList.scrollTop;
      const direction = y < top + 22 ? -1 : y > bottom - 22 ? 1 : 0;
      widgetList.scrollTop += direction * 7;
      if (widgetList.scrollTop !== previous) layerDrag.frame = requestAnimationFrame(updateLayerDrop);
    }
  }

  function cancelLayerDrag() {
    if (!layerDrag) return;
    cancelAnimationFrame(layerDrag.frame);
    layerDrag.marker?.removeAttribute('data-drop');
    layerDrag.row.removeAttribute('data-dragging');
    layerDrag = undefined;
  }

  window.addEventListener('beforeunload', (event) => {
    if (!textEditing && !Object.values(drafts).some(hasChanges)) return;
    event.preventDefault();
    event.returnValue = '';
  });

  unlock.addEventListener('submit', (event) => {
    event.preventDefault();
    const code = codeField.value.trim();
    if (code) loadLayouts(code);
    else setText(accessStatus, badCode);
  });

  for (const [index, tab] of tabs.entries()) {
    tab.addEventListener('click', () => {
      if (tab.dataset.screen === screen) return;
      finishText(true);
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
  stage.addEventListener('dblclick', (event) => {
    const hitbox = event.target.closest('.editor-hitbox');
    if (hitbox) startText(Number(hitbox.dataset.index));
  });
  inlineText.addEventListener('blur', () => finishText(true));
  inlineText.addEventListener('keydown', (event) => {
    if (event.isComposing) return;
    const singleLine = layers()[current().selection]?.variant === 'single';
    if (event.key === 'Escape' || (event.key === 'Enter' && (singleLine || event.ctrlKey || event.metaKey))) {
      event.preventDefault();
      finishText(event.key !== 'Escape', true);
    }
  });
  stage.addEventListener('pointerdown', (event) => {
    if (drag || paletteDrag || layerDrag || event.button !== 0) return;
    if (event.target === inlineText) return;
    finishText(true);
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
      id: event.pointerId, point: canvasPoint(event), index, corner, origin: boundsOf(layers()[index]),
      before: current().layout,
    };
    (hitbox ?? stage).setPointerCapture(event.pointerId);
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
    if (drag.corner) {
      drag.delta = {dx, dy};
      resizeWidget(dx, dy, drag, event.shiftKey);
    }
    else moveWidget(dx, dy, drag.origin, true);
  });
  for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    stage.addEventListener(event, ({pointerId, type}) => {
      if (drag?.id !== pointerId) return;
      const {bytes, before, inkOffset} = drag;
      drag = undefined;
      showGuides();
      if (bytes) {
        if (type === 'pointerup') storeInk(bytes);
        else showInk();
        compose();
      } else if (inkOffset) {
        translateInk(inkOffset);
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
  widgetList.addEventListener('pointerdown', (event) => {
    const button = event.target.closest('button[data-index]');
    if (!button || drag || paletteDrag || layerDrag || event.button !== 0) return;
    if (event.pointerType === 'touch' && !event.target.closest('.editor-grip')) return;
    event.preventDefault();
    const index = Number(button.dataset.index);
    button.focus({preventScroll: true});
    setTool('select');
    selectWidget(index);
    button.setPointerCapture(event.pointerId);
    layerDrag = {id: event.pointerId, index, row: button.parentElement, startY: event.clientY};
  });
  widgetList.addEventListener('pointermove', (event) => {
    if (layerDrag?.id !== event.pointerId) return;
    const {clientX: x, clientY: y} = event;
    if (!layerDrag.moved && Math.abs(y - layerDrag.startY) < 5) return;
    Object.assign(layerDrag, {x, y, moved: true});
    layerDrag.row.dataset.dragging = '';
    cancelAnimationFrame(layerDrag.frame);
    updateLayerDrop();
  });
  for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    widgetList.addEventListener(name, (event) => {
      if (layerDrag?.id !== event.pointerId) return;
      const {index, moved} = layerDrag;
      const slot = layerDropSlot(event.clientX, event.clientY);
      cancelLayerDrag();
      if (!moved || slot < 0 || event.type !== 'pointerup') return;
      const count = layers().length;
      const originalRow = count - 1 - index;
      reorder(index, count - slot - Number(slot <= originalRow));
    });
  }
  widgetList.addEventListener('keydown', (event) => {
    if (!event.altKey || !['ArrowUp', 'ArrowDown'].includes(event.key)) return;
    const button = event.target.closest('button[data-index]');
    if (!button) return;
    event.preventDefault();
    const index = Number(button.dataset.index);
    reorder(index, index + (event.key === 'ArrowUp' ? 1 : -1));
  });
  widgetList.addEventListener('dblclick', (event) => {
    const button = event.target.closest('button[data-index]');
    if (button) startText(Number(button.dataset.index));
  });

  palette.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-widget]');
    if (event.detail === 0 && button && !drag) addWidget(definition(button.dataset.widget));
  });
  palette.addEventListener('pointerdown', (event) => {
    const button = event.target.closest('button[data-widget]');
    if (!button || button.disabled || drag || paletteDrag || layerDrag || event.button !== 0) return;
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
    else showGuides();
  });
  for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    palette.addEventListener(event, (event) => {
      if (paletteDrag?.id !== event.pointerId) return;
      const {item, button} = paletteDrag;
      paletteDrag = undefined;
      dropMarker.hidden = true;
      showGuides();
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
  magnet.addEventListener('click', () => {
    magnet.setAttribute('aria-pressed', String(magnet.getAttribute('aria-pressed') !== 'true'));
    showGuides();
  });
  undo.addEventListener('click', () => stepHistory('undo', 'redo'));
  redo.addEventListener('click', () => stepHistory('redo', 'undo'));
  for (const button of [clearDrawing, element('editor-remove-drawing')]) {
    button.addEventListener('click', () => {
      if (!drag) removeLayer(layers().findIndex(layer => layer.type === 'drawing'));
    });
  }
  for (const name of ['keydown', 'keyup']) {
    window.addEventListener(name, (event) => {
      if (event.key !== 'Shift' || !drag?.corner || !drag.delta) return;
      resizeWidget(drag.delta.dx, drag.delta.dy, drag, event.shiftKey);
    });
  }
  editor.addEventListener('keydown', (event) => {
    if (content.hidden || event.isComposing || event.target.matches('input, textarea, select')) return;
    const selected = current().selection;
    if ((event.key === 'Delete' || event.key === 'Backspace') &&
        selected >= 0 && !drag && !layerDrag && !paletteDrag) {
      event.preventDefault();
      removeLayer(selected);
      (widgetButtons[current().selection] ?? palette.firstElementChild).focus();
    } else if (['Enter', 'F2'].includes(event.key) && event.target.matches('button[data-index]') &&
        layers()[Number(event.target.dataset.index)]?.type === 'text') {
      event.preventDefault();
      startText(Number(event.target.dataset.index));
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
      event.preventDefault();
      if (event.shiftKey) stepHistory('redo', 'undo');
      else stepHistory('undo', 'redo');
    }
  });

  remove.addEventListener('click', () => {
    removeLayer(current().selection);
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
  scaleField.addEventListener('change', () => {
    const widget = layers()[current().selection];
    if (!widget || widget.type === 'drawing') return;
    if (!Number.isFinite(scaleField.valueAsNumber)) {
      updateInspector();
      return;
    }
    const size = clamp(Math.round(scaleField.valueAsNumber), 1, Number(scaleField.max));
    const ratio = size / Math.max(widget.w, widget.h);
    scaleField.value = size;
    const change = {w: Math.max(1, Math.round(widget.w * ratio)), h: Math.max(1, Math.round(widget.h * ratio))};
    if (!element('editor-text-style').hidden) change.size = clamp(Math.round(widget.size * ratio), 8, 60);
    editWidget(change);
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
    (save.disabled ? back : save).focus();
  });
  blank.addEventListener('click', () => {
    current().selection = -1;
    setDraft([], true);
    save.focus();
  });

  retry.addEventListener('click', () => schedulePreview(0));

  save.addEventListener('click', async () => {
    finishText(true);
    const draft = current();
    if (!hasChanges(draft) || savingScreen || drag || paletteDrag || layerDrag) return;
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
      if (code === setupCode && draft.message === badCode) askForCode(draft.message);
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
      for (const [index, widget] of layers().entries()) {
        const label = widgetLabel(widget, index);
        hitboxes[index]?.setAttribute('aria-label', label);
        widgetButtons[index].setAttribute('aria-label', label);
        widgetButtons[index].querySelector('span').textContent = layerName(widget);
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

  askForCode('');
  fetch('/api/state').then(response => response.ok ? response.json() : null).then(data => {
    if (!data) return;
    document.documentElement.dataset.theme = data.theme;
    applyLanguage(data.language);
  }).catch(() => {});
}
