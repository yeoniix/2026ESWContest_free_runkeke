#include "display_protocol.h"
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "HT_TinyGPS++.h"
#include "LoRaWan_APP.h"
#include "Arduino.h"

// =====================================================
// GPS ATGM336H
// GPS TX -> Heltec GPIO45 (RX)
// GPS RX -> Heltec GPIO2  (TX, optional)
// =====================================================
#define GPS_RX         45
#define GPS_TX          2
#define GPS_MAX_AGE_MS 15000

HardwareSerial GPSSerial(1);
TinyGPSPlus gps;

// =====================================================
// Emergency button
// GPIO7 -- BUTTON -- GND
// =====================================================
#define BUTTON_PIN          7
#define EMERGENCY_CANCEL_MS 10000UL
#define DEBOUNCE_MS         50UL

bool emergencyActive = false;
unsigned long emergencyStartMs = 0;
bool lastButtonState = HIGH;
unsigned long lastDebounceMs = 0;

// =====================================================
// FAN / MOTOR DRIVER
//
// A-1A -> GPIO6
// A-1B -> GND
// B-1A -> GPIO47
// B-1B -> GND
//
// C1은 물리적으로 FAN1=100%, FAN2=0%로 운전해
// 전체 냉각 단계 50%로 취급한다.
// =====================================================
#define FAN1_PIN  6
#define FAN2_PIN 47
#define FAN_FREQ  5000
#define FAN_BITS  8

uint8_t currentFan1Pct = 0;
uint8_t currentFan2Pct = 0;
uint8_t currentCoolingPct = 0;
bool fansOn = false;

void setFanPins(uint8_t pct1, uint8_t pct2, uint8_t aggregatePct) {
  pct1 = constrain(pct1, 0, 100);
  pct2 = constrain(pct2, 0, 100);
  aggregatePct = constrain(aggregatePct, 0, 100);

  ledcWrite(FAN1_PIN, (uint32_t)pct1 * 255 / 100);
  ledcWrite(FAN2_PIN, (uint32_t)pct2 * 255 / 100);

  bool newFansOn = pct1 > 0 || pct2 > 0;

  if (newFansOn != fansOn ||
      pct1 != currentFan1Pct ||
      pct2 != currentFan2Pct) {
    Serial.printf(
      "[FAN] FAN1=%u%% FAN2=%u%% / cooling=%u%%\n",
      pct1, pct2, aggregatePct
    );
  }

  currentFan1Pct = pct1;
  currentFan2Pct = pct2;
  currentCoolingPct = aggregatePct;
  fansOn = newFansOn;
}

void applyCoolingStage(uint8_t stage) {
  switch (stage) {
    case COOLING_C1:
      // 2개 팬 중 1개 100% = 전체 냉각 50%
      setFanPins(100, 0, 50);
      break;

    case COOLING_C2:
    case COOLING_C3:
    case COOLING_C4:
      setFanPins(100, 100, 100);
      break;

    case COOLING_C0:
    default:
      setFanPins(0, 0, 0);
      break;
  }
}

// =====================================================
// LoRa TX interval
// =====================================================
#define LORA_INTERVAL_NO_FIX 10000UL
#define LORA_INTERVAL_FIXED   2000UL

// =====================================================
// Glove ESP32U MAC
// =====================================================
uint8_t gloveMac[] = {
  0x34, 0x98, 0x7A, 0xBD, 0x7A, 0x2C
};

// =====================================================
// Glove -> Belt SensorPacket
// =====================================================
typedef struct SensorPacket {
  int bpm;
  float temp;
  int gsr;
  int gsrDiff;
  long ir;
  bool finger;
  unsigned long seq;
} SensorPacket;

SensorPacket gloveData;
bool gloveDataReceived = false;
unsigned long lastGloveReceiveTime = 0;

// =====================================================
// Belt -> Glove DisplayPacket
// =====================================================
DisplayPacket displayData;
uint16_t displaySequence = 0;

// =====================================================
// Belt -> Base LoRa TelemetryPacket
//
// 35 bytes 유지.
// airTemp_x10:
//   high byte = DeviceState
//   low byte  = Cause
//
// humidity_x10:
//   high byte = CoolingStage(C0~C4)
//   low byte  = RiskIndex(0~100, 255=invalid)
// =====================================================
struct __attribute__((packed)) TelemetryPacket {
  uint16_t magic;
  uint8_t  version;
  uint8_t  nodeId;
  uint16_t seq;

  uint8_t  bpm;
  int16_t  skinTemp_x100;
  uint16_t gsr;
  int16_t  gsrDiff;
  uint32_t ir;

  int16_t  airTemp_x10;
  uint16_t humidity_x10;

  int32_t  latitude_e7;
  int32_t  longitude_e7;
  uint8_t  satellites;
  int16_t  altitude_dm;
  uint16_t speed_x10;

  uint8_t  flags;
};

static_assert(
  sizeof(TelemetryPacket) == 35,
  "TelemetryPacket must be 35 bytes"
);

TelemetryPacket txData;
uint16_t loraSequence = 0;

// 현재 Belt가 실제로 사용 중인 단일 판정값
uint8_t currentRiskIndex = 255;
uint8_t currentCoolingStage = COOLING_C0;
uint8_t currentState = STATE_BOOT;
uint8_t currentCause = CAUSE_NONE;

// =====================================================
// Baseline 3 minutes
// =====================================================
#define BASELINE_TIME 180000UL

bool baselineStarted = false;
unsigned long baselineStartTime = 0;
int baselineSampleCnt = 0;

double baselineBPMSum = 0;
double baselineTempSum = 0;
long baselineGSRSum = 0;

float baselineBPM = 0.0f;
float baselineTemp = 0.0f;
int baselineGSR = 0;

// =====================================================
// Skin temperature slope
// =====================================================
float temp60sAgo = 0.0f;
unsigned long lastTemp60s = 0;
float tempSlopePM = 0.0f;

void updateTempSlope(float currentTemp) {
  if (millis() - lastTemp60s >= 60000UL) {
    if (lastTemp60s > 0) {
      tempSlopePM = currentTemp - temp60sAgo;
    }
    temp60sAgo = currentTemp;
    lastTemp60s = millis();
  }
}

// =====================================================
// Risk calculation 0~100
//
// 현재 실물 Belt의 센서 3종(HR / SkinTemp / GSR)을 이용.
// 이 점수 하나를 팬, OLED, LoRa, Dashboard가 모두 공유한다.
// =====================================================
uint8_t calculateRisk() {
  if (baselineSampleCnt < 10) {
    return 0;
  }

  int risk = 0;

  float bpmDev = (float)gloveData.bpm - baselineBPM;

  if (bpmDev >= 40.0f) {
    risk += 60;
  }
  else if (bpmDev >= 25.0f) {
    risk += 40;
  }

  float tempDev = gloveData.temp - baselineTemp;

  if (tempDev >= 0.9f || tempSlopePM >= 0.20f) {
    risk += 55;
  }
  else if (tempDev >= 0.5f || tempSlopePM >= 0.10f) {
    risk += 35;
  }

  int gsrThresh = max(10, baselineGSR / 20);
  int gsrAbsDev = abs(gloveData.gsr - baselineGSR);
  int gsrRelPct =
    baselineGSR > 0
      ? (gsrAbsDev * 100 / baselineGSR)
      : 0;

  if (gsrAbsDev >= gsrThresh || gsrRelPct >= 15) {
    risk += 25;
  }

  return (uint8_t)constrain(risk, 0, 100);
}

// =====================================================
// Main cause
// =====================================================
uint8_t determineCause() {
  float bpmDev = (float)gloveData.bpm - baselineBPM;
  float tempDev = gloveData.temp - baselineTemp;
  int gsrThresh = max(10, baselineGSR / 20);
  int gsrAbsDev = abs(gloveData.gsr - baselineGSR);

  if (bpmDev >= 25.0f) {
    return CAUSE_HR_HIGH;
  }

  if (tempDev >= 0.5f || tempSlopePM >= 0.10f) {
    return CAUSE_TEMP_UP;
  }

  if (gsrAbsDev >= gsrThresh) {
    return CAUSE_GSR_UP;
  }

  return CAUSE_NONE;
}

// =====================================================
// FSM threshold/hold settings
//
// CAUTION:
// enter >=60 for 10 sec
// exit  <55 for 30 sec
//
// C1:
// enter >=80 for 10 sec
// exit  <70 for 30 sec
//
// C2:
// enter >=90 for 10 sec
// exit  <80 for 30 sec
//
// C3:
// enter >=90 for 60 sec
// exit  <85 for 60 sec + commander confirmation
//
// C4:
// >=95 immediately / no automatic release
// =====================================================
#define CAUTION_ENTER_RISK     60
#define CAUTION_ENTER_HOLD_MS  10000UL
#define CAUTION_EXIT_RISK      55
#define CAUTION_EXIT_HOLD_MS   30000UL

#define C1_ENTER_RISK          80
#define C1_ENTER_HOLD_MS       10000UL
#define C1_EXIT_RISK           70
#define C1_EXIT_HOLD_MS        30000UL

#define C2_ENTER_RISK          90
#define C2_ENTER_HOLD_MS       10000UL
#define C2_EXIT_RISK           80
#define C2_EXIT_HOLD_MS        30000UL

#define C3_ENTER_RISK          90
#define C3_ENTER_HOLD_MS       60000UL
#define C3_EXIT_RISK           85
#define C3_EXIT_HOLD_MS        60000UL

#define C4_ENTER_RISK          95

struct HoldTimer {
  bool active;
  unsigned long startedAt;

  HoldTimer() : active(false), startedAt(0) {}

  unsigned long update(bool condition) {
    if (!condition) {
      active = false;
      startedAt = 0;
      return 0;
    }

    if (!active) {
      active = true;
      startedAt = millis();
      return 0;
    }

    return millis() - startedAt;
  }

  void reset() {
    active = false;
    startedAt = 0;
  }
};

HoldTimer cautionEnterTimer;
HoldTimer cautionExitTimer;
HoldTimer c1EnterTimer;
HoldTimer c1ExitTimer;
HoldTimer c2EnterTimer;
HoldTimer c2ExitTimer;
HoldTimer c3EnterTimer;
HoldTimer c3ExitTimer;

bool cautionActive = false;

// C3 -> C2 강등에 필요한 지휘관 확인.
// 현재 하드웨어에는 Gateway->Belt 명령 경로를 아직 연결하지 않았으므로
// 기본 false. 향후 관제 확인 명령을 받을 때 confirmRecovery() 호출.
bool commanderRecoveryConfirmed = false;

void confirmRecovery() {
  commanderRecoveryConfirmed = true;
}

void resetRiskFsm() {
  cautionActive = false;
  currentCoolingStage = COOLING_C0;
  currentRiskIndex = 255;
  commanderRecoveryConfirmed = false;

  cautionEnterTimer.reset();
  cautionExitTimer.reset();
  c1EnterTimer.reset();
  c1ExitTimer.reset();
  c2EnterTimer.reset();
  c2ExitTimer.reset();
  c3EnterTimer.reset();
  c3ExitTimer.reset();

  applyCoolingStage(COOLING_C0);
}

// =====================================================
// LoRa
// =====================================================
#define RF_FREQUENCY          922300000
#define TX_OUTPUT_POWER       10
#define LORA_BANDWIDTH        0
#define LORA_SPREADING_FACTOR 7
#define LORA_CODINGRATE       1
#define LORA_PREAMBLE_LENGTH  8
#define LORA_FIX_LENGTH_PAYLOAD_ON false
#define LORA_IQ_INVERSION_ON       false

static RadioEvents_t RadioEvents;
bool loraIdle = true;

// =====================================================
// ESP-NOW receive
// =====================================================
void onDataRecv(
  const esp_now_recv_info_t *recv_info,
  const uint8_t *incomingData,
  int len
) {
  if (memcmp(recv_info->src_addr, gloveMac, 6) != 0) {
    return;
  }

  if (len != sizeof(SensorPacket)) {
    Serial.printf(
      "[ESP-NOW] SIZE ERROR: %d / expected %d\n",
      len,
      (int)sizeof(SensorPacket)
    );
    return;
  }

  memcpy(&gloveData, incomingData, sizeof(gloveData));
  gloveDataReceived = true;
  lastGloveReceiveTime = millis();
}

// =====================================================
// LoRa callbacks
// =====================================================
void OnTxDone() {
  Serial.println(">>> LoRa TX DONE <<<");
  loraIdle = true;
}

void OnTxTimeout() {
  Serial.println(">>> LoRa TX TIMEOUT <<<");
  Radio.Sleep();
  loraIdle = true;
}

// =====================================================
// Emergency button
// =====================================================
void checkButton() {
  bool reading = digitalRead(BUTTON_PIN);

  if (reading != lastButtonState) {
    lastDebounceMs = millis();
  }

  lastButtonState = reading;

  if (millis() - lastDebounceMs < DEBOUNCE_MS) {
    return;
  }

  static bool prevStable = HIGH;

  if (reading == LOW && prevStable == HIGH) {
    prevStable = LOW;

    if (!emergencyActive) {
      emergencyActive = true;
      emergencyStartMs = millis();

      Serial.println();
      Serial.println("!!!!!!!!!!!!!!!!!!!!!!!!!!!!");
      Serial.println(" EMERGENCY BUTTON PRESSED");
      Serial.println("!!!!!!!!!!!!!!!!!!!!!!!!!!!!");
    }
    else {
      unsigned long elapsed =
        millis() - emergencyStartMs;

      if (elapsed <= EMERGENCY_CANCEL_MS) {
        // 물리 버튼에 의한 명시적 해제.
        // 자동 해제가 아니므로 C4 정책과 충돌하지 않는다.
        emergencyActive = false;
        currentCoolingStage = COOLING_C3;

        Serial.println(
          "[BUTTON] Emergency CANCELLED by physical confirmation"
        );
      }
      else {
        Serial.println(
          "[BUTTON] Emergency still ACTIVE (confirmation window expired)"
        );
      }
    }
  }

  if (reading == HIGH) {
    prevStable = HIGH;
  }
}

// =====================================================
// Display result helper
// =====================================================
void commitDisplayResult(
  uint8_t state,
  uint8_t cause,
  uint8_t stage
) {
  currentState = state;
  currentCause = cause;
  currentCoolingStage = stage;

  displayData.state = state;
  displayData.cause = cause;

  if (stage == COOLING_C1) {
    displayData.fanPercent = 50;
  }
  else if (
    stage == COOLING_C2 ||
    stage == COOLING_C3 ||
    stage == COOLING_C4
  ) {
    displayData.fanPercent = 100;
  }
  else {
    displayData.fanPercent = 0;
  }

  displayData.flags =
    displaySetCoolingStage(
      displayData.flags,
      stage
    );

  if (displayData.fanPercent > 0) {
    displayData.flags |= DISPLAY_FLAG_FAN_ON;
  }
}

// =====================================================
// State + cooling FSM
// =====================================================
void makeDisplayStatus() {
  memset(&displayData, 0, sizeof(displayData));

  displayData.magic = DISPLAY_PACKET_MAGIC;
  displayData.version = DISPLAY_PACKET_VERSION;
  displayData.seq = displaySequence++;

  bool gloveValid =
    gloveDataReceived &&
    (millis() - lastGloveReceiveTime < 10000UL);

  if (gloveValid) {
    displayData.flags |= DISPLAY_FLAG_GLOVE_VALID;

    displayData.bpm =
      (uint8_t)constrain(
        gloveData.bpm,
        0,
        255
      );

    displayData.skinTemp_x100 =
      (int16_t)(gloveData.temp * 100.0f);

    if (gloveData.finger) {
      displayData.flags |= DISPLAY_FLAG_FINGER;
    }

    updateTempSlope(gloveData.temp);
  }

  if (emergencyActive) {
    displayData.flags |= DISPLAY_FLAG_EMERGENCY;
  }

  // ---------------------------------------------------
  // 1) Manual/Risk Emergency latch
  // ---------------------------------------------------
  if (emergencyActive) {
    currentRiskIndex =
      baselineSampleCnt >= 10
        ? calculateRisk()
        : 255;

    applyCoolingStage(COOLING_C4);

    commitDisplayResult(
      STATE_EMERGENCY,
      CAUSE_NONE,
      COOLING_C4
    );

    return;
  }

  // ---------------------------------------------------
  // 2) BOOT
  // ---------------------------------------------------
  if (millis() < 3000UL) {
    currentRiskIndex = 255;
    applyCoolingStage(COOLING_C0);

    commitDisplayResult(
      STATE_BOOT,
      CAUSE_NONE,
      COOLING_C0
    );

    return;
  }

  // ---------------------------------------------------
  // 3) SENSOR_CHECK
  // ---------------------------------------------------
  if (
    !gloveValid ||
    !gloveData.finger ||
    gloveData.bpm <= 0
  ) {
    baselineStarted = false;
    baselineSampleCnt = 0;

    resetRiskFsm();

    commitDisplayResult(
      STATE_SENSOR_CHECK,
      CAUSE_SENSOR,
      COOLING_C0
    );

    return;
  }

  // ---------------------------------------------------
  // 4) BASELINE
  // ---------------------------------------------------
  if (!baselineStarted) {
    baselineStarted = true;
    baselineStartTime = millis();

    baselineSampleCnt = 0;
    baselineBPMSum = 0;
    baselineTempSum = 0;
    baselineGSRSum = 0;

    lastTemp60s = millis();
    temp60sAgo = gloveData.temp;
    tempSlopePM = 0.0f;

    resetRiskFsm();
  }

  unsigned long baselineElapsed =
    millis() - baselineStartTime;

  if (baselineElapsed < BASELINE_TIME) {
    if (baselineSampleCnt < 30000) {
      baselineSampleCnt++;
      baselineBPMSum += gloveData.bpm;
      baselineTempSum += gloveData.temp;
      baselineGSRSum += gloveData.gsr;
    }

    baselineBPM =
      (float)(baselineBPMSum / baselineSampleCnt);

    baselineTemp =
      (float)(baselineTempSum / baselineSampleCnt);

    baselineGSR =
      (int)(baselineGSRSum / baselineSampleCnt);

    currentRiskIndex = 255;

    applyCoolingStage(COOLING_C0);

    commitDisplayResult(
      STATE_BASELINE,
      CAUSE_NONE,
      COOLING_C0
    );

    return;
  }

  // ---------------------------------------------------
  // 5) RiskIndex - single source of truth
  // ---------------------------------------------------
  uint8_t risk = calculateRisk();
  currentRiskIndex = risk;

  // Risk >= 95 -> C4 immediate emergency latch
  if (risk >= C4_ENTER_RISK) {
    emergencyActive = true;
    emergencyStartMs = millis();
    displayData.flags |= DISPLAY_FLAG_EMERGENCY;

    applyCoolingStage(COOLING_C4);

    commitDisplayResult(
      STATE_EMERGENCY,
      determineCause(),
      COOLING_C4
    );

    Serial.println(
      "[FSM] Risk >= 95 -> EMERGENCY C4 latched"
    );

    return;
  }

  // ---------------------------------------------------
  // 6) CAUTION hysteresis
  // ---------------------------------------------------
  unsigned long cautionEnterHeld =
    cautionEnterTimer.update(
      risk >= CAUTION_ENTER_RISK
    );

  unsigned long cautionExitHeld =
    cautionExitTimer.update(
      risk < CAUTION_EXIT_RISK
    );

  if (
    !cautionActive &&
    cautionEnterHeld >= CAUTION_ENTER_HOLD_MS
  ) {
    cautionActive = true;
    Serial.println("[FSM] CAUTION ENTER");
  }

  if (
    cautionActive &&
    cautionExitHeld >= CAUTION_EXIT_HOLD_MS
  ) {
    cautionActive = false;
    Serial.println("[FSM] CAUTION EXIT");
  }

  // ---------------------------------------------------
  // 7) Cooling stage enter timers
  // ---------------------------------------------------
  unsigned long c1EnterHeld =
    c1EnterTimer.update(
      risk >= C1_ENTER_RISK
    );

  unsigned long c2EnterHeld =
    c2EnterTimer.update(
      risk >= C2_ENTER_RISK
    );

  unsigned long c3EnterHeld =
    c3EnterTimer.update(
      risk >= C3_ENTER_RISK
    );

  uint8_t candidateStage = COOLING_C0;

  if (c1EnterHeld >= C1_ENTER_HOLD_MS) {
    candidateStage = COOLING_C1;
  }

  if (c2EnterHeld >= C2_ENTER_HOLD_MS) {
    candidateStage = COOLING_C2;
  }

  if (c3EnterHeld >= C3_ENTER_HOLD_MS) {
    candidateStage = COOLING_C3;
  }

  // 승급은 즉시 가장 높은 만족 단계까지
  if (candidateStage > currentCoolingStage) {
    currentCoolingStage = candidateStage;

    Serial.printf(
      "[FSM] Cooling stage -> C%u\n",
      currentCoolingStage
    );
  }

  // ---------------------------------------------------
  // 8) Cooling stage exit hysteresis
  // ---------------------------------------------------
  unsigned long c1ExitHeld =
    c1ExitTimer.update(
      risk < C1_EXIT_RISK
    );

  unsigned long c2ExitHeld =
    c2ExitTimer.update(
      risk < C2_EXIT_RISK
    );

  unsigned long c3ExitHeld =
    c3ExitTimer.update(
      risk < C3_EXIT_RISK
    );

  if (
    currentCoolingStage == COOLING_C3 &&
    c3ExitHeld >= C3_EXIT_HOLD_MS &&
    commanderRecoveryConfirmed
  ) {
    currentCoolingStage = COOLING_C2;
    commanderRecoveryConfirmed = false;
    Serial.println("[FSM] C3 -> C2");
  }
  else if (
    currentCoolingStage == COOLING_C2 &&
    c2ExitHeld >= C2_EXIT_HOLD_MS
  ) {
    currentCoolingStage = COOLING_C1;
    Serial.println("[FSM] C2 -> C1");
  }
  else if (
    currentCoolingStage == COOLING_C1 &&
    c1ExitHeld >= C1_EXIT_HOLD_MS
  ) {
    currentCoolingStage = COOLING_C0;
    Serial.println("[FSM] C1 -> C0");
  }

  // ---------------------------------------------------
  // 9) Final DeviceState
  // ---------------------------------------------------
  uint8_t state;
  uint8_t cause;

  if (currentCoolingStage != COOLING_C0) {
    state = STATE_COOLING;
    cause = determineCause();
  }
  else if (cautionActive) {
    state = STATE_CAUTION;
    cause = determineCause();
  }
  else {
    state = STATE_NORMAL;
    cause = CAUSE_NONE;
  }

  applyCoolingStage(currentCoolingStage);

  commitDisplayResult(
    state,
    cause,
    currentCoolingStage
  );
}

void sendDisplayStatus() {
  makeDisplayStatus();

  esp_err_t result =
    esp_now_send(
      gloveMac,
      (uint8_t *)&displayData,
      sizeof(displayData)
    );

  if (result != ESP_OK) {
    Serial.println(
      "[DISPLAY] ESP-NOW SEND ERROR"
    );
  }
}

// =====================================================
// LoRa telemetry
// =====================================================
void makeTelemetryPacket() {
  memset(&txData, 0, sizeof(txData));

  txData.magic = 0xA55A;

  // version 2:
  // unified DeviceState + CoolingStage/Risk packed field
  txData.version = 2;

  txData.nodeId = 1;
  txData.seq = loraSequence++;

  uint8_t flags = 0;

  bool gloveValid =
    gloveDataReceived &&
    (millis() - lastGloveReceiveTime < 10000UL);

  if (gloveValid) {
    flags |= (1 << 0);

    txData.bpm =
      (uint8_t)constrain(
        gloveData.bpm,
        0,
        255
      );

    txData.skinTemp_x100 =
      (int16_t)(gloveData.temp * 100.0f);

    txData.gsr =
      (uint16_t)constrain(
        gloveData.gsr,
        0,
        65535
      );

    txData.gsrDiff =
      (int16_t)constrain(
        gloveData.gsrDiff,
        -32768,
        32767
      );

    txData.ir =
      (uint32_t)gloveData.ir;

    if (gloveData.finger) {
      flags |= (1 << 3);
    }
  }

  // state/cause
  txData.airTemp_x10 =
    (int16_t)(
      ((uint16_t)currentState << 8) |
      (uint16_t)currentCause
    );

  // stage/risk
  txData.humidity_x10 =
    (uint16_t)(
      ((uint16_t)currentCoolingStage << 8) |
      (uint16_t)currentRiskIndex
    );

  // GPS
  bool gpsFresh =
    gps.location.isValid() &&
    gps.location.age() < GPS_MAX_AGE_MS;

  if (gpsFresh) {
    flags |= (1 << 2);

    txData.latitude_e7 =
      (int32_t)(
        gps.location.lat() *
        10000000.0
      );

    txData.longitude_e7 =
      (int32_t)(
        gps.location.lng() *
        10000000.0
      );
  }

  if (gps.satellites.isValid()) {
    txData.satellites =
      gps.satellites.value();
  }

  if (gps.altitude.isValid()) {
    txData.altitude_dm =
      (int16_t)(
        gps.altitude.meters() *
        10.0
      );
  }

  if (gps.speed.isValid()) {
    float speed =
      max(0.0f, (float)gps.speed.kmph());

    txData.speed_x10 =
      (uint16_t)(speed * 10.0f);
  }

  if (emergencyActive) {
    flags |= (1 << 4);
  }

  if (fansOn) {
    flags |= (1 << 5);
  }

  txData.flags = flags;
}

// =====================================================
// Serial debug
// =====================================================
const char* stateName(uint8_t state) {
  switch (state) {
    case STATE_BOOT:         return "BOOT";
    case STATE_BASELINE:     return "BASELINE";
    case STATE_NORMAL:       return "NORMAL";
    case STATE_CAUTION:      return "CAUTION";
    case STATE_COOLING:      return "COOLING";
    case STATE_EMERGENCY:    return "EMERGENCY";
    case STATE_SENSOR_CHECK: return "SENSOR CHECK";
    default:                 return "UNKNOWN";
  }
}

const char* causeName(uint8_t cause) {
  switch (cause) {
    case CAUSE_NONE:      return "NONE";
    case CAUSE_HR_HIGH:   return "HR HIGH";
    case CAUSE_HR_CHANGE: return "HR CHANGE";
    case CAUSE_TEMP_UP:   return "TEMP UP";
    case CAUSE_GSR_UP:    return "GSR UP";
    case CAUSE_HOT_ENV:   return "HOT ENV";
    case CAUSE_ACTIVE:    return "ACTIVE";
    case CAUSE_SENSOR:    return "SENSOR";
    default:              return "UNKNOWN";
  }
}

void printTelemetry() {
  Serial.println();
  Serial.println("================================");
  Serial.println(" BELT STATUS");
  Serial.println("================================");

  Serial.println();
  Serial.println("[ FSM ]");
  Serial.printf(
    "State        : %s\n",
    stateName(currentState)
  );
  Serial.printf(
    "CoolingStage : C%u\n",
    currentCoolingStage
  );
  Serial.printf(
    "Cause        : %s\n",
    causeName(currentCause)
  );

  if (currentRiskIndex <= 100) {
    Serial.printf(
      "RiskIndex    : %u\n",
      currentRiskIndex
    );
  }
  else {
    Serial.println(
      "RiskIndex    : INVALID"
    );
  }

  Serial.printf(
    "Fan1/Fan2    : %u%% / %u%%\n",
    currentFan1Pct,
    currentFan2Pct
  );

  Serial.printf(
    "Cooling      : %u%%\n",
    currentCoolingPct
  );

  if (baselineSampleCnt > 0) {
    Serial.printf(
      "Baseline     : BPM %.1f | Temp %.2fC | GSR %d\n",
      baselineBPM,
      baselineTemp,
      baselineGSR
    );

    Serial.printf(
      "Temp slope   : %.2f C/min\n",
      tempSlopePM
    );
  }

  Serial.println();
  Serial.println("[ GLOVE / ESP32U ]");

  if (txData.flags & (1 << 0)) {
    Serial.printf(
      "BPM          : %d\n",
      txData.bpm
    );

    Serial.printf(
      "Skin Temp    : %.2f C\n",
      txData.skinTemp_x100 / 100.0f
    );

    Serial.printf(
      "GSR          : %d\n",
      txData.gsr
    );

    Serial.printf(
      "GSR Diff     : %d\n",
      txData.gsrDiff
    );

    Serial.printf(
      "IR           : %lu\n",
      txData.ir
    );

    Serial.printf(
      "Finger       : %s\n",
      (txData.flags & (1 << 3))
        ? "YES"
        : "NO"
    );

    Serial.printf(
      "ESP-NOW age  : %lu ms\n",
      millis() - lastGloveReceiveTime
    );
  }
  else {
    Serial.println("NO DATA");
  }

  Serial.println();
  Serial.println("[ GPS ]");

  Serial.printf(
    "GPS chars    : %lu\n",
    gps.charsProcessed()
  );

  Serial.printf(
    "Checksum OK  : %lu\n",
    gps.passedChecksum()
  );

  Serial.printf(
    "Checksum ERR : %lu\n",
    gps.failedChecksum()
  );

  if (gps.charsProcessed() == 0) {
    Serial.println(
      "*** UART NO DATA - GPS TX -> GPIO45 확인 ***"
    );
  }
  else {
    uint8_t satellites =
      gps.satellites.isValid()
        ? gps.satellites.value()
        : 0;

    Serial.printf(
      "Satellites   : %u\n",
      satellites
    );

    if (txData.flags & (1 << 2)) {
      Serial.printf(
        "Latitude     : %.6f\n",
        txData.latitude_e7 / 10000000.0
      );

      Serial.printf(
        "Longitude    : %.6f\n",
        txData.longitude_e7 / 10000000.0
      );

      Serial.printf(
        "Altitude     : %.1f m\n",
        txData.altitude_dm / 10.0f
      );

      Serial.printf(
        "Speed        : %.1f km/h\n",
        txData.speed_x10 / 10.0f
      );
    }
    else {
      Serial.printf(
        "Fix          : NO (sats: %u)\n",
        satellites
      );
    }
  }

  Serial.println();
  Serial.printf(
    "Emergency    : %s\n",
    emergencyActive
      ? "ACTIVE"
      : "NORMAL"
  );

  Serial.printf(
    "Flags        : 0x%02X\n",
    txData.flags
  );

  Serial.printf(
    "LoRa SEQ     : %u\n",
    txData.seq
  );

  Serial.printf(
    "LoRa bytes   : %u\n",
    (unsigned)sizeof(txData)
  );

  Serial.println("================================");
}

// =====================================================
// SETUP
// =====================================================
void setup() {
  Serial.begin(115200);
  delay(2000);

  Serial.println();
  Serial.println("================================");
  Serial.println(" BELT HELTEC V4");
  Serial.println(" Unified 7-State + C0~C4");
  Serial.println("================================");

  Mcu.begin(
    HELTEC_BOARD,
    SLOW_CLK_TPYE
  );

  Serial.println("[OK] MCU");

  pinMode(
    BUTTON_PIN,
    INPUT_PULLUP
  );

  Serial.println(
    "[OK] BUTTON GPIO7"
  );

  ledcAttach(
    FAN1_PIN,
    FAN_FREQ,
    FAN_BITS
  );

  ledcAttach(
    FAN2_PIN,
    FAN_FREQ,
    FAN_BITS
  );

  applyCoolingStage(COOLING_C0);

  Serial.println(
    "[OK] FAN PWM GPIO6 / GPIO47"
  );

  GPSSerial.begin(
    9600,
    SERIAL_8N1,
    GPS_RX,
    GPS_TX
  );

  Serial.println(
    "[OK] GPS UART RX=GPIO45 / TX=GPIO2"
  );

  WiFi.mode(WIFI_STA);
  esp_wifi_set_ps(WIFI_PS_NONE);
  delay(300);

  if (esp_now_init() != ESP_OK) {
    Serial.println(
      "[ERROR] ESP-NOW INIT"
    );

    while (true) {
      delay(1000);
    }
  }

  esp_now_register_recv_cb(
    onDataRecv
  );

  esp_now_peer_info_t peerInfo = {};

  memcpy(
    peerInfo.peer_addr,
    gloveMac,
    6
  );

  peerInfo.channel = 0;
  peerInfo.encrypt = false;

  if (!esp_now_is_peer_exist(gloveMac)) {
    if (esp_now_add_peer(&peerInfo) != ESP_OK) {
      Serial.println(
        "[ERROR] GLOVE PEER"
      );
    }
    else {
      Serial.println(
        "[OK] GLOVE PEER"
      );
    }
  }

  Serial.println("[OK] ESP-NOW");

  RadioEvents.TxDone = OnTxDone;
  RadioEvents.TxTimeout = OnTxTimeout;

  Radio.Init(&RadioEvents);

  Radio.SetChannel(
    RF_FREQUENCY
  );

  Radio.SetTxConfig(
    MODEM_LORA,
    TX_OUTPUT_POWER,
    0,
    LORA_BANDWIDTH,
    LORA_SPREADING_FACTOR,
    LORA_CODINGRATE,
    LORA_PREAMBLE_LENGTH,
    LORA_FIX_LENGTH_PAYLOAD_ON,
    true,
    0,
    0,
    LORA_IQ_INVERSION_ON,
    3000
  );

  Serial.println("[OK] LoRa TX");

  Serial.printf(
    "Telemetry: %u bytes | Display: %u bytes\n",
    (unsigned)sizeof(TelemetryPacket),
    (unsigned)sizeof(DisplayPacket)
  );

  Serial.println(
    "READY - baseline 3 min"
  );
}

// =====================================================
// LOOP
// =====================================================
void loop() {
  Radio.IrqProcess();

  checkButton();

  while (GPSSerial.available() > 0) {
    gps.encode(
      GPSSerial.read()
    );
  }

  static unsigned long lastDisplaySend = 0;

  if (
    millis() - lastDisplaySend >= 500UL
  ) {
    lastDisplaySend = millis();
    sendDisplayStatus();
  }

  unsigned long loraInterval =
    gps.location.isValid()
      ? LORA_INTERVAL_FIXED
      : LORA_INTERVAL_NO_FIX;

  static unsigned long lastLoRaSend = 0;

  if (
    loraIdle &&
    millis() - lastLoRaSend >= loraInterval
  ) {
    lastLoRaSend = millis();

    makeTelemetryPacket();
    printTelemetry();

    loraIdle = false;

    Radio.Send(
      (uint8_t *)&txData,
      sizeof(txData)
    );
  }
}
