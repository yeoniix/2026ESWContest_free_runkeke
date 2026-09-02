import type { TelemetryV2 } from "../types/device";
import {
  BELT_CAUSE_LABEL_KO,
  BELT_STATE_LABEL_KO,
  STATE_LABEL_KO,
} from "../types/device";

interface DeviceCardProps {
  telemetry: TelemetryV2;
}

/**
 * 화면 색상은 가능하면 Belt의 실제 상태를 기준으로 한다.
 * raw.belt_state가 없는 구형/시뮬레이터 데이터만 telemetry.state를 fallback으로 사용.
 */
function stateClass(telemetry: TelemetryV2): string {
  const beltState = telemetry.raw?.belt_state ?? null;

  if (beltState) {
    switch (beltState) {
      case "NORMAL":
        return "soldier-card normal";

      case "CAUTION":
        return "soldier-card warning";

      case "COOLING_50":
      case "DANGER":
        return "soldier-card cooling";

      case "EMERGENCY":
        return "soldier-card emergency";

      case "BOOT":
      case "BASELINE":
        return "soldier-card baseline";

      case "SENSOR_CHECK":
      default:
        return "soldier-card fault";
    }
  }

  // 구형/시뮬레이터 데이터 fallback
  switch (telemetry.state) {
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
  const beltState = telemetry.raw?.belt_state ?? null;
  const beltCause = telemetry.raw?.belt_cause ?? null;

  const coolingStage = `C${telemetry.cooling.requested}`;
  const riskDisplay =
    telemetry.risk_index === 255 ? "—" : telemetry.risk_index;

  // ------------------------------------------------------------------
  // ★ 사용자에게 보여주는 상태 이름은 Belt/장갑 OLED와 동일하게 표시
  //
  // Belt CAUTION      -> "주의"
  // Belt COOLING_50   -> "냉각 50%"
  // Belt DANGER       -> "위험 · 냉각 100%"
  // ------------------------------------------------------------------
  const displayedState = beltState
    ? BELT_STATE_LABEL_KO[beltState]
    : STATE_LABEL_KO[telemetry.state];

  const isEmergency =
    beltState === "EMERGENCY" || telemetry.state === "EMERGENCY";

  const sensorCheck =
    beltState === "SENSOR_CHECK" ||
    telemetry.active_errors.includes("SENSOR_CHECK");

  // 판단 근거는 Belt Cause를 최우선 사용한다.
  // Belt Cause가 없는 구형 데이터에서만 contributions를 fallback으로 사용.
  const strongestSignal = Object.entries(telemetry.contributions).sort(
    ([, a], [, b]) => b - a,
  )[0]?.[0];

  const causeLabels: Record<string, string> = {
    HR_dev: "심박 상승",
    HRV_suppression: "심박 변동 감소",
    SkinTemp_slope: "피부온도 상승",
    EDA_delta: "GSR 변화",
    ActivityLoad: "활동량 증가",
    EnvHeatProxy: "고온 환경",
  };

  const cause =
    beltCause && beltCause !== "NONE"
      ? BELT_CAUSE_LABEL_KO[beltCause]
      : strongestSignal
        ? (causeLabels[strongestSignal] ?? strongestSignal)
        : telemetry.risk_index === 255
          ? "상태 계산 대기"
          : "특이사항 없음";

  // BELT_STATE_MISMATCH는 더 이상 사용자에게 보여줄 필요가 없다.
  // 실제 현장 Belt 판정을 화면의 기준으로 사용하기 때문이다.
  const visibleErrors = telemetry.active_errors.filter(
    (error) => error !== "BELT_STATE_MISMATCH",
  );

  const sensorStatus =
    visibleErrors.length > 0 ? visibleErrors.join(", ") : "센서 정상";

  return (
    <div className={stateClass(telemetry)}>
      <div className="soldier-card-header">
        <div>
          <p className="soldier-id">병사 · {telemetry.device_id}</p>

          <h2>
            {isEmergency
              ? "응급"
              : sensorCheck
                ? "센서 확인"
                : displayedState}
          </h2>
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
          <strong
            className={
              visibleErrors.length > 0
                ? "sensor-warning"
                : "sensor-ok"
            }
          >
            {sensorStatus}
          </strong>
        </div>
      </div>

      {/*
        예전에는 이 위치에 "현장 장치 판정"을 한 번 더 표시했다.
        이제 카드 최상단 상태 자체가 Belt의 실제 상태이므로 중복 표시하지 않는다.
      */}

      {telemetry.raw && (
        <div className="raw-signals">
          <span>
            GSR <strong>{telemetry.raw.gsr ?? "—"}</strong>
          </span>

          {telemetry.raw.air_temp_c !== null && (
            <span>
              환경{" "}
              <strong>
                {telemetry.raw.air_temp_c}℃ /{" "}
                {telemetry.raw.humidity_percent ?? "—"}%
              </strong>
            </span>
          )}

          <span>
            Finger{" "}
            <strong>
              {telemetry.raw.finger_detected ? "YES" : "NO"}
            </strong>
          </span>

          <span>
            LoRa{" "}
            <strong>
              {telemetry.radio?.rssi_dbm ?? "—"} dBm
            </strong>
          </span>

          <span>
            GPS{" "}
            <strong>
              {telemetry.raw.gps_fix
                ? `${telemetry.raw.latitude?.toFixed(5) ?? "—"}, ${
                    telemetry.raw.longitude?.toFixed(5) ?? "—"
                  }`
                : "NO FIX"}
            </strong>
          </span>
        </div>
      )}

      <div className="soldier-card-footer">
        <span>seq {telemetry.sequence}</span>

        <span>
          {new Date(telemetry.gateway_utc).toLocaleTimeString("ko-KR", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}
        </span>
      </div>
    </div>
  );
}
