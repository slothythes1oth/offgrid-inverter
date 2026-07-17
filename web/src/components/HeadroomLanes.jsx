// Twin-leg headroom lanes (SPEC 8B.2). Two horizontal lanes, L1 and L2, in
// AMPS, filling toward the hard bypass-relay ceiling (~40 A/leg). Both lanes
// share one scale so leg imbalance is visible at a glance. Zone tints on the
// track make the danger zone explicit (green -> amber -> red); the fill color
// follows the same semantics. Below the lanes: the plain-language available
// capacity readout so a non-technical family member can judge turning
// something on.

const WARN_FRAC = 0.6; // of the ceiling
const DANGER_FRAC = 0.85;
// Ceiling sits at 88% of the track so an over-limit fill visibly crosses it.
const CEIL_POS = 0.88;

function laneColor(frac) {
  if (frac >= DANGER_FRAC) return "var(--danger)";
  if (frac >= WARN_FRAC) return "var(--warn)";
  return "var(--ok)";
}

function Lane({ label, amps, limitA }) {
  const frac = Math.max(0, (amps ?? 0) / limitA);
  const fillPct = Math.min(100, frac * CEIL_POS * 100);
  return (
    <div className="flex items-center gap-2">
      <span className="text-muted text-xs font-semibold w-5">{label}</span>
      <div className="relative h-4 flex-1 rounded-md bg-surface-2 overflow-hidden">
        {/* Zone tints: caution and danger bands up to the ceiling. */}
        <div
          className="absolute inset-y-0"
          style={{
            left: `${WARN_FRAC * CEIL_POS * 100}%`,
            width: `${(DANGER_FRAC - WARN_FRAC) * CEIL_POS * 100}%`,
            background: "color-mix(in srgb, var(--warn) 14%, transparent)",
          }}
        />
        <div
          className="absolute inset-y-0"
          style={{
            left: `${DANGER_FRAC * CEIL_POS * 100}%`,
            right: 0,
            background: "color-mix(in srgb, var(--danger) 14%, transparent)",
          }}
        />
        <div
          className="absolute inset-y-0 left-0 rounded-md"
          style={{
            width: `${fillPct}%`,
            background: laneColor(frac),
            transition: "width 0.5s ease, background 0.4s ease",
          }}
        />
        {/* Hard ceiling line at the bypass limit. */}
        <div
          className="absolute top-0 bottom-0 w-0.5"
          style={{ left: `${CEIL_POS * 100}%`, background: "var(--text)", opacity: 0.8 }}
        />
      </div>
      <span className="tnum text-sm font-semibold w-12 text-right">
        {amps == null ? "--" : Math.round(amps)} A
      </span>
    </div>
  );
}

export default function HeadroomLanes({ l1A, l2A, limitA = 40, availW, continuousW = 6500 }) {
  return (
    <div>
      <div className="flex flex-col gap-2">
        <Lane label="L1" amps={l1A} limitA={limitA} />
        <Lane label="L2" amps={l2A} limitA={limitA} />
      </div>
      <div className="flex justify-end mt-1" style={{ paddingRight: "3.5rem" }}>
        <span className="text-muted" style={{ fontSize: "0.65rem" }}>
          hard limit {limitA} A per leg
        </span>
      </div>

      {/* Plain-language available capacity (SPEC 8, Outage item 4). */}
      <div className="mt-3 text-lg">
        <span className="text-muted">Available: </span>
        <span className="tnum font-semibold">
          ~{availW == null ? "--" : (availW / 1000).toFixed(1)} kW free
        </span>
      </div>
      <div className="text-muted text-xs mt-1">
        room to turn things on before the {(continuousW / 1000).toFixed(1)} kW limit
      </div>
    </div>
  );
}
