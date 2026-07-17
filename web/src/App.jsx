import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { Freshness } from "./components/primitives";
import TabBar from "./components/TabBar";
import { fmtAge } from "./format";
import { useLiveState } from "./hooks/useLiveState";
import Gallery from "./pages/Gallery";
import Home from "./pages/Home";
import Outage from "./pages/Outage";

// History carries ECharts: code-split so Home/Outage (the pages that matter
// in an emergency) never pay for the chart library at startup.
const History = lazy(() => import("./pages/History"));
const Settings = lazy(() => import("./pages/Settings"));

export default function App() {
  const { state, ageS, connected } = useLiveState();
  const navigate = useNavigate();
  const location = useLocation();
  const prevOutage = useRef(false);
  const [justRestored, setJustRestored] = useState(false);

  const outageActive = !!state?.outage?.active;

  // Auto-switch to Outage when one is active; return Home on restore with a
  // brief confirmation. The gallery route opts out of auto-switching. The
  // query string is preserved so ?demo= survives the switch.
  useEffect(() => {
    if (location.pathname === "/gallery") return;
    if (outageActive && location.pathname !== "/outage") {
      navigate({ pathname: "/outage", search: location.search });
    } else if (!outageActive && prevOutage.current) {
      setJustRestored(true);
      navigate({ pathname: "/", search: location.search });
      const id = setTimeout(() => setJustRestored(false), 8000);
      return () => clearTimeout(id);
    }
    prevOutage.current = outageActive;
  }, [outageActive, location.pathname, location.search, navigate]);

  const stale = state ? state.stale || (ageS != null && ageS > 30) : true;
  const ageText = fmtAge(ageS);

  // State-change theatre (SPEC 8B.8): on outage/restore and fault raise/clear
  // the accent temperature shifts (via [data-app-state] in index.css) and a
  // brief full-screen color wash plays. Reduced motion drops the wash in CSS.
  const appState = state?.fault_active ? "fault" : outageActive ? "outage" : "normal";
  const prevAppState = useRef(null);
  const [wash, setWash] = useState(null);
  useEffect(() => {
    const prev = prevAppState.current;
    prevAppState.current = appState;
    if (prev === null || prev === appState) return; // no theatre on first load
    const level = appState === "fault" ? "danger" : appState === "outage" ? "warn" : "ok";
    setWash({ level, key: Date.now() });
    const id = setTimeout(() => setWash(null), 1600);
    return () => clearTimeout(id);
  }, [appState]);

  return (
    <div className="min-h-[100dvh] safe-x safe-b flex flex-col" data-app-state={appState}>
      {wash && <div className="theatre-wash" data-wash={wash.level} key={wash.key} aria-hidden="true" />}
      <header className="safe-t px-4 pt-3 pb-2 flex items-center justify-between">
        <span className="text-sm font-semibold text-muted">Home Backup</span>
        <Freshness ageText={ageText} connected={connected} />
      </header>
      <main className="flex-1 px-4 pb-4">
        <Routes>
          <Route
            path="/"
            element={
              <Home state={state} stale={stale} ageText={ageText} justRestored={justRestored} />
            }
          />
          <Route path="/outage" element={<Outage state={state} stale={stale} ageText={ageText} />} />
          <Route
            path="/history"
            element={
              <Suspense
                fallback={
                  <div className="max-w-md mx-auto w-full">
                    <div className="chart-skeleton w-full" style={{ height: 320 }} />
                  </div>
                }
              >
                <History stale={stale} />
              </Suspense>
            }
          />
          <Route
            path="/settings"
            element={
              <Suspense fallback={null}>
                <Settings />
              </Suspense>
            }
          />
          <Route path="/gallery" element={<Gallery />} />
        </Routes>
      </main>
      {!outageActive && <TabBar />}
    </div>
  );
}
