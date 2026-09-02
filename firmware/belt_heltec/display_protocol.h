#pragma once
#include <stdint.h>

// =====================================================
// HeatSentry Belt ↔ Glove Display Protocol
//
// DeviceState는 프로젝트 전체에서 아래 7개만 사용:
// BOOT / BASELINE / NORMAL / CAUTION / COOLING
// EMERGENCY / SENSOR_CHECK
//
// 냉각 강도는 DeviceState와 분리하여 CoolingStage C0~C4로 표현.
// DisplayPacket 크기는 기존과 동일한 12 bytes 유지.
// CoolingStage는 flags bit4~6에 저장.
// =====================================================

#define DISPLAY_PACKET_MAGIC   0xD15A
#define DISPLAY_PACKET_VERSION 2

// =====================================================
// DeviceState - 프로젝트 전체 공통 7상태
// =====================================================
enum StateCode : uint8_t {
  STATE_BOOT         = 0,
  STATE_BASELINE     = 1,
  STATE_NORMAL       = 2,
  STATE_CAUTION      = 3,
  STATE_COOLING      = 4,
  STATE_EMERGENCY    = 5,
  STATE_SENSOR_CHECK = 6
};

// =====================================================
// CoolingStage - 팬 냉각 단계
//
// C0 : 0%
// C1 : 50%
// C2 : 100%
// C3 : 100% (고위험 지속)
// C4 : 100% (Emergency)
// =====================================================
enum CoolingStageCode : uint8_t {
  COOLING_C0 = 0,
  COOLING_C1 = 1,
  COOLING_C2 = 2,
  COOLING_C3 = 3,
  COOLING_C4 = 4
};

// =====================================================
// Cause - 판단 원인
// =====================================================
enum CauseCode : uint8_t {
  CAUSE_NONE      = 0,
  CAUSE_HR_HIGH   = 1,
  CAUSE_HR_CHANGE = 2,
  CAUSE_TEMP_UP   = 3,
  CAUSE_GSR_UP    = 4,
  CAUSE_HOT_ENV   = 5,
  CAUSE_ACTIVE    = 6,
  CAUSE_SENSOR    = 7
};

// =====================================================
// DisplayPacket flags
// =====================================================
#define DISPLAY_FLAG_FINGER       (1U << 0)
#define DISPLAY_FLAG_EMERGENCY    (1U << 1)
#define DISPLAY_FLAG_FAN_ON       (1U << 2)
#define DISPLAY_FLAG_GLOVE_VALID  (1U << 3)

#define DISPLAY_STAGE_SHIFT       4
#define DISPLAY_STAGE_MASK        (0x07U << DISPLAY_STAGE_SHIFT)

inline uint8_t displaySetCoolingStage(uint8_t flags, uint8_t stage) {
  flags &= (uint8_t)~DISPLAY_STAGE_MASK;
  flags |= (uint8_t)((stage & 0x07U) << DISPLAY_STAGE_SHIFT);
  return flags;
}

inline uint8_t displayGetCoolingStage(uint8_t flags) {
  return (uint8_t)((flags & DISPLAY_STAGE_MASK) >> DISPLAY_STAGE_SHIFT);
}

// =====================================================
// DisplayPacket 12 bytes
// =====================================================
struct __attribute__((packed)) DisplayPacket {
  uint16_t magic;          // 0xD15A
  uint8_t  version;        // DISPLAY_PACKET_VERSION
  uint8_t  state;          // StateCode
  uint8_t  cause;          // CauseCode
  uint8_t  fanPercent;     // 전체 냉각 출력 0 / 50 / 100
  uint8_t  bpm;
  int16_t  skinTemp_x100;
  uint8_t  flags;          // bit0~3 상태 + bit4~6 CoolingStage
  uint16_t seq;
};

static_assert(sizeof(DisplayPacket) == 12, "DisplayPacket must be 12 bytes");
