#include "display_protocol.h"
#include <Wire.h>
#include <WiFi.h>
#include <esp_now.h>
#include "MAX30105.h"
#include "heartRate.h"
#include "SparkFun_TMP117.h"
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ===================== 핀 설정 =====================
#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 22
#define GSR_PIN     34
#define MOTOR_PIN   25

// ===================== OLED 128x64 I2C =====================
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT  64
#define OLED_ADDRESS  0x3C
#define OLED_RESET     -1

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);
bool oledReady = false;

// ===================== 손목 → 벨트 ESP-NOW =====================
// 브로드캐스트로 센서값 전송, 벨트가 유니캐스트 회신
const uint8_t BELT_BROADCAST_MAC[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

typedef struct SensorPacket {
  int           bpm;
  float         temp;
  int           gsr;
  int           gsrDiff;
  long          ir;
  bool          finger;
  unsigned long seq;
} SensorPacket;

SensorPacket  sensorTxData;
unsigned long sensorSequence = 0;

// ===================== 벨트 → 손목 표시 결과 =====================
DisplayPacket beltDisplayData;
bool          beltDisplayReceived = false;
unsigned long lastBeltDisplayTime = 0;

// ===================== 센서 객체 =====================
MAX30105 particleSensor;
TMP117   tempSensor;

// ===================== 심박 =====================
const byte RATE_SIZE = 8;
byte          rates[RATE_SIZE];
byte          rateSpot      = 0;
byte          validRateCount = 0;
unsigned long lastBeat       = 0;
float         beatsPerMinute = 0.0f;
int           beatAvg        = 0;
long          irValue        = 0;

// ===================== GSR =====================
int gsrBaseline = 0;
int gsrValue    = 0;
int gsrDiff     = 0;

// ===================== 온도 =====================
float tempC = 0.0f;

// ===================== 타이밍 =====================
unsigned long lastTempRead      = 0;
unsigned long lastGsrRead       = 0;
unsigned long lastSerialPrint   = 0;
unsigned long lastMotorEvent    = 0;
unsigned long lastDisplayUpdate = 0;
unsigned long lastSensorSend    = 0;

const unsigned long TEMP_INTERVAL    = 1000;
const unsigned long GSR_INTERVAL     = 200;
const unsigned long SERIAL_INTERVAL  = 1000;
const unsigned long MOTOR_COOLDOWN   = 3000;
const unsigned long DISPLAY_INTERVAL = 500;
const unsigned long SENSOR_SEND_INTERVAL = 1000;
const unsigned long BELT_STATUS_TIMEOUT  = 3000;

// ===================== 임계값 =====================
const int IR_FINGER_THRESHOLD = 50000;
const int BPM_MIN_VALID       = 45;
const int BPM_MAX_VALID       = 180;

// ===================== 함수 =====================

int readGSRFiltered() {
  long sum = 0;
  const int samples = 10;
  for (int i = 0; i < samples; i++) {
    sum += analogRead(GSR_PIN);
    delay(2);
  }
  return (int)(sum / samples);
}

int calibrateGSRBaseline() {
  long sum = 0;
  const int samples = 50;
  Serial.println("Calibrating GSR... keep still.");
  for (int i = 0; i < samples; i++) {
    sum += readGSRFiltered();
    delay(50);
  }
  return (int)(sum / samples);
}

void vibrateMotor(int onTimeMs) {
  digitalWrite(MOTOR_PIN, HIGH);
  delay(onTimeMs);
  digitalWrite(MOTOR_PIN, LOW);
}

const char* displayCauseText(uint8_t cause) {
  switch (cause) {
    case CAUSE_HR_HIGH:   return "HR HIGH";
    case CAUSE_HR_CHANGE: return "HR CHANGE";
    case CAUSE_TEMP_UP:   return "TEMP UP";
    case CAUSE_GSR_UP:    return "GSR UP";
    case CAUSE_HOT_ENV:   return "HOT ENV";
    case CAUSE_ACTIVE:    return "ACTIVE";
    case CAUSE_SENSOR:    return "CHECK BODY";
    default:              return "CHECK BODY";
  }
}

bool beltStatusFresh() {
  return beltDisplayReceived &&
         (millis() - lastBeltDisplayTime < BELT_STATUS_TIMEOUT);
}

bool beltAlertActive() {
  if (!beltStatusFresh()) return false;

  return
    beltDisplayData.state == STATE_CAUTION ||
    beltDisplayData.state == STATE_COOLING ||
    beltDisplayData.state == STATE_EMERGENCY;
}

// ===================== ESP-NOW 수신 (벨트 → 손목) =====================
void onBeltDataRecv(
  const esp_now_recv_info_t *recv_info,
  const uint8_t             *incomingData,
  int                        len
) {
  if (len != sizeof(DisplayPacket)) return;

  DisplayPacket received;
  memcpy(&received, incomingData, sizeof(received));

  if (received.magic   != DISPLAY_PACKET_MAGIC ||
      received.version != DISPLAY_PACKET_VERSION) return;

  beltDisplayData      = received;
  beltDisplayReceived  = true;
  lastBeltDisplayTime  = millis();
}

// ===================== 센서값 전송 =====================
void sendSensorPacket(bool fingerDetected) {
  sensorTxData.bpm     = beatAvg;
  sensorTxData.temp    = tempC;
  sensorTxData.gsr     = gsrValue;
  sensorTxData.gsrDiff = gsrDiff;
  sensorTxData.ir      = irValue;
  sensorTxData.finger  = fingerDetected;
  sensorTxData.seq     = sensorSequence++;

  esp_now_send(
    BELT_BROADCAST_MAC,
    reinterpret_cast<const uint8_t *>(&sensorTxData),
    sizeof(sensorTxData)
  );
}

// ===================== OLED 업데이트 =====================
void updateDisplay() {
  if (!oledReady) return;

  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextWrap(false);

  if (!beltStatusFresh()) {
    display.setTextSize(2);
    display.setCursor(0, 5);
    display.println("LINK LOST");

    display.setTextSize(1);
    display.setCursor(0, 38);
    display.println("CHECK BELT");

    display.setCursor(0, 52);
    display.println("ESP-NOW WAIT");

    display.display();
    return;
  }

  float temp =
    beltDisplayData.skinTemp_x100 / 100.0f;

  uint8_t coolingStage =
    displayGetCoolingStage(
      beltDisplayData.flags
    );

  // ---------------------------------------------------
  // line 1
  // ---------------------------------------------------
  display.setTextSize(2);
  display.setCursor(0, 4);

  switch (beltDisplayData.state) {
    case STATE_BOOT:
      display.println("BOOT");
      break;

    case STATE_BASELINE:
      display.println("BASELINE");
      break;

    case STATE_NORMAL:
      display.println("NORMAL");
      break;

    case STATE_CAUTION:
      display.println("CAUTION");
      break;

    case STATE_COOLING:
      if (coolingStage == COOLING_C3) {
        display.println("HIGH RISK");
      }
      else if (coolingStage == COOLING_C2) {
        display.println("DANGER");
      }
      else {
        display.println("COOLING");
      }
      break;

    case STATE_EMERGENCY:
      display.println("EMERGENCY");
      break;

    case STATE_SENSOR_CHECK:
      display.setTextSize(1);
      display.setCursor(0, 9);
      display.println("SENSOR CHECK");
      break;

    default:
      display.println("UNKNOWN");
      break;
  }

  // ---------------------------------------------------
  // line 2
  // ---------------------------------------------------
  display.setTextSize(1);
  display.setCursor(0, 36);

  switch (beltDisplayData.state) {
    case STATE_BOOT:
      display.println("STARTING");
      break;

    case STATE_BASELINE:
      display.println("STAY STILL");
      break;

    case STATE_NORMAL:
      display.print("HR ");
      display.print(beltDisplayData.bpm);
      display.print("  T ");
      display.print(temp, 1);
      display.println("C");
      break;

    case STATE_CAUTION:
      display.println(
        displayCauseText(
          beltDisplayData.cause
        )
      );
      break;

    case STATE_COOLING:
      if (coolingStage == COOLING_C1) {
        display.print("FAN 50% ");
      }
      else {
        display.print("FAN 100% ");
      }

      display.println(
        displayCauseText(
          beltDisplayData.cause
        )
      );
      break;

    case STATE_EMERGENCY:
      display.println("SOS FAN 100%");
      break;

    case STATE_SENSOR_CHECK:
      display.println("WEAR GLOVE");
      break;

    default:
      display.println("CHECK BELT");
      break;
  }

  display.display();
}

// ===================== SETUP =====================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);

  // ESP-NOW
  WiFi.mode(WIFI_STA);
  if (esp_now_init() != ESP_OK) {
    Serial.println("ESP-NOW init failed");
    while (1);
  }

  esp_now_register_recv_cb(onBeltDataRecv);

  esp_now_peer_info_t broadcastPeer = {};
  memcpy(broadcastPeer.peer_addr, BELT_BROADCAST_MAC, 6);
  broadcastPeer.channel = 0;
  broadcastPeer.encrypt = false;

  if (esp_now_add_peer(&broadcastPeer) != ESP_OK) {
    Serial.println("ESP-NOW broadcast peer failed");
    while (1);
  }

  // OLED
  oledReady = display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS);
  if (!oledReady) {
    Serial.println("OLED init failed - continuing without display");
  } else {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("HEATSENTRY");
    display.println("STARTING");
    display.display();
  }

  // 모터
  pinMode(MOTOR_PIN, OUTPUT);
  digitalWrite(MOTOR_PIN, LOW);

  // ADC
  analogReadResolution(12);

  // TMP117
  if (!tempSensor.begin()) {
    Serial.println("TMP117 init failed");
    while (1);
  }

  // MAX30102
  if (!particleSensor.begin(Wire, I2C_SPEED_STANDARD)) {
    Serial.println("MAX30102 init failed");
    while (1);
  }
  particleSensor.setup(60, 4, 2, 100, 411, 4096);
  particleSensor.setPulseAmplitudeRed(0x2A);
  particleSensor.setPulseAmplitudeIR(0x2A);
  particleSensor.setPulseAmplitudeGreen(0);

  // GSR 베이스라인
  gsrBaseline = calibrateGSRBaseline();
  Serial.printf("GSR baseline = %d\n", gsrBaseline);

  vibrateMotor(120);
  Serial.println("System ready");
}

// ===================== LOOP =====================
void loop() {
  unsigned long now = millis();

  // ── MAX30102 심박 ─────────────────────────────
  irValue = particleSensor.getIR();
  bool fingerDetected = (irValue > IR_FINGER_THRESHOLD);

  if (fingerDetected) {
    if (checkForBeat(irValue)) {
      unsigned long delta = now - lastBeat;
      lastBeat = now;
      beatsPerMinute = 60.0f / (delta / 1000.0f);

      if (beatsPerMinute > BPM_MIN_VALID &&
          beatsPerMinute < BPM_MAX_VALID) {
        rates[rateSpot++] = (byte)beatsPerMinute;
        rateSpot %= RATE_SIZE;
        if (validRateCount < RATE_SIZE) validRateCount++;

        int sum = 0;
        for (byte i = 0; i < validRateCount; i++) sum += rates[i];
        beatAvg = sum / validRateCount;
      }
    }
  } else {
    beatsPerMinute = 0;
    beatAvg        = 0;
    validRateCount = 0;
  }

  // ── TMP117 온도 ──────────────────────────────
  if (now - lastTempRead >= TEMP_INTERVAL) {
    lastTempRead = now;
    tempC = tempSensor.readTempC();
  }

  // ── GSR ─────────────────────────────────────
  if (now - lastGsrRead >= GSR_INTERVAL) {
    lastGsrRead = now;
    gsrValue = readGSRFiltered();
    gsrDiff  = gsrValue - gsrBaseline;
  }

  // ── 센서값 → 벨트 전송 ──────────────────────
  if (now - lastSensorSend >= SENSOR_SEND_INTERVAL) {
    lastSensorSend = now;
    sendSensorPacket(fingerDetected);
  }

  // ── OLED 갱신 ────────────────────────────────
  if (now - lastDisplayUpdate >= DISPLAY_INTERVAL) {
    lastDisplayUpdate = now;
    updateDisplay();
  }

  // ── 진동 모터: 벨트 판정 결과에만 반응 ───────
  if (beltAlertActive()) {
    if (now - lastMotorEvent >= MOTOR_COOLDOWN) {
      lastMotorEvent = now;
      vibrateMotor(120);
      delay(120);
      vibrateMotor(120);
    }
  }

  // ── 시리얼 출력 ──────────────────────────────
  if (now - lastSerialPrint >= SERIAL_INTERVAL) {
    lastSerialPrint = now;
    Serial.printf(
      "Finger=%s  IR=%ld  BPM=%.1f  Avg=%d  Temp=%.2f  GSR=%d  Diff=%d  Alert=%s\n",
      fingerDetected ? "YES" : "NO",
      irValue, beatsPerMinute, beatAvg,
      tempC, gsrValue, gsrDiff,
      beltAlertActive() ? "YES" : "NO"
    );
  }
}
