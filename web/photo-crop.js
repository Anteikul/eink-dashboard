function createPhotoCrop(surface, button, paint, canvasPoint) {
  const image = surface.querySelector('#editor-photo-image');
  let edit;
  let drag;

  const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
  const changed = () => edit?.crop.some((value, index) => value !== edit.original[index]);

  function setCrop(crop) {
    edit.crop = crop;
    const {w: width, h: height} = edit.photo;
    const [x, y, w, h] = crop;
    surface.style.setProperty('--crop-left', x / width * 100 + '%');
    surface.style.setProperty('--crop-top', y / height * 100 + '%');
    surface.style.setProperty('--crop-width', w / width * 100 + '%');
    surface.style.setProperty('--crop-height', h / height * 100 + '%');
  }

  function open({photo, crop, onApply}) {
    edit = {photo, original: crop, onApply};
    paint(image, photo);
    setCrop(crop);
    surface.hidden = false;
    button.setAttribute('aria-pressed', 'true');
    surface.focus({preventScroll: true});
  }

  function close(apply = true) {
    if (!edit) return;
    const previous = edit;
    const commit = apply && changed();
    if (drag && surface.hasPointerCapture(drag.id)) surface.releasePointerCapture(drag.id);
    edit = drag = undefined;
    surface.hidden = true;
    button.setAttribute('aria-pressed', 'false');
    if (commit) previous.onApply(previous.crop);
  }

  function closeOutside(event) {
    if (edit && !surface.contains(event.target) && !button.contains(event.target)) close();
  }
  surface.ownerDocument.addEventListener('pointerdown', closeOutside, true);
  surface.ownerDocument.addEventListener('click', closeOutside, true);

  function point(event) {
    const {w, h} = edit.photo;
    const {x, y} = canvasPoint(event, surface, w, h);
    return [clamp(Math.round(x), 0, w), clamp(Math.round(y), 0, h)];
  }

  function moveCrop([left, top, w, h], dx, dy) {
    setCrop([clamp(left + dx, 0, edit.photo.w - w), clamp(top + dy, 0, edit.photo.h - h), w, h]);
  }

  function resizeCrop([left, top, w, h], corner, dx, dy) {
    const west = corner.includes('w');
    const north = corner.includes('n');
    const right = left + w;
    const bottom = top + h;
    const l = west ? clamp(left + dx, 0, right - 1) : left;
    const t = north ? clamp(top + dy, 0, bottom - 1) : top;
    const r = west ? right : clamp(right + dx, left + 1, edit.photo.w);
    const b = north ? bottom : clamp(bottom + dy, top + 1, edit.photo.h);
    setCrop([l, t, r - l, b - t]);
  }

  surface.addEventListener('pointerdown', event => {
    if (!edit || drag || event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    const [x, y] = point(event);
    const [left, top, w, h] = edit.crop;
    const inside = x >= left && x < left + w && y >= top && y < top + h;
    const move = inside && (w < edit.photo.w || h < edit.photo.h);
    drag = {id: event.pointerId, start: [x, y], corner: event.target.dataset.corner, crop: edit.crop, move};
    surface.setPointerCapture(event.pointerId);
  });
  surface.addEventListener('pointermove', event => {
    if (drag?.id !== event.pointerId) return;
    const [x, y] = point(event);
    const [startX, startY] = drag.start;
    if (x === startX && y === startY && !drag.moved) return;
    drag.moved = true;
    if (drag.corner) resizeCrop(drag.crop, drag.corner, x - startX, y - startY);
    else if (drag.move) moveCrop(drag.crop, x - startX, y - startY);
    else {
      setCrop([
        Math.min(x, startX, edit.photo.w - 1), Math.min(y, startY, edit.photo.h - 1),
        Math.max(1, Math.abs(x - startX)), Math.max(1, Math.abs(y - startY)),
      ]);
    }
  });
  for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    surface.addEventListener(name, event => {
      if (drag?.id === event.pointerId) drag = undefined;
    });
  }
  surface.addEventListener('keydown', event => {
    if (!edit || drag) return;
    if (event.key === 'Escape' || event.key === 'Enter') {
      event.preventDefault();
      event.stopPropagation();
      close(event.key === 'Enter');
      button.focus({preventScroll: true});
      return;
    }
    const dx = Number(event.key === 'ArrowRight') - Number(event.key === 'ArrowLeft');
    const dy = Number(event.key === 'ArrowDown') - Number(event.key === 'ArrowUp');
    if (!dx && !dy) return;
    event.preventDefault();
    event.stopPropagation();
    if (event.shiftKey) resizeCrop(edit.crop, 'se', dx, dy);
    else moveCrop(edit.crop, dx, dy);
  });
  return {open, close, changed, get active() { return Boolean(edit); }};
}
