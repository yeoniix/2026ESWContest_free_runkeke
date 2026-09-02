// HS-SIID-002 p6 "게이트웨이 데이터 계약"(schema_version 2.0)과 1:1로 대응한다.
// 옛 GPS 분대 관제용 Soldier 타입(soldier_id/risk_level/GPS 좌표 등)은
// HS-SIID-002/HS-PDD-002 v2.0 기준선으로 완전히 대체됐다.

export type DeviceState =
  | "BOOT"
  | "BASELINE"
  | "NORMAL"
  | "WARNING"
  | "COOLING"
  | "EMERGENCY"
  | "FAULT";

export type ActivityLabel = "REST" | "WALK" | "RUN" | "CRAWL" | "STATIC" | "UNKNOWN";

// 벨트 펌웨어(firmware/belt_heltec)가 자체 임계값으로 내린 판정.
// 게이트웨이의 RiskIndex v0.3 판정(DeviceState)과는 기준이 다르다 —
// 현장에서 팬을 돌리고 장갑 OLED에 뜬 것은 이쪽 값이다.
export type BeltState =
  | "BOOT"
  | "BASELINE"
  | "NORMAL"
  | "CAUTION"
  | "COOLING_50"
  | "DANGER"
  | "EMERGENCY"
  | "SENSOR_CHECK";

export type BeltCause =
  | "NONE"
  | "HR_HIGH"
  | "HR_CHANGE"
  | "TEMP_UP"
  | "GSR_UP"
  | "HOT_ENV"
  | "ACTIVE"
  | "SENSOR";

export interface QualityV2 {
  ppg: number;
  skin: number;
  eda: number;
  imu: number;
}

export interface SignalsV2 {
  hr_bpm: number;
  skin_c: number;
  activity: ActivityLabel;
}

export interface CoolingV2 {
  requested: number; // 0~4, C0~C4
  actual_pwm: number; // 0~100
  current_ma: number;
}

export interface RawGloveV2 {
  gsr: number | null;
  gsr_diff: number | null;
  ir: number | null;
  air_temp_c: number | null;
  humidity_percent: number | null;
  finger_detected: boolean | null;
  glove_data: boolean | null;
  dht_data: boolean | null;
  gps_fix: boolean | null;
  latitude: number | null;
  longitude: number | null;
  belt_state: BeltState | null;
  belt_cause: BeltCause | null;
  belt_fan_on: boolean | null;
}

export interface RadioLinkV2 {
  rssi_dbm: number | null;
  snr_db: number | null;
}

export interface TelemetryV2 {
  schema_version: "2.0";
  gateway_utc: string;
  device_id: string;
  monotonic_ms: number;
  state: DeviceState;
  risk_index: number; // 0~100, 255=invalid
  valid_weight: number;
  quality: QualityV2;
  signals: SignalsV2;
  cooling: CoolingV2;
  contributions: Record<string, number>;
  active_errors: string[];
  raw?: RawGloveV2 | null;
  radio?: RadioLinkV2 | null;
  config_version: string;
  sequence: number;
}

export interface EventRecord {
  seq: number;
  gateway_utc: string;
  monotonic_ms: number;
  device_id: string;
  event_type: string;
  reason: string;
  payload: Record<string, unknown>;
  previous_hash: string;
  event_hash: string;
}

export interface CommandAckMessage {
  cmd_id: number;
  device_id: string;
  requested_level: number;
  requested_reason: string;
  actual_pwm: number;
  current_ma: number;
  result: string;
  retries: number;
  gateway_utc: string;
}

export interface AlertRecord {
  id: string;
  device_id: string;
  state: DeviceState;
  opened_at: string;
  acknowledged: boolean;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
}

export interface EmergencyRecord {
  id: string;
  device_id: string;
  opened_at: string;
  open: boolean;
  closed_by: string | null;
  closed_at: string | null;
  close_reason: string | null;
}

// 표6 "로컬 API v2" 권한 컬럼과 동일.
export type Role = "observer" | "commander" | "tester" | "maintainer";

export const STATE_ORDER: DeviceState[] = [
  "BOOT",
  "BASELINE",
  "NORMAL",
  "WARNING",
  "COOLING",
  "EMERGENCY",
  "FAULT",
];

export const STATE_LABEL_KO: Record<DeviceState, string> = {
  BOOT: "부팅",
  BASELINE: "기준선 측정",
  NORMAL: "정상",
  WARNING: "경고",
  COOLING: "냉각 중",
  EMERGENCY: "응급",
  FAULT: "고장",
};

export const BELT_STATE_LABEL_KO: Record<BeltState, string> = {
  BOOT: "부팅",
  BASELINE: "기준선 측정",
  NORMAL: "정상",
  CAUTION: "주의",
  COOLING_50: "냉각 50%",
  DANGER: "위험 · 냉각 100%",
  EMERGENCY: "응급",
  SENSOR_CHECK: "센서 확인",
};

export const BELT_CAUSE_LABEL_KO: Record<BeltCause, string> = {
  NONE: "특이사항 없음",
  HR_HIGH: "심박 상승",
  HR_CHANGE: "심박 변동",
  TEMP_UP: "피부온도 상승",
  GSR_UP: "GSR 변화",
  HOT_ENV: "고온 환경",
  ACTIVE: "활동량 증가",
  SENSOR: "센서 접촉 불량",
};

export const ACTIVITY_LABEL_KO: Record<ActivityLabel, string> = {
  REST: "휴식",
  WALK: "저강도 이동",
  RUN: "고강도 이동",
  CRAWL: "포복/극한 활동",
  STATIC: "정지(무동작)",
  UNKNOWN: "알 수 없음",
};
