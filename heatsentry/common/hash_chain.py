"""이벤트 해시체인.

출처: HS-SIID-002 p9 "데이터 저장·무결성·개인정보".
    event_hash = SHA256(previous_hash || canonical_json(event_without_hash))
    canonical_json: UTF-8, sorted keys, no whitespace, fixed decimal precision

DAT-001("모든 경보·명령·ACK·확인을 순번·시간·이전 해시와 저장")과
T10("로그 변조 -> 해시체인 불일치 검출")을 만족시키기 위한 최소 구현.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

GENESIS_HASH = "0" * 64
_DECIMAL_PRECISION = 6


def _normalize(value: Any) -> Any:
    """fixed decimal precision 규칙을 적용해 재현 가능한 값으로 바꾼다."""
    if isinstance(value, float):
        return round(value, _DECIMAL_PRECISION)
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    return value


def canonical_json(event: Mapping[str, Any]) -> bytes:
    normalized = _normalize(dict(event))
    return json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def compute_event_hash(previous_hash: str, event_without_hash: Mapping[str, Any]) -> str:
    payload = previous_hash.encode("utf-8") + canonical_json(event_without_hash)
    return hashlib.sha256(payload).hexdigest()


def append_event(previous_hash: str, event: dict) -> dict:
    """event에 previous_hash/event_hash를 채워 반환한다(원본은 변경하지 않음)."""
    event_wo_hash = {k: v for k, v in event.items() if k not in ("previous_hash", "event_hash")}
    event_hash = compute_event_hash(previous_hash, event_wo_hash)
    return {**event_wo_hash, "previous_hash": previous_hash, "event_hash": event_hash}


def verify_chain(events: list[dict]) -> tuple[bool, int | None]:
    """순서대로 해시체인을 검증한다. (정상여부, 최초 불일치 인덱스)를 반환한다."""
    expected_previous = GENESIS_HASH
    for i, event in enumerate(events):
        event_wo_hash = {
            k: v for k, v in event.items() if k not in ("previous_hash", "event_hash")
        }
        if event.get("previous_hash") != expected_previous:
            return False, i
        recomputed = compute_event_hash(expected_previous, event_wo_hash)
        if recomputed != event.get("event_hash"):
            return False, i
        expected_previous = event["event_hash"]
    return True, None
