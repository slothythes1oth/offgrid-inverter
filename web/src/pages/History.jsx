import { useRef, useState } from "react";

import BatteryTrend from "../charts/BatteryTrend";
import EventLog from "../charts/EventLog";
import LoadProfile from "../charts/LoadProfile";
import OutageHistory from "../charts/OutageHistory";
import TouSection from "../charts/TouSection";
import { Card } from "../components/primitives";

// History: "what's my pattern, why did it trip?" — sections in SPEC's
// priority order: load profile, fault/event log, outage history, TOU cost
// + savings, battery trends.
export default function History({ stale }) {
  const [dayFocus, setDayFocus] = useState(null);
  const topRef = useRef(null);

  // Calendar heatmap tap: pin the load profile to that local day (8B.5).
  const selectDay = (dateStr) => {
    const start = new Date(`${dateStr}T00:00:00`);
    const end = new Date(start);
    end.setDate(end.getDate() + 1);
    setDayFocus({
      from: Math.floor(start.getTime() / 1000),
      to: Math.floor(end.getTime() / 1000),
      label: start.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" }),
    });
    topRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="flex flex-col gap-3 max-w-md mx-auto w-full pb-4">
      <div ref={topRef} />
      <Card title="Load profile">
        <LoadProfile stale={stale} focus={dayFocus} onClearFocus={() => setDayFocus(null)} />
        <div className="text-muted mt-2" style={{ fontSize: "0.65rem" }}>
          Peaks are 5-second samples; sub-second surges land in the fault log,
          not here. Gaps mean the collector was off (laptop asleep).
        </div>
      </Card>

      <Card title="Faults & events">
        <EventLog />
      </Card>

      <Card title="Outages">
        <OutageHistory />
      </Card>

      <Card title="Cost & savings">
        <TouSection onSelectDay={selectDay} />
      </Card>

      <Card title="Battery">
        <BatteryTrend />
      </Card>
    </div>
  );
}
