import { useEffect, useState } from "react";

/**
 * Returns the current breakpoint bucket: 'mobile' (<768), 'tablet' (768–1023),
 * 'desktop' (1024–1919) or 'tv' (>=1920).
 *
 * Updates on window resize (debounced by rAF). SSR-safe.
 */
export function useBreakpoint() {
  const [bp, setBp] = useState(() => classify(getWidth()));
  useEffect(() => {
    // Explicit override for automated testing and demos — e.g.
    // /?forceBp=mobile forces the mobile layout regardless of viewport size.
    try {
      const sp = new URLSearchParams(window.location.search);
      const forced = sp.get("forceBp");
      if (forced && ["mobile", "tablet", "desktop", "tv"].includes(forced)) {
        setBp(forced);
        return;
      }
    } catch {
      /* noop */
    }
    let raf = 0;
    const onResize = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setBp(classify(getWidth())));
    };
    window.addEventListener("resize", onResize);
    window.addEventListener("orientationchange", onResize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("orientationchange", onResize);
    };
  }, []);
  return bp;
}

function getWidth() {
  if (typeof window === "undefined") return 1440;
  return window.innerWidth;
}

function classify(w) {
  if (w < 768) return "mobile";
  if (w < 1024) return "tablet";
  if (w < 1920) return "desktop";
  return "tv";
}

export const isNarrow = (bp) => bp === "mobile" || bp === "tablet";
