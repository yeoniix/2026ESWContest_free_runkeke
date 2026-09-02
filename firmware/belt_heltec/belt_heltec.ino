#include "display_protocol.h"
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "HT_TinyGPS++.h"
#include "LoRaWan_APP.h"
#include "Arduino.h"

// =====================================================
// GPS ATGM336H  RX=GPIO45  TX=GPIO2
// ★ GPS 안테나를 Heltec 보드에서 10cm 이상 이격 권장
// =====================================================
#define GPS_RX        45
#define GPS_TX         2
#define GPS_MAX_AGE_MS 15000

HardwareSerial GPSSerial(1);
TinyGPSPlus    gps;

// =====================================================
// 비상 버튼  GPIO7 — INPUT_PULLUP — GND
// =====================================================
#define BUTTON_PIN           7
#define EMERGENCY_CANCEL_MS  10000  // Emergency 중 10초 이내 재입력 시 해제

bool          emergencyActive     = false;
unsigned long emergencyStartMs    = 0;   // Emergency 진입 시각
bool          lastButtonState     = HIGH;
unsigned long lastDebounceMs      = 0;
#define DEBOUNCE_MS 50

// =====================================================
// FAN / MOTOR DRIVER — LEDC PWM
// A-1A = GPIO6   A-1B = GND
// B-1A = GPIO47  B-1B = GND
// VCC = 5V | GND = 공통 GND
// =====================================================
#define FAN1_PIN  6
#define FAN2_PIN 47
#define FAN_FREQ  5000   // Hz
#define FAN_BITS  8      // 0~255 duty

bool    fansOn        = false;
uint8_t currentFanPct = 0;

// pct1 = FAN1, pct2 = FAN2 (0~100 각각)
void setFanPins(uint8_t pct1, uint8_t pct2) {
  ledcWrite(FAN1_PIN, (uint32_t)pct1 * 255 / 100);
  ledcWrite(FAN2_PIN, (uint32_t)pct2 * 255 / 100);
  uint8_t newPct = max(pct1, pct2);
  bool wasOn = (currentFanPct > 0);
  bool nowOn = (newPct > 0);
  if (nowOn != wasOn) {
    Serial.println(nowOn ? "=== FAN ON ===" : "=== FAN OFF ===");
  } else if (nowOn && newPct != currentFanPct) {
    Serial.printf("=== FAN1=%d%% FAN2=%d%% ===\n", pct1, pct2);
  }
  currentFanPct = newPct;
  fansOn        = nowOn;
}

// =====================================================
// LoRa TX 간격
// =====================================================
#define LORA_INTERVAL_NO_FIX  10000UL
#define LORA_INTERVAL_FIXED    2000UL

// =====================================================
// 장갑 ESP32U MAC
// =====================================================
uint8_t gloveMac[] = {0x34, 0x98, 0x7A, 0xBD, 0x7A, 0x2C};

// =====================================================
// Glove → Belt : Sensor Packet
// ★ 장갑 코드와 반드시 동일
// =====================================================
typedef struct SensorPacket {
  int           bpm;
  float         temp;
  int           gsr;
  int           gsrDiff;
  long          ir;
  bool          finger;
  unsigned long seq;
} SensorPacket;

SensorPacket  gloveData;
bool          gloveDataReceived    = false;
unsigned long lastGloveReceiveTime = 0;

// =====================================================
// Belt → Glove : Display Packet  (display_protocol.h)
// =====================================================
DisplayPacket displayData;
uint16_t      displaySequence = 0;

// =====================================================
// Belt → Base : LoRa Telemetry Packet (35 bytes)
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
  int16_t  airTemp_x10;    // ★ 재활용: high byte=state, low byte=cause
  uint16_t humidity_x10;   // ★ 재활용: Belt RiskIndex (0~100, 255=INVALID)
  int32_t  latitude_e7;
  int32_t  longitude_e7;
  uint8_t  satellites;
  int16_t  altitude_dm;
  uint16_t speed_x10;
  uint8_t  flags;
};
static_assert(sizeof(TelemetryPacket) == 35, "TelemetryPacket must be 35 bytes");

TelemetryPacket txData;
uint16_t        loraSequence = 0;

// ★ Belt가 실제 FSM에 사용한 RiskIndex를 관제까지 그대로 전달
// 0~100 = 유효, 255 = BOOT / BASELINE / SENSOR_CHECK 등 아직 계산 불가
uint8_t         currentRiskIndex = 255;

// =====================================================
// BASELINE 수집 (3분)
// =====================================================
#define BASELINE_TIME 180000UL  // 3분

bool          baselineStarted   = false;
unsigned long baselineStartTime = 0;
int           baselineSampleCnt = 0;
double        baselineBPMSum    = 0;
double        baselineTempSum   = 0;
long          baselineGSRSum    = 0;
float         baselineBPM       = 0.0f;
float         baselineTemp      = 0.0f;
int           baselineGSR       = 0;

// =====================================================
// 온도 기울기 (°C/min)
// 60초마다 현재 온도를 기록해 1분 변화량으로 계산
// =====================================================
float         temp60sAgo   = 0.0f;
unsigned long lastTemp60s  = 0;
float         tempSlopePM  = 0.0f;   // °C per minute

void updateTempSlope(float currentTemp) {
  if (millis() - lastTemp60s >= 60000UL) {
    if (lastTemp60s > 0) {
      tempSlopePM = currentTemp - temp60sAgo;
    }
    temp60sAgo  = currentTemp;
    lastTemp60s = millis();
  }
}

// =====================================================
// 위험 지수 타이머 (10초 이상 유지 조건)
// =====================================================
#define RISK_HOLD_TIME 10000UL

bool          riskTimerActive = false;
unsigned long riskTimerStart  = 0;

// =====================================================
// 위험 지수 계산 (0~100)
// =====================================================
uint8_t calculateRisk() {
  if (baselineSampleCnt < 10) return 0;

  int risk = 0;

  // BPM 편차
  float bpmDev = (float)gloveData.bpm - baselineBPM;
  if      (bpmDev >= 40.0f) risk += 60;
  else if (bpmDev >= 25.0f) risk += 40;

  // 피부온도 편차 / 기울기
  float tempDev = gloveData.temp - baselineTemp;
  if      (tempDev >= 0.9f || tempSlopePM >= 0.20f) risk += 55;
  else if (tempDev >= 0.5f || tempSlopePM >= 0.10f) risk += 35;

  // GSR 변화
  int gsrThresh = max(10, baselineGSR / 20);           // baseline 의 5%
  int gsrAbsDev = abs(gloveData.gsr - baselineGSR);
  int gsrRelPct = (baselineGSR > 0)
                  ? (gsrAbsDev * 100 / baselineGSR) : 0;
  if (gsrAbsDev >= gsrThresh || gsrRelPct >= 15) risk += 25;

  return (uint8_t)constrain(risk, 0, 100);
}

// =====================================================
// 원인 판단
// =====================================================
uint8_t determineCause() {
  float bpmDev   = (float)gloveData.bpm - baselineBPM;
  float tempDev  = gloveData.temp - baselineTemp;
  int   gsrThresh = max(10, baselineGSR / 20);
  int   gsrAbsDev = abs(gloveData.gsr - baselineGSR);

  if      (bpmDev   >= 25.0f)   return CAUSE_HR_HIGH;
  if      (tempDev  >= 0.5f)    return CAUSE_TEMP_UP;
  if      (gsrAbsDev >= gsrThresh) return CAUSE_GSR_UP;
  return CAUSE_NONE;
}

// =====================================================
// LoRa 설정
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
// ESP-NOW 수신 (Glove → Belt)
// =====================================================
void onDataRecv(
  const esp_now_recv_info_t *recv_info,
  const uint8_t             *incomingData,
  int                        len
) {
  if (memcmp(recv_info->src_addr, gloveMac, 6) != 0) return;

  if (len != sizeof(SensorPacket)) {
    Serial.printf("[ESP-NOW] SIZE ERROR : %d / Expected : %d\n",
                  len, (int)sizeof(SensorPacket));
    return;
  }

  memcpy(&gloveData, incomingData, sizeof(gloveData));
  gloveDataReceived    = true;
  lastGloveReceiveTime = millis();
}

// =====================================================
// LoRa 콜백
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
// 비상 버튼
// =====================================================
void checkButton() {
  bool reading = digitalRead(BUTTON_PIN);

  // 디바운스
  if (reading != lastButtonState) {
    lastDebounceMs = millis();
  }
  lastButtonState = reading;

  if (millis() - lastDebounceMs < DEBOUNCE_MS) return;

  // 버튼 눌림 (LOW = 눌림, INPUT_PULLUP)
  static bool prevStable = HIGH;
  if (reading == LOW && prevStable == HIGH) {
    prevStable = LOW;

    if (!emergencyActive) {
      // Emergency 진입
      emergencyActive  = true;
      emergencyStartMs = millis();
      Serial.println();
      Serial.println("!!!!!!!!!!!!!!!!!!!!!!!!!!!!");
      Serial.println(" EMERGENCY BUTTON PRESSED");
      Serial.println("!!!!!!!!!!!!!!!!!!!!!!!!!!!!");
    } else {
      // Emergency 중 재입력
      unsigned long held = millis() - emergencyStartMs;
      if (held <= EMERGENCY_CANCEL_MS) {
        emergencyActive = false;
        Serial.println("[BUTTON] Emergency CANCELLED (double press)");
      } else {
        // 10초 초과 재입력 → 무시 (Emergency 유지)
        Serial.println("[BUTTON] Emergency still ACTIVE (too late)");
      }
    }
  }
  if (reading == HIGH) prevStable = HIGH;
}

// =====================================================
// 상태 생성 + 팬 제어 (0.5초마다 호출)
// =====================================================
void makeDisplayStatus() {
  memset(&displayData, 0, sizeof(displayData));
  displayData.magic   = DISPLAY_PACKET_MAGIC;
  displayData.version = DISPLAY_PACKET_VERSION;
  displayData.seq     = displaySequence++;

  // 매 상태 계산 주기마다 우선 INVALID로 초기화.
  // 실제 Risk 계산 단계까지 도달하면 아래에서 0~100으로 갱신한다.
  currentRiskIndex = 255;

  bool gloveValid = gloveDataReceived &&
                    (millis() - lastGloveReceiveTime < 10000);

  // 글로브 정보 기입
  if (gloveValid) {
    displayData.flags        |= (1 << 3);
    displayData.bpm           = (uint8_t)constrain(gloveData.bpm, 0, 255);
    displayData.skinTemp_x100 = (int16_t)(gloveData.temp * 100.0f);
    if (gloveData.finger) displayData.flags |= (1 << 0);

    // 온도 기울기 갱신
    updateTempSlope(gloveData.temp);
  }

  if (emergencyActive) displayData.flags |= (1 << 1);

  // ── 1. 수동 SOS ──────────────────────────────────
  if (emergencyActive) {
    setFanPins(100, 100);
    displayData.state      = STATE_EMERGENCY;
    displayData.cause      = CAUSE_NONE;
    displayData.fanPercent = 100;
    displayData.flags     |= (1 << 2);
    return;
  }

  // ── 2. 센서 없음 ─────────────────────────────────
  if (!gloveValid || !gloveData.finger || gloveData.bpm <= 0) {
    setFanPins(0, 0);
    displayData.state = STATE_SENSOR_CHECK;
    displayData.cause = CAUSE_SENSOR;
    // 장갑 떼면 베이스라인 초기화
    baselineStarted   = false;
    baselineSampleCnt = 0;
    riskTimerActive   = false;
    return;
  }

  // ── 3. 베이스라인 수집 (3분) ─────────────────────
  if (!baselineStarted) {
    baselineStarted   = true;
    baselineStartTime = millis();
    baselineSampleCnt = 0;
    baselineBPMSum    = 0;
    baselineTempSum   = 0;
    baselineGSRSum    = 0;
    lastTemp60s       = millis();
    temp60sAgo        = gloveData.temp;
    tempSlopePM       = 0.0f;
  }

  unsigned long elapsed = millis() - baselineStartTime;

  if (elapsed < BASELINE_TIME) {
    // 베이스라인 샘플 적산 (최대 30000개)
    if (baselineSampleCnt < 30000) {
      baselineSampleCnt++;
      baselineBPMSum  += gloveData.bpm;
      baselineTempSum += gloveData.temp;
      baselineGSRSum  += gloveData.gsr;
    }
    baselineBPM  = (float)(baselineBPMSum  / baselineSampleCnt);
    baselineTemp = (float)(baselineTempSum / baselineSampleCnt);
    baselineGSR  = (int)  (baselineGSRSum  / baselineSampleCnt);

    setFanPins(0, 0);
    displayData.state = STATE_BASELINE;
    displayData.cause = CAUSE_NONE;
    return;
  }

  // ── 4. Risk 계산 ──────────────────────────────────
  uint8_t risk = calculateRisk();

  // ★ 이 값이 팬/OLED/LoRa/대시보드가 공유하는 단일 RiskIndex
  currentRiskIndex = risk;

  // ── 5. 10초 타이머 (risk ≥ 60 구간) ──────────────
  if (risk >= 60) {
    if (!riskTimerActive) {
      riskTimerActive = true;
      riskTimerStart  = millis();
    }
  } else {
    riskTimerActive = false;
  }

  bool held10s = riskTimerActive &&
                 (millis() - riskTimerStart >= RISK_HOLD_TIME);

  // ── 6. FSM ────────────────────────────────────────
  uint8_t newState;
  uint8_t fan1Pct, fan2Pct;

  if (risk < 40) {
    newState = STATE_NORMAL;
    fan1Pct = 0;   fan2Pct = 0;
  } else if (risk < 60) {
    newState = STATE_CAUTION;
    fan1Pct = 0;   fan2Pct = 0;
  } else if (risk < 85) {
    // COOLING_50 : FAN1 100% 1개만, FAN2 OFF
    newState = held10s ? STATE_COOLING_50 : STATE_CAUTION;
    fan1Pct  = held10s ? 100 : 0;
    fan2Pct  = 0;
  } else {
    // DANGER : 두 팬 100%
    newState = held10s ? STATE_DANGER : STATE_CAUTION;
    fan1Pct  = held10s ? 100 : 0;
    fan2Pct  = held10s ? 100 : 0;
  }

  uint8_t fanPct = max(fan1Pct, fan2Pct);
  setFanPins(fan1Pct, fan2Pct);
  displayData.state      = newState;
  displayData.cause      = (newState >= STATE_CAUTION)
                           ? determineCause() : CAUSE_NONE;
  displayData.fanPercent = fanPct;
  if (fanPct > 0) displayData.flags |= (1 << 2);
}

void sendDisplayStatus() {
  makeDisplayStatus();
  esp_err_t result = esp_now_send(
    gloveMac, (uint8_t *)&displayData, sizeof(displayData)
  );
  if (result != ESP_OK)
    Serial.println("[DISPLAY] ESP-NOW SEND ERROR");
}

// =====================================================
// LoRa Telemetry 생성
// =====================================================
void makeTelemetryPacket() {
  memset(&txData, 0, sizeof(txData));

  txData.magic   = 0xA55A;
  txData.version = 1;
  txData.nodeId  = 1;
  txData.seq     = loraSequence++;

  uint8_t flags = 0;

  bool gloveValid = gloveDataReceived &&
                    (millis() - lastGloveReceiveTime < 10000);

  if (gloveValid) {
    flags               |= (1 << 0);
    txData.bpm           = (uint8_t)constrain(gloveData.bpm, 0, 255);
    txData.skinTemp_x100 = (int16_t)(gloveData.temp * 100.0f);
    txData.gsr           = (uint16_t)constrain(gloveData.gsr, 0, 65535);
    txData.gsrDiff       = (int16_t)constrain(gloveData.gsrDiff, -32768, 32767);
    txData.ir            = (uint32_t)gloveData.ir;
    if (gloveData.finger) flags |= (1 << 3);
  }

  // ★ airTemp_x10 재활용: high byte = state, low byte = cause
  txData.airTemp_x10 = (int16_t)(
    ((uint16_t)displayData.state << 8) | (uint16_t)displayData.cause
  );

  // ★ humidity_x10 재활용: Belt가 실제 FSM에 사용한 RiskIndex
  // 패킷 크기는 기존과 동일한 35 bytes 유지
  txData.humidity_x10 = (uint16_t)currentRiskIndex;

  // GPS
  bool gpsFresh = gps.location.isValid() &&
                  gps.location.age() < GPS_MAX_AGE_MS;

  if (gpsFresh) {
    flags              |= (1 << 2);
    txData.latitude_e7  = (int32_t)(gps.location.lat() * 10000000.0);
    txData.longitude_e7 = (int32_t)(gps.location.lng() * 10000000.0);
  }

  if (gps.satellites.isValid())
    txData.satellites = gps.satellites.value();
  if (gps.altitude.isValid())
    txData.altitude_dm = (int16_t)(gps.altitude.meters() * 10.0);
  if (gps.speed.isValid()) {
    float spd = max(0.0f, (float)gps.speed.kmph());
    txData.speed_x10 = (uint16_t)(spd * 10.0f);
  }

  if (emergencyActive) flags |= (1 << 4);
  if (fansOn)          flags |= (1 << 5);

  txData.flags = flags;
}

// =====================================================
// Serial 로그
// =====================================================
void printTelemetry() {
  const char* stateNames[] = {
    "BOOT","BASELINE","NORMAL","CAUTION",
    "COOLING 50%","DANGER","EMERGENCY","SENSOR CHECK"
  };
  const char* causeNames[] = {
    "NONE","HR HIGH","HR CHANGE","TEMP UP",
    "GSR UP","HOT ENV","ACTIVE","SENSOR"
  };

  Serial.println();
  Serial.println("================================");
  Serial.println(" BELT STATUS");
  Serial.println("================================");

  // RISK
  Serial.println();
  Serial.println("[ RISK ]");
  uint8_t s = displayData.state;
  uint8_t c = displayData.cause;
  Serial.printf("State        : %s\n", s < 8 ? stateNames[s] : "?");
  Serial.printf("Cause        : %s\n", c < 8 ? causeNames[c] : "?");
  Serial.printf("Fan          : %d%%\n", currentFanPct);
  if (baselineSampleCnt > 0) {
    Serial.printf("Baseline     : BPM %.1f | Temp %.2fC | GSR %d\n",
                  baselineBPM, baselineTemp, baselineGSR);
    Serial.printf("Temp slope   : %.2f C/min\n", tempSlopePM);
  }

  if (currentRiskIndex <= 100)
    Serial.printf("Risk Score   : %d\n", currentRiskIndex);
  else
    Serial.println("Risk Score   : INVALID");

  // GLOVE
  Serial.println();
  Serial.println("[ GLOVE / ESP32U ]");
  if (txData.flags & (1 << 0)) {
    Serial.printf("BPM          : %d\n",     txData.bpm);
    Serial.printf("Skin Temp    : %.2f C\n", txData.skinTemp_x100 / 100.0f);
    Serial.printf("GSR          : %d\n",     txData.gsr);
    Serial.printf("GSR Diff     : %d\n",     txData.gsrDiff);
    Serial.printf("IR           : %lu\n",    txData.ir);
    Serial.printf("Finger       : %s\n",
                  (txData.flags & (1 << 3)) ? "YES" : "NO");
    Serial.printf("ESP-NOW age  : %lu ms\n",
                  millis() - lastGloveReceiveTime);
  } else {
    Serial.println("NO DATA");
  }

  // GPS
  Serial.println();
  Serial.println("[ GPS ]");
  Serial.printf("GPS chars    : %lu\n", gps.charsProcessed());

  if (gps.charsProcessed() == 0) {
    Serial.println("*** UART NO DATA — GPIO45 배선 확인 ***");
  } else {
    uint8_t sats = gps.satellites.isValid() ? gps.satellites.value() : 0;
    Serial.printf("Satellites   : %d\n", sats);
    if (txData.flags & (1 << 2)) {
      Serial.printf("Latitude     : %.6f\n",   txData.latitude_e7  / 10000000.0);
      Serial.printf("Longitude    : %.6f\n",   txData.longitude_e7 / 10000000.0);
      Serial.printf("Altitude     : %.1f m\n", txData.altitude_dm  / 10.0f);
      Serial.printf("Speed        : %.1f km/h\n", txData.speed_x10 / 10.0f);
    } else {
      Serial.printf("Fix : NO  (sats: %d)\n", sats);
    }
  }

  // EMERGENCY
  Serial.println();
  Serial.printf("Emergency    : %s\n",    emergencyActive ? "ACTIVE" : "NORMAL");
  Serial.printf("LoRa TX      : %s\n",
                gps.location.isValid() ? "2초 (GPS 고정)" : "10초 (GPS 대기)");
  Serial.printf("Flags        : 0x%02X\n", txData.flags);
  Serial.printf("LoRa SEQ     : %d\n",     txData.seq);
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
  Serial.println(" Risk FSM + Fan PWM");
  Serial.println("================================");

  Mcu.begin(HELTEC_BOARD, SLOW_CLK_TPYE);
  Serial.println("[OK] MCU");

  // 비상 버튼
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  Serial.println("[OK] BUTTON GPIO7");

  // FAN LEDC PWM (Core 3.x)
  ledcAttach(FAN1_PIN, FAN_FREQ, FAN_BITS);
  ledcAttach(FAN2_PIN, FAN_FREQ, FAN_BITS);
  setFanPins(0, 0);
  Serial.println("[OK] FAN PWM  GPIO6(CH0) / GPIO47(CH1)");

  // GPS
  GPSSerial.begin(9600, SERIAL_8N1, GPS_RX, GPS_TX);
  Serial.println("[OK] GPS UART  RX=GPIO45 / TX=GPIO2");

  // ESP-NOW
  WiFi.mode(WIFI_STA);
  esp_wifi_set_ps(WIFI_PS_NONE);
  delay(300);

  if (esp_now_init() != ESP_OK) {
    Serial.println("[ERROR] ESP-NOW INIT");
    while (true) delay(1000);
  }

  esp_now_register_recv_cb(onDataRecv);

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, gloveMac, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;

  if (!esp_now_is_peer_exist(gloveMac)) {
    if (esp_now_add_peer(&peerInfo) != ESP_OK)
      Serial.println("[ERROR] GLOVE PEER");
    else
      Serial.println("[OK] GLOVE PEER");
  }
  Serial.println("[OK] ESP-NOW");

  // LoRa
  RadioEvents.TxDone    = OnTxDone;
  RadioEvents.TxTimeout = OnTxTimeout;

  Radio.Init(&RadioEvents);
  Radio.SetChannel(RF_FREQUENCY);
  Radio.SetTxConfig(
    MODEM_LORA, TX_OUTPUT_POWER, 0,
    LORA_BANDWIDTH, LORA_SPREADING_FACTOR, LORA_CODINGRATE,
    LORA_PREAMBLE_LENGTH, LORA_FIX_LENGTH_PAYLOAD_ON,
    true, 0, 0, LORA_IQ_INVERSION_ON, 3000
  );

  Serial.println("[OK] LoRa TX");
  Serial.printf("Telemetry : %d bytes | Display : %d bytes\n",
                (int)sizeof(TelemetryPacket), (int)sizeof(DisplayPacket));
  Serial.println();
  Serial.println("READY — 베이스라인 3분 수집 대기 중");
}

// =====================================================
// LOOP
// =====================================================
void loop() {
  Radio.IrqProcess();
  checkButton();

  // GPS NMEA 수신
  while (GPSSerial.available() > 0) {
    gps.encode(GPSSerial.read());
  }

  // 0.5초: 상태 계산 + 팬 제어 + Glove로 전송
  static unsigned long lastDisplaySend = 0;
  if (millis() - lastDisplaySend >= 500) {
    lastDisplaySend = millis();
    sendDisplayStatus();
  }

  // LoRa TX (GPS 미고정=10초, 고정=2초)
  unsigned long loraInterval = gps.location.isValid()
                               ? LORA_INTERVAL_FIXED
                               : LORA_INTERVAL_NO_FIX;

  static unsigned long lastLoRaSend = 0;
  if (loraIdle && millis() - lastLoRaSend >= loraInterval) {
    lastLoRaSend = millis();
    makeTelemetryPacket();
    printTelemetry();
    loraIdle = false;
    Radio.Send((uint8_t *)&txData, sizeof(txData));
  }
}
