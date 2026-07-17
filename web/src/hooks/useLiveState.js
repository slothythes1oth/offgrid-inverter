import { useEffect, useRef, useState } from "react";

// Subscribes to /api/stream via EventSource (which reconnects natively on
// drop). Returns { state, ageS, connected }.
//
// Freshness is driven by DATA AGE, not connection state: we re-derive age
// every second from the sample's ts + the server-reported age at receipt, so
// a silently-dead collector (SSE still "connected") still ages into stale.
// `connected` only reflects the transport, shown as a secondary signal.
export function useLiveState() {
  const [state, setState] = useState(null);
  const [connected, setConnected] = useState(false);
  const [nowTick, setNowTick] = useState(0);
  const received = useRef({ ts: null, ageAtRecv: 0, recvAt: 0 });

  useEffect(() => {
    // Debug/snapshot mode: ?snapshot fetches /api/current once and skips the
    // live stream. Lets headless tools render a settled page (the always-open
    // SSE connection otherwise keeps the page from ever going network-idle).
    const snapshot = new URLSearchParams(window.location.search).has("snapshot");
    if (snapshot) {
      fetch("/api/current")
        .then((r) => r.json())
        .then((data) => {
          setState(data);
          setConnected(true);
          received.current = { ts: data.ts, ageAtRecv: data.age_s ?? 0, recvAt: Date.now() };
        })
        .catch(() => setConnected(false));
      return;
    }

    const es = new EventSource("/api/stream");
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false); // EventSource retries on its own
    es.addEventListener("state", (e) => {
      const data = JSON.parse(e.data);
      setState(data);
      received.current = {
        ts: data.ts,
        ageAtRecv: data.age_s ?? 0,
        recvAt: Date.now(),
      };
    });
    return () => es.close();
  }, []);

  // 1 Hz local clock so "updated Xs ago" and staleness advance smoothly
  // between server pushes.
  useEffect(() => {
    const id = setInterval(() => setNowTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  let ageS = null;
  if (received.current.ts != null) {
    ageS =
      received.current.ageAtRecv +
      (Date.now() - received.current.recvAt) / 1000;
  }
  // Reference nowTick so the value recomputes each second.
  void nowTick;

  return { state, ageS, connected };
}
