import BurnDown from "../components/BurnDown";
import EnergyFlow from "../components/EnergyFlow";
import HeadroomLanes from "../components/HeadroomLanes";
import {
  Card,
  Freshness,
  HealthStrip,
  LoadGauge,
  SocRing,
  StaleBanner,
  StatusBanner,
} from "../components/primitives";

const NOW = Date.now() / 1000;
const DEMO_SUNS = [
  { type: "sunrise", ts: NOW + 8.2 * 3600 },
  { type: "sunset", ts: NOW + 21.5 * 3600 },
];

// /gallery — every primitive in every state, for review on the phone before
// the pages are trusted. Not linked from the app; open it directly.
export default function Gallery() {
  return (
    <div className="flex flex-col gap-4 max-w-md mx-auto w-full pb-8">
      <h1 className="text-lg font-bold">Design system</h1>

      <section className="flex flex-col gap-2">
        <h2 className="text-muted text-sm">Status banners (color + icon + word)</h2>
        <StatusBanner level="ok" word="All Normal" icon="check" sub="Running on grid power" />
        <StatusBanner level="warn" word="ON BATTERY" icon="bolt" sub="Running on battery" />
        <StatusBanner level="danger" word="FAULT" icon="warning" sub="Bypass overload" />
        <StatusBanner level="danger" word="NO DATA" icon="warning" sub="Collector not reporting" />
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-muted text-sm">SoC ring (thresholds)</h2>
        <div className="flex items-center justify-around">
          <SocRing soc={96} size={110} stroke={10} />
          <SocRing soc={38} size={110} stroke={10} />
          <SocRing soc={12} size={110} stroke={10} />
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-muted text-sm">Load gauge (safe zone + over-limit)</h2>
        <Card>
          <LoadGauge value={466} max={6500} threshold={6500} label="normal" />
        </Card>
        <Card>
          <LoadGauge value={5200} max={6500} threshold={6500} label="near limit" />
        </Card>
        <Card>
          <LoadGauge value={6800} max={6500} threshold={6500} label="over limit" big />
        </Card>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-muted text-sm">Living energy flow (8B.1) — normal / charging / outage / fault / idle</h2>
        <div className="grid grid-cols-2 gap-3">
          <Card title="Grid → home">
            <EnergyFlow flow="grid_to_house" fault={false} loadW={466} battW={0} />
          </Card>
          <Card title="Charging">
            <EnergyFlow flow="grid_to_battery" fault={false} loadW={466} battW={-795} />
          </Card>
          <Card title="Outage">
            <EnergyFlow flow="battery_to_house" fault={false} loadW={2170} battW={2170} />
          </Card>
          <Card title="Fault (frozen)">
            <EnergyFlow flow="grid_to_house" fault={true} loadW={5900} battW={0} />
          </Card>
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-muted text-sm">Twin-leg headroom lanes (8B.2)</h2>
        <Card title="Balanced, comfortable">
          <HeadroomLanes l1A={6.5} l2A={5.1} limitA={40} availW={5100} />
        </Card>
        <Card title="Imbalanced, L1 hot">
          <HeadroomLanes l1A={31} l2A={7} limitA={40} availW={1900} />
        </Card>
        <Card title="Near the ceiling">
          <HeadroomLanes l1A={38} l2A={22} limitA={40} availW={0} />
        </Card>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-muted text-sm">Outage burn-down (8B.3)</h2>
        <Card title="Draining — sunrise before empty">
          <BurnDown soc={48} runtimeH={11.5} capped={false} lowSocPct={40} sunEvents={DEMO_SUNS} nowTs={NOW} />
        </Card>
        <Card title="Draining fast — empty before sunrise">
          <BurnDown soc={35} runtimeH={3.2} capped={false} lowSocPct={40} sunEvents={DEMO_SUNS} nowTs={NOW} />
        </Card>
        <Card title="Near-zero draw">
          <BurnDown soc={92} runtimeH={null} capped={true} lowSocPct={40} sunEvents={DEMO_SUNS} nowTs={NOW} />
        </Card>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-muted text-sm">Load gauge with L1/L2 ticks (8B.2, Home)</h2>
        <Card>
          <LoadGauge value={2170} max={6500} threshold={6500} label="with legs" legs={{ l1W: 1700, l2W: 470 }} />
        </Card>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-muted text-sm">Freshness / stale / health</h2>
        <Freshness ageText="3s ago" connected={true} />
        <Freshness ageText="2m ago" connected={false} />
        <StaleBanner ageText="4m ago" />
        <HealthStrip ok={true} text="System nominal · 54.2 V" />
        <HealthStrip ok={false} text="Inverter fault active" detail="see Technical" />
      </section>
    </div>
  );
}
