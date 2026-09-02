import { useCallback, useEffect, useState } from "react";
import "./App.css";

import {
  fetchAlerts,
  fetchEmergencies,
} from "./api/gateway";

import CommandConsole from "./components/CommandConsole";
import DeviceCard from "./components/DeviceCard";
import RiskTrend from "./components/RiskTrend";
import RoleSwitcher from "./components/RoleSwitcher";
import TacticalMap from "./components/TacticalMap";

import { useLiveDevices } from "./hooks/useLiveDevices";

import type {
  AlertRecord,
  EmergencyRecord,
  Role,
  TelemetryV2,
} from "./types/device";


function loadRole(): Role {
  return (
    (localStorage.getItem("hs_role") as Role) ??
    "observer"
  );
}


function loadActorId(): string {
  return localStorage.getItem("hs_actor") ?? "OBS1";
}


/**
 * 실제 현장 Belt 상태를 우선 사용해 냉각 중인지 판단한다.
 *
 * COOLING_50 = 팬 1개 동작 / 50% 냉각 단계
 * DANGER     = 100% 냉각 단계
 *
 * raw.belt_state가 없는 시뮬레이터/구형 데이터는
 * 기존 telemetry.state === "COOLING"을 fallback으로 사용한다.
 */
function isCoolingDevice(device: TelemetryV2): boolean {
  const beltState = device.raw?.belt_state ?? null;

  if (beltState) {
    return (
      beltState === "COOLING_50" ||
      beltState === "DANGER"
    );
  }

  return device.state === "COOLING";
}


/**
 * Emergency도 Belt 판정을 최우선 사용한다.
 */
function isEmergencyDevice(device: TelemetryV2): boolean {
  const beltState = device.raw?.belt_state ?? null;

  if (beltState) {
    return beltState === "EMERGENCY";
  }

  return device.state === "EMERGENCY";
}


function App() {
  const [role, setRole] =
    useState<Role>(loadRole);

  const [actorId, setActorId] =
    useState(loadActorId);

  const [alerts, setAlerts] =
    useState<AlertRecord[]>([]);

  const [emergencies, setEmergencies] =
    useState<EmergencyRecord[]>([]);

  const {
    devices,
    riskHistory,
    connected,
    error,
  } = useLiveDevices(role, actorId);


  // ★ 상단 요약도 현장 Belt 상태 기준
  const emergencyCount =
    devices.filter(isEmergencyDevice).length;

  const coolingCount =
    devices.filter(isCoolingDevice).length;


  const priorityDevice = [...devices].sort(
    (a, b) => b.risk_index - a.risk_index,
  )[0];


  useEffect(
    () => localStorage.setItem("hs_role", role),
    [role],
  );


  useEffect(
    () => localStorage.setItem("hs_actor", actorId),
    [actorId],
  );


  const refreshConsole = useCallback(async () => {
    try {
      const [
        nextAlerts,
        nextEmergencies,
      ] = await Promise.all([
        fetchAlerts(role, actorId),
        fetchEmergencies(role, actorId),
      ]);

      setAlerts(nextAlerts);
      setEmergencies(nextEmergencies);
    }
    catch {
      // live-device 연결 오류에서 Gateway 실패를 표시한다.
    }
  }, [role, actorId]);


  useEffect(() => {
    const initial = window.setTimeout(
      () => void refreshConsole(),
      0,
    );

    const timer = window.setInterval(
      () => void refreshConsole(),
      2000,
    );

    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [refreshConsole]);


  return (
    <main className="app">
      <header className="topbar">
        <div>
          <p className="eyebrow">
            HEATSENTRY
          </p>

          <h1>
            실시간 병사 관제
          </h1>
        </div>

        <div className="topbar-right">
          <div className="summary">
            <span>
              <strong>
                {devices.length}
              </strong>{" "}
              연결
            </span>

            <span
              className={
                coolingCount > 0
                  ? "summary-cooling"
                  : ""
              }
            >
              <strong>
                {coolingCount}
              </strong>{" "}
              냉각
            </span>

            <span
              className={
                emergencyCount > 0
                  ? "summary-emergency"
                  : ""
              }
            >
              <strong>
                {emergencyCount}
              </strong>{" "}
              위급
            </span>
          </div>

          <span
            className={`connection ${
              connected
                ? "online"
                : "offline"
            }`}
          >
            <i />

            {connected
              ? "실시간 연결"
              : "연결 대기"}
          </span>

          <RoleSwitcher
            role={role}
            actorId={actorId}
            onRoleChange={setRole}
            onActorChange={setActorId}
          />
        </div>
      </header>


      {error && (
        <div className="error">
          {error}
        </div>
      )}


      <section
        className="soldier-grid"
        aria-label="병사 상태 카드"
      >
        {devices.length === 0 && !error
          ? (
            <div className="empty">
              수신된 병사 데이터가 없습니다.
            </div>
          )
          : (
            devices.map((telemetry) => (
              <DeviceCard
                key={telemetry.device_id}
                telemetry={telemetry}
              />
            ))
          )}
      </section>


      <section
        className="operations-grid"
        aria-label="위험도 추이와 관제 요약"
      >
        {priorityDevice
          ? (
            <RiskTrend
              deviceId={priorityDevice.device_id}
              points={
                riskHistory[
                  priorityDevice.device_id
                ] ?? []
              }
            />
          )
          : (
            <section className="risk-trend trend-placeholder">
              <p>
                RISK INDEX TREND
              </p>

              <h2>
                수신 대기 중
              </h2>
            </section>
          )}


        <section className="operations-summary">
          <p className="eyebrow">
            OPERATIONS SUMMARY
          </p>

          <h2>
            우선 대응
          </h2>

          <div className="priority-row">
            <span>
              확인 대기 경보
            </span>

            <strong>
              {
                alerts.filter(
                  (alert) =>
                    !alert.acknowledged,
                ).length
              }
            </strong>
          </div>

          <div className="priority-row emergency-row">
            <span>
              열린 응급 상황
            </span>

            <strong>
              {
                emergencies.filter(
                  (emergency) =>
                    emergency.open,
                ).length
              }
            </strong>
          </div>

          <p className="priority-note">
            경보 확인은 수신 기록이며,
            장치의 응급 래치를 해제하지 않습니다.
          </p>
        </section>
      </section>


      <TacticalMap devices={devices} />


      <CommandConsole
        alerts={alerts}
        emergencies={emergencies}
        role={role}
        actorId={actorId}
        onChanged={() =>
          void refreshConsole()
        }
      />
    </main>
  );
}


export default App;
