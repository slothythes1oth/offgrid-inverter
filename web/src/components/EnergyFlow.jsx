// Living energy flow (SPEC 8B.1). Three nodes — grid, battery, home — with
// animated pulses travelling along the active paths in the direction of power
// flow. Direction comes from the server's power-balance `flow`, never the
// battery current sign. Pulse speed + stroke width scale with watts in three
// buckets; the dash animation itself is continuous CSS (cheap, GPU-friendly)
// while the DATA driving it only changes at poll cadence.
//
// States: grid→home (normal, green) · grid→home + grid→battery (charging,
// green) · battery→home with grid dimmed (outage, amber) · fault freezes the
// pulses and goes red. Reduced motion (handled in index.css): dashes become
// solid static arrows; the W labels and arrowheads below are always rendered,
// so the static fallback needs no separate markup.

import { fmtW } from "../format";

// Node centers in the 180x130 viewBox.
const GRID = { x: 32, y: 34 };
const HOME = { x: 148, y: 34 };
const BATT = { x: 90, y: 104 };

const PATHS = {
  grid_home: `M ${GRID.x + 15} ${GRID.y} L ${HOME.x - 15} ${HOME.y}`,
  grid_batt: `M ${GRID.x + 8} ${GRID.y + 13} Q 52 82 ${BATT.x - 15} ${BATT.y - 5}`,
  batt_home: `M ${BATT.x + 15} ${BATT.y - 5} Q 128 82 ${HOME.x - 8} ${HOME.y + 13}`,
};

// Three-bucket scaling: watts -> [stroke width, seconds per dash cycle].
function bucket(w) {
  const a = Math.abs(w ?? 0);
  if (a >= 2500) return { width: 5, dur: "0.9s" };
  if (a >= 800) return { width: 3.6, dur: "1.4s" };
  return { width: 2.4, dur: "2.2s" };
}

function Node({ cx, cy, label, labelBelow, dim, children }) {
  return (
    <g opacity={dim ? 0.35 : 1} style={{ transition: "opacity 0.6s ease" }}>
      <circle cx={cx} cy={cy} r={13} fill="var(--surface-2)" stroke="var(--border)" strokeWidth="1.5" />
      <g transform={`translate(${cx} ${cy})`} stroke="var(--muted)" strokeWidth="1.6" fill="none">
        {children}
      </g>
      <text
        x={cx}
        y={labelBelow ? cy + 24 : cy - 19}
        textAnchor="middle"
        fontSize="10"
        fontWeight="600"
        fill="var(--text)"
      >
        {label}
      </text>
    </g>
  );
}

function FlowPath({ d, active, color, watts, frozen, label }) {
  const { width, dur } = bucket(watts);
  return (
    <g>
      {/* Track: always visible so the topology reads even when idle. */}
      <path d={d} className="flow-path" stroke="var(--surface-2)" strokeWidth="2" />
      {active && (
        <path
          d={d}
          className={`flow-path flow-active${frozen ? " flow-frozen" : ""}`}
          stroke={color}
          strokeWidth={width}
          style={{ "--dur": dur, transition: "stroke-width 0.5s ease, stroke 0.5s ease" }}
          markerEnd="url(#flow-arrow)"
        />
      )}
      {active && label && (
        <text
          x={label.x}
          y={label.y}
          textAnchor={label.anchor || "middle"}
          fontSize="9.5"
          fontWeight="600"
          className="tnum"
          fill={color}
        >
          {fmtW(Math.abs(watts ?? 0))}
        </text>
      )}
    </g>
  );
}

export default function EnergyFlow({ flow, fault, loadW, battW }) {
  const outage = flow === "battery_to_house";
  const charging = flow === "grid_to_battery"; // grid feeds house AND charges
  const gridActive = charging || flow === "grid_to_house";
  const base = fault ? "var(--danger)" : outage ? "var(--warn)" : "var(--ok)";

  return (
    <svg
      viewBox="0 0 180 130"
      width="100%"
      role="img"
      aria-label={
        fault
          ? "Power flow frozen: inverter fault"
          : outage
            ? `Battery powering home, ${fmtW(loadW)}`
            : gridActive
              ? `Grid powering home, ${fmtW(loadW)}${charging ? ", battery charging" : ""}`
              : "Power flow idle"
      }
    >
      <defs>
        <marker id="flow-arrow" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
          <path d="M0,0 L8,4 L0,8 Z" fill="context-stroke" />
        </marker>
      </defs>

      <FlowPath
        d={PATHS.grid_home}
        active={gridActive}
        frozen={fault}
        color={base}
        watts={loadW}
        label={{ x: 90, y: 24 }}
      />
      <FlowPath
        d={PATHS.grid_batt}
        active={charging}
        frozen={fault}
        color={base}
        watts={battW}
        label={{ x: 44, y: 80, anchor: "end" }}
      />
      <FlowPath
        d={PATHS.batt_home}
        active={outage}
        frozen={fault}
        color={base}
        watts={loadW}
        label={{ x: 136, y: 80, anchor: "start" }}
      />

      {/* Grid node dims during an outage (SPEC 8B.1). */}
      <Node cx={GRID.x} cy={GRID.y} label="Grid" dim={outage}>
        <path d="M-2.5,-5.5 V-1.5 M2.5,-5.5 V-1.5 M-4.5,-1.5 H4.5 V1 A4.5,4.5 0 0 1 -4.5,1 Z M0,5.5 V3" />
      </Node>
      <Node cx={HOME.x} cy={HOME.y} label="Home">
        <path d="M-5.5,0 L0,-5.5 L5.5,0 V5 H-5.5 Z" strokeLinejoin="round" />
      </Node>
      <Node cx={BATT.x} cy={BATT.y} label="Battery" labelBelow>
        <g strokeLinejoin="round">
          <rect x="-5.5" y="-3" width="10" height="6" rx="1" />
          <path d="M4.5,-1.2 H6 V1.2 H4.5" />
        </g>
      </Node>
    </svg>
  );
}
