import { useLayoutEffect, useRef, type RefObject } from "react";

/** Reflow once, then move the canvas without stretching text or animating tracks. */
export function usePaneMotion(shell: RefObject<HTMLDivElement | null>, collapsed: boolean, ready: boolean, variant: string, resizing: boolean) {
  const previous = useRef<{ left: number; collapsed: boolean; variant: string } | null>(null);
  const motion = useRef<Animation | null>(null);

  useLayoutEffect(() => {
    const root = document.documentElement;
    const pointer = () => { root.dataset.motionInput = "pointer"; };
    const keyboard = () => { root.dataset.motionInput = "keyboard"; motion.current?.cancel(); };
    document.addEventListener("pointerdown", pointer, true);
    document.addEventListener("keydown", keyboard, true);
    return () => {
      document.removeEventListener("pointerdown", pointer, true);
      document.removeEventListener("keydown", keyboard, true);
      motion.current?.cancel();
      delete root.dataset.motionInput;
    };
  }, []);

  useLayoutEffect(() => {
    const main = shell.current?.querySelector<HTMLElement>(":scope > .main-area");
    if (!main) return;
    const left = main.offsetLeft;
    const last = previous.current;
    const transform = getComputedStyle(main).transform;
    const offset = motion.current?.playState === "running" && transform !== "none" ? new DOMMatrixReadOnly(transform).m41 : 0;
    motion.current?.cancel();
    previous.current = { left, collapsed, variant };
    if (!last || last.collapsed === collapsed || last.variant !== variant || resizing
      || document.documentElement.dataset.motionInput === "keyboard"
      || window.matchMedia("(prefers-reduced-motion: reduce)").matches || !main.animate) return;
    const distance = last.left + offset - left;
    motion.current = main.animate([
      { transform: `translateX(${distance}px)` }, { transform: "translateX(0)" },
    ], { duration: 220, easing: getComputedStyle(main).getPropertyValue("--ease-drawer").trim() });
  }, [shell, collapsed, ready, variant, resizing]);
}
