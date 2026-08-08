// HS-SIID-002 표6 "로컬 API v2" 클라이언트.
import axios from "axios";
import type {
  AlertRecord,
  EmergencyRecord,
  EventRecord,
  Role,
  TelemetryV2,
} from "../types/device";

export const API_BASE_URL =
  (import.meta.env.VITE_GATEWAY_URL as string | undefined) ?? "http://127.0.0.1:8000";
export const WS_URL = API_BASE_URL.replace(/^http/, "ws") + "/ws/live";

function authHeaders(role: Role, actorId: string) {
  return { "X-HS-Role": role, "X-HS-Actor": actorId };
}

export async function fetchDevices(role: Role, actorId: string): Promise<TelemetryV2[]> {
  const res = await axios.get<TelemetryV2[]>(`${API_BASE_URL}/api/v2/devices`, {
    headers: authHeaders(role, actorId),
  });
  return res.data;
}

export async function fetchEvents(
  role: Role,
  actorId: string,
  params: { device_id?: string; event_type?: string; since_seq?: number } = {}
): Promise<EventRecord[]> {
  const res = await axios.get<EventRecord[]>(`${API_BASE_URL}/api/v2/events`, {
    headers: authHeaders(role, actorId),
    params,
  });
  return res.data;
}

export async function fetchAlerts(role: Role, actorId: string): Promise<AlertRecord[]> {
  const res = await axios.get<AlertRecord[]>(`${API_BASE_URL}/api/v2/alerts`, {
    headers: authHeaders(role, actorId),
  });
  return res.data;
}

export async function fetchEmergencies(role: Role, actorId: string): Promise<EmergencyRecord[]> {
  const res = await axios.get<EmergencyRecord[]>(`${API_BASE_URL}/api/v2/emergency`, {
    headers: authHeaders(role, actorId),
  });
  return res.data;
}

// commander 전용: "확인"일 뿐 응급 해제가 아니다 (HMI-001).
export async function ackAlert(
  role: Role,
  actorId: string,
  alertId: string,
  reason: string
): Promise<AlertRecord> {
  const res = await axios.post<AlertRecord>(
    `${API_BASE_URL}/api/v2/alerts/${alertId}/ack`,
    { reason },
    { headers: authHeaders(role, actorId) }
  );
  return res.data;
}

// commander 전용: 현장 확인자 ID·사유가 반드시 필요하다 (PDD #16).
export async function closeEmergency(
  role: Role,
  actorId: string,
  emergencyId: string,
  siteConfirmerId: string,
  reason: string
): Promise<EmergencyRecord> {
  const res = await axios.post<EmergencyRecord>(
    `${API_BASE_URL}/api/v2/emergency/${emergencyId}/close`,
    { reason, site_confirmer_id: siteConfirmerId },
    { headers: authHeaders(role, actorId) }
  );
  return res.data;
}

// tester 전용.
export async function exportData(
  role: Role,
  actorId: string,
  format: "json" | "csv",
  deviceId?: string
): Promise<string> {
  const res = await axios.post(
    `${API_BASE_URL}/api/v2/export`,
    { format, device_id: deviceId },
    { headers: authHeaders(role, actorId), responseType: "text" }
  );
  return res.data as string;
}
