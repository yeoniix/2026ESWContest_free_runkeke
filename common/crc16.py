"""CRC-16/CCITT-FALSE 구현.

HS-SIID-002 표5: "22-23 crc16 u16 LE CRC-16/CCITT-FALSE".
poly=0x1021, init=0xFFFF, no reflect, xorout=0x0000.
"""

_POLY = 0x1021
_INIT = 0xFFFF


def crc16_ccitt_false(data: bytes) -> int:
    crc = _INIT
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ _POLY) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def append_crc16(data: bytes) -> bytes:
    """data 뒤에 CRC16(LE)을 붙인 전체 패킷을 반환한다."""
    crc = crc16_ccitt_false(data)
    return data + crc.to_bytes(2, "little")


def verify_crc16(packet: bytes) -> bool:
    """마지막 2바이트를 CRC16(LE)으로 보고 앞부분과 일치하는지 검사한다."""
    if len(packet) < 2:
        return False
    body, tail = packet[:-2], packet[-2:]
    expected = int.from_bytes(tail, "little")
    return crc16_ccitt_false(body) == expected
