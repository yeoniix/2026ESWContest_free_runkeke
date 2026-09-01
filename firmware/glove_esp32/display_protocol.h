#pragma once
#include <stdint.h>

// =====================================================
// Belt ↔ Glove : Display Protocol
// ★ 벨트 / 장갑 양쪽 폴더에 동일 파일 복사할 것
// =====================================================

#define DISPLAY_PACKET_MAGIC   0xD15A
#define DISPLAY_PACKET_VERSION 1

// =====================================================
// State (위험 단계)
// =====================================================
enum StateCode : uint8_t {
  STATE_BOOT         = 0,
  STATE_BASELINE     = 1,   // 처음 3분 베이스라인
  STATE_NORMAL       = 2,   // Risk < 40
  STATE_CAUTION      = 3,   // Risk 40~84  (10초 미만 포함)
  STATE_COOLING_50   = 4,   // Risk 60~84, 10초 이상  → 팬 50%
  STATE_DANGER       = 5,   // Risk ≥ 85,  10초 이상  → 팬 100%
  STATE_EMERGENCY    = 6,   // 수동 SOS              → 팬 100%
  STATE_SENSOR_CHECK = 7    // 손가락 없음 / BPM=0
};

// =====================================================
// Cause (원인)
// =====================================================
enum CauseCode : uint8_t {
  CAUSE_NONE      = 0,
  CAUSE_HR_HIGH   = 1,   // BPM ≥ baseline + 25
  CAUSE_HR_CHANGE = 2,
  CAUSE_TEMP_UP   = 3,   // 피부온도 상승
  CAUSE_GSR_UP    = 4,   // GSR 변화
  CAUSE_HOT_ENV   = 5,
  CAUSE_ACTIVE    = 6,
  CAUSE_SENSOR    = 7
};

// =====================================================
// DisplayPacket  12 bytes  (Belt → Glove, ESP-NOW)
// =====================================================
struct __attribute__((packed)) DisplayPacket {
  uint16_t magic;          // 0xD15A
  uint8_t  version;        // DISPLAY_PACKET_VERSION
  uint8_t  state;          // StateCode
  uint8_t  cause;          // CauseCode
  uint8_t  fanPercent;     // 0 / 50 / 100
  uint8_t  bpm;
  int16_t  skinTemp_x100;  // 온도 × 100
  uint8_t  flags;          // bit0=finger, bit1=emergency, bit2=fan, bit3=gloveValid
  uint16_t seq;
};
static_assert(sizeof(DisplayPacket) == 12, "DisplayPacket must be 12 bytes");
