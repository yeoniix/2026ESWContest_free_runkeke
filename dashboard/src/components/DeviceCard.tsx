import type {
  TelemetryV2,
} from "../types/device";

import {
  BELT_CAUSE_LABEL_KO,
  coolingStageLabel,
  deviceDisplayLabel,
} from "../types/device";


interface DeviceCardProps {
  telemetry: TelemetryV2;
}


function stateClass(
  telemetry: TelemetryV2,
): string {

  switch (telemetry.state) {
    case "NORMAL":
      return "soldier-card normal";

    case "CAUTION":
      return "soldier-card warning";

    case "COOLING":
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


export default function DeviceCard({
  telemetry,
}: DeviceCardProps) {

  const coolingStage =
    coolingStageLabel(
      telemetry.cooling.requested,
    );

  const riskDisplay =
    telemetry.risk_index === 255
      ? "—"
      : telemetry.risk_index;

  const displayedState =
    deviceDisplayLabel(
      telemetry,
    );

  const beltCause =
    telemetry.raw?.belt_cause
    ?? null;

  const strongestSignal =
    Object.entries(
      telemetry.contributions,
    )
      .sort(
        ([, a], [, b]) => b - a,
      )[0]?.[0];

  const contributionLabels:
    Record<string, string> = {
      HR_dev: "심박 상승",
      HRV_suppression: "심박 변동 감소",
      SkinTemp_slope: "피부온도 상승",
      EDA_delta: "GSR 변화",
      ActivityLoad: "활동량 증가",
      EnvHeatProxy: "고온 환경",
    };

  const cause =
    beltCause
    && beltCause !== "NONE"
      ? BELT_CAUSE_LABEL_KO[
          beltCause
        ]
      : strongestSignal
        ? (
          contributionLabels[
            strongestSignal
          ]
          ?? strongestSignal
        )
        : telemetry.risk_index === 255
          ? "상태 계산 대기"
          : "특이사항 없음";

  const visibleErrors =
    telemetry.active_errors;

  const sensorStatus =
    visibleErrors.length > 0
      ? visibleErrors.join(", ")
      : "센서 정상";

  return (
    <div className={
      stateClass(telemetry)
    }>
      <div className="soldier-card-header">
        <div>
          <p className="soldier-id">
            병사 · {telemetry.device_id}
          </p>

          <h2>
            {displayedState}
          </h2>
        </div>

        <div className="risk-score">
          <strong>
            {riskDisplay}
          </strong>

          <span>
            위험도
          </span>
        </div>
      </div>

      <div className="soldier-metrics">
        <div>
          <span>심박</span>

          <strong>
            {telemetry.signals.hr_bpm} bpm
          </strong>
        </div>

        <div>
          <span>피부온도</span>

          <strong>
            {telemetry.signals.skin_c.toFixed(2)} ℃
          </strong>
        </div>

        <div>
          <span>팬 출력</span>

          <strong>
            {telemetry.cooling.actual_pwm}%
          </strong>
        </div>

        <div>
          <span>냉각 단계</span>

          <strong>
            {coolingStage}
          </strong>
        </div>
      </div>

      <div className="card-context">
        <div>
          <span>판단 근거</span>

          <strong>
            {cause}
          </strong>
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

      {telemetry.raw && (
        <div className="raw-signals">
          <span>
            GSR{" "}
            <strong>
              {telemetry.raw.gsr ?? "—"}
            </strong>
          </span>

          <span>
            Finger{" "}
            <strong>
              {telemetry.raw.finger_detected
                ? "YES"
                : "NO"}
            </strong>
          </span>

          <span>
            LoRa{" "}
            <strong>
              {telemetry.radio?.rssi_dbm
                ?? "—"} dBm
            </strong>
          </span>

          <span>
            GPS{" "}
            <strong>
              {telemetry.raw.gps_fix
                ? `${
                    telemetry.raw.latitude
                      ?.toFixed(5)
                    ?? "—"
                  }, ${
                    telemetry.raw.longitude
                      ?.toFixed(5)
                    ?? "—"
                  }`
                : "NO FIX"}
            </strong>
          </span>
        </div>
      )}

      <div className="soldier-card-footer">
        <span>
          seq {telemetry.sequence}
        </span>

        <span>
          {new Date(
            telemetry.gateway_utc,
          ).toLocaleTimeString(
            "ko-KR",
            {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            },
          )}
        </span>
      </div>
    </div>
  );
}
