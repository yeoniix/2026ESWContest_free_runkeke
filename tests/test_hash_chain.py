from common.hash_chain import GENESIS_HASH, append_event, compute_event_hash, verify_chain


def _build_chain(n: int) -> list[dict]:
    events = []
    prev = GENESIS_HASH
    for i in range(n):
        event = append_event(prev, {"seq": i, "event_type": "TEST", "value": i * 1.0})
        events.append(event)
        prev = event["event_hash"]
    return events


def test_chain_verifies_when_untouched():
    events = _build_chain(5)
    ok, bad_index = verify_chain(events)
    assert ok is True
    assert bad_index is None


def test_chain_detects_tampering():
    events = _build_chain(5)
    events[2]["value"] = 999  # DAT-001 / T10: 로그 변조 -> 해시체인 불일치 검출
    ok, bad_index = verify_chain(events)
    assert ok is False
    assert bad_index == 2


def test_chain_detects_reordering():
    events = _build_chain(3)
    events[0], events[1] = events[1], events[0]
    ok, bad_index = verify_chain(events)
    assert ok is False
    assert bad_index == 0


def test_canonical_json_is_deterministic_regardless_of_key_order():
    a = {"b": 1, "a": 2.0000001}
    b = {"a": 2.0000001, "b": 1}
    assert compute_event_hash(GENESIS_HASH, a) == compute_event_hash(GENESIS_HASH, b)
