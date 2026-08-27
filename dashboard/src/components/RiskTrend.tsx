import type { RiskPoint } from "../hooks/useLiveDevices";

interface RiskTrendProps {
  deviceId: string;
  points: RiskPoint[];
}

function linePath(points: RiskPoint[]): string {
  if (points.length === 0) return "";
  const width = 300;
  const height = 94;
  return points
    .map((point, index) => {
      const x = points.length === 1 ? width : (index / (points.length - 1)) * width;
      const y = height - (Math.max(0, Math.min(100, point.riskIndex)) / 100) * height;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export default function RiskTrend({ deviceId, points }: RiskTrendProps) {
  const current = points.at(-1)?.riskIndex;
  return (
    <section className="risk-trend" aria-label={`${deviceId} 위험도 추이`}>
      <div className="panel-heading">
        <div>
          <p>RISK INDEX TREND</p>
          <h2>{deviceId}</h2>
        </div>
        <strong>{current ?? "—"}<small>/100</small></strong>
      </div>
      <div className="trend-chart">
        <span className="trend-threshold threshold-warning">60</span>
        <span className="trend-threshold threshold-cooling">80</span>
        <span className="trend-threshold threshold-danger">90</span>
        {points.length > 1 ? (
          <svg viewBox="0 0 300 100" preserveAspectRatio="none" role="img" aria-label="최근 위험도 변화">
            <path className="trend-area" d={`${linePath(points)} L300,100 L0,100 Z`} />
            <path className="trend-line" d={linePath(points)} />
          </svg>
        ) : (
          <p className="trend-empty">실시간 데이터가 누적되면 최근 60개 측정값을 표시합니다.</p>
        )}
      </div>
    </section>
  );
}
