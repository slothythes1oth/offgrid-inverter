import EnergyFlow from "../components/EnergyFlow";
import {
  Card,
  HealthStrip,
  LoadGauge,
  SocRing,
  StaleBanner,
  StatusBanner,
} from "../components/primitives";
import { deriveStatus } from "../format";

// Home: "are we okay?" — five-second rule, no decimals, boring when normal.
export default function Home({ state, stale, ageText, justRestored }) {
  const status = deriveStatus(state, stale);
  const soc = state?.soc;
  const load = state?.load_w_total;
  const cont = state?.headroom?.continuous_load_w ?? 6500;
  const onGrid = state && !state.on_battery;

  return (
    <div className="flex flex-col gap-3 max-w-md mx-auto w-full">
      {justRestored && (
        <div
          className="rounded-xl px-4 py-2.5 text-sm font-medium"
          style={{ background: "color-mix(in srgb, var(--ok) 18%, var(--surface))", color: "var(--ok)" }}
          role="status"
        >
          ✓ Back on grid
        </div>
      )}

      <StatusBanner
        level={status.level}
        word={status.word}
        icon={status.icon}
        sub={onGrid ? "Running on grid power" : state?.on_battery ? "Running on battery" : undefined}
      />

      {stale && <StaleBanner ageText={ageText} />}

      <div className="grid place-items-center py-2">
        <SocRing soc={soc} size={220} stroke={18} />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Card title="Current load">
          <LoadGauge
            value={load}
            max={cont}
            threshold={cont}
            label={null}
            legs={{ l1W: state?.load_w_l1, l2W: state?.load_w_l2 }}
          />
          <div className="text-muted text-xs mt-2">
            safe to {(cont / 1000).toFixed(1)} kW
          </div>
        </Card>
        <Card title="Power flow">
          <EnergyFlow
            flow={state?.flow}
            fault={state?.fault_active}
            loadW={load}
            battW={state?.batt_w}
          />
        </Card>
      </div>

      <HealthStrip
        ok={!state?.fault_active}
        text={
          state?.fault_active
            ? "Inverter fault active"
            : `System nominal · ${state?.batt_v ?? "--"} V`
        }
        detail={state?.fault_active ? "see Technical" : null}
      />
    </div>
  );
}
