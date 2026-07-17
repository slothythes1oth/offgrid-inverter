// Bottom tab bar: Home / History (Technical arrives with phase-3 item 2).
// 44pt touch targets, safe-area padding, icon + word per the status rules.

import { NavLink, useLocation } from "react-router-dom";

function HomeIcon(p) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" {...p}>
      <path
        d="M4 11l8-8 8 8v9a1 1 0 01-1 1h-5v-6h-4v6H5a1 1 0 01-1-1v-9z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ChartIcon(p) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" {...p}>
      <path
        d="M4 19V5M4 19h16M8 15v-4M12 15V8M16 15v-6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function GaugeIcon(p) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" {...p}>
      <path
        d="M5 17a8 8 0 1114 0M12 13l3.5-3.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <circle cx="12" cy="14" r="1.6" fill="currentColor" />
    </svg>
  );
}

const TABS = [
  { to: "/", label: "Home", Icon: HomeIcon },
  { to: "/history", label: "History", Icon: ChartIcon },
  { to: "/technical", label: "Technical", Icon: GaugeIcon },
];

export default function TabBar() {
  const location = useLocation();
  return (
    <nav
      className="safe-b border-t border-border"
      style={{ background: "var(--surface)" }}
      aria-label="Pages"
    >
      <div className="flex max-w-md mx-auto">
        {TABS.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={{ pathname: to, search: location.search }}
            end={to === "/"}
            className="flex-1 flex flex-col items-center justify-center gap-0.5"
            style={({ isActive }) => ({
              minHeight: "3.1rem", // >= 44pt target
              color: isActive ? "var(--accent)" : "var(--muted)",
            })}
          >
            <Icon />
            <span className="text-[0.65rem] font-medium">{label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
