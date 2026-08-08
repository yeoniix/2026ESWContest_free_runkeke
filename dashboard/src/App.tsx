import { useEffect, useState } from "react";
import "./App.css";
import { fetchAlerts, fetchEmergencies } from "./api/gateway";
import CommandConsole from "./components/CommandConsole";
import DeviceCard from "./components/DeviceCard";
import EventLog from "./components/EventLog";
import RoleSwitcher from "./components/RoleSwitcher";
import { useLiveDevices } from "./hooks/useLiveDevices";
import type { AlertRecord, EmergencyRecord, Role } from "./types/device";

function loadRole(): Role {
  return (localStorage.getItem("hs_role") as Role) ?? "observer";
}

function loadActorId(): string {
  return localStorage.getItem("hs_actor") ?? "OBS1";
}

function App() {
  const [role, setRole] = useState<Role>(loadRole);
  const [actorId, setActorId] = useState<string>(loadActorId);
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [emergencies, setEmergencies] = useState<EmergencyRecord[]>([]);

  const { devices, events, connected, error } = useLiveDevices(role, actorId);

  useEffect(() => {
    localStorage.setItem("hs_role", role);
  }, [role]);
  useEffect(() => {
    localStorage.setItem("hs_actor", actorId);
  }, [actorId]);

  async function refreshConsole() {
    try {
      const [a, e] = await Promise.all([fetchAlerts(role, actorId), fetchEmergencies(role, actorId)]);
      setAlerts(a);
      setEmergencies(e);
    } catch (err) {
      console.error(err);
    }
  }

  useEffect(() => {
    // 마운트 시 1회 즉시 조회 + 2초 폴링. refreshConsole은 commander 액션 뒤
    // 수동 재조회에도 쓰이는 공용 함수라 effect 밖에 두었다.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshConsole();
    const id = window.setInterval(refreshConsole, 2000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role, actorId]);

  const stateCounts = devices.reduce<Record<string, number>>((acc, d) => {
    acc[d.state] = (acc[d.state] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <main className="app">
      <section className="hero">
        <div>
          <p className="eyebrow">HeatSentry Gateway Dashboard · HS-SIID-002 v2.0</p>
          <h1>손목·허리 폐루프 관제 대시보드</h1>
          <p className="description">
            센서 품질 → RiskIndex → 자동 냉각 → 30초 재평가 → SOS → 감사 로그로 이어지는 폐루프를
            실시간으로 표시합니다. RiskIndex와 피부온도는 의료 진단값이 아닙니다.
          </p>
        </div>

        <div className="status-panel">
          <div>
            <span>정상</span>
            <strong>{stateCounts.NORMAL ?? 0}</strong>
          </div>
          <div>
            <span>경고</span>
            <strong>{stateCounts.WARNING ?? 0}</strong>
          </div>
          <div>
            <span>냉각</span>
            <strong>{stateCounts.COOLING ?? 0}</strong>
          </div>
          <div>
            <span>응급</span>
            <strong>{stateCounts.EMERGENCY ?? 0}</strong>
          </div>
        </div>
      </section>

      <section className="toolbar">
        <span>연결 상태: {connected ? "WebSocket 연결됨" : "REST 폴백 중"}</span>
        <RoleSwitcher role={role} actorId={actorId} onRoleChange={setRole} onActorChange={setActorId} />
      </section>

      {error && <div className="error">{error}</div>}

      <section className="grid">
        {devices.length === 0 && !error ? (
          <div className="empty">
            아직 수신된 장치 데이터가 없습니다. 게이트웨이(uvicorn server.app.main:app)와 node_sim(python -m
            node_sim.run_demo)을 먼저 실행하세요.
          </div>
        ) : (
          devices.map((t) => <DeviceCard key={t.device_id} telemetry={t} />)
        )}
      </section>

      <CommandConsole
        alerts={alerts}
        emergencies={emergencies}
        role={role}
        actorId={actorId}
        onChanged={refreshConsole}
      />

      <EventLog events={events} role={role} actorId={actorId} />
    </main>
  );
}

export default App;
