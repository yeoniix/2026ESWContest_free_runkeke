"""HeatSentry 손목/허리 노드 시뮬레이터 CLI.

손목(SU-W)+허리(SU-B) 폐루프를 시나리오대로 재생하고, 그 결과를
게이트웨이에 HTTP POST로 흘려보낸다.

사용 예:
    # 게이트웨이가 켜져 있어야 한다: uvicorn heatsentry.server.main:app --port 8000
    python -m heatsentry.simulator.run_demo --scenario T03
    python -m heatsentry.simulator.run_demo --scenario T08 --fast --sleep 0
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time

from heatsentry.algorithm.risk_config import DEFAULT_CONFIG, RiskConfig
from .belt_node import BeltNode
from .gateway_client import GatewayClient, GatewayUnavailable
from .scenarios import SCENARIOS
from .wrist_node import WristNode


def build_config(fast: bool) -> RiskConfig:
    if not fast:
        return DEFAULT_CONFIG
    # --fast: SYS-001의 3~5분 기준선 대신 6~9초로 줄여 로컬에서 빠르게 돌려본다.
    # 실제 심사/시연에서는 절대 쓰지 않는다.
    fast_baseline = dataclasses.replace(DEFAULT_CONFIG.baseline, min_minutes=0.1, max_minutes=0.15)
    return dataclasses.replace(DEFAULT_CONFIG, baseline=fast_baseline)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HeatSentry wrist+belt node simulator")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="T03")
    parser.add_argument("--gateway-url", default="http://127.0.0.1:8000")
    parser.add_argument("--device-id", default="HS-W-001")
    parser.add_argument("--fast", action="store_true", help="기준선 시간을 줄여서 빨리 돌려본다(시연용 아님)")
    parser.add_argument("--sleep", type=float, default=1.0, help="tick 사이 실제 대기 시간(초). 0이면 최대속도")
    parser.add_argument("--dt", type=float, default=1.0, help="tick 하나가 나타내는 시뮬레이션 시간(초)")
    parser.add_argument("--cycles", type=int, default=3, help="T10 통합 시나리오 반복 횟수")
    args = parser.parse_args(argv)

    config = build_config(args.fast)
    baseline_ticks = int(config.baseline.min_minutes * 60) + 5

    scenario_fn = SCENARIOS[args.scenario]
    if args.scenario == "T10":
        ticks = scenario_fn(baseline_ticks, cycles=args.cycles)
    else:
        ticks = scenario_fn(baseline_ticks)

    belt = BeltNode(device_id=args.device_id.replace("W", "B"))
    wrist = WristNode(belt, device_id=args.device_id, config=config)
    client = GatewayClient(args.gateway_url)

    print(f"HeatSentry simulator 시작 — scenario={args.scenario} device={args.device_id} ticks={len(ticks)}")
    print(f"게이트웨이: {args.gateway_url}")
    print("Ctrl+C로 중단할 수 있습니다.\n")

    for i, raw in enumerate(ticks):
        belt.overcurrent_fault = raw.belt_overcurrent
        belt.low_temp_fault = raw.belt_low_temp
        if raw.belt_physical_stop:
            belt.press_physical_stop()
        else:
            belt.release_physical_stop()

        result = wrist.tick(raw, dt_s=args.dt)
        telemetry = result["telemetry"]

        try:
            client.post_telemetry(telemetry)
            for event in result["events"]:
                client.post_event(
                    {
                        "device_id": args.device_id,
                        "monotonic_ms": telemetry["monotonic_ms"],
                        "event_type": event["event_type"],
                        "reason": event.get("reason", ""),
                        "payload": event.get("payload", {}),
                    }
                )
            if result["command_ack"]:
                client.post_command_ack(result["command_ack"])
        except GatewayUnavailable as exc:
            print(f"\n[오류] {exc}")
            return 1

        event_tags = ",".join(e["event_type"] for e in result["events"]) or "-"
        print(
            f"[t={i:04d}] state={telemetry['state']:<10} risk={telemetry['risk_index']:>3} "
            f"stage=C{telemetry['cooling']['requested']} fan={telemetry['cooling']['actual_pwm']:>3}% "
            f"hr={telemetry['signals']['hr_bpm']:>3} events={event_tags}"
        )

        if args.sleep > 0:
            time.sleep(args.sleep)

    print("\n시나리오 재생 완료.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
