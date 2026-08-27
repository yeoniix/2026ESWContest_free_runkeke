import { useEffect, useMemo, useRef, useState } from "react";
import type { TelemetryV2 } from "../types/device";

interface TacticalMapProps {
  devices: TelemetryV2[];
}

type LocatedDevice = TelemetryV2 & { raw: NonNullable<TelemetryV2["raw"]> };

function isLocated(device: TelemetryV2): device is LocatedDevice {
  return Boolean(
    device.raw?.gps_fix
    && Number.isFinite(device.raw.latitude)
    && Number.isFinite(device.raw.longitude)
  );
}

type KakaoMap = { setCenter(position: unknown): void; relayout(): void };
type KakaoOverlay = { setMap(map: KakaoMap | null): void };

declare global {
  interface Window {
    kakao?: {
      maps: {
        load(callback: () => void): void;
        Map: new (container: HTMLElement, options: { center: unknown; level: number }) => KakaoMap;
        LatLng: new (latitude: number, longitude: number) => unknown;
        CustomOverlay: new (options: { position: unknown; content: HTMLElement; yAnchor: number }) => KakaoOverlay;
      };
    };
  }
}

const KAKAO_APP_KEY = import.meta.env.VITE_KAKAO_MAP_APP_KEY as string | undefined;
const DEFAULT_CENTER = { latitude: 37.566535, longitude: 126.977969 };

function markerClass(state: TelemetryV2["state"]) {
  return state === "NORMAL" || state === "BASELINE" || state === "BOOT" ? "safe" : "danger";
}

export default function TacticalMap({ devices }: TacticalMapProps) {
  const located = useMemo(() => devices.filter(isLocated), [devices]);
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<KakaoMap | null>(null);
  const overlaysRef = useRef<KakaoOverlay[]>([]);
  const [mapError, setMapError] = useState<string | null>(null);

  useEffect(() => {
    if (!KAKAO_APP_KEY || !containerRef.current) return;
    let cancelled = false;

    const renderMarkers = () => {
      if (cancelled || !window.kakao || !containerRef.current) return;
      const maps = window.kakao.maps;
      const centerDevice = located[0];
      const center = centerDevice
        ? new maps.LatLng(centerDevice.raw.latitude as number, centerDevice.raw.longitude as number)
        : new maps.LatLng(DEFAULT_CENTER.latitude, DEFAULT_CENTER.longitude);

      if (!mapRef.current) {
        mapRef.current = new maps.Map(containerRef.current, { center, level: centerDevice ? 4 : 7 });
      } else {
        mapRef.current.setCenter(center);
        mapRef.current.relayout();
      }

      overlaysRef.current.forEach((overlay) => overlay.setMap(null));
      overlaysRef.current = located.map((device) => {
        const marker = document.createElement("button");
        marker.type = "button";
        marker.className = `kakao-device-marker ${markerClass(device.state)}`;
        marker.setAttribute("aria-label", `${device.device_id}: ${device.state}, 위험도 ${device.risk_index}`);
        marker.innerHTML = `<span>${device.device_id.replace("HS-W-", "W-")} · R${device.risk_index === 255 ? "—" : device.risk_index}</span><i aria-hidden="true"></i>`;
        const overlay = new maps.CustomOverlay({
          position: new maps.LatLng(device.raw.latitude as number, device.raw.longitude as number),
          content: marker,
          yAnchor: 1,
        });
        overlay.setMap(mapRef.current);
        return overlay;
      });
    };

    const loadMap = () => {
      if (!window.kakao) return;
      window.kakao.maps.load(renderMarkers);
    };

    const existing = document.getElementById("kakao-map-sdk") as HTMLScriptElement | null;
    if (existing) {
      if (window.kakao) loadMap();
      else existing.addEventListener("load", loadMap, { once: true });
    } else {
      const script = document.createElement("script");
      script.id = "kakao-map-sdk";
      script.async = true;
      script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(KAKAO_APP_KEY)}&autoload=false`;
      script.onload = loadMap;
      script.onerror = () => setMapError("카카오맵을 불러오지 못했습니다. 등록 도메인과 API 키를 확인하세요.");
      document.head.appendChild(script);
    }
    return () => { cancelled = true; };
  }, [located]);

  return (
    <section className="tactical-map" aria-label="GPS 장치 위치">
      <div className="section-header">
        <div>
          <p className="eyebrow">GPS POSITION</p>
          <h2>현장 위치</h2>
        </div>
        <span>{located.length}/{devices.length} GPS 수신</span>
      </div>
      {!KAKAO_APP_KEY ? (
        <div className="map-empty">`.env.local`에 `VITE_KAKAO_MAP_APP_KEY`를 설정하면 카카오맵에 GPS 위치가 표시됩니다.</div>
      ) : (
        <div className="map-content">
          <div className="kakao-map" ref={containerRef} aria-label="카카오맵 장치 위치" />
          <div className="location-list">
            {mapError && <p className="map-error">{mapError}</p>}
            {located.length === 0 && <p className="map-empty-inline">GPS Fix 수신 대기 중</p>}
            {located.map((device) => (
              <div className="location-row" key={device.device_id}>
                <div>
                  <strong>{device.device_id}</strong>
                  <span>{(device.raw.latitude as number).toFixed(6)}, {(device.raw.longitude as number).toFixed(6)}</span>
                </div>
                <b className={markerClass(device.state)}>{device.state === "NORMAL" ? "정상" : "위험"}</b>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
