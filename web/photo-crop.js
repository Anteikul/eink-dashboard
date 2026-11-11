function createPhotoCrop(dialog, paint) {
  const find = id => dialog.querySelector('#editor-photo-' + id);
  const form = dialog.querySelector('form');
  const controls = find('controls');
  const status = find('status');
  const surface = find('surface');
  const image = find('image');
  const selection = find('selection');
  const apply = find('apply');
  const reset = find('reset');
  const fields = [...dialog.querySelectorAll('[data-crop]')];
  let edit;
  let drag;

  const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
  const fullPhoto = ({w, h}) => [0, 0, w, h];

  function setCrop(crop) {
    edit.crop = crop;
    const {w: width, h: height} = edit.photo;
    const [x, y, w, h] = crop;
    Object.assign(selection.style, {
      left: x / width * 100 + '%', top: y / height * 100 + '%',
      width: w / width * 100 + '%', height: h / height * 100 + '%',
    });
    const limits = [width - w, height - h, width - x, height - y];
    for (const [index, field] of fields.entries()) {
      field.max = limits[index];
      field.value = crop[index];
    }
  }

  function present(photo, crop) {
    edit.photo = photo;
    paint(image, photo);
    surface.style.setProperty('--photo-ratio', photo.w / photo.h);
    setCrop(crop ?? fullPhoto(photo));
    controls.hidden = reset.hidden = apply.disabled = false;
    setText(status, '');
  }

  async function open({photo, crop, load, onApply}) {
    if (dialog.open || edit) return;
    const controller = new AbortController();
    edit = {controller, onApply};
    controls.hidden = reset.hidden = apply.disabled = true;
    setText(apply, load ? 'Add photo' : 'Apply crop');
    setText(status, load ? 'Converting photo to black and white…' : '');
    dialog.returnValue = '';
    dialog.showModal();
    try {
      const source = photo ?? await load(controller.signal);
      if (!controller.signal.aborted) present(source, crop);
    } catch (error) {
      if (!controller.signal.aborted) setText(status, error.message);
    }
  }

  function point(event) {
    const bounds = surface.getBoundingClientRect();
    return [
      clamp(Math.round((event.clientX - bounds.left) / bounds.width * edit.photo.w), 0, edit.photo.w),
      clamp(Math.round((event.clientY - bounds.top) / bounds.height * edit.photo.h), 0, edit.photo.h),
    ];
  }

  surface.addEventListener('pointerdown', event => {
    if (!edit?.photo || drag || event.button !== 0) return;
    event.preventDefault();
    drag = {id: event.pointerId, start: point(event), corner: event.target.dataset.corner, crop: edit.crop};
    surface.setPointerCapture(event.pointerId);
  });
  surface.addEventListener('pointermove', event => {
    if (drag?.id !== event.pointerId) return;
    const [x, y] = point(event);
    const [startX, startY] = drag.start;
    if (x === startX && y === startY && !drag.moved) return;
    drag.moved = true;
    if (drag.corner) {
      const [left, top, w, h] = drag.crop;
      const west = drag.corner.includes('w');
      const north = drag.corner.includes('n');
      const right = left + w;
      const bottom = top + h;
      const l = west ? clamp(left + x - startX, 0, right - 1) : left;
      const t = north ? clamp(top + y - startY, 0, bottom - 1) : top;
      const r = west ? right : clamp(right + x - startX, left + 1, edit.photo.w);
      const b = north ? bottom : clamp(bottom + y - startY, top + 1, edit.photo.h);
      setCrop([l, t, r - l, b - t]);
    } else {
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
  for (const field of fields) {
    field.addEventListener('change', () => {
      const crop = edit.crop.slice();
      if (Number.isFinite(field.valueAsNumber)) {
        crop[Number(field.dataset.crop)] = clamp(Math.round(field.valueAsNumber), Number(field.min), Number(field.max));
      }
      setCrop(crop);
    });
  }
  reset.addEventListener('click', () => setCrop(fullPhoto(edit.photo)));
  find('cancel').addEventListener('click', () => dialog.close());
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!apply.disabled) dialog.close('apply');
  });
  dialog.addEventListener('close', () => {
    const previous = edit;
    edit = drag = undefined;
    previous.controller.abort();
    if (dialog.returnValue === 'apply') previous.onApply(previous.photo, previous.crop);
  });
  return {open};
}
