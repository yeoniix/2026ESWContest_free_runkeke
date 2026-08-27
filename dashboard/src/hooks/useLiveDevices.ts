// IF-05 게이트웨이->UI WebSocket(≤1s) 구독. 연결이 끊기면 REST 폴링으로
// 저하 운용한다 — SU-D는 통신이 없어도 "로컬 관제가 완전하게 동작"해야 한다는
// 원칙(HS-SIID-002 "통합 원칙")을 화면 쪽에서도 지키기 위함이다.
import { useCallback, useEffect, useRef, useState } from "react";
import { WS_URL, fetchDevices, fetchEvents } from "../api/gateway";
import type { EventRecord, Role, TelemetryV2 } from "../types/device";

const MAX_EVENTS = 300;
const MAX_RISK_POINTS = 60;

export interface RiskPoint {
  timestamp: string;
  riskIndex: number;
}

export type RiskHistory = Record<string, RiskPoint[]>;

function appendRiskPoint(history: RiskHistory, telemetry: TelemetryV2): RiskHistory {
  if (telemetry.risk_index === 255) return history;
  const points = history[telemetry.device_id] ?? [];
  const last = points.at(-1);
  if (last?.timestamp === telemetry.gateway_utc) return history;
  return {
    ...history,
    [telemetry.device_id]: [...points, { timestamp: telemetry.gateway_utc, riskIndex: telemetry.risk_index }].slice(-MAX_RISK_POINTS),
  };
}

export function useLiveDevices(role: Role, actorId: string) {
  const [devices, setDevices] = useState<Record<string, TelemetryV2>>({});
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [riskHistory, setRiskHistory] = useState<RiskHistory>({});
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const applyTelemetry = useCallback((t: TelemetryV2) => {
    setDevices((prev) => ({ ...prev, [t.device_id]: t }));
    setRiskHistory((prev) => appendRiskPoint(prev, t));
  }, []);

  const applyEvent = useCallback((e: EventRecord) => {
    setEvents((prev) => [...prev, e].slice(-MAX_EVENTS));
  }, []);

  const pollOnce = useCallback(async () => {
    try {
      const [deviceList, eventList] = await Promise.all([
        fetchDevices(role, actorId),
        fetchEvents(role, actorId),
      ]);
      setDevices(Object.fromEntries(deviceList.map((d) => [d.device_id, d])));
      setRiskHistory((prev) => deviceList.reduce(appendRiskPoint, prev));
      setEvents(eventList.slice(-MAX_EVENTS));
      setError(null);
    } catch (err) {
      console.error(err);
      setError("게이트웨이에서 데이터를 가져오지 못했습니다.");
    }
  }, [role, actorId]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let cancelled = false;

    function startPolling() {
      if (pollRef.current) return;
      pollOnce();
      pollRef.current = window.setInterval(pollOnce, 1500);
    }

    function stopPolling() {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }

    try {
      ws = new WebSocket(WS_URL);
      ws.onopen = () => {
        if (cancelled) return;
        setConnected(true);
        setError(null);
        stopPolling();
      };
      ws.onmessage = (evt) => {
        const msg = JSON.parse(evt.data);
        if (msg.type === "snapshot") {
          const snapshotDevices = msg.data.devices as TelemetryV2[];
          setDevices(Object.fromEntries(snapshotDevices.map((d) => [d.device_id, d])));
          setRiskHistory((prev) => snapshotDevices.reduce(appendRiskPoint, prev));
          setEvents((msg.data.events as EventRecord[]).slice(-MAX_EVENTS));
        } else if (msg.type === "telemetry") {
          applyTelemetry(msg.data as TelemetryV2);
        } else if (msg.type === "event") {
          applyEvent(msg.data as EventRecord);
        }
      };
      ws.onclose = () => {
        if (cancelled) return;
        setConnected(false);
        startPolling();
      };
      ws.onerror = () => {
        ws?.close();
      };
    } catch {
      startPolling();
    }

    return () => {
      cancelled = true;
      stopPolling();
      ws?.close();
    };
  }, [applyTelemetry, applyEvent, pollOnce]);

  return { devices: Object.values(devices), events, riskHistory, connected, error, refresh: pollOnce };
}
