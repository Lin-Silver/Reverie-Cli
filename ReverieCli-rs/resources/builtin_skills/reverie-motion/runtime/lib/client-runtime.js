// reverie-motion client runtime — dependency-free browser code that is inlined
// verbatim into every exported module. Native Reverie Motion code (MIT).
// Exports: mount(spec, root?, options?) → controller
//   controller.play(id) / reverse(id) / toggle(id) / flip(id, mutate?, {reverse}) /
//   seek(ms) / pause() / resume() / finished() / destroy() / reducedMotion

const RM_TRANSFORM_ORDER = ["translateX", "translateY", "translateZ", "scale", "scaleX", "scaleY", "rotate", "rotateX", "rotateY", "rotateZ", "skewX", "skewY"];
const RM_UNITS = {
  translateX: "px", translateY: "px", translateZ: "px", rotate: "deg", rotateX: "deg", rotateY: "deg", rotateZ: "deg",
  skewX: "deg", skewY: "deg", blur: "px", backdropBlur: "px", borderRadius: "px", width: "px", height: "px",
  fontSize: "px", letterSpacing: "px", hueRotate: "deg", top: "px", left: "px", right: "px", bottom: "px", margin: "px", padding: "px",
};
const RM_FILTERS = { blur: "blur", brightness: "brightness", saturate: "saturate", contrast: "contrast", hueRotate: "hue-rotate" };

function rmValue(prop, value) {
  return typeof value === "number" ? `${value}${RM_UNITS[prop] || ""}` : String(value);
}

/** Convert a Reverie keyframe property map into WAAPI/CSS declarations. */
function rmFrameToCss(props) {
  const out = {};
  const transform = [];
  for (const p of RM_TRANSFORM_ORDER) if (props[p] !== undefined) transform.push(`${p}(${rmValue(p, props[p])})`);
  if (transform.length) out.transform = transform.join(" ");
  const filter = [];
  for (const p of Object.keys(RM_FILTERS)) if (props[p] !== undefined) filter.push(`${RM_FILTERS[p]}(${rmValue(p, props[p])})`);
  if (filter.length) out.filter = filter.join(" ");
  for (const [p, v] of Object.entries(props)) {
    if (RM_TRANSFORM_ORDER.includes(p) || RM_FILTERS[p]) continue;
    if (p === "backdropBlur") {
      out.backdropFilter = `blur(${rmValue(p, v)})`;
      continue;
    }
    if (p === "strokeDashoffset" || p === "opacity") {
      out[p] = String(v);
      continue;
    }
    out[p] = rmValue(p, v);
  }
  return out;
}

function rmSupportsLinear() {
  try {
    return typeof CSS !== "undefined" && CSS.supports("animation-timing-function", "linear(0, 0.5 50%, 1)");
  } catch {
    return false;
  }
}

function rmEasing(e, compiled) {
  if (!e) return "ease-out";
  if (e.css) return e.css;
  if (e.type === "spring") return compiled.linear && rmSupportsLinear() ? compiled.linear : compiled.fallback || "cubic-bezier(0.22, 1, 0.36, 1)";
  return compiled.css || "ease-out";
}

function rmPrefersReduced(options) {
  if (options && typeof options.reducedMotion === "boolean") return options.reducedMotion;
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function rmStaggerIndex(i, count, from) {
  if (from === "end") return count - 1 - i;
  if (from === "center") return Math.round(Math.abs(i - (count - 1) / 2));
  return i;
}

function rmMulberry(seed) {
  let a = seed >>> 0;
  return function next() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Deterministic particle field: positions are a pure function of time. */
function rmParticles(component, host, ctx) {
  const cfg = component.particles;
  const canvas = document.createElement("canvas");
  canvas.setAttribute("aria-hidden", "true");
  canvas.dataset.rmParticles = component.id;
  canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%;pointer-events:none;display:block";
  if (getComputedStyle(host).position === "static") host.style.position = "relative";
  host.appendChild(canvas);
  const g = canvas.getContext("2d");
  const rand = rmMulberry(cfg.seed);
  const items = Array.from({ length: cfg.count }, () => ({
    x: rand(), y: rand(),
    vx: (rand() - 0.5) * cfg.drift, vy: -(0.25 + rand() * 0.75),
    size: cfg.sizeMin + rand() * (cfg.sizeMax - cfg.sizeMin),
    color: cfg.colors[Math.floor(rand() * cfg.colors.length)],
    phase: rand() * Math.PI * 2, wobble: 0.5 + rand(),
  }));
  let w = 0;
  let h = 0;
  let dpr = 1;
  function resize() {
    const r = host.getBoundingClientRect();
    dpr = Math.min(window.devicePixelRatio || 1, cfg.maxDpr);
    w = Math.max(1, r.width);
    h = Math.max(1, r.height);
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  function draw(tMs) {
    const t = tMs / 1000;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    for (const p of items) {
      const px = (((p.x * w + p.vx * cfg.speed * t + Math.sin(t * p.wobble + p.phase) * 6) % w) + w) % w;
      const py = (((p.y * h + p.vy * cfg.speed * t) % h) + h) % h;
      const alpha = cfg.twinkle ? 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * 2 * p.wobble + p.phase)) : 0.9;
      g.globalAlpha = alpha;
      g.fillStyle = p.color;
      g.beginPath();
      g.arc(px, py, p.size, 0, Math.PI * 2);
      g.fill();
    }
    g.globalAlpha = 1;
  }
  resize();
  const ro = typeof ResizeObserver === "function" ? new ResizeObserver(() => { resize(); draw(state.t); }) : null;
  if (ro) ro.observe(host);
  // manual: set by seek(); observers must not restart real-time playback until resume().
  const state = { t: 0, raf: 0, last: 0, visible: true, running: false, manual: false };
  const io = typeof IntersectionObserver === "function" ? new IntersectionObserver((entries) => {
    state.visible = entries.some((e) => e.isIntersecting);
    if (state.visible) start(); else stop();
  }) : null;
  if (io) io.observe(host);
  function frame(now) {
    if (!state.running) return;
    if (state.last) state.t += Math.min(64, now - state.last);
    state.last = now;
    draw(state.t);
    state.raf = requestAnimationFrame(frame);
  }
  function start() {
    if (state.running || state.manual || ctx.reduced || ctx.manualClock || document.hidden || !state.visible) return;
    state.running = true;
    state.last = 0;
    state.raf = requestAnimationFrame(frame);
  }
  function stop() {
    state.running = false;
    cancelAnimationFrame(state.raf);
  }
  const onVisibility = () => (document.hidden ? stop() : start());
  document.addEventListener("visibilitychange", onVisibility);
  draw(0);
  start();
  return {
    seek(ms) { state.manual = true; stop(); state.t = ms; draw(ms); },
    pause() { state.manual = true; stop(); },
    resume() { state.manual = false; start(); },
    destroy() { stop(); if (ro) ro.disconnect(); if (io) io.disconnect(); document.removeEventListener("visibilitychange", onVisibility); canvas.remove(); },
  };
}

export function mount(spec, root, options) {
  const scope = root || document;
  const opts = options || {};
  const ctx = { reduced: rmPrefersReduced(opts), manualClock: !!opts.manualClock, animations: new Map(), cleanups: [], fields: [] };
  const byId = new Map(spec.components.map((c) => [c.id, c]));

  // The scope element itself counts (e.g. a React ref / Svelte action on the animated element).
  function query(selector) {
    const self = scope !== document && scope.matches && scope.matches(selector) ? [scope] : [];
    return self.concat(Array.from(scope.querySelectorAll(selector)));
  }

  function elementsOf(c) {
    return c.selector ? query(c.selector) : [];
  }

  function keyframesOf(c, reduced) {
    const frames = c.keyframes.map((k) => {
      const css = rmFrameToCss(k.properties);
      css.offset = k.offset;
      if (k.easing) css.easing = rmEasing(k.easing, k.compiledEasing || {});
      return css;
    });
    if (!reduced) return frames;
    if (c.reducedMotion === "fade") {
      const first = c.keyframes[0].properties;
      const last = c.keyframes[c.keyframes.length - 1].properties;
      const finalCss = rmFrameToCss(Object.assign({}, ...c.keyframes.map((k) => k.properties)));
      return [
        Object.assign({}, finalCss, { opacity: String(first.opacity !== undefined ? first.opacity : 1), offset: 0 }),
        Object.assign({}, finalCss, { opacity: String(last.opacity !== undefined ? last.opacity : 1), offset: 1 }),
      ];
    }
    return frames;
  }

  function timingOf(c, index, reduced) {
    let delay = c.delayMs;
    if (c.stagger) delay += rmStaggerIndex(index, c.__count, c.stagger.from) * c.stagger.eachMs;
    const timing = {
      duration: c.durationMs, delay, iterations: c.iterationCount === "infinite" ? Infinity : c.iterationCount,
      direction: c.direction, fill: c.fillMode, easing: rmEasing(c.easing, c.compiledEasing || {}),
    };
    if (reduced && c.reducedMotion === "fade") Object.assign(timing, { duration: 150, delay: 0, iterations: 1, easing: "linear", direction: "normal" });
    return timing;
  }

  function applyStatic(c, el) {
    // reduced-motion "final-state" / "first-frame": no movement, end state visible.
    const props = c.reducedMotion === "first-frame" ? c.keyframes[0].properties : Object.assign({}, ...c.keyframes.map((k) => k.properties));
    const css = rmFrameToCss(props);
    for (const [k, v] of Object.entries(css)) el.style[k] = v;
  }

  function animate(c, direction) {
    const els = elementsOf(c);
    c.__count = els.length;
    const list = [];
    els.forEach((el, i) => {
      if (c.transformOrigin) el.style.transformOrigin = c.transformOrigin;
      if (ctx.reduced && c.reducedMotion !== "keep" && c.reducedMotion !== "fade") {
        if (direction === "reverse") {
          const css = rmFrameToCss(c.keyframes[0].properties);
          for (const [k, v] of Object.entries(css)) el.style[k] = v;
        } else applyStatic(c, el);
        return;
      }
      const a = el.animate(keyframesOf(c, ctx.reduced), timingOf(c, i, ctx.reduced));
      if (direction === "reverse") a.reverse();
      if (ctx.manualClock) a.pause();
      list.push(a);
    });
    ctx.animations.set(c.id, list);
    return list;
  }

  function toggle(c) {
    const current = ctx.animations.get(c.id);
    if (!current || !current.length) {
      c.__open = true;
      return animate(c, "forward");
    }
    // Interruptible: reverse from the current position instead of restarting.
    c.__open = !c.__open;
    for (const a of current) {
      if (a.playState === "finished" || a.playState === "running" || a.playState === "paused") a.reverse();
    }
    return current;
  }

  function flip(id, mutate, flipOptions) {
    const c = byId.get(id);
    if (!c || c.kind !== "flip") throw new Error(`reverie-motion: "${id}" is not a flip component`);
    const reverse = !!(flipOptions && flipOptions.reverse);
    const fromSel = reverse ? c.flip.to : c.flip.from;
    const toSel = reverse ? c.flip.from : c.flip.to;
    const from = query(fromSel)[0];
    const to = query(toSel)[0];
    if (!from || !to) throw new Error(`reverie-motion: flip targets not found (${fromSel} → ${toSel})`);
    const first = from.getBoundingClientRect();
    if (typeof mutate === "function") mutate({ from, to, reverse });
    else {
      to.hidden = false;
      from.style.visibility = "hidden";
    }
    const last = to.getBoundingClientRect();
    if (ctx.reduced && c.reducedMotion !== "keep") {
      if (c.reducedMotion === "fade") {
        const a = to.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 150, easing: "linear", fill: "both" });
        ctx.animations.set(c.id, [a]);
        return [a];
      }
      ctx.animations.set(c.id, []);
      return [];
    }
    const dx = first.left - last.left;
    const dy = first.top - last.top;
    const sx = last.width ? first.width / last.width : 1;
    const sy = last.height ? first.height / last.height : 1;
    to.style.transformOrigin = "0 0";
    const timing = { duration: c.durationMs, delay: c.delayMs, easing: rmEasing(c.easing, c.compiledEasing || {}), fill: "both" };
    const list = [to.animate([{ transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})` }, { transform: "none" }], timing)];
    if (c.flip.crossfade) {
      list.push(to.animate([{ opacity: 0.6 }, { opacity: 1 }], { duration: Math.min(c.durationMs, 220), easing: "linear", fill: "both" }));
    }
    if (ctx.manualClock) list.forEach((a) => a.pause());
    ctx.animations.set(c.id, list);
    return list;
  }

  function bind(c) {
    const trigger = c.triggerSelector ? query(c.triggerSelector)[0] || null : null;
    if (c.kind === "particles") {
      for (const el of elementsOf(c)) ctx.fields.push(rmParticles(c, el, ctx));
      return;
    }
    if (c.kind === "flip") {
      if (c.trigger === "onClick") {
        let open = false;
        const target = trigger || query(c.flip.from)[0];
        const handler = () => { flip(c.id, null, { reverse: open }); open = !open; };
        if (target) { target.addEventListener("click", handler); ctx.cleanups.push(() => target.removeEventListener("click", handler)); }
      }
      return;
    }
    if (c.trigger === "onLoad") animate(c, "forward");
    else if (c.trigger === "onClick") {
      const els = trigger ? [trigger] : elementsOf(c);
      const handler = () => (c.toggle ? toggle(c) : animate(c, "forward"));
      els.forEach((el) => el.addEventListener("click", handler));
      ctx.cleanups.push(() => els.forEach((el) => el.removeEventListener("click", handler)));
    } else if (c.trigger === "onHover") {
      if (typeof matchMedia === "function" && !matchMedia("(hover: hover)").matches) return;
      const els = trigger ? [trigger] : elementsOf(c);
      const enter = () => { if (!ctx.animations.get(c.id)) animate(c, "forward"); else { const l = ctx.animations.get(c.id); l.forEach((a) => { if (a.playbackRate < 0) a.reverse(); }); } };
      const leave = () => (ctx.animations.get(c.id) || []).forEach((a) => { if (a.playbackRate > 0) a.reverse(); });
      els.forEach((el) => { el.addEventListener("pointerenter", enter); el.addEventListener("pointerleave", leave); });
      ctx.cleanups.push(() => els.forEach((el) => { el.removeEventListener("pointerenter", enter); el.removeEventListener("pointerleave", leave); }));
    } else if (c.trigger === "onScroll") {
      const els = elementsOf(c);
      if (typeof IntersectionObserver !== "function") { animate(c, "forward"); return; }
      const io = new IntersectionObserver((entries) => {
        if (entries.some((e) => e.isIntersecting)) { animate(c, "forward"); io.disconnect(); }
      }, { threshold: 0.2 });
      els.forEach((el) => io.observe(el));
      ctx.cleanups.push(() => io.disconnect());
    }
    // manual / onState: driven through the controller.
  }

  spec.components.forEach(bind);

  const controller = {
    spec,
    get reducedMotion() { return ctx.reduced; },
    play(id) { return animate(byId.get(id), "forward"); },
    reverse(id) { return animate(byId.get(id), "reverse"); },
    toggle(id) { return toggle(byId.get(id)); },
    flip,
    animations() { return Array.from(ctx.animations.values()).flat(); },
    seek(ms) {
      for (const a of controller.animations()) { a.pause(); a.currentTime = ms; }
      for (const f of ctx.fields) f.seek(ms);
    },
    pause() { controller.animations().forEach((a) => a.pause()); ctx.fields.forEach((f) => f.pause()); },
    resume() { controller.animations().forEach((a) => a.play()); ctx.fields.forEach((f) => f.resume()); },
    finished() { return Promise.all(controller.animations().filter((a) => a.effect && a.effect.getTiming().iterations !== Infinity).map((a) => a.finished.catch(() => null))); },
    destroy() {
      ctx.cleanups.forEach((fn) => fn());
      controller.animations().forEach((a) => a.cancel());
      ctx.fields.forEach((f) => f.destroy());
      ctx.animations.clear();
    },
  };
  return controller;
}
