import type { TelemetryV2 } from "../types/device";
import { STATE_LABEL_KO } from "../types/device";

interface DeviceCardProps {
  telemetry: TelemetryV2;
}

function stateClass(state: TelemetryV2["state"]): string {
  switch (state) {
    case "NORMAL":
      return "soldier-card normal";
    case "WARNING":
      return "soldier-card warning";
    case "COOLING":
      return "soldier-card cooling";
    case "EMERGENCY":
      return "soldier-card emergency";
    case "BASELINE":
    case "BOOT":
      return "soldier-card baseline";
    default:
      return "soldier-card fault";
  }
}

export default function DeviceCard({ telemetry }: DeviceCardProps) {
  const coolingStage = `C${telemetry.cooling.requested}`;
  const riskDisplay = telemetry.risk_index === 255 ? "—" : telemetry.risk_index;
  const isEmergency = telemetry.state === "EMERGENCY";
  const sensorCheck = telemetry.active_errors.includes("SENSOR_CHECK");
  const strongestSignal = Object.entries(telemetry.contributions).sort(([, a], [, b]) => b - a)[0]?.[0];
  const causeLabels: Record<string, string> = {
    HR_dev: "심박 상승",
    HRV_suppression: "심박 변동 감소",
    SkinTemp_slope: "피부온도 상승",
    EDA_delta: "GSR 변화",
    ActivityLoad: "활동량 증가",
    EnvHeatProxy: "고온 환경",
  };
  const cause = strongestSignal
    ? (causeLabels[strongestSignal] ?? strongestSignal)
    : telemetry.risk_index === 255 ? "상태 계산 대기" : "특이사항 없음";
  const sensorStatus = telemetry.active_errors.length > 0 ? telemetry.active_errors.join(", ") : "센서 정상";

  return (
    <div className={stateClass(telemetry.state)}>
      <div className="soldier-card-header">
        <div>
          <p className="soldier-id">병사 · {telemetry.device_id}</p>
          <h2>{isEmergency ? "위급" : sensorCheck ? "센서 확인" : STATE_LABEL_KO[telemetry.state]}</h2>
        </div>
        <div className="risk-score">
          <strong>{riskDisplay}</strong>
          <span>위험도</span>
        </div>
      </div>

      <div className="soldier-metrics">
        <div>
          <span>심박</span>
          <strong>{telemetry.signals.hr_bpm} bpm</strong>
        </div>
        <div>
          <span>피부온도</span>
          <strong>{telemetry.signals.skin_c.toFixed(2)} ℃</strong>
        </div>
        <div>
          <span>팬 출력</span>
          <strong>{telemetry.cooling.actual_pwm}%</strong>
        </div>
        <div>
          <span>냉각 단계</span>
          <strong>{coolingStage}</strong>
        </div>
      </div>

      <div className="card-context">
        <div>
          <span>판단 근거</span>
          <strong>{cause}</strong>
        </div>
        <div>
          <span>센서 상태</span>
          <strong className={telemetry.active_errors.length > 0 ? "sensor-warning" : "sensor-ok"}>{sensorStatus}</strong>
        </div>
      </div>

      {telemetry.raw && (
        <div className="raw-signals">
          <span>GSR <strong>{telemetry.raw.gsr ?? "—"}</strong></span>
          <span>환경 <strong>{telemetry.raw.air_temp_c ?? "—"}℃ / {telemetry.raw.humidity_percent ?? "—"}%</strong></span>
          <span>Finger <strong>{telemetry.raw.finger_detected ? "YES" : "NO"}</strong></span>
          <span>LoRa <strong>{telemetry.radio?.rssi_dbm ?? "—"} dBm</strong></span>
          <span>GPS <strong>{telemetry.raw.gps_fix ? `${telemetry.raw.latitude?.toFixed(5) ?? "—"}, ${telemetry.raw.longitude?.toFixed(5) ?? "—"}` : "NO FIX"}</strong></span>
        </div>
      )}

      <div className="soldier-card-footer">
        <span>seq {telemetry.sequence}</span>
        <span>{new Date(telemetry.gateway_utc).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
      </div>
    </div>
  );
}
