import {
  useState,
} from "react";

import {
  exportData,
} from "../api/gateway";

import type {
  EventRecord,
  Role,
} from "../types/device";


interface EventLogProps {
  events: EventRecord[];
  role: Role;
  actorId: string;
}


const SEVERITY_CLASS:
  Record<string, string> = {

    EMERGENCY_ENTER:
      "sev-critical",

    EMERGENCY_ACK_CLOSED:
      "sev-critical",

    SAFETY_STOP:
      "sev-critical",

    COOLING_C3:
      "sev-warning",

    COOLING_C2:
      "sev-warning",

    CAUTION_ENTER:
      "sev-warning",

    COOL_CMD_FAILED:
      "sev-warning",

    ACK_TIMEOUT:
      "sev-warning",
  };


function severityClass(
  eventType: string,
): string {

  return (
    SEVERITY_CLASS[eventType]
    ?? "sev-info"
  );
}


export default function EventLog({
  events,
  role,
  actorId,
}: EventLogProps) {

  const [
    exporting,
    setExporting,
  ] = useState(false);

  const [
    exportError,
    setExportError,
  ] = useState<string | null>(
    null
  );


  async function handleExport(
    format: "json" | "csv",
  ) {
    setExporting(true);
    setExportError(null);

    try {
      const data = await exportData(
        role,
        actorId,
        format,
      );

      const blob = new Blob(
        [data],
        {
          type:
            format === "csv"
              ? "text/csv"
              : "application/json",
        },
      );

      const url =
        URL.createObjectURL(blob);

      const a =
        document.createElement("a");

      a.href = url;
      a.download =
        `heatsentry-events.${format}`;

      a.click();

      URL.revokeObjectURL(url);
    }
    catch {
      setExportError(
        role === "tester"
          ? "내보내기에 실패했습니다."
          : "tester 권한이 필요합니다.",
      );
    }
    finally {
      setExporting(false);
    }
  }


  const ordered = [
    ...events,
  ].reverse();


  return (
    <section className="event-log-panel">
      <div className="section-header">
        <div>
          <p className="eyebrow">
            Audit Trail
          </p>

          <h2>
            이벤트 로그 (해시체인)
          </h2>
        </div>

        <div className="export-buttons">
          <button
            disabled={exporting}
            onClick={() =>
              handleExport("csv")
            }
          >
            CSV 내보내기
          </button>

          <button
            disabled={exporting}
            onClick={() =>
              handleExport("json")
            }
          >
            JSON 내보내기
          </button>
        </div>
      </div>

      {exportError && (
        <div className="error">
          {exportError}
        </div>
      )}

      <div className="event-log-list">
        {ordered.length === 0 && (
          <div className="empty">
            아직 이벤트가 없습니다.
          </div>
        )}

        {ordered.map((event) => (
          <div
            key={event.event_hash}
            className={
              `event-row ${
                severityClass(
                  event.event_type,
                )
              }`
            }
          >
            <span className="event-seq">
              #{event.seq}
            </span>

            <span className="event-type">
              {event.event_type}
            </span>

            <span className="event-device">
              {event.device_id}
            </span>

            <span className="event-reason">
              {event.reason}
            </span>

            <span className="event-time">
              {event.gateway_utc}
            </span>

            <span
              className="event-hash"
              title={event.event_hash}
            >
              {event.event_hash.slice(
                0,
                8,
              )}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
