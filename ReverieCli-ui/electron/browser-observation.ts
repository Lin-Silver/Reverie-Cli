/** Fixed functions run only in the guest's isolated CDP world; arguments are data. */
export const OBSERVE_FUNCTION = String.raw`function (observationId, bindingName) {
  const previous = globalThis.__reverieBrowserObservation;
  if (previous) {
    previous.observer.disconnect();
    for (const name of previous.events) removeEventListener(name, previous.invalidate, true);
  }
  const viewport = { width: innerWidth, height: innerHeight, device_scale_factor: devicePixelRatio };
  const store = { id: observationId, viewport, entries: new Map(), dirty: false, events: ['scroll', 'resize', 'input', 'change', 'focusin'] };
  const clean = (value, length) => String(value ?? '').replace(/[\x00-\x1f\x7f]/g, ' ').slice(0, length);
  const parent = node => node.parentElement || node.getRootNode()?.host || null;
  const bounds = node => {
    if (!node.isConnected) return null;
    const style = getComputedStyle(node);
    if (style.display === 'none' || style.visibility !== 'visible' || Number(style.opacity) === 0 || node.closest('[aria-hidden="true"]')) return null;
    const rect = node.getBoundingClientRect();
    let left = Math.max(0, rect.left), top = Math.max(0, rect.top);
    let right = Math.min(innerWidth, rect.right), bottom = Math.min(innerHeight, rect.bottom);
    let ancestor = parent(node), depth = 0;
    for (; ancestor && depth < 64; ancestor = parent(ancestor), depth++) {
      const overflow = getComputedStyle(ancestor);
      if (Number(overflow.opacity) === 0 || ancestor.getAttribute('aria-hidden') === 'true') return null;
      const clipped = ancestor.getBoundingClientRect();
      if (/(auto|scroll|hidden|clip)/.test(overflow.overflowX)) { left = Math.max(left, clipped.left + ancestor.clientLeft); right = Math.min(right, clipped.left + ancestor.clientLeft + ancestor.clientWidth); }
      if (/(auto|scroll|hidden|clip)/.test(overflow.overflowY)) { top = Math.max(top, clipped.top + ancestor.clientTop); bottom = Math.min(bottom, clipped.top + ancestor.clientTop + ancestor.clientHeight); }
    }
    if (ancestor) return null;
    return right > left && bottom > top ? { x: left, y: top, width: right - left, height: bottom - top } : null;
  };
  const point = (node, rect) => {
    const root = node.getRootNode();
    for (const [dx, dy] of [[.5,.5],[.2,.2],[.8,.2],[.2,.8],[.8,.8]]) {
      const x = rect.x + rect.width * dx, y = rect.y + rect.height * dy;
      let hit = document.elementFromPoint(x,y);
      while (hit?.shadowRoot?.elementFromPoint) {
        const child = hit.shadowRoot.elementFromPoint(x,y);
        if (!child || child === hit) break;
        hit = child;
      }
      if (hit === node || node.contains(hit) || root.host === hit) return { x, y };
    }
    return null;
  };
  const describe = node => {
    const rect = bounds(node);
    if (!rect) return null;
    const tag = node.tagName.toLowerCase();
    const kind = tag === 'input' ? node.type : '';
    let role = node.getAttribute('role') || ({ button:'button', a:'link', textarea:'textbox', select:'combobox', iframe:'iframe', h1:'heading', h2:'heading', h3:'heading', h4:'heading', h5:'heading', h6:'heading' })[tag] || (tag === 'input' ? ['checkbox','radio','range','number'].includes(kind) ? ({range:'slider',number:'spinbutton'})[kind] || kind : ['button','submit','reset','file'].includes(kind) ? 'button' : 'textbox' : node.isContentEditable ? 'textbox' : 'text');
    let name = node.getAttribute('aria-label') || '';
    if (!name && node.getAttribute('aria-labelledby')) {
      name = node.getAttribute('aria-labelledby').split(/\s+/).map(id => node.getRootNode().getElementById?.(id)?.innerText || '').join(' ');
    }
    if (!name && node.labels?.length) name = Array.from(node.labels).map(label => label.innerText).join(' ');
    if (!name) name = node.getAttribute('placeholder') || node.getAttribute('alt') || node.getAttribute('title') || (['button','a','label','select'].includes(tag) ? node.innerText : '') || '';
    const text = kind === 'password' ? '' : ['input','textarea'].includes(tag) ? node.value : node.innerText || '';
    const editable = !node.disabled && !node.readOnly && !['file','checkbox','radio','range','button','submit','reset','hidden','image','color'].includes(kind) && (tag === 'input' || tag === 'textarea' || node.isContentEditable);
    const result = { role: clean(role,32), name: clean(name,128), text: clean(text,512), editable, bounds: rect };
    return { result, fingerprint: JSON.stringify([result, tag, kind, node.disabled, node.readOnly, node.getAttribute('href'), node.getAttribute('aria-disabled')]), point: point(node,rect) };
  };
  store.describe = describe;
  store.invalidate = () => {
    if (store.dirty) return;
    store.dirty = true;
    const binding = globalThis[bindingName];
    if (typeof binding === 'function') binding(JSON.stringify({ observation_id: observationId }));
  };
  store.observer = new MutationObserver(store.invalidate);
  store.observer.observe(document, { subtree:true, childList:true, attributes:true, characterData:true });
  for (const name of store.events) addEventListener(name, store.invalidate, true);
  globalThis.__reverieBrowserObservation = store;
  const roots = [document], interactive = [], textNodes = [];
  let scanned = 0;
  for (let rootIndex = 0; rootIndex < roots.length && rootIndex < 64; rootIndex++) {
    if (rootIndex) store.observer.observe(roots[rootIndex], { subtree:true, childList:true, attributes:true, characterData:true });
    for (const node of roots[rootIndex].querySelectorAll('*')) {
      if (++scanned > 10000) break;
      if (node.shadowRoot && roots.length < 64) roots.push(node.shadowRoot);
      if (node.matches('button,a[href],input:not([type="hidden"]),textarea,select,[role],[contenteditable="true"],[tabindex]')) interactive.push(node);
      else if (node.matches('h1,h2,h3,h4,h5,h6,p,li,label,dt,dd,iframe')) textNodes.push(node);
    }
    if (scanned > 10000) break;
  }
  const elements = [];
  for (const node of [...interactive,...textNodes]) {
    if (elements.length >= 256) break;
    const described = describe(node);
    if (!described || !described.point || !described.result.name && !described.result.text && described.result.role === 'text') continue;
    const elementId = 'e' + elements.length;
    store.entries.set(elementId, { node, ...described });
    elements.push({ element_id:elementId, ...described.result, point:described.point });
  }
  return { viewport, elements };
}`;

export const VERIFY_OBSERVATION_FUNCTION = String.raw`function (observationId) {
  const store = globalThis.__reverieBrowserObservation;
  return Boolean(store && store.id === observationId && !store.dirty && innerWidth === store.viewport.width && innerHeight === store.viewport.height && devicePixelRatio === store.viewport.device_scale_factor);
}`;

export const RESOLVE_ELEMENT_FUNCTION = String.raw`function (observationId, elementId) {
  const store = globalThis.__reverieBrowserObservation;
  if (!store || store.id !== observationId || store.dirty || innerWidth !== store.viewport.width || innerHeight !== store.viewport.height || devicePixelRatio !== store.viewport.device_scale_factor) return null;
  const entry = store.entries.get(elementId);
  if (!entry || !entry.node.isConnected || entry.node.disabled || entry.node.getAttribute('aria-disabled') === 'true' || entry.node.tagName === 'IFRAME' || entry.node.tagName === 'INPUT' && entry.node.type === 'file') return null;
  const current = store.describe(entry.node);
  if (!current || current.fingerprint !== entry.fingerprint || !current.point || current.point.x !== entry.point.x || current.point.y !== entry.point.y) return null;
  return entry.node;
}`;

export const FOCUS_ELEMENT_FUNCTION = String.raw`function (replace) {
  if (!this.isConnected || this.disabled || this.readOnly) return false;
  this.focus({preventScroll:true});
  if (replace) {
    if (this.tagName === 'INPUT' || this.tagName === 'TEXTAREA') {
      if (typeof this.select !== 'function') return false;
      this.select();
    } else if (this.isContentEditable) {
      const selection = getSelection(), range = document.createRange();
      range.selectNodeContents(this); selection.removeAllRanges(); selection.addRange(range);
    } else return false;
  }
  let active = document.activeElement;
  while (active?.shadowRoot?.activeElement) active = active.shadowRoot.activeElement;
  return this.isConnected && (active === this || this.isContentEditable && this.contains(active));
}`;

export const VERIFY_FOCUSED_ELEMENT_FUNCTION = String.raw`function (elementId) {
  const store = globalThis.__reverieBrowserObservation;
  const entry = store?.entries.get(elementId);
  const current = entry && store.describe(this);
  let active = document.activeElement;
  while (active?.shadowRoot?.activeElement) active = active.shadowRoot.activeElement;
  return Boolean(entry?.node === this && current?.fingerprint === entry.fingerprint && this.isConnected && !this.disabled && !this.readOnly && (active === this || this.isContentEditable && this.contains(active)));
}`;

export const VERIFY_KEY_FUNCTION = String.raw`function (observationId) {
  const store = globalThis.__reverieBrowserObservation;
  if (!store || store.id !== observationId || store.dirty) return false;
  let active = document.activeElement;
  while (active?.shadowRoot?.activeElement) active = active.shadowRoot.activeElement;
  return !(active?.tagName === 'IFRAME' || active?.tagName === 'INPUT' && active.type === 'file');
}`;

export const SCROLL_FUNCTION = String.raw`function (observationId, elementId, dx, dy) {
  const store = globalThis.__reverieBrowserObservation;
  if (!store || store.id !== observationId || store.dirty) return false;
  let node = elementId === null ? document.scrollingElement : this;
  if (!node || elementId !== null && store.entries.get(elementId)?.node !== node) return false;
  while (node && node !== document.scrollingElement) {
    const style = getComputedStyle(node);
    const horizontal = dx && /auto|scroll|overlay/.test(style.overflowX) && node.scrollWidth > node.clientWidth;
    const vertical = dy && /auto|scroll|overlay/.test(style.overflowY) && node.scrollHeight > node.clientHeight;
    if (horizontal || vertical) break;
    node = node.parentElement || node.getRootNode()?.host;
  }
  (node || window).scrollBy({left:dx,top:dy,behavior:'instant'});
  return true;
}`;
