import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

/**
 * localStorage-backed state.
 */
export function usePersistedState(key, initial) {
  const [v, setV] = useState(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw != null) return JSON.parse(raw);
    } catch {
      /* noop */
    }
    return initial;
  });
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(v));
    } catch {
      /* noop */
    }
  }, [key, v]);
  return [v, setV];
}

/**
 * Collapsible section with a titled header + persisted open/closed state.
 *
 * Props:
 *  - id: stable string for localStorage key
 *  - title: header text
 *  - icon:  optional lucide icon element to place before the title
 *  - right: optional right-aligned node (e.g. action buttons)
 *  - defaultOpen: default state (defaults to true)
 *  - children: body content
 *  - testid: base data-testid for the panel (header uses `${testid}-header`)
 */
export function CollapsiblePanel({
  id,
  title,
  icon,
  right,
  defaultOpen = true,
  testid,
  children,
}) {
  const [open, setOpen] = usePersistedState(`panel:${id}`, defaultOpen);
  const toggle = useCallback(() => setOpen((o) => !o), [setOpen]);
  return (
    <section
      data-testid={testid}
      className="border-b border-[#2a2a2a]"
    >
      <div className="flex items-center justify-between gap-2 px-3 py-1.5">
        <button
          type="button"
          data-testid={testid ? `${testid}-header` : undefined}
          onClick={toggle}
          className="flex min-w-0 flex-1 items-center gap-1.5 text-left text-neutral-300 hover:text-[#00f0ff]"
          aria-expanded={open}
        >
          {open ? (
            <ChevronDown className="h-3 w-3 shrink-0 text-neutral-500" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0 text-neutral-500" />
          )}
          {icon && <span className="shrink-0 text-[#00f0ff]">{icon}</span>}
          <span className="truncate mono text-[10px] uppercase tracking-[0.3em]">
            {title}
          </span>
        </button>
        {right && <div onClick={(e) => e.stopPropagation()}>{right}</div>}
      </div>
      {open && <div className="pb-2">{children}</div>}
    </section>
  );
}
