// Outage burn-down (SPEC 8B.3): "will we make it to morning". A projected SoC
// line from now toward empty at the smoothed draw, in the shared 8A chart
// style (faint horizontal gridlines only, muted tabular axis text, accent
// series, semantic threshold colors). Markers: the low-SoC alert threshold,
// the projected-empty time, and local sunrise/sunset computed OFFLINE by the
// backend from configured lat/long (no network). Near-zero draw renders a
// flat line labelled "> 24 hrs" instead of a misleading slope.
//
// Pure SVG, no chart library: Home/Outage stay ECharts-free by design (8A).

// Chart box in viewBox units.
const W = 340;
const H = 150;
const M = { top: 22, right: 10, bottom: 20, left: 26 };
const PW = W - M.left - M.right;
const PH = H - M.top - M.bottom;

function fmtClock(ts) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export default function BurnDown({ soc, runtimeH, capped, lowSocPct = 40, sunEvents = [], nowTs }) {
  const now = nowTs ?? Date.now() / 1000;
  const flat = capped || runtimeH == null;

  // X domain (hours from now): far enough to show projected empty, and
  // stretched to include the first sunrise so "morning" is on the chart.
  const sunsH = sunEvents.map((e) => ({ ...e, h: (e.ts - now) / 3600 })).filter((e) => e.h > 0);
  const firstSunrise = sunsH.find((e) => e.type === "sunrise");
  let endH = flat ? 24 : Math.max(runtimeH * 1.08, 4);
  if (firstSunrise) endH = Math.max(endH, Math.min(firstSunrise.h + 0.75, 36));
  endH = Math.min(endH, 36);

  const x = (h) => M.left + (Math.max(0, Math.min(h, endH)) / endH) * PW;
  const y = (pct) => M.top + (1 - Math.max(0, Math.min(pct, 100)) / 100) * PH;

  const socNow = Math.max(0, Math.min(100, soc ?? 0));
  const endX = flat ? x(endH) : x(runtimeH);
  const endY = flat ? y(socNow) : y(0);
  const line = `M ${x(0)} ${y(socNow)} L ${endX} ${endY}`;
  const area = `${line} L ${endX} ${y(0)} L ${x(0)} ${y(0)} Z`;

  const visibleSuns = sunsH.filter((e) => e.h <= endH);
  const midTs = now + (endH / 2) * 3600;
  const endTs = now + endH * 3600;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
      aria-label={
        flat
          ? `Battery projection: more than 24 hours at this draw, currently ${Math.round(socNow)} percent`
          : `Battery projection: empty around ${fmtClock(now + runtimeH * 3600)}`
      }
    >
      <defs>
        <linearGradient id="bd-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.22" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Horizontal gridlines only (8A), faint. */}
      {[25, 50, 75, 100].map((p) => (
        <line key={p} x1={M.left} x2={W - M.right} y1={y(p)} y2={y(p)} stroke="var(--border)" strokeWidth="0.6" opacity="0.6" />
      ))}
      {[0, 50, 100].map((p) => (
        <text key={p} x={M.left - 5} y={y(p) + 3} textAnchor="end" fontSize="8.5" className="tnum" fill="var(--muted)">
          {p}
        </text>
      ))}

      {/* Sunrise/sunset markers (offline suncalc via config lat/long). */}
      {visibleSuns.map((e) => (
        <g key={e.ts}>
          <line x1={x(e.h)} x2={x(e.h)} y1={M.top} y2={H - M.bottom} stroke="var(--warn)" strokeWidth="0.8" strokeDasharray="2 3" opacity="0.7" />
          <text x={x(e.h)} y={M.top - 11} textAnchor="middle" fontSize="10" fill="var(--warn)">
            {e.type === "sunrise" ? "☀" : "☾"}
          </text>
          <text x={x(e.h)} y={M.top - 3} textAnchor="middle" fontSize="7.5" className="tnum" fill="var(--warn)">
            {fmtClock(e.ts)}
          </text>
        </g>
      ))}

      {/* Low-SoC alert threshold. */}
      <line x1={M.left} x2={W - M.right} y1={y(lowSocPct)} y2={y(lowSocPct)} stroke="var(--warn)" strokeWidth="0.9" strokeDasharray="4 3" opacity="0.9" />
      <text x={W - M.right - 2} y={y(lowSocPct) - 3} textAnchor="end" fontSize="8" className="tnum" fill="var(--warn)">
        {lowSocPct}% alert
      </text>

      {/* Projection. */}
      <path d={area} fill="url(#bd-fill)" />
      <path d={line} fill="none" stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx={x(0)} cy={y(socNow)} r="3.2" fill="var(--accent)" />
      <text x={x(0) + 6} y={y(socNow) - 6} fontSize="9" fontWeight="600" className="tnum" fill="var(--text)">
        {Math.round(socNow)}%
      </text>

      {flat ? (
        <text x={M.left + PW / 2} y={y(socNow) - 8} textAnchor="middle" fontSize="10" fontWeight="600" fill="var(--text)">
          &gt; 24 hrs at this draw
        </text>
      ) : (
        <g>
          <line x1={endX} x2={endX} y1={endY - 8} y2={endY} stroke="var(--danger)" strokeWidth="1.4" />
          <text x={Math.min(endX, W - M.right - 4)} y={endY - 12} textAnchor="end" fontSize="9" fontWeight="600" className="tnum" fill="var(--danger)">
            empty ~{fmtClock(now + runtimeH * 3600)}
          </text>
        </g>
      )}

      {/* Time axis: now / mid / end, local time. */}
      <text x={x(0)} y={H - 7} textAnchor="start" fontSize="8.5" fill="var(--muted)">
        now
      </text>
      <text x={x(endH / 2)} y={H - 7} textAnchor="middle" fontSize="8.5" className="tnum" fill="var(--muted)">
        {fmtClock(midTs)}
      </text>
      <text x={x(endH)} y={H - 7} textAnchor="end" fontSize="8.5" className="tnum" fill="var(--muted)">
        {fmtClock(endTs)}
      </text>
    </svg>
  );
}
