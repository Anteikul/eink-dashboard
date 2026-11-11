{
  const element = (id) => document.getElementById(id);
  const editor = element('layout-editor');
  const back = element('editor-back');
  const accessStatus = element('editor-access-status');
  const accessActions = element('editor-access-actions');
  const accessRetry = element('editor-access-retry');
  const signIn = element('editor-sign-in');
  const content = element('editor-content');
  const panel = element('editor-panel');
  const tabs = [...editor.querySelectorAll('[role=tab]')];
  const stage = element('editor-stage');
  const canvasArea = element('editor-canvas-area');
  const panelFrame = element('editor-panel-frame');
  const preview = element('editor-image');
  const output = preview.getContext('2d');
  const canvas = document.createElement('canvas');
  const frame = canvas.getContext('2d');
  const drawing = document.createElement('canvas');
  const eraseSurface = document.createElement('canvas');
  const eraseContext = eraseSurface.getContext('2d');
  const selection = element('editor-selection');
  const marquee = element('editor-marquee');
  const dropMarker = element('editor-drop-marker');
  const guides = {x: element('editor-guide-x'), y: element('editor-guide-y')};
  const magnet = element('editor-snap');
  const inlineText = element('editor-inline-text');
  const previewStatus = element('editor-preview-status');
  const retry = element('editor-preview-retry');
  const widgetList = element('editor-widgets');
  const palette = element('editor-palette');
  const photoFile = element('editor-photo-file');
  const cropButton = element('editor-crop-photo');
  const cropSurface = element('editor-photo-crop');
  const photoStatus = element('editor-photo-status');
  const photoCrop = createPhotoCrop(cropSurface, cropButton, (canvas, photo) => {
    canvas.width = photo.w;
    canvas.height = photo.h;
    paintInk(canvas, decodeInk(photo.bitmap), 255);
  }, {point: canvasPoint, direction: canvasDirection});
  const tools = element('editor-tools');
  const toolbar = element('editor-toolbar');
  const history = element('editor-history');
  const brush = element('editor-brush');
  const brushOptions = element('editor-brush-options');
  const brushWidth = element('editor-brush-width');
  const fontOptions = element('editor-font-options');
  const fontSize = element('editor-font-size');
  const contentTools = element('editor-content-tools');
  const boldControl = element('editor-bold');
  const canvasAlignment = element('editor-canvas-alignment');
  const clearDrawing = element('editor-clear-drawing');
  const drawingProperties = element('editor-drawing-properties');
  const undo = element('editor-undo');
  const redo = element('editor-redo');
  const blank = element('editor-blank');
  const properties = element('editor-properties');
  const alignment = element('editor-alignment');
  const fields = Object.fromEntries(
    [...properties.querySelectorAll('[data-property]')].map(field => [field.dataset.property, field]),
  );
  const clockStyleLabel = element('editor-clock-style');
  const variantName = element('editor-variant-name');
  const scaleField = element('editor-scale');
  const dividerSettings = element('editor-divider-settings');
  const dividerLength = element('editor-divider-length');
  const dividerThickness = element('editor-divider-thickness');
  const remove = element('editor-remove');
  const reset = element('editor-reset');
  const save = element('editor-save');
  const saveStatus = element('editor-save-status');
  const libraryToggle = element('editor-library-toggle');
  const library = element('editor-library');
  const libraryForm = element('editor-library-form');
  const libraryName = element('editor-library-name');
  const librarySave = element('editor-library-save');
  const libraryList = element('editor-library-list');
  const libraryStatus = element('editor-library-status');
  const drafts = Object.fromEntries(tabs.map(tab => [
    tab.dataset.screen, {saved: null, librarySaved: null, layout: null, selection: -1, group: [], message: '', undo: [], redo: []},
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
    photo: 'M4 5h10m-10 0a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1v-8M3 17l5-5 4 4 3-3 6 6M18 3v8m-4-4h8',
    progress: 'M3 9h18v6H3Zm0 3h11',
    'playback-time': 'M4 4h16v16H4Zm5 5 6 3-6 3Z',
    drawing: 'm4 15 10-10 4 4L8 19l-5 1 1-5Zm10-10 2-2a1.5 1.5 0 0 1 2 0l3 3a1.5 1.5 0 0 1 0 2l-2 2M13 21h8',
    grip: 'M8 5h.01m8 0h.01M8 12h.01m8 0h.01M8 19h.01m8 0h.01',
    trash: 'M4 6h16m-11 0V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7',
  };
  const badCode = 'Check the device setup code.';

  let schema;
  let screen = 'dashboard';
  let hitboxes = [];
  let widgetButtons = [];
  let drag;
  let paletteDrag;
  let photoPoint;
  let photoImporting = false;
  let layerDrag;
  let textEditing;
  let tool = 'select';
  let loadController;
  let previewController;
  let previewTimer;
  let atlas;
  let tiles = new Map();
  const layerKeys = new WeakMap();
  const previousTileKeys = new WeakMap();
  const inkTiles = new Map();
  let savingScreen;
  let libraryOperation;
  let librarySelection;
  let libraryThumbnails;
  let libraryEntries = [];
  let librarySelected = null;

  const current = () => drafts[screen];
  const layers = (layout = current().layout) => layout ?? schema.defaults[screen];
  const widgets = () => layers().filter(layer => layer.type !== 'drawing');
  const drawings = () => layers().filter(layer => layer.type === 'drawing');
  const definitions = (target = screen) => schema.widgets[target];
  const definition = (type, target) => definitions(target).find(widget => widget.type === type);
  const hasChanges = ({saved, layout}) => JSON.stringify(saved) !== JSON.stringify(layout);
  const restoreLayout = draft => draft.librarySaved?.layout ?? null;
  const clamp = (value, min, max) => Math.max(min, Math.min(value, max));
  const stride = width => Math.ceil(width / 8);
  const displaySize = () => [schema.width, schema.height];
  const selectedIndices = () => current().selection >= 0 ? [current().selection] : current().group;

  function layerKey(layer) {
    if (!layerKeys.has(layer)) {
      const {x, y, placement, ...appearance} = layer;
      layerKeys.set(layer, JSON.stringify(appearance));
    }
    return layerKeys.get(layer);
  }

  function positionHistory() {
    const area = canvasArea.getBoundingClientRect();
    if (!schema || !area.width || !area.height) return;
    const extraRow = toolbar.hasAttribute('data-history-row') ? toolbar.offsetHeight - tools.offsetHeight : 0;
    const {width, height} = schema.panel;
    const widthInOneRow = Math.min(area.width, (area.height + extraRow) * width / height);
    toolbar.toggleAttribute('data-history-row', (widthInOneRow - tools.offsetWidth) / 2 < history.offsetWidth + 2);
    history.style.marginInlineEnd = Math.max(0, area.right - panelFrame.getBoundingClientRect().right) + 'px';
  }

  const historyObserver = new ResizeObserver(positionHistory);
  historyObserver.observe(canvasArea);
  historyObserver.observe(panelFrame);

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

  async function request(path, {payload, file, signal, fallback} = {}) {
    const options = {signal};
    if (payload !== undefined) {
      options.headers = {'Content-Type': 'application/json'};
      options.method = 'POST';
      options.body = JSON.stringify(payload);
    }
    if (file) {
      options.headers = {'Content-Type': 'application/octet-stream'};
      options.method = 'POST';
      options.body = file;
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
      const label = translate(tab.dataset.label);
      tab.setAttribute('aria-label', dirty ? label + ' (' + translate('Unapplied changes') + ')' : label);
    }
    const draft = current();
    reset.disabled = JSON.stringify(draft.layout) === JSON.stringify(restoreLayout(draft));
    reset.setAttribute('aria-label', translate(draft.librarySaved?.name ? 'Restore saved layout' : 'Reset to default'));
    blank.disabled = current().layout?.length === 0;
    clearDrawing.disabled = drawings().length === 0;
    undo.disabled = current().undo.length === 0;
    redo.disabled = current().redo.length === 0;
    save.disabled = Boolean(savingScreen || librarySelection) || !hasChanges(current());
    setText(saveStatus, current().message);
  }

  function layerName(layer) {
    return translate(layer.type === 'drawing' ? 'Pen stroke' : definition(layer.type).label);
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
      button.setAttribute('aria-label', translate(item.type === 'photo' ? 'Import photo' : item.label));
      button.append(icon(item.type));
      return button;
    }));
    updatePalette();
  }

  function updatePalette() {
    const full = widgets().length >= schema.maxWidgets;
    for (const button of palette.children) {
      button.disabled = full || (photoImporting && button.dataset.widget === 'photo');
    }
  }

  function updateInspector() {
    const widget = layers()[current().selection];
    cropButton.disabled = widget?.type !== 'photo';
    const isDrawing = widget?.type === 'drawing';
    const item = widget && !isDrawing ? definition(widget.type) : null;
    const analog = widget?.clockStyle === 'analog';
    const textStyle = item?.textStyle && !(
      analog ||
      (widget.type === 'weather' && widget.variant === 'icon-only')
    );
    brushOptions.hidden = tool === 'select';
    brushWidth.hidden = tool !== 'draw';
    fontOptions.hidden = tool !== 'select' || !textStyle;
    const iconOnly = widget?.type === 'weather' && widget.variant === 'icon-only';
    contentTools.hidden = tool !== 'select' || !(textStyle || iconOnly);
    boldControl.hidden = !textStyle;
    if (textStyle) boldControl.setAttribute('aria-pressed', String(widget.font.endsWith('bold')));
    canvasAlignment.hidden = tool !== 'select' || !selectedIndices().length;
    if (textStyle && fontSize.value !== String(widget.size)) fontSize.value = widget.size;
    properties.hidden = !widget || isDrawing;
    drawingProperties.hidden = !isDrawing;
    element('editor-inspector-title').hidden = !widget;
    if (!widget || isDrawing) return;

    element('editor-selected-widget').textContent = widgetLabel(widget, current().selection);
    clockStyleLabel.hidden = !item.clockStyles;
    element('editor-variant-label').hidden = analog || item.variants.length === 0;
    setText(variantName, item.clockStyles ? 'Time format' : 'Variant');
    element('editor-text-style').hidden = !textStyle;
    element('editor-text-label').hidden = widget.type !== 'text';
    const customFormat = !analog && item.customFormat && widget.variant === 'custom';
    element('editor-format').hidden = !customFormat;
    if (customFormat) {
      const isDate = widget.type === 'date';
      setText(element('editor-format-label'), isDate ? 'Date format' : 'Custom format');
      setText(element('editor-format-help'), isDate
        ? 'Use DD.MM.YYYY for numbers, MMM for the short month, dddd for the weekday, and [brackets] for literal text.'
        : 'Use HH:mm for 24-hour time, h:mm A for AM/PM, and ss for seconds. Put literal text in [brackets].');
    }

    if (fields.variant.dataset.type !== widget.type) {
      fields.variant.replaceChildren(...item.variants.map(variant =>
        new Option(translate(variant.label), variant.value)));
      if (item.clockStyles) fields.clockStyle.replaceChildren(...item.clockStyles.map(style =>
        new Option(translate(style.label), style.value)));
      fields.variant.dataset.type = widget.type;
    }

    const box = controlBounds(widget);
    fields.x.max = schema.width - box.w;
    fields.y.max = schema.height - box.h;
    fields.w.max = schema.width - box.x;
    fields.h.max = schema.height - box.y;
    for (const [name, field] of Object.entries(fields)) {
      const value = String(box[name] ?? widget[name] ?? '');
      if (field.value !== value) field.value = value;
    }
    for (const button of alignment.children) {
      button.setAttribute('aria-pressed', String(widget.align === button.dataset.align));
    }
    const divider = widget.type === 'divider';
    element('editor-scale-label').hidden = divider;
    dividerSettings.hidden = !divider;
    if (divider) {
      const vertical = widget.variant === 'vertical';
      dividerLength.max = vertical ? schema.height : schema.width;
      dividerLength.value = vertical ? box.h : box.w;
      dividerThickness.max = vertical ? schema.width : schema.height;
      dividerThickness.value = vertical ? box.w : box.h;
      return;
    }
    const size = Math.max(box.w, box.h);
    scaleField.max = Math.floor(Math.min(
      (schema.width - box.x) * size / box.w,
      (schema.height - box.y) * size / box.h,
    ));
    scaleField.value = size;
  }

  function updateSelection() {
    const indices = selectedIndices();
    stage.toggleAttribute('data-group', indices.length > 1);
    for (const [index, button] of widgetButtons.entries()) {
      const selected = String(indices.includes(index));
      hitboxes[index]?.setAttribute('aria-pressed', selected);
      if (hitboxes[index]) hitboxes[index].tabIndex = tool === 'select' ? 0 : -1;
      button.setAttribute('aria-pressed', selected);
    }
    positionSelection(indices);
    updateInspector();
  }

  function selectionBounds(indices = selectedIndices(), layout = layers()) {
    if (!indices.length) return null;
    const boxes = indices.map(index => controlBounds(layout[index]));
    const x = Math.min(...boxes.map(box => box.x));
    const y = Math.min(...boxes.map(box => box.y));
    return {x, y, w: Math.max(...boxes.map(box => box.x + box.w)) - x,
      h: Math.max(...boxes.map(box => box.y + box.h)) - y};
  }

  function positionSelection(indices = selectedIndices()) {
    const box = selectionBounds(indices);
    const layer = layers()[current().selection];
    selection.hidden = !box || tool !== 'select';
    selection.dataset.kind = indices.length > 1 ? 'group' : layer?.type ?? '';
    if (box) positionLayer(selection, layer ?? box);
  }

  function position(hitbox, {x, y, w, h}) {
    hitbox.style.left = (x / schema.width * 100) + '%';
    hitbox.style.top = (y / schema.height * 100) + '%';
    hitbox.style.width = (w / schema.width * 100) + '%';
    hitbox.style.height = (h / schema.height * 100) + '%';
  }

  function positionLayer(hitbox, layer) {
    const box = controlBounds(layer);
    position(hitbox, box);
    const vertical = layer.variant === 'vertical';
    if (layer.type === 'divider' && (vertical ? box.w : box.h) < 4) hitbox.dataset.thin = layer.variant;
    else delete hitbox.dataset.thin;
  }

  function renderWidgets() {
    for (const hitbox of hitboxes) hitbox?.remove();
    hitboxes = [];
    widgetButtons = [];
    const list = document.createDocumentFragment();
    for (const [index, widget] of layers().entries()) {
      const label = widgetLabel(widget, index);
      const hitbox = document.createElement('button');
      hitbox.type = 'button';
      hitbox.className = 'editor-hitbox';
      hitbox.dataset.index = index;
      hitbox.dataset.kind = widget.type;
      hitbox.setAttribute('aria-label', label);
      positionLayer(hitbox, widget);
      stage.append(hitbox);
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
    selectLayers(index < 0 ? [] : [index]);
  }

  function selectLayers(indices) {
    const draft = current();
    draft.selection = indices.length === 1 ? indices[0] : -1;
    draft.group = indices.length > 1 ? indices : [];
    updateSelection();
  }

  function clearPreview(keepFrame = false) {
    atlas?.close();
    atlas = undefined;
    tiles.clear();
    if (!keepFrame) output.clearRect(0, 0, preview.width, preview.height);
  }

  function tileFor(layer) {
    return tiles.get(layerKey(layer)) ?? tiles.get(previousTileKeys.get(layer));
  }

  function sourceBounds(layer) {
    return tileFor(layer)?.bounds ?? {x: 0, y: 0, w: layer.w, h: layer.h};
  }

  function controlBounds(layer) {
    if (!layer.type || layer.type === 'drawing') return layer;
    const source = sourceBounds(layer);
    if (!layer.placement) return {x: layer.x + source.x, y: layer.y + source.y, w: source.w, h: source.h};
    const {x, y, scaleX, scaleY, referenceWidth} = layer.placement;
    const w = clamp(Math.round(source.w * scaleX), 1, schema.width);
    const h = clamp(Math.round(source.h * scaleY), 1, schema.height);
    const factor = {left: 0, center: .5, right: 1}[layer.align];
    const left = x + Math.round(((referenceWidth ?? w) - w) * factor);
    return {x: clamp(left, 0, schema.width - w), y: Math.min(y, schema.height - h), w, h};
  }

  function boxChange(layer, {x, y, w, h}) {
    if (layer.type === 'drawing') return {x, y};
    const current = controlBounds(layer);
    if (x === current.x && y === current.y && w === current.w && h === current.h) {
      return {placement: layer.placement};
    }
    const source = sourceBounds(layer);
    const scaleX = w === current.w ? layer.placement?.scaleX ?? 1 : w / source.w;
    const scaleY = h === current.h ? layer.placement?.scaleY ?? 1 : h / source.h;
    return {placement: {x, y, scaleX, scaleY, referenceWidth: w}};
  }

  function compose() {
    if (!atlas) return;
    frame.imageSmoothingEnabled = false;
    frame.drawImage(atlas, 0, 0, 1, 1, 0, 0, schema.width, schema.height);
    for (const widget of layers()) {
      if (widget.type === 'drawing') {
        composeInk(widget);
        continue;
      }
      const tile = tileFor(widget);
      if (tile && widget.placement && tile.bounds) {
        const {x, y, w, h} = tile.bounds;
        composeTile(atlas, x, tile.y + y, w, h, controlBounds(widget));
      } else if (tile && !widget.placement) {
        composeTile(atlas, 0, tile.y, tile.w, tile.h, widget);
      }
    }
    if (drag?.bytes && !drag.erase) frame.drawImage(drawing, 0, 0);

    const {rotation, bounds: [x, y, w, h]} = schema.panel;
    const [width, height] = rotation % 180 ? [h, w] : [w, h];
    output.imageSmoothingEnabled = false;
    output.drawImage(atlas, 0, 0, 1, 1, 0, 0, preview.width, preview.height);
    output.save();
    output.translate(x + w / 2, y + h / 2);
    output.rotate(rotation * Math.PI / 180);
    output.drawImage(canvas, -width / 2, -height / 2, width, height);
    output.restore();
  }

  function decodeInk(bitmap) {
    return Uint8Array.from(atob(bitmap), character => character.charCodeAt(0));
  }

  function visitInk(bytes, w, h, visit) {
    const rowBytes = stride(w);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const offset = y * rowBytes + (x >> 3);
        const bit = 128 >> (x & 7);
        if (bytes[offset] & bit) visit(x, y, offset, bit);
      }
    }
  }

  function cropInk(bytes, width, height, x = 0, y = 0) {
    let left = width, top = height, right = -1, bottom = -1;
    visitInk(bytes, width, height, (px, py) => {
      left = Math.min(left, px);
      top = Math.min(top, py);
      right = Math.max(right, px);
      bottom = py;
    });
    if (right < 0) return null;
    const w = right - left + 1;
    const h = bottom - top + 1;
    const rowBytes = stride(w);
    const cropped = new Uint8Array(rowBytes * h);
    visitInk(bytes, width, height, (px, py) => {
      const localX = px - left;
      cropped[(py - top) * rowBytes + (localX >> 3)] |= 128 >> (localX & 7);
    });
    return {type: 'drawing', x: x + left, y: y + top, w, h, bitmap: btoa(String.fromCharCode(...cropped))};
  }

  function editableLayout(layout) {
    return layout?.map(layer => layer.type === 'drawing' && layer.w === undefined
      ? cropInk(decodeInk(layer.bitmap), schema.width, schema.height) : layer).filter(Boolean) ?? null;
  }

  function paintInk(canvas, bytes, color) {
    const {width, height} = canvas;
    const context = canvas.getContext('2d');
    const image = context.createImageData(width, height);
    visitInk(bytes, width, height, (x, y) => {
      const offset = (y * width + x) * 4;
      image.data.fill(color, offset, offset + 3);
      image.data[offset + 3] = 255;
    });
    context.putImageData(image, 0, 0);
  }

  function inkColor() {
    return document.documentElement.dataset.theme === 'dark' ? 255 : 0;
  }

  function composeInk(layer) {
    const {w, h, bitmap} = layer;
    const color = inkColor();
    const key = w + ':' + h + ':' + color + ':' + bitmap;
    let tile = inkTiles.get(key);
    if (!tile) {
      tile = document.createElement('canvas');
      tile.width = w;
      tile.height = h;
      paintInk(tile, decodeInk(bitmap), color);
      inkTiles.set(key, tile);
      if (inkTiles.size > 128) inkTiles.delete(inkTiles.keys().next().value);
    }
    composeTile(tile, 0, 0, w, h, layer);
  }

  function composeTile(source, sourceX, sourceY, sourceWidth, sourceHeight, {x, y, w, h}) {
    if (drag?.erase) {
      eraseContext.clearRect(0, 0, w, h);
      eraseContext.imageSmoothingEnabled = false;
      eraseContext.drawImage(source, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, w, h);
      eraseContext.globalCompositeOperation = 'destination-out';
      eraseContext.drawImage(drawing, -x, -y);
      eraseContext.globalCompositeOperation = 'source-over';
      frame.drawImage(eraseSurface, 0, 0, w, h, x, y, w, h);
    } else {
      frame.drawImage(source, sourceX, sourceY, sourceWidth, sourceHeight, x, y, w, h);
    }
  }

  function changeLayers(transform) {
    const draft = current();
    const layout = [];
    let changed = false;
    let changedWidget = false;
    let selection = -1;
    for (const [index, layer] of layers().entries()) {
      const result = transform(layer);
      if (result !== layer) {
        changed = true;
        if (layer.type !== 'drawing') changedWidget = true;
      }
      if (!result) continue;
      if (draft.selection === index) selection = layout.length;
      layout.push(result);
    }
    if (!changed) return;
    if (changedWidget) clearPreview(true);
    draft.selection = selection;
    setDraft(layout, true);
  }

  function eraseWidget(layer, brush, brushStride) {
    const {w, h, mask} = layer;
    const box = layer.placement ? controlBounds(layer) : layer;
    const source = layer.placement ? sourceBounds(layer) : {x: 0, y: 0, w, h};
    const rowBytes = stride(w);
    const old = mask ? decodeInk(mask.bitmap) : null;
    const oldStride = mask ? stride(mask.w) : 0;
    const bytes = new Uint8Array(rowBytes * h);
    if (mask) {
      for (let py = 0; py < h; py++) {
        const oldY = Math.floor((py + .5) * mask.h / h);
        for (let px = 0; px < w; px++) {
          const oldX = Math.floor((px + .5) * mask.w / w);
          if (old[oldY * oldStride + (oldX >> 3)] & (128 >> (oldX & 7))) {
            bytes[py * rowBytes + (px >> 3)] |= 128 >> (px & 7);
          }
        }
      }
    }
    let changed = false;
    for (let py = 0; py < box.h; py++) {
      const maskY = source.y + Math.floor((py + .5) * source.h / box.h);
      for (let px = 0; px < box.w; px++) {
        const globalX = box.x + px;
        if (!(brush[(box.y + py) * brushStride + (globalX >> 3)] & (128 >> (globalX & 7)))) continue;
        const maskX = source.x + Math.floor((px + .5) * source.w / box.w);
        const offset = maskY * rowBytes + (maskX >> 3);
        const bit = 128 >> (maskX & 7);
        if (!(bytes[offset] & bit)) {
          bytes[offset] |= bit;
          changed = true;
        }
      }
    }
    return changed ? {...layer, mask: {w, h, bitmap: btoa(String.fromCharCode(...bytes))}} : layer;
  }

  function eraseLayers(mask) {
    const rowBytes = stride(schema.width);
    changeLayers(layer => {
      if (layer.type !== 'drawing') return eraseWidget(layer, mask, rowBytes);
      const {x, y, w, h, bitmap} = layer;
      const bytes = decodeInk(bitmap);
      let changed = false;
      visitInk(bytes, w, h, (px, py, offset, bit) => {
        const globalX = x + px;
        if (mask[(y + py) * rowBytes + (globalX >> 3)] & (128 >> (globalX & 7))) {
          bytes[offset] &= ~bit;
          changed = true;
        }
      });
      return changed ? cropInk(bytes, w, h, x, y) : layer;
    });
  }

  function stopPreview() {
    clearTimeout(previewTimer);
    previewController?.abort();
    previewController = undefined;
  }

  function showAccessError(message) {
    const expired = message === badCode;
    accessActions.hidden = false;
    signIn.hidden = !expired;
    setText(accessStatus, expired ? 'Sign in again, then retry here.' : message);
  }

  function schedulePreview(delay = 160) {
    stopPreview();
    retry.hidden = true;
    setText(previewStatus, '');
    const payload = {screen, layout: widgets(), layers: true, displaySize: displaySize()};
    const controller = new AbortController();
    previewController = controller;
    previewTimer = setTimeout(async () => {
      try {
        const response = await request('/api/layout-preview', {
          payload, signal: controller.signal, fallback: 'Could not load the sample preview.',
        });
        const blob = await response.blob();
        if (controller.signal.aborted || previewController !== controller) return;
        if (blob.type !== 'image/png') throw new Error('Could not load the sample preview.');
        const geometry = JSON.parse(response.headers.get('X-Eink-Layer-Bounds'));
        if (!Array.isArray(geometry) || geometry.length !== payload.layout.length) {
          throw new Error('Could not load the sample preview.');
        }
        const image = await createImageBitmap(blob);
        if (controller.signal.aborted || previewController !== controller) {
          image.close();
          return;
        }
        const nextTiles = new Map();
        for (const [index, widget] of payload.layout.entries()) {
          const key = layerKey(widget);
          if (nextTiles.has(key)) continue;
          const tile = {y: 1 + index * schema.height, w: widget.w, h: widget.h};
          if (geometry[index]) {
            const [x, y, w, h] = geometry[index];
            tile.bounds = {x, y, w, h};
          }
          nextTiles.set(key, tile);
        }
        atlas?.close();
        atlas = image;
        tiles = nextTiles;
        for (const [index, layer] of layers().entries()) positionLayer(hitboxes[index], layer);
        positionSelection();
        updateInspector();
        compose();
      } catch (error) {
        if (controller.signal.aborted || previewController !== controller) return;
        if (error.message === badCode) {
          showAccessError(error.message);
          return;
        }
        setText(previewStatus, error instanceof TypeError ? 'The Pi did not respond.' : error.message);
        retry.hidden = false;
      }
    }, delay);
  }

  function showScreen() {
    photoCrop.close(false);
    finishText(false);
    drag = undefined;
    marquee.hidden = true;
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
    renderWidgets();
    updateStatus();
    schedulePreview(0);
    if (!library.hidden) loadLibrary();
  }

  function updateLibraryControls() {
    const busy = Boolean(libraryOperation);
    librarySave.disabled = busy || Boolean(librarySelection) || !libraryName.value.trim();
    for (const button of libraryList.querySelectorAll('button')) {
      button.disabled = busy || (button.hasAttribute('data-delete') && Boolean(librarySelection));
      if (button.hasAttribute('data-name')) {
        button.setAttribute('aria-pressed', String(button.dataset.name === librarySelected));
      }
    }
  }

  function libraryPath(params) {
    return '/api/layout-library?' + new URLSearchParams({
      screen, width: schema.width, height: schema.height, ...params,
    });
  }

  function stopLibraryThumbnails() {
    if (!libraryThumbnails) return;
    libraryThumbnails.controller.abort();
    libraryThumbnails.observer.disconnect();
    for (const url of libraryThumbnails.urls) URL.revokeObjectURL(url);
    libraryThumbnails = undefined;
  }

  function loadLibraryThumbnails(images) {
    stopLibraryThumbnails();
    const controller = new AbortController();
    const urls = [];
    const queue = [];
    let loading = false;
    async function nextThumbnail() {
      if (loading) return;
      loading = true;
      while (queue.length && !controller.signal.aborted) {
        const img = queue.shift();
        try {
          const response = await request(libraryPath({name: img.dataset.name, thumbnail: '1'}),
            {signal: controller.signal});
          const blob = await response.blob();
          if (controller.signal.aborted || blob.type !== 'image/png') continue;
          const url = URL.createObjectURL(blob);
          urls.push(url);
          img.src = url;
          img.hidden = false;
        } catch {
          // The card still opens normally if its thumbnail cannot be rendered.
        }
      }
      loading = false;
    }
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        observer.unobserve(entry.target);
        queue.push(entry.target.querySelector('img'));
      }
      nextThumbnail();
    }, {root: libraryList, rootMargin: '45px'});
    libraryThumbnails = {controller, observer, urls};
    for (const img of images) observer.observe(img.parentElement);
  }

  function showLibraryEntries(entries, selected = null) {
    libraryEntries = entries;
    librarySelected = selected;
    const dateFormat = new Intl.DateTimeFormat(document.documentElement.lang, {
      dateStyle: 'medium', timeStyle: 'short',
    });
    const images = [];
    const items = [{name: '', layers: schema.defaults[screen].length}, ...entries].map(entry => {
      const {name, savedAt, layers} = entry;
      const row = document.createElement('li');
      row.className = 'editor-library-item';
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'editor-library-card';
      card.dataset.name = name;
      const thumb = document.createElement('span');
      thumb.className = 'editor-library-thumb';
      const img = document.createElement('img');
      img.alt = '';
      img.hidden = true;
      img.dataset.name = name;
      thumb.append(img);
      images.push(img);
      const details = document.createElement('span');
      details.className = 'editor-library-details';
      const title = document.createElement('strong');
      title.textContent = name || '🔒 ' + translate('Default layout');
      const date = document.createElement('small');
      if (!name) {
        date.textContent = translate('Built-in layout');
      } else if (savedAt && Number.isFinite(Date.parse(savedAt))) {
        const time = document.createElement('time');
        time.dateTime = savedAt;
        time.textContent = dateFormat.format(new Date(savedAt));
        date.append(time);
      } else {
        date.textContent = translate('Save date unknown');
      }
      details.append(title, date);
      if (layers !== null) {
        const count = document.createElement('small');
        count.className = 'editor-library-layer-count';
        count.textContent = translate('Layers') + ' · ' + layers;
        details.append(count);
      }
      card.append(thumb, details);
      row.append(card);
      if (name) {
        const deleteButton = document.createElement('button');
        deleteButton.type = 'button';
        deleteButton.className = 'editor-icon';
        deleteButton.dataset.delete = name;
        deleteButton.setAttribute('aria-label', translate('Delete saved layout'));
        deleteButton.append(icon('trash'));
        row.append(deleteButton);
      }
      return row;
    });
    libraryList.replaceChildren(...items);
    updateLibraryControls();
    loadLibraryThumbnails(images);
  }

  function reportLibraryError(error) {
    const message = error instanceof TypeError ? 'The Pi did not respond.' : error.message;
    if (message === badCode) showAccessError(message);
    else setText(libraryStatus, message);
  }

  async function chooseLibraryLayout(card) {
    if (drag || layerDrag || paletteDrag || libraryOperation) return;
    librarySelection?.abort();
    const controller = new AbortController();
    librarySelection = controller;
    const signal = controller.signal;
    const name = card.dataset.name;
    setText(libraryStatus, '');
    updateLibraryControls();
    updateStatus();
    try {
      let layout = null;
      if (name) {
        const response = await request(libraryPath({name}), {
          signal, fallback: 'Could not open the layout library.',
        });
        ({layout} = await response.json());
      }
      if (signal.aborted) return;
      layout = editableLayout(layout);
      // Reuse the finished thumbnail while the editable layer preview arrives.
      clearPreview(true);
      const img = card.querySelector('img');
      if (img.complete && img.naturalWidth) output.drawImage(img, 0, 0);
      const draft = current();
      draft.selection = -1;
      setDraft(layout, true);
      draft.librarySaved = {name, layout};
      librarySelected = name;
    } catch (error) {
      if (!signal.aborted) reportLibraryError(error);
    } finally {
      if (librarySelection === controller) {
        librarySelection = undefined;
        updateLibraryControls();
        updateStatus();
      }
    }
  }

  async function requestLibrary({payload, onSuccess}) {
    if (libraryOperation) return;
    const controller = new AbortController();
    libraryOperation = controller;
    const signal = controller.signal;
    const path = payload ? '/api/layout-library' : libraryPath({details: '1'});
    setText(libraryStatus, '');
    updateLibraryControls();
    try {
      const response = await request(path, {
        signal,
        payload: payload ? {screen, ...payload, displaySize: displaySize()} : undefined,
        fallback: 'Could not open the layout library.',
      });
      const data = await response.json();
      if (!signal.aborted) onSuccess(data);
    } catch (error) {
      if (!signal.aborted) reportLibraryError(error);
    } finally {
      if (libraryOperation === controller) {
        libraryOperation = undefined;
        updateLibraryControls();
      }
    }
  }

  function loadLibrary() {
    stopLibraryRequests();
    libraryForm.reset();
    showLibraryEntries([]);
    requestLibrary({onSuccess: ({entries}) => showLibraryEntries(entries, current().librarySaved?.name)});
  }

  function stopLibraryRequests() {
    libraryOperation?.abort();
    libraryOperation = undefined;
    librarySelection?.abort();
    librarySelection = undefined;
    stopLibraryThumbnails();
    if (schema) updateStatus();
  }

  function setLibraryVisible(visible) {
    libraryToggle.setAttribute('aria-expanded', String(visible));
    library.hidden = !visible;
    element('editor-widget-settings').hidden = visible;
    if (visible) {
      loadLibrary();
    } else {
      stopLibraryRequests();
    }
  }

  async function loadLayouts() {
    loadController?.abort();
    const controller = new AbortController();
    loadController = controller;
    accessRetry.disabled = true;
    setText(accessStatus, 'Loading layouts…');
    try {
      const response = await request('/api/layouts', {
        signal: controller.signal, fallback: 'Could not load the layouts.',
      });
      const data = await response.json();
      if (controller.signal.aborted) return;
      schema = data;
      for (const [name, draft] of Object.entries(drafts)) {
        const saved = editableLayout(data.layouts[name]);
        if (!hasChanges(draft) && JSON.stringify(draft.saved) !== JSON.stringify(saved)) {
          draft.layout = saved;
          draft.group = [];
          draft.undo = [];
          draft.redo = [];
        }
        draft.saved = saved;
        const visible = draft.layout ?? data.defaults[name];
        draft.selection = Math.min(draft.selection, visible.length - 1);
      }
      for (const surface of [canvas, drawing, eraseSurface]) {
        surface.width = data.width;
        surface.height = data.height;
      }
      const {width, height, rotation, bounds: [x, y, w, h]} = data.panel;
      const quarterTurn = rotation % 180 !== 0;
      preview.width = width;
      preview.height = height;
      editor.style.setProperty('--display-ratio', width / height);
      stage.style.setProperty('--rotation', rotation + 'deg');
      stage.toggleAttribute('data-quarter-turn', quarterTurn);
      stage.style.left = (x + w / 2) / width * 100 + '%';
      stage.style.top = (y + h / 2) / height * 100 + '%';
      stage.style.width = (quarterTurn ? h : w) / width * 100 + '%';
      stage.style.height = (quarterTurn ? w : h) / height * 100 + '%';
      element('editor-resolution').textContent = data.width + ' × ' + data.height + ' px';
      for (const draft of Object.values(drafts)) {
        if (draft.message === badCode) draft.message = '';
      }
      accessActions.hidden = true;
      content.hidden = false;
      setText(accessStatus, '');
      showScreen();
      tabs.find(tab => tab.dataset.screen === screen).focus();
    } catch (error) {
      if (controller.signal.aborted) return;
      showAccessError(error instanceof TypeError ? 'The Pi did not respond.' : error.message);
    } finally {
      if (loadController === controller) accessRetry.disabled = false;
    }
  }

  function recordHistory(previous, {undo, redo, layout} = current()) {
    if (JSON.stringify(previous) === JSON.stringify(layout)) return;
    undo.push(previous);
    if (undo.length > 40) undo.shift();
    redo.length = 0;
  }

  function refreshPreview() {
    if (!atlas || widgets().some(widget => !tiles.has(layerKey(widget)))) schedulePreview(80);
  }

  function setDraft(layout, structureChanged = false, remember = true, target = screen) {
    const draft = drafts[target];
    const previous = draft.layout;
    draft.layout = layout;
    if (remember) recordHistory(previous, draft);
    draft.message = '';
    if (structureChanged) draft.group = [];
    if (target !== screen) {
      updateStatus();
      return;
    }
    if (structureChanged) {
      renderWidgets();
    } else {
      for (const index of selectedIndices()) positionLayer(hitboxes[index], layers()[index]);
      positionSelection();
      updateInspector();
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
    if (widget.type === 'divider' && !('thickness' in change)) {
      const minorAxis = widget.variant === 'vertical' ? 'w' : 'h';
      if (change[minorAxis] !== undefined && change[minorAxis] !== widget[minorAxis]) {
        change = {...change, thickness: change[minorAxis]};
      }
    }
    const updated = {...widget, ...change};
    const key = layerKey(widget);
    previousTileKeys.set(updated, tiles.has(key) ? key : previousTileKeys.get(widget));
    layout[index] = updated;
    setDraft(layout, false, remember);
    if (textEditing) styleInlineText(layout[index]);
  }

  function moveWidget(dx, dy, origin = layers()[current().selection], snap = false) {
    const {x, y, w, h} = controlBounds(origin);
    const next = {
      x: clamp(x + dx, 0, schema.width - w),
      y: clamp(y + dy, 0, schema.height - h),
      w, h,
    };
    if (snap) snapPosition(next, [current().selection]);
    editWidget(boxChange(origin, next), !drag);
  }

  function moveGroup(dx, dy, origin = layers(), snap = false) {
    const indices = selectedIndices();
    const bounds = selectionBounds(indices, origin);
    const {x, y, w, h} = bounds;
    const next = {x: clamp(x + dx, 0, schema.width - w), y: clamp(y + dy, 0, schema.height - h), w, h};
    if (snap) snapPosition(next, indices);
    const layout = layers().slice();
    const currentBox = selectionBounds(indices, layout);
    if (next.x === currentBox.x && next.y === currentBox.y) return;
    for (const index of indices) {
      const layer = origin[index];
      const box = controlBounds(layer);
      layout[index] = {...layer, ...boxChange(layer, {...box, x: box.x + next.x - x, y: box.y + next.y - y})};
    }
    setDraft(layout, false, !drag);
  }

  function editDivider(widget, variant, length, thickness) {
    const vertical = variant === 'vertical';
    const rotated = variant !== widget.variant;
    length = Math.min(length, vertical ? schema.height : schema.width);
    thickness = Math.min(thickness, vertical ? schema.width : schema.height);
    const [w, h] = vertical ? [thickness, length] : [length, thickness];
    const box = controlBounds(widget);
    // Round in opposite directions so a round trip does not shift a half-pixel center.
    const roundCenter = vertical ? Math.ceil : Math.floor;
    const x = clamp(box.x + (rotated ? roundCenter((box.w - w) / 2) : 0), 0, schema.width - w);
    const y = clamp(box.y + (rotated ? roundCenter((box.h - h) / 2) : 0), 0, schema.height - h);
    const change = {variant, x, y, w, h, thickness, placement: undefined};
    if (rotated && widget.mask) change.mask = rotateMask(widget.mask, w, h, vertical);
    editWidget(change);
  }

  function rotateMask(mask, w, h, clockwise) {
    const source = decodeInk(mask.bitmap);
    const sourceStride = stride(mask.w);
    const rowBytes = stride(w);
    const rotated = new Uint8Array(rowBytes * h);
    for (let y = 0; y < h; y++) {
      const along = Math.floor((y + .5) * mask.w / h);
      const px = clockwise ? along : mask.w - 1 - along;
      for (let x = 0; x < w; x++) {
        const across = Math.floor((x + .5) * mask.h / w);
        const py = clockwise ? mask.h - 1 - across : across;
        if (source[py * sourceStride + (px >> 3)] & (128 >> (px & 7))) {
          rotated[y * rowBytes + (x >> 3)] |= 128 >> (x & 7);
        }
      }
    }
    return {w, h, bitmap: btoa(String.fromCharCode(...rotated))};
  }

  function resizeWidget(dx, dy, {origin, corner, visible}, free) {
    const {x, y, w, h} = visible;
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
      const {position, guide} = snapAxis(axis, anchor + sign * span, 0, Math.min(first, last),
        Math.max(first, last), [current().selection]);
      return {size: sign * (position - anchor), guide};
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
    const box = {
      x: west ? right - width : x, y: north ? bottom - height : y,
      w: width, h: height,
    };
    editWidget(boxChange(origin, box), false);
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

  function canvasDirection(x, y) {
    switch (schema.panel.rotation) {
      case 90: return [y, -x];
      case 180: return [-x, -y];
      case 270: return [-y, x];
      default: return [x, y];
    }
  }

  function canvasPoint(event, target = stage, canvasWidth = schema.width, canvasHeight = schema.height) {
    const {left, top, width, height} = target.getBoundingClientRect();
    const [x, y] = canvasDirection((event.clientX - left) / width - .5, (event.clientY - top) / height - .5);
    return {x: (x + .5) * canvasWidth, y: (y + .5) * canvasHeight};
  }

  function updateMarquee(from, to) {
    const x = clamp(Math.min(from.x, to.x), 0, schema.width);
    const y = clamp(Math.min(from.y, to.y), 0, schema.height);
    const right = clamp(Math.max(from.x, to.x), 0, schema.width);
    const bottom = clamp(Math.max(from.y, to.y), 0, schema.height);
    marquee.hidden = Math.max(right - x, bottom - y) < 2;
    if (!marquee.hidden) position(marquee, {x, y, w: right - x, h: bottom - y});
    const indices = [];
    if (!marquee.hidden) {
      for (const [index, layer] of layers().entries()) {
        const box = controlBounds(layer);
        if (box.x < right && box.x + box.w > x && box.y < bottom && box.y + box.h > y) {
          indices.push(index);
        }
      }
    }
    selectLayers(indices);
  }

  function brushPoint(event) {
    const {x, y} = canvasPoint(event);
    return [clamp(Math.floor(x), 0, schema.width - 1), clamp(Math.floor(y), 0, schema.height - 1)];
  }

  function strokeTo(point) {
    const {bytes, radius} = drag;
    let [x, y] = drag.point;
    const [endX, endY] = point;
    const dx = Math.abs(endX - x);
    const dy = -Math.abs(endY - y);
    const stepX = Math.sign(endX - x);
    const stepY = Math.sign(endY - y);
    const rowBytes = stride(schema.width);
    let error = dx + dy;
    // Stamp a round brush along an integer line so rapid motions have no gaps.
    for (;;) {
      for (let py = Math.max(0, y - radius); py <= Math.min(schema.height - 1, y + radius); py++) {
        for (let px = Math.max(0, x - radius); px <= Math.min(schema.width - 1, x + radius); px++) {
          if ((px - x) ** 2 + (py - y) ** 2 > (radius + .35) ** 2) continue;
          const index = py * rowBytes + (px >> 3);
          const bit = 128 >> (px & 7);
          bytes[index] |= bit;
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
    paintInk(drawing, bytes, inkColor());
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
      if (selected.includes(index)) continue;
      const box = controlBounds(layer);
      const start = box[axis];
      const span = horizontal ? box.w : box.h;
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

  function snapPosition(box, selected = []) {
    const x = snapAxis('x', box.x, box.w, 0, schema.width - box.w, selected);
    const y = snapAxis('y', box.y, box.h, 0, schema.height - box.h, selected);
    box.x = x.position;
    box.y = y.position;
    showGuides(x.guide, y.guide);
    return box;
  }

  function widgetAt({w, h}, point, snap = true) {
    const box = {
      x: clamp(Math.round(point.x - w / 2), 0, schema.width - w),
      y: clamp(Math.round(point.y - h / 2), 0, schema.height - h),
      w, h,
    };
    return snap ? snapPosition(box) : box;
  }

  function insideCanvas({x, y}) {
    return x >= 0 && y >= 0 && x < schema.width && y < schema.height;
  }

  function addWidget(item, point, overrides, target = screen) {
    const draft = drafts[target];
    const previous = draft.layout ?? schema.defaults[target];
    if (previous.filter(layer => layer.type !== 'drawing').length >= schema.maxWidgets) return false;
    const active = target === screen;
    const template = {...item.template, ...overrides};
    const widget = {...template, ...(point && widgetAt(template, point, active && !photoCrop.active))};
    if (widget.type === 'text') widget.text = translate(widget.text);
    const layout = [...previous, widget];
    const select = active && !photoCrop.active && !textEditing;
    if (select) draft.selection = layout.length - 1;
    setDraft(layout, true, true, target);
    if (select) {
      setTool('select');
      showGuides();
      hitboxes.at(-1).focus({preventScroll: true});
    }
    return true;
  }

  function pickWidget(item, point) {
    if (item.type === 'photo') {
      photoPoint = point;
      photoFile.click();
    } else {
      addWidget(item, point);
    }
  }

  async function importPhoto(file, point) {
    if (!file || photoImporting || widgets().length >= schema.maxWidgets) return;
    if (!file.size || file.size > schema.photoMaxBytes) {
      setText(photoStatus, 'Choose an image file up to 16 MB.');
      return;
    }
    const target = screen;
    photoImporting = true;
    updatePalette();
    setText(photoStatus, 'Converting photo to black and white…');
    try {
      const response = await request('/api/photo-import', {file, fallback: 'Could not import the photo.'});
      const photo = await response.json();
      while (target === screen && (drag || paletteDrag || layerDrag)) {
        await new Promise(requestAnimationFrame);
      }
      const scale = Math.min(schema.width * .75 / photo.w, schema.height * .75 / photo.h);
      const w = Math.max(1, Math.round(photo.w * scale));
      const h = Math.max(1, Math.round(photo.h * scale));
      const crop = [0, 0, photo.w, photo.h];
      const destination = point ?? {x: schema.width / 2, y: schema.height / 2};
      const added = addWidget(definition('photo', target), destination, {w, h, photo, crop}, target);
      setText(photoStatus, added ? '' : 'Use up to 18 widgets per layout.');
    } catch (error) {
      if (error.message === badCode) showAccessError(error.message);
      setText(photoStatus, error instanceof TypeError ? 'Could not import the photo.' : error.message);
    } finally {
      photoImporting = false;
      updatePalette();
    }
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
    const {clientWidth: width, clientHeight: height} = stage;
    const box = controlBounds(widget);
    const w = Math.min(schema.width, Math.max(box.w, 80 / width * schema.width));
    const h = Math.min(schema.height, Math.max(box.h, 40 / height * schema.height));
    position(inlineText, {x: Math.min(box.x, schema.width - w),
      y: Math.min(box.y, schema.height - h), w, h});
    styleInlineText(widget, width);
    inlineText.value = widget.text;
    inlineText.hidden = false;
    textEditing = {index, screen};
    inlineText.focus({preventScroll: true});
    inlineText.select();
  }

  function styleInlineText(widget, width = stage.clientWidth) {
    inlineText.style.fontSize = clamp(widget.size * (widget.placement?.scaleY ?? 1) * width / schema.width, 16, 38) + 'px';
    inlineText.style.fontFamily = widget.font.startsWith('mono') ? 'var(--mono)' : '';
    inlineText.style.fontWeight = widget.font.endsWith('bold') ? '700' : '';
    inlineText.style.textAlign = widget.align;
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
    const unsaved = Object.values(drafts).some(draft => hasChanges(draft) &&
      (!draft.librarySaved || JSON.stringify(draft.librarySaved.layout) !== JSON.stringify(draft.layout)));
    if (!textEditing && !photoCrop.changed() && !unsaved) return;
    event.preventDefault();
    event.returnValue = '';
  });

  accessRetry.addEventListener('click', loadLayouts);

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
  inlineText.addEventListener('blur', (event) => {
    if (!contentTools.contains(event.relatedTarget)) finishText(true);
  });
  contentTools.addEventListener('focusout', (event) => {
    if (event.relatedTarget !== inlineText && !contentTools.contains(event.relatedTarget)) finishText(true);
  });
  inlineText.addEventListener('keydown', (event) => {
    if (event.isComposing) return;
    if (event.key === 'Escape' || (event.key === 'Enter' && !event.shiftKey)) {
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
      if (tool === 'draw' && drawings().length >= schema.maxDrawings) {
        current().message = 'Use up to 96 pen strokes per layout.';
        updateStatus();
        return;
      }
      const point = brushPoint(event);
      drag = {
        id: event.pointerId, point, bytes: new Uint8Array(stride(schema.width) * schema.height),
        radius: Number(brush.value) >> 1,
        erase: tool === 'erase',
      };
      stage.setPointerCapture(event.pointerId);
      strokeTo(point);
      return;
    }
    const corner = event.target.dataset.corner;
    const hitbox = event.target.closest('.editor-hitbox');
    event.preventDefault();
    const point = canvasPoint(event);
    if (!hitbox && !corner) {
      selectWidget(-1);
      stage.focus({preventScroll: true});
      drag = {id: event.pointerId, point, marquee: true};
      stage.setPointerCapture(event.pointerId);
      return;
    }
    const index = hitbox ? Number(hitbox.dataset.index) : current().selection;
    hitboxes[index].focus({preventScroll: true});
    if (current().group.includes(index)) {
      drag = {id: event.pointerId, point, groupOrigin: layers(), before: current().layout};
      stage.setPointerCapture(event.pointerId);
      return;
    }
    selectWidget(index);
    const origin = layers()[index];
    drag = {
      id: event.pointerId, point, index, corner, origin, visible: controlBounds(origin),
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
    if (drag.marquee) {
      updateMarquee(drag.point, point);
      return;
    }
    const dx = Math.round(point.x - drag.point.x);
    const dy = Math.round(point.y - drag.point.y);
    if (drag.groupOrigin) {
      moveGroup(dx, dy, drag.groupOrigin, true);
    } else if (drag.corner) {
      drag.delta = {dx, dy};
      resizeWidget(dx, dy, drag, event.shiftKey);
    } else moveWidget(dx, dy, drag.origin, true);
  });
  for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    stage.addEventListener(event, ({pointerId, type}) => {
      if (drag?.id !== pointerId) return;
      const {bytes, before, erase, marquee: selecting} = drag;
      drag = undefined;
      if (selecting) {
        marquee.hidden = true;
        if (type === 'pointercancel') selectWidget(-1);
        return;
      }
      showGuides();
      if (bytes) {
        if (type === 'pointerup' && erase) eraseLayers(bytes);
        if (type === 'pointerup' && !erase) {
          const layer = cropInk(bytes, schema.width, schema.height);
          if (layer) {
            current().selection = layers().length;
            setDraft([...layers(), layer], true);
          }
        }
        compose();
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
    const group = current().group;
    if (drag || tool !== 'select' || !Array.isArray(offset) ||
        (!hitbox && (event.target !== stage || !selectedIndices().length))) return;
    event.preventDefault();
    const step = event.shiftKey ? 10 : 1;
    const [dx, dy] = canvasDirection(offset[0] * step, offset[1] * step);
    if (group.length && (!hitbox || group.includes(Number(hitbox.dataset.index)))) moveGroup(dx, dy);
    else {
      if (hitbox) selectWidget(Number(hitbox.dataset.index));
      moveWidget(dx, dy);
    }
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
    if (event.detail === 0 && button && !drag && !paletteDrag && !layerDrag) {
      pickWidget(definition(button.dataset.widget));
    }
  });
  palette.addEventListener('pointerdown', (event) => {
    const button = event.target.closest('button[data-widget]');
    if (!button || button.disabled || drag || paletteDrag || layerDrag || event.button !== 0) return;
    event.preventDefault();
    button.focus({preventScroll: true});
    button.setPointerCapture(event.pointerId);
    paletteDrag = {
      id: event.pointerId, item: definition(button.dataset.widget), button,
      startX: event.clientX, startY: event.clientY, moved: false,
    };
  });
  palette.addEventListener('pointermove', (event) => {
    if (paletteDrag?.id !== event.pointerId) return;
    paletteDrag.moved ||= Math.hypot(event.clientX - paletteDrag.startX, event.clientY - paletteDrag.startY) >= 5;
    if (!paletteDrag.moved) return;
    const point = canvasPoint(event);
    dropMarker.hidden = !insideCanvas(point);
    if (!dropMarker.hidden) position(dropMarker, widgetAt(paletteDrag.item.template, point));
    else showGuides();
  });
  for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    palette.addEventListener(event, (event) => {
      if (paletteDrag?.id !== event.pointerId) return;
      const {item, button, moved} = paletteDrag;
      paletteDrag = undefined;
      dropMarker.hidden = true;
      showGuides();
      if (event.type !== 'pointerup') return;
      const point = canvasPoint(event);
      if (insideCanvas(point)) pickWidget(item, point);
      else if (!moved && button.contains(document.elementFromPoint(event.clientX, event.clientY))) pickWidget(item);
    });
  }
  photoFile.addEventListener('change', () => {
    const file = photoFile.files[0];
    photoFile.value = '';
    importPhoto(file, photoPoint);
    photoPoint = undefined;
  });
  cropButton.addEventListener('click', () => {
    if (photoCrop.active) {
      photoCrop.close();
      return;
    }
    const layer = layers()[current().selection];
    if (layer?.type !== 'photo' || drag || layerDrag || paletteDrag) return;
    const {photo, crop: [cropX, cropY, cropW, cropH]} = layer;
    const box = controlBounds(layer);
    const scale = Math.min(box.w / cropW, box.h / cropH, schema.width / photo.w, schema.height / photo.h);
    const w = photo.w * scale;
    const h = photo.h * scale;
    const x = clamp(box.x + (box.w - cropW * scale) / 2 - cropX * scale, 0, Math.max(0, schema.width - w));
    const y = clamp(box.y + (box.h - cropH * scale) / 2 - cropY * scale, 0, Math.max(0, schema.height - h));
    position(cropSurface, {x, y, w, h});
    setTool('select');
    photoCrop.open({photo, crop: layer.crop, onApply: crop => editWidget({crop})});
  });
  stage.addEventListener('dragover', event => {
    if (event.dataTransfer.types.includes('Files')) event.preventDefault();
  });
  stage.addEventListener('drop', event => {
    const file = event.dataTransfer.files[0];
    if (!file) return;
    event.preventDefault();
    importPhoto(file, canvasPoint(event));
  });

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
  clearDrawing.addEventListener('click', () => {
    if (!drag) changeLayers(layer => layer.type === 'drawing' ? null : layer);
  });
  element('editor-remove-drawing').addEventListener('click', () => {
    if (!drag && layers()[current().selection]?.type === 'drawing') removeLayer(current().selection);
  });
  for (const name of ['keydown', 'keyup']) {
    window.addEventListener(name, (event) => {
      if (event.key !== 'Shift' || !drag?.corner || !drag.delta) return;
      resizeWidget(drag.delta.dx, drag.delta.dy, drag, event.shiftKey);
    });
  }
  editor.addEventListener('keydown', (event) => {
    if (photoCrop.active || content.hidden || event.isComposing || event.target.matches('input, textarea, select')) return;
    const selected = selectedIndices();
    if ((event.key === 'Delete' || event.key === 'Backspace') &&
        selected.length && !drag && !layerDrag && !paletteDrag) {
      event.preventDefault();
      if (selected.length === 1) removeLayer(selected[0]);
      else setDraft(layers().filter((_, index) => !selected.includes(index)), true);
      (widgetButtons[current().selection] ?? palette.firstElementChild).focus();
    } else if (['Enter', 'F2'].includes(event.key) && event.target.matches('button[data-index]') &&
        layers()[Number(event.target.dataset.index)]?.type === 'text') {
      event.preventDefault();
      startText(Number(event.target.dataset.index));
    }
  });
  window.addEventListener('keydown', (event) => {
    if (photoCrop.active || content.hidden || event.isComposing || !(event.ctrlKey || event.metaKey) ||
        event.key.toLowerCase() !== 'z' || event.target.isContentEditable ||
        event.target.matches?.('input, textarea, select')) return;
    event.preventDefault();
    if (event.shiftKey) stepHistory('redo', 'undo');
    else stepHistory('undo', 'redo');
  });

  remove.addEventListener('click', () => {
    removeLayer(current().selection);
    (widgetButtons[current().selection] ?? palette.firstElementChild).focus();
  });

  properties.addEventListener('change', (event) => {
    const field = event.target;
    const name = field.dataset.property;
    if (!name || name === 'text') return;
    const widget = layers()[current().selection];
    const customFormat = widget && definition(widget.type)?.customFormat;
    if (customFormat) {
      if (name === 'format') {
        if (!field.value.trim()) field.value = customFormat;
        editWidget({format: field.value});
        return;
      }
      if (name === 'variant' && field.value === 'custom') {
        editWidget({variant: 'custom', format: widget.format ?? customFormat});
        return;
      }
    }
    if (name === 'variant' && widget?.type === 'divider' && field.value !== widget.variant) {
      editDivider(widget, field.value, Number(dividerLength.value), Number(dividerThickness.value));
      return;
    }
    if (field.type === 'number') {
      if (!Number.isFinite(field.valueAsNumber)) {
        updateInspector();
        return;
      }
      const value = clamp(Math.round(field.valueAsNumber), Number(field.min), Number(field.max));
      field.value = value;
      const box = controlBounds(widget);
      editWidget(boxChange(widget, {...box, [name]: value}));
    } else {
      editWidget({[name]: field.value});
    }
  });
  alignment.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-align]');
    const widget = layers()[current().selection];
    if (!button || !widget || drag || paletteDrag || layerDrag) return;
    const align = button.dataset.align;
    const {placement} = widget;
    const change = {align};
    if (placement && (widget.align !== align || placement.referenceWidth === undefined)) {
      const {x, w} = controlBounds(widget);
      change.placement = {...placement, x, referenceWidth: w};
    }
    editWidget(change);
  });
  boldControl.addEventListener('click', () => {
    const layer = layers()[current().selection];
    if (!layer || boldControl.hidden || drag || paletteDrag || layerDrag) return;
    const mono = layer.font.startsWith('mono');
    const bold = layer.font.endsWith('bold');
    editWidget({font: mono ? (bold ? 'mono' : 'mono-bold') : (bold ? 'regular' : 'bold')});
  });
  canvasAlignment.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-canvas-align]');
    const box = selectionBounds();
    if (!button || !box || drag || paletteDrag || layerDrag) return;
    const side = button.dataset.canvasAlign;
    const horizontal = ['left', 'center', 'right'].indexOf(side);
    const vertical = ['top', 'middle', 'bottom'].indexOf(side);
    const [axisX, axisY] = canvasDirection(Number(horizontal >= 0), Number(vertical >= 0));
    const alignment = Math.max(horizontal, vertical) - 1;
    const x = axisX ? Math.round((schema.width - box.w) * (axisX * alignment + 1) / 2) : box.x;
    const y = axisY ? Math.round((schema.height - box.h) * (axisY * alignment + 1) / 2) : box.y;
    if (current().group.length) moveGroup(x - box.x, y - box.y);
    else moveWidget(x - box.x, y - box.y);
  });
  dividerSettings.addEventListener('change', () => {
    const widget = layers()[current().selection];
    if (widget?.type !== 'divider') return;
    if (!Number.isFinite(dividerLength.valueAsNumber) || !Number.isFinite(dividerThickness.valueAsNumber)) {
      updateInspector();
      return;
    }
    const length = clamp(Math.round(dividerLength.valueAsNumber), 1, Number(dividerLength.max));
    const thickness = clamp(Math.round(dividerThickness.valueAsNumber), 1, Number(dividerThickness.max));
    editDivider(widget, widget.variant, length, thickness);
  });
  fontSize.addEventListener('change', () => {
    if (fontOptions.hidden) return;
    if (!Number.isFinite(fontSize.valueAsNumber)) {
      updateInspector();
      return;
    }
    const size = clamp(Math.round(fontSize.valueAsNumber), Number(fontSize.min), Number(fontSize.max));
    fontSize.value = size;
    editWidget({size});
  });
  scaleField.addEventListener('change', () => {
    const widget = layers()[current().selection];
    if (!widget || widget.type === 'drawing') return;
    if (!Number.isFinite(scaleField.valueAsNumber)) {
      updateInspector();
      return;
    }
    const size = clamp(Math.round(scaleField.valueAsNumber), 1, Number(scaleField.max));
    const box = controlBounds(widget);
    const ratio = size / Math.max(box.w, box.h);
    scaleField.value = size;
    editWidget(boxChange(widget, {...box, w: Math.max(1, Math.round(box.w * ratio)),
      h: Math.max(1, Math.round(box.h * ratio))}));
  });
  for (const event of ['input', 'compositionend']) {
    fields.text.addEventListener(event, ({isComposing}) => {
      if (isComposing) return;
      const text = [...fields.text.value].slice(0, 120).join('');
      if (fields.text.value !== text) fields.text.value = text;
      editWidget({text});
    });
  }
  fields.text.addEventListener('keydown', (event) => {
    if (event.isComposing || event.key !== 'Enter' || event.shiftKey) return;
    event.preventDefault();
    hitboxes[current().selection]?.focus({preventScroll: true});
  });

  reset.addEventListener('click', () => {
    current().selection = -1;
    setDraft(restoreLayout(current()), true);
    (save.disabled ? back : save).focus();
  });
  blank.addEventListener('click', () => {
    current().selection = -1;
    setDraft([], true);
    save.focus();
  });

  retry.addEventListener('click', () => schedulePreview(0));

  libraryToggle.addEventListener('click', () => setLibraryVisible(library.hidden));
  libraryName.addEventListener('input', updateLibraryControls);
  libraryForm.addEventListener('submit', (event) => {
    event.preventDefault();
    if (drag || layerDrag || paletteDrag) return;
    const name = libraryName.value.trim().normalize('NFC');
    if (!name) {
      setText(libraryStatus, 'Enter a layout name with 1–64 characters.');
      return;
    }
    const draft = current();
    const snapshot = layers();
    requestLibrary({
      payload: {name, layout: snapshot},
      onSuccess: ({entries}) => {
        draft.librarySaved = {name, layout: snapshot};
        updateStatus();
        libraryForm.reset();
        showLibraryEntries(entries, name);
        setText(libraryStatus, 'Layout saved to the library.');
      },
    });
  });
  libraryList.addEventListener('click', (event) => {
    const card = event.target.closest('.editor-library-card');
    if (card) {
      chooseLibraryLayout(card);
      return;
    }
    const name = event.target.closest('button[data-delete]')?.dataset.delete;
    if (!name || librarySelection || !window.confirm(translate('Delete this saved layout?'))) return;
    requestLibrary({
      payload: {name, delete: true},
      onSuccess: ({entries}) => {
        if (current().librarySaved?.name === name) current().librarySaved = null;
        updateStatus();
        showLibraryEntries(entries, librarySelected === name ? null : librarySelected);
      },
    });
  });

  save.addEventListener('click', async () => {
    finishText(true);
    const draft = current();
    if (!hasChanges(draft) || savingScreen || librarySelection || drag || paletteDrag || layerDrag) return;
    const payload = {screen, layout: draft.layout, displaySize: displaySize()};
    const saved = draft.librarySaved;
    if (saved?.name && JSON.stringify(saved.layout) === JSON.stringify(draft.layout)) payload.libraryName = saved.name;
    savingScreen = screen;
    draft.message = 'Saving layout…';
    updateStatus();
    try {
      const response = await request('/api/layouts', {payload, fallback: 'Could not save the layout.'});
      const data = await response.json();
      if (draft.layout === payload.layout) draft.layout = data.layout;
      draft.saved = data.layout;
      draft.message = 'Layout saved. The display will refresh shortly.';
    } catch (error) {
      draft.message = error instanceof TypeError ? 'The Pi did not respond.' : error.message;
      if (draft.message === badCode) showAccessError(draft.message);
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
      if (!library.hidden) showLibraryEntries(libraryEntries, librarySelected);
      updateInspector();
      updateStatus();
    } else if (!records.some(record => record.oldValue !== root.getAttribute('data-theme'))) {
      return;
    }
    if (drag?.bytes) paintInk(drawing, drag.bytes, inkColor());
    schedulePreview();
  }).observe(document.documentElement, {attributeOldValue: true, attributeFilter: ['lang', 'data-theme']});

  loadLayouts();
  fetch('/api/state').then(response => response.ok ? response.json() : null).then(data => {
    if (!data) return;
    document.documentElement.dataset.theme = data.theme;
    applyLanguage(data.language);
  }).catch(() => {});
}
