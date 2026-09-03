"""벨트↔장갑 표시 프로토콜과 파이썬 디코더가 같은 코드 체계를 쓰는지 검사한다.

Arduino 스케치는 자기 폴더 안의 헤더만 볼 수 있어서, display_protocol.h가
belt_heltec/과 glove_esp32/ 양쪽에 복사돼 있어야 한다(헤더 주석의 요구사항).
사본이 갈라지면 벨트가 보낸 상태 코드를 장갑이 다른 뜻으로 읽게 되고,
게이트웨이의 DeviceStateCode까지 어긋난다. 세 정의를 여기서 한 번에 묶어 둔다.
"""

import re
from pathlib import Path

import pytest

from heatsentry.common.glove_packets import (
    BeltCauseCode,
    CoolingStageCode,
    DeviceStateCode,
)

FIRMWARE = Path(__file__).resolve().parents[1] / "firmware"
BELT_HEADER = FIRMWARE / "belt_heltec" / "display_protocol.h"
GLOVE_HEADER = FIRMWARE / "glove_esp32" / "display_protocol.h"


def _parse_enum(header_text: str, enum_name: str) -> dict[str, int]:
    """`enum X : uint8_t { A = 0, B = 1, ... }` 본문을 이름->값으로 푼다."""
    match = re.search(rf"enum\s+{enum_name}\s*:\s*uint8_t\s*\{{(.*?)\}}", header_text, re.S)
    assert match, f"{enum_name} 정의를 헤더에서 찾지 못했다"

    # 주석에도 쉼표가 들어 있으므로(예: "Risk 60~84, 10초 이상") 줄 단위로 먼저 지운다.
    body = "\n".join(re.sub(r"//.*", "", line) for line in match.group(1).splitlines())

    values: dict[str, int] = {}
    next_implicit = 0
    for entry in body.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "=" in entry:
            name, raw = (part.strip() for part in entry.split("=", 1))
            next_implicit = int(raw, 0)
        else:
            name = entry
        values[name] = next_implicit
        next_implicit += 1
    return values


def test_both_sketch_folders_have_the_header():
    """어느 한쪽이 없으면 그 스케치는 컴파일되지 않는다."""
    assert BELT_HEADER.exists(), "belt_heltec/display_protocol.h 누락 — 벨트 스케치가 빌드되지 않는다"
    assert GLOVE_HEADER.exists(), "glove_esp32/display_protocol.h 누락 — 장갑 스케치가 빌드되지 않는다"


def test_two_copies_are_identical():
    assert BELT_HEADER.read_bytes() == GLOVE_HEADER.read_bytes(), (
        "두 display_protocol.h 사본이 갈라졌다. 한쪽을 고쳤으면 다른 쪽에도 복사한다."
    )


@pytest.mark.parametrize(
    ("enum_name", "prefix", "python_enum"),
    [
        ("StateCode", "STATE_", DeviceStateCode),
        ("CoolingStageCode", "COOLING_", CoolingStageCode),
        ("CauseCode", "CAUSE_", BeltCauseCode),
    ],
)
def test_python_mirror_matches_firmware(enum_name, prefix, python_enum):
    """파이썬 디코더의 enum이 펌웨어 헤더와 이름·값 모두 같아야 한다."""
    firmware_values = {
        name.removeprefix(prefix): value
        for name, value in _parse_enum(GLOVE_HEADER.read_text(), enum_name).items()
    }
    python_values = {member.name: int(member) for member in python_enum}
    assert firmware_values == python_values
