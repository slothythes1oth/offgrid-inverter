// Inline SVG icons (no icon-font dependency). currentColor so they inherit
// the status color. Each status is always icon + word + color, never color
// alone (SPEC section 7, accessibility).

const base = { width: 24, height: 24, viewBox: "0 0 24 24", fill: "none" };

export function CheckIcon(p) {
  return (
    <svg {...base} {...p}>
      <path
        d="M20 6L9 17l-5-5"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function BoltIcon(p) {
  return (
    <svg {...base} {...p}>
      <path
        d="M13 2L4 14h6l-1 8 9-12h-6l1-8z"
        fill="currentColor"
        stroke="currentColor"
        strokeWidth="1"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function WarningIcon(p) {
  return (
    <svg {...base} {...p}>
      <path
        d="M12 3l9 16H3l9-16z"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      <path
        d="M12 10v4"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
      <circle cx="12" cy="17.5" r="1.3" fill="currentColor" />
    </svg>
  );
}

export function PlugIcon(p) {
  return (
    <svg {...base} {...p}>
      <path
        d="M9 2v6M15 2v6M6 8h12v3a6 6 0 01-12 0V8zM12 17v5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
