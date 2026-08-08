import type { TelemetryV2 } from "../types/device";
import { ACTIVITY_LABEL_KO, STATE_LABEL_KO } from "../types/device";

interface DeviceCardProps {
  telemetry: TelemetryV2;
}

function stateClass(state: TelemetryV2["state"]): string {
  switch (state) {
    case "NORMAL":
      return "card normal";
    case "WARNING":
      return "card warning";
    case "COOLING":
      return "card cooling";
    case "EMERGENCY":
      return "card critical";
    case "BASELINE":
    case "BOOT":
      return "card baseline";
    default:
      return "card fault";
  }
}

const QUALITY_LABELS: Record<keyof TelemetryV2["quality"], string> = {
  ppg: "PPG",
  skin: "피부온도",
  eda: "EDA",
  imu: "IMU",
};

function QualityBar({ label, value }: { label: string; value: number }) {
  const tone = value >= 70 ? "ok" : value >= 40 ? "mid" : "low";
  return (
    <div className="quality-row">
      <span>{label}</span>
      <div className="quality-track">
        <div className={`quality-fill ${tone}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
      <strong>{value}</strong>
    </div>
  );
}

export default function DeviceCard({ telemetry }: DeviceCardProps) {
  const coolingStage = `C${telemetry.cooling.requested}`;
  const riskDisplay = telemetry.risk_index === 255 ? "—" : telemetry.risk_index;

  return (
    <div className={stateClass(telemetry.state)}>
      <div className="card-header">
        <div>
          <h2>{telemetry.device_id}</h2>
          <p className="subtitle">{STATE_LABEL_KO[telemetry.state]}</p>
        </div>
        <div className="score">
          {riskDisplay}
          <span>/100</span>
        </div>
      </div>

      {telemetry.active_errors.length > 0 && (
        <div className="error-chips">
          {telemetry.active_errors.map((code) => (
            <span key={code} className="error-chip">
              {code}
            </span>
          ))}
        </div>
      )}

      <div className="metrics">
        <div>
          <span>심박</span>
          <strong>{telemetry.signals.hr_bpm} bpm</strong>
        </div>
        <div>
          <span>피부온도</span>
          <strong>{telemetry.signals.skin_c.toFixed(2)} ℃</strong>
        </div>
        <div>
          <span>활동 상태</span>
          <strong>{ACTIVITY_LABEL_KO[telemetry.signals.activity] ?? telemetry.signals.activity}</strong>
        </div>
        <div>
          <span>유효 가중치</span>
          <strong>{(telemetry.valid_weight * 100).toFixed(0)}%</strong>
        </div>
      </div>

      <div className="cooling-panel">
        <span>냉각 단계 {coolingStage}</span>
        <div className="cooling-bar-track">
          <div className="cooling-bar-fill" style={{ width: `${telemetry.cooling.actual_pwm}%` }} />
        </div>
        <div className="cooling-readout">
          <span>목표 {telemetry.cooling.actual_pwm}%</span>
          <span>{telemetry.cooling.current_ma} mA</span>
        </div>
      </div>

      <div className="quality-panel">
        {(Object.keys(QUALITY_LABELS) as (keyof TelemetryV2["quality"])[]).map((key) => (
          <QualityBar key={key} label={QUALITY_LABELS[key]} value={telemetry.quality[key]} />
        ))}
      </div>

      {Object.keys(telemetry.contributions).length > 0 && (
        <div className="contributions">
          <span>RiskIndex 기여도</span>
          <ul>
            {Object.entries(telemetry.contributions)
              .sort((a, b) => b[1] - a[1])
              .map(([name, value]) => (
                <li key={name}>
                  <span>{name}</span>
                  <strong>{(value * 100).toFixed(1)}</strong>
                </li>
              ))}
          </ul>
        </div>
      )}

      <div className="footer-meta">
        <span>seq {telemetry.sequence}</span>
        <span>config {telemetry.config_version}</span>
        <span>{telemetry.gateway_utc}</span>
      </div>
    </div>
  );
}
