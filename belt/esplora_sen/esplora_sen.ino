#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <DHTesp.h>
#include "HT_TinyGPS++.h"
#include "LoRaWan_APP.h"
#include "Arduino.h"

// =====================================================
// DHT11
// VCC  -> 3.3V
// GND  -> GND
// DATA -> GPIO33
// =====================================================
#define DHT_PIN 33

DHTesp dht;

// DHT 캐시 (loop에서 분리 읽기)
static float         g_airTemp   = NAN;
static float         g_humidity  = NAN;
static bool          g_dhtValid  = false;
static unsigned long lastDHTRead = 0;
#define DHT_READ_INTERVAL 3000

// =====================================================
// GPS ATGM336H
// GPS TX -> Heltec GPIO38 (ESP32 RX)
// GPS RX -> Heltec GPIO39 (ESP32 TX)
// VCC    -> 3.3V
// GND    -> GND
// ★ GPS 안테나를 Heltec 보드에서 10cm 이상 이격 권장
// =====================================================
#define GPS_RX 38
#define GPS_TX 39

#define GPS_MAX_AGE_MS 15000

HardwareSerial GPSSerial(1);
TinyGPSPlus    gps;

// =====================================================
// 비상 버튼
// GPIO7 ---- BUTTON ---- GND  |  INPUT_PULLUP
// =====================================================
#define BUTTON_PIN 7

bool          emergencyActive     = false;
unsigned long lastButtonPressTime = 0;
#define EMERGENCY_HOLD_TIME 5000

// =====================================================
// FAN / MOTOR DRIVER
// A-1A -> GPIO6   A-1B -> GND
// B-1A -> GPIO47  B-1B -> GND
// VCC -> 5V  |  GND -> 공통 GND
// =====================================================
#define FAN1_PIN 6
#define FAN2_PIN 47

#define FAN_ON_TEMP  30.0f
#define WARNING_TEMP 29.0f

bool fansOn = false;

// =====================================================
// 장갑 ESP32U MAC
// =====================================================
uint8_t gloveMac[] = {
  0x34, 0x98, 0x7A, 0xBD, 0x7A, 0x2C
};

// =====================================================
// Glove -> Belt : ESP-NOW Sensor Packet
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
// Belt -> Base : LoRa Telemetry Packet (35 bytes)
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

static_assert(sizeof(TelemetryPacket) == 35,
              "TelemetryPacket must be 35 bytes");

TelemetryPacket txData;
uint16_t        loraSequence = 0;

// =====================================================
// Belt -> Glove : State / Cause
// =====================================================
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

// =====================================================
// Belt -> Glove : Display Packet (12 bytes)
// =====================================================
struct __attribute__((packed)) DisplayPacket {
  uint16_t magic;
  uint8_t  version;
  uint8_t  state;
  uint8_t  cause;
  uint8_t  fanPercent;
  uint8_t  bpm;
  int16_t  skinTemp_x100;
  uint8_t  flags;
  uint16_t seq;
};

static_assert(sizeof(DisplayPacket) == 12,
              "DisplayPacket must be 12 bytes");

DisplayPacket displayData;
uint16_t      displaySequence = 0;

// =====================================================
// BASELINE
// =====================================================
bool          baselineStarted   = false;
unsigned long baselineStartTime = 0;
#define BASELINE_TIME 10000

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
// ESP-NOW 수신 (Glove -> Belt)
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
  if (digitalRead(BUTTON_PIN) == LOW) {
    lastButtonPressTime = millis();
    if (!emergencyActive) {
      emergencyActive = true;
      Serial.println();
      Serial.println("!!!!!!!!!!!!!!!!!!!!!!!!!!!!");
      Serial.println(" EMERGENCY BUTTON PRESSED");
      Serial.println("!!!!!!!!!!!!!!!!!!!!!!!!!!!!");
    }
  }

  if (emergencyActive &&
      millis() - lastButtonPressTime >= EMERGENCY_HOLD_TIME) {
    emergencyActive = false;
    Serial.println("[BUTTON] Emergency cleared");
  }
}

// =====================================================
// FAN ON/OFF
// =====================================================
void setFans(bool on) {
  if (on) {
    digitalWrite(FAN1_PIN, HIGH);
    digitalWrite(FAN2_PIN, HIGH);
    if (!fansOn) {
      Serial.println();
      Serial.println("============================");
      Serial.println(" FAN1 ON / FAN2 ON");
      Serial.println("============================");
    }
    fansOn = true;
  } else {
    digitalWrite(FAN1_PIN, LOW);
    digitalWrite(FAN2_PIN, LOW);
    if (fansOn) {
      Serial.println();
      Serial.println("============================");
      Serial.println(" FAN1 OFF / FAN2 OFF");
      Serial.println("============================");
    }
    fansOn = false;
  }
}

void controlFans() {
  bool gloveValid = gloveDataReceived &&
                    (millis() - lastGloveReceiveTime < 5000);

  if (emergencyActive)             { setFans(true);  return; }
  if (!gloveValid)                 { setFans(false); return; }
  setFans(gloveData.temp >= FAN_ON_TEMP);
}

// =====================================================
// DHT11 분리 읽기 (DHTesp 라이브러리)
// ★ ESP32-S3 + WiFi 환경에 맞는 타이밍 사용
// =====================================================
void readDHT() {
  if (millis() - lastDHTRead < DHT_READ_INTERVAL) return;
  lastDHTRead = millis();

  g_dhtValid = false;

  for (int i = 0; i < 3; i++) {
    TempAndHumidity data = dht.getTempAndHumidity();

    float t = data.temperature;
    float h = data.humidity;

    if (dht.getStatus() == DHTesp::ERROR_NONE &&
        !isnan(t) && !isnan(h)   &&
        t > -10.0f && t < 60.0f &&
        h >=  0.0f && h <= 100.0f) {
      g_airTemp  = t;
      g_humidity = h;
      g_dhtValid = true;
      Serial.printf("[DHT11] OK  T=%.1fC  H=%.1f%%\n", t, h);
      return;
    }

    Serial.printf("[DHT11] retry %d  status=%s\n",
                  i + 1, dht.getStatusString());
    delay(500);
  }

  Serial.println("[DHT11] 3회 실패 — 배선 확인");
}

// =====================================================
// OLED 상태 생성 (Belt -> Glove)
// =====================================================
void makeDisplayStatus() {
  memset(&displayData, 0, sizeof(displayData));

  displayData.magic   = 0xD15A;
  displayData.version = 1;
  displayData.seq     = displaySequence++;

  bool gloveValid = gloveDataReceived &&
                    (millis() - lastGloveReceiveTime < 5000);

  if (gloveValid) {
    displayData.flags        |= (1 << 3);
    displayData.bpm           = constrain(gloveData.bpm, 0, 255);
    displayData.skinTemp_x100 = (int16_t)(gloveData.temp * 100.0f);
    if (gloveData.finger) displayData.flags |= (1 << 0);
  }

  if (emergencyActive) displayData.flags |= (1 << 1);
  if (fansOn) {
    displayData.flags     |= (1 << 2);
    displayData.fanPercent = 100;
  }

  // FSM
  if (emergencyActive) {
    displayData.state = STATE_EMERGENCY;
    displayData.cause = CAUSE_NONE;
    return;
  }
  if (millis() < 3000) {
    displayData.state = STATE_BOOT;
    displayData.cause = CAUSE_NONE;
    return;
  }
  if (!gloveValid || !gloveData.finger || gloveData.bpm <= 0) {
    displayData.state = STATE_SENSOR_CHECK;
    displayData.cause = CAUSE_SENSOR;
    baselineStarted   = false;
    return;
  }
  if (!baselineStarted) {
    baselineStarted   = true;
    baselineStartTime = millis();
  }
  if (gloveData.temp >= FAN_ON_TEMP) {
    displayData.state = STATE_DANGER;
    displayData.cause = CAUSE_TEMP_UP;
    return;
  }
  if (gloveData.temp >= WARNING_TEMP) {
    displayData.state = STATE_WARNING;
    displayData.cause = CAUSE_TEMP_UP;
    return;
  }
  if (millis() - baselineStartTime < BASELINE_TIME) {
    displayData.state = STATE_BASELINE;
    displayData.cause = CAUSE_NONE;
    return;
  }
  displayData.state = STATE_NORMAL;
  displayData.cause = CAUSE_NONE;
}

void sendDisplayStatus() {
  makeDisplayStatus();
  esp_err_t result = esp_now_send(
    gloveMac,
    (uint8_t *)&displayData,
    sizeof(displayData)
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

  // GLOVE
  bool gloveValid = gloveDataReceived &&
                    (millis() - lastGloveReceiveTime < 5000);

  if (gloveValid) {
    flags               |= (1 << 0);
    txData.bpm           = constrain(gloveData.bpm, 0, 255);
    txData.skinTemp_x100 = (int16_t)(gloveData.temp * 100.0f);
    txData.gsr           = constrain(gloveData.gsr, 0, 65535);
    txData.gsrDiff       = constrain(gloveData.gsrDiff, -32768, 32767);
    txData.ir            = (uint32_t)gloveData.ir;
    if (gloveData.finger) flags |= (1 << 3);
  }

  // DHT11 — loop()에서 갱신된 캐시 사용
  if (g_dhtValid) {
    flags              |= (1 << 1);
    txData.airTemp_x10  = (int16_t)(g_airTemp  * 10.0f);
    txData.humidity_x10 = (uint16_t)(g_humidity * 10.0f);
  }

  // GPS — 유효 기간 15초
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
    float spd = gps.speed.kmph();
    if (spd < 0) spd = 0;
    txData.speed_x10 = (uint16_t)(spd * 10.0);
  }

  if (emergencyActive) flags |= (1 << 4);
  if (fansOn)          flags |= (1 << 5);

  txData.flags = flags;
}

// =====================================================
// Serial 로그
// =====================================================
void printTelemetry() {
  Serial.println();
  Serial.println("================================");
  Serial.println(" BELT STATUS");
  Serial.println("================================");

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

  // DHT11
  Serial.println();
  Serial.println("[ DHT11 ]");
  if (txData.flags & (1 << 1)) {
    Serial.printf("Air Temp     : %.1f C\n",  txData.airTemp_x10  / 10.0f);
    Serial.printf("Humidity     : %.1f %%\n", txData.humidity_x10 / 10.0f);
  } else {
    Serial.println("READ FAILED");
    Serial.printf("DHT status   : %s\n", dht.getStatusString());
  }

  // GPS
  Serial.println();
  Serial.println("[ GPS ]");
  Serial.printf("GPS chars    : %lu\n", gps.charsProcessed());

  if (gps.charsProcessed() == 0) {
    Serial.println("*** UART NO DATA — GPIO38 배선 확인 ***");
  } else {
    Serial.printf("Satellites   : %s\n",
                  gps.satellites.isValid()
                    ? String(gps.satellites.value()).c_str()
                    : "--");
    Serial.printf("GPS age      : %s\n",
                  gps.location.isValid()
                    ? (String(gps.location.age()) + " ms").c_str()
                    : "INVALID");

    if (txData.flags & (1 << 2)) {
      Serial.println("Fix          : YES");
      Serial.printf("Latitude     : %.6f\n",
                    txData.latitude_e7  / 10000000.0);
      Serial.printf("Longitude    : %.6f\n",
                    txData.longitude_e7 / 10000000.0);
      Serial.printf("Altitude     : %.1f m\n",
                    txData.altitude_dm  / 10.0f);
      Serial.printf("Speed        : %.1f km/h\n",
                    txData.speed_x10    / 10.0f);
    } else {
      if (!gps.location.isValid()) {
        Serial.println("Fix          : NO — 위성 고정 대기 or RF 간섭");
        Serial.println(
          "  ★ GPS 안테나를 Heltec 보드에서 10cm 이상 이격 권장");
      } else {
        Serial.printf("Fix          : age %lu ms > %d ms\n",
                      gps.location.age(), GPS_MAX_AGE_MS);
      }
    }
  }

  // EMERGENCY
  Serial.println();
  Serial.println("[ EMERGENCY BUTTON ]");
  Serial.printf("Status       : %s\n",
                emergencyActive ? "PRESSED" : "NORMAL");

  // FAN
  Serial.println();
  Serial.println("[ FAN ]");
  Serial.printf("Threshold    : %.1f C\n", FAN_ON_TEMP);
  Serial.printf("FAN1         : %s\n",     fansOn ? "ON" : "OFF");
  Serial.printf("FAN2         : %s\n",     fansOn ? "ON" : "OFF");

  // PACKET
  Serial.println();
  Serial.printf("Flags        : 0x%02X\n", txData.flags);
  Serial.printf("LoRa SEQ     : %d\n",     txData.seq);
  Serial.printf("LoRa bytes   : %d\n",     (int)sizeof(txData));
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
  Serial.println(" BELT HELTEC SYSTEM");
  Serial.println(" DHT + GPS + FAN + BUTTON");
  Serial.println("================================");

  Mcu.begin(HELTEC_BOARD, SLOW_CLK_TPYE);
  Serial.println("[OK] MCU");

  // BUTTON
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  Serial.println("[OK] BUTTON GPIO7");

  // FAN
  pinMode(FAN1_PIN, OUTPUT);
  pinMode(FAN2_PIN, OUTPUT);
  setFans(false);
  Serial.println("[OK] FAN1 GPIO6");
  Serial.println("[OK] FAN2 GPIO47");

  // DHT11 (DHTesp)
  dht.setup(DHT_PIN, DHTesp::DHT11);
  delay(2000);
  Serial.println("[OK] DHT11 GPIO33");

  // GPS
  GPSSerial.begin(9600, SERIAL_8N1, GPS_RX, GPS_TX);
  Serial.println("[OK] GPS UART");
  Serial.println("GPS RX = GPIO38  |  GPS TX = GPIO39");

  // ESP-NOW
  WiFi.mode(WIFI_STA);
  esp_wifi_set_ps(WIFI_PS_NONE);  // WiFi 파워세이빙 OFF
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
    MODEM_LORA,
    TX_OUTPUT_POWER,
    0,
    LORA_BANDWIDTH,
    LORA_SPREADING_FACTOR,
    LORA_CODINGRATE,
    LORA_PREAMBLE_LENGTH,
    LORA_FIX_LENGTH_PAYLOAD_ON,
    true, 0, 0,
    LORA_IQ_INVERSION_ON,
    3000
  );

  Serial.println("[OK] LoRa TX");
  Serial.printf("Telemetry Size : %d bytes\n", (int)sizeof(TelemetryPacket));
  Serial.printf("Display Size   : %d bytes\n", (int)sizeof(DisplayPacket));
  Serial.println();
  Serial.println("SYSTEM READY");
}

// =====================================================
// LOOP
// =====================================================
void loop() {
  Radio.IrqProcess();
  checkButton();
  controlFans();

  // DHT11 — 3초 주기 분리 읽기
  readDHT();

  // GPS — 계속 NMEA 수신
  while (GPSSerial.available() > 0) {
    gps.encode(GPSSerial.read());
  }

  // 0.5초: Belt -> Glove OLED 상태 전송
  static unsigned long lastDisplaySend = 0;
  if (millis() - lastDisplaySend >= 500) {
    lastDisplaySend = millis();
    sendDisplayStatus();
  }

  // 2초: LoRa 송신
  static unsigned long lastLoRaSend = 0;
  if (loraIdle && millis() - lastLoRaSend >= 2000) {
    lastLoRaSend = millis();
    makeTelemetryPacket();
    printTelemetry();
    loraIdle = false;
    Radio.Send((uint8_t *)&txData, sizeof(txData));
  }
}
