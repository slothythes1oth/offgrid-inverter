import { Card } from "../components/primitives";
import LoadProfile from "../charts/LoadProfile";

// History: "what's my pattern, why did it trip?" Sections land in SPEC's
// priority order — load profile first (checkpoint c); events, outages, TOU,
// and battery trends follow at checkpoint d.
export default function History({ stale }) {
  return (
    <div className="flex flex-col gap-3 max-w-md mx-auto w-full pb-4">
      <Card title="Load profile">
        <LoadProfile stale={stale} />
        <div className="text-muted mt-2" style={{ fontSize: "0.65rem" }}>
          Peaks are 5-second samples; sub-second surges land in the fault log,
          not here. Gaps mean the collector was off (laptop asleep).
        </div>
      </Card>
    </div>
  );
}
