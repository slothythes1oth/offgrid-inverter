import {
  Card,
  FlowDiagram,
  Freshness,
  HealthStrip,
  LoadGauge,
  SocRing,
  StaleBanner,
  StatusBanner,
} from "../components/primitives";

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

      <section className="grid grid-cols-2 gap-3">
        <Card title="Power flow">
          <FlowDiagram flow="battery_to_house" />
        </Card>
        <Card title="Power flow">
          <FlowDiagram flow="grid_to_battery" />
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
