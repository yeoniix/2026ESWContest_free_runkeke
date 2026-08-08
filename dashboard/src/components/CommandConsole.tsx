// HMI-001: "지휘관 확인은 수신 확인이며 응급 해제와 분리". 두 작업을 서로 다른
// 폼/버튼으로 완전히 분리해 하나의 클릭으로 경보 확인과 응급 해제가 동시에
// 일어나지 않게 한다 (금지 사항, HS-SIID-002 p7).
import { useState } from "react";
import { ackAlert, closeEmergency } from "../api/gateway";
import type { AlertRecord, EmergencyRecord, Role } from "../types/device";

interface CommandConsoleProps {
  alerts: AlertRecord[];
  emergencies: EmergencyRecord[];
  role: Role;
  actorId: string;
  onChanged: () => void;
}

export default function CommandConsole({ alerts, emergencies, role, actorId, onChanged }: CommandConsoleProps) {
  const [ackReason, setAckReason] = useState<Record<string, string>>({});
  const [closeForm, setCloseForm] = useState<Record<string, { confirmerId: string; reason: string }>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const openAlerts = alerts.filter((a) => !a.acknowledged);
  const openEmergencies = emergencies.filter((e) => e.open);

  const canAck = role === "commander";
  const canClose = role === "commander";

  async function handleAck(alertId: string) {
    setBusy(alertId);
    setMessage(null);
    try {
      await ackAlert(role, actorId, alertId, ackReason[alertId] ?? "");
      setMessage(`경보 ${alertId.slice(0, 8)} 확인 완료`);
      onChanged();
    } catch {
      setMessage("확인 처리에 실패했습니다 (commander 권한 필요).");
    } finally {
      setBusy(null);
    }
  }

  async function handleClose(emergencyId: string) {
    const form = closeForm[emergencyId];
    if (!form?.confirmerId || !form?.reason) {
      setMessage("현장 확인자 ID와 사유를 모두 입력해야 합니다.");
      return;
    }
    setBusy(emergencyId);
    setMessage(null);
    try {
      await closeEmergency(role, actorId, emergencyId, form.confirmerId, form.reason);
      setMessage(`응급 ${emergencyId.slice(0, 8)} 해제 기록 완료`);
      onChanged();
    } catch {
      setMessage("해제 처리에 실패했습니다 (commander 권한 필요).");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="console-panel">
      <div className="section-header">
        <div>
          <p className="eyebrow">Command Console</p>
          <h2>확인 · 응급 해제</h2>
        </div>
        <span>{role !== "commander" ? "관측 전용 (commander만 조작 가능)" : "지휘관 모드"}</span>
      </div>

      {message && <div className="console-message">{message}</div>}

      <div className="console-columns">
        <div className="console-column">
          <h3>대기 중인 경보 확인</h3>
          {openAlerts.length === 0 && <p className="empty-inline">확인 대기 중인 경보가 없습니다.</p>}
          {openAlerts.map((alert) => (
            <div key={alert.id} className="console-item">
              <div className="console-item-header">
                <strong>{alert.device_id}</strong>
                <span>{alert.state}</span>
              </div>
              <p className="console-item-meta">{alert.opened_at}</p>
              <input
                placeholder="확인 사유(선택)"
                value={ackReason[alert.id] ?? ""}
                onChange={(e) => setAckReason((prev) => ({ ...prev, [alert.id]: e.target.value }))}
                disabled={!canAck}
              />
              <button disabled={!canAck || busy === alert.id} onClick={() => handleAck(alert.id)}>
                수신 확인 (해제 아님)
              </button>
            </div>
          ))}
        </div>

        <div className="console-column">
          <h3>응급 해제 (현장 확인 필요)</h3>
          {openEmergencies.length === 0 && <p className="empty-inline">열려 있는 응급 상황이 없습니다.</p>}
          {openEmergencies.map((em) => (
            <div key={em.id} className="console-item emergency">
              <div className="console-item-header">
                <strong>{em.device_id}</strong>
                <span>EMERGENCY</span>
              </div>
              <p className="console-item-meta">{em.opened_at}</p>
              <input
                placeholder="현장 확인자 ID (필수)"
                value={closeForm[em.id]?.confirmerId ?? ""}
                onChange={(e) =>
                  setCloseForm((prev) => ({
                    ...prev,
                    [em.id]: { confirmerId: e.target.value, reason: prev[em.id]?.reason ?? "" },
                  }))
                }
                disabled={!canClose}
              />
              <input
                placeholder="해제 사유 (필수)"
                value={closeForm[em.id]?.reason ?? ""}
                onChange={(e) =>
                  setCloseForm((prev) => ({
                    ...prev,
                    [em.id]: { confirmerId: prev[em.id]?.confirmerId ?? "", reason: e.target.value },
                  }))
                }
                disabled={!canClose}
              />
              <button disabled={!canClose || busy === em.id} onClick={() => handleClose(em.id)}>
                현장 확인 후 응급 해제 기록
              </button>
              <p className="console-item-note">
                이 버튼은 관제 기록만 남깁니다. 실제 팬·SOS 래치 해제는 허리 노드의 물리 버튼으로만 됩니다.
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
