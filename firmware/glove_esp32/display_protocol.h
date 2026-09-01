#pragma once

#include <Arduino.h>

// 벨트가 판정하고 손목 OLED로 보내는 상태 코드.
// 벨트 코드의 StateCode/CauseCode/DisplayPacket과 반드시 같아야 한다.
enum StateCode : uint8_t {
  STATE_BOOT = 0,
  STATE_BASELINE,
  STATE_NORMAL,
  STATE_WARNING,
  STATE_COOLING,
  STATE_DANGER,
  STATE_HIGH_RISK,
  STATE_EMERGENCY,
  STATE_SENSOR_CHECK
};

enum CauseCode : uint8_t {
  CAUSE_NONE = 0,
  CAUSE_HR_HIGH,
  CAUSE_HR_CHANGE,
  CAUSE_TEMP_UP,
  CAUSE_GSR_UP,
  CAUSE_HOT_ENV,
  CAUSE_ACTIVE,
  CAUSE_SENSOR
};

struct __attribute__((packed)) DisplayPacket {
  uint16_t magic;
  uint8_t version;
  uint8_t state;
  uint8_t cause;
  uint8_t fanPercent;
  uint8_t bpm;
  int16_t skinTemp_x100;
  uint8_t flags;
  uint16_t seq;
};

static_assert(sizeof(DisplayPacket) == 12,
              "DisplayPacket must be 12 bytes");

constexpr uint16_t DISPLAY_PACKET_MAGIC = 0xD15A;
constexpr uint8_t DISPLAY_PACKET_VERSION = 1;
