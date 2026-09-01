#include <Wire.h>
#include <WiFi.h>
#include <esp_now.h>
#include "MAX30105.h"
#include "heartRate.h"
#include "SparkFun_TMP117.h"
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "display_protocol.h"

// ===================== 핀 설정 =====================
#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 22
#define GSR_PIN     34
#define MOTOR_PIN   25

// ===================== OLED 128x64 I2C =====================
// MAX30102, TMP117과 같은 I2C 버스(GPIO21/22)를 공유한다.
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64
#define OLED_ADDRESS  0x3C
#define OLED_RESET    -1

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);
bool oledReady = false;

// ===================== 손목 → 벨트 ESP-NOW =====================
// 벨트 MAC을 몰라도 시험할 수 있도록 브로드캐스트로 센서값을 보낸다.
// 벨트는 수신한 손목 MAC으로 DisplayPacket을 유니캐스트 회신한다.
const uint8_t BELT_BROADCAST_MAC[] = {
  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF
};

typedef struct SensorPacket {
  int bpm;
  float temp;
  int gsr;
  int gsrDiff;
  long ir;
  bool finger;
  unsigned long seq;
} SensorPacket;

SensorPacket sensorTxData;
unsigned long sensorSequence = 0;

// ===================== 벨트 → 손목 표시 결과 =====================
DisplayPacket beltDisplayData;
bool beltDisplayReceived = false;
unsigned long lastBeltDisplayTime = 0;

// ===================== 센서 객체 =====================
MAX30105 particleSensor;
TMP117 tempSensor;

// ===================== 심박 관련 =====================
const byte RATE_SIZE = 8;
byte rates[RATE_SIZE];
byte rateSpot = 0;
byte validRateCount = 0;

unsigned long lastBeat = 0;
float beatsPerMinute = 0.0;
int beatAvg = 0;
long irValue = 0;

// ===================== GSR 관련 =====================
int gsrBaseline = 0;
int gsrValue = 0;
int gsrDiff = 0;

// ===================== 온도 =====================
float tempC = 0.0;

// ===================== 타이밍 =====================
unsigned long lastTempRead = 0;
unsigned long lastGsrRead = 0;
unsigned long lastSerialPrint = 0;
unsigned long lastMotorEvent = 0;
unsigned long lastDisplayUpdate = 0;
unsigned long lastSensorSend = 0;

const unsigned long TEMP_INTERVAL   = 1000;   // 1초
const unsigned long GSR_INTERVAL    = 200;    // 200ms
const unsigned long SERIAL_INTERVAL = 1000;   // 1초
const unsigned long MOTOR_COOLDOWN  = 3000;   // 진동 최소 간격 3초
const unsigned long DISPLAY_INTERVAL = 500;   // OLED 갱신 0.5초
const unsigned long SENSOR_SEND_INTERVAL = 1000;
const unsigned long BELT_STATUS_TIMEOUT = 3000;

// ===================== 임계값(필요시 조정) =====================
const int   IR_FINGER_THRESHOLD = 50000;
const int   BPM_MIN_VALID = 45;
const int   BPM_MAX_VALID = 180;

// ===================== 함수 =====================
int readGSRFiltered() {
  long sum = 0;
  const int samples = 10;

  for (int i = 0; i < samples; i++) {
    sum += analogRead(GSR_PIN);
    delay(2);
  }

  return sum / samples;
}

int calibrateGSRBaseline() {
  long sum = 0;
  const int samples = 50;

  Serial.println("Calibrating GSR... keep still.");

  for (int i = 0; i < samples; i++) {
    sum += readGSRFiltered();
    delay(50);
  }

  return sum / samples;
}

void vibrateMotor(int onTimeMs) {
  digitalWrite(MOTOR_PIN, HIGH);
  delay(onTimeMs);
  digitalWrite(MOTOR_PIN, LOW);
}

const char* displayCauseText(uint8_t cause) {
  switch (cause) {
    case CAUSE_HR_HIGH: return "HR HIGH";
    case CAUSE_HR_CHANGE: return "HR CHANGE";
    case CAUSE_TEMP_UP: return "TEMP UP";
    case CAUSE_GSR_UP: return "GSR UP";
    case CAUSE_HOT_ENV: return "HOT ENV";
    case CAUSE_ACTIVE: return "ACTIVE";
    case CAUSE_SENSOR: return "CHECK BODY";
    default: return "CHECK BODY";
  }
}

bool beltStatusFresh() {
  return beltDisplayReceived &&
         (millis() - lastBeltDisplayTime < BELT_STATUS_TIMEOUT);
}

bool beltAlertActive() {
  if (!beltStatusFresh()) return false;
  return beltDisplayData.state >= STATE_WARNING &&
         beltDisplayData.state <= STATE_EMERGENCY;
}

void onBeltDataRecv(
  const esp_now_recv_info_t *recv_info,
  const uint8_t *incomingData,
  int len
) {
  if (len != sizeof(DisplayPacket)) return;

  DisplayPacket received;
  memcpy(&received, incomingData, sizeof(received));

  if (received.magic != DISPLAY_PACKET_MAGIC ||
      received.version != DISPLAY_PACKET_VERSION) {
    return;
  }

  beltDisplayData = received;
  beltDisplayReceived = true;
  lastBeltDisplayTime = millis();
}

void sendSensorPacket(bool fingerDetected) {
  sensorTxData.bpm = beatAvg;
  sensorTxData.temp = tempC;
  sensorTxData.gsr = gsrValue;
  sensorTxData.gsrDiff = gsrDiff;
  sensorTxData.ir = irValue;
  sensorTxData.finger = fingerDetected;
  sensorTxData.seq = sensorSequence++;

  esp_now_send(
    BELT_BROADCAST_MAC,
    reinterpret_cast<const uint8_t *>(&sensorTxData),
    sizeof(sensorTxData)
  );
}

void updateDisplay() {
  if (!oledReady) return;

  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextWrap(false);

  // 상태 판단은 하지 않고 벨트가 보낸 결과만 2줄로 표시한다.
  if (!beltStatusFresh()) {
    display.setTextSize(2);
    display.setCursor(0, 5);
    display.println("LINK LOST");

    display.setTextSize(1);
    display.setCursor(0, 38);
    display.println("CHECK BELT");

    display.setCursor(0, 52);
    display.println("ESP-NOW WAIT");
  }
  else {
    float temp = beltDisplayData.skinTemp_x100 / 100.0f;

    // 1줄: 상태/단계
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
      case STATE_WARNING:
        display.println("WARNING");
        break;
      case STATE_COOLING:
        display.println("COOLING");
        break;
      case STATE_DANGER:
        display.println("DANGER");
        break;
      case STATE_HIGH_RISK:
        display.println("HIGH RISK");
        break;
      case STATE_EMERGENCY:
        display.println("EMERGENCY");
        break;
      case STATE_SENSOR_CHECK:
        // 12자는 2배 글꼴로 128px를 넘어가므로 이 상태만 1배로 표시한다.
        display.setTextSize(1);
        display.setCursor(0, 9);
        display.println("SENSOR CHECK");
        break;
      default:
        display.println("UNKNOWN");
        break;
    }

    // 2줄: 단계별 행동 또는 원인
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
      case STATE_WARNING:
        display.println(displayCauseText(beltDisplayData.cause));
        break;
      case STATE_COOLING:
        display.print("FAN ");
        display.print(beltDisplayData.fanPercent);
        display.print("% ");
        display.println(displayCauseText(beltDisplayData.cause));
        break;
      case STATE_DANGER:
        display.print("FAN 100% ");
        display.println(displayCauseText(beltDisplayData.cause));
        break;
      case STATE_HIGH_RISK:
        display.println("FAN 100%");
        break;
      case STATE_EMERGENCY:
        display.println("SOS  FAN 100%");
        break;
      case STATE_SENSOR_CHECK:
        display.println("WEAR GLOVE");
        break;
      default:
        display.println("CHECK BELT");
        break;
    }
  }

  display.display();
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  // ESP32 I2C 핀 지정
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);

  // ESP-NOW: 센서값 송신 + 벨트 판정 결과 수신
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

  // OLED 시작. 화면이 연결되지 않아도 센서 기능은 계속 동작한다.
  oledReady = display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS);
  if (!oledReady) {
    Serial.println("OLED init failed - continuing without display");
  }
  else {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("HEATSENTRY");
    display.println("STARTING");
    display.display();
  }

  pinMode(MOTOR_PIN, OUTPUT);
  digitalWrite(MOTOR_PIN, LOW);

  // ESP32 ADC 설정
  analogReadResolution(12); // 0~4095

  // TMP117 시작
  if (!tempSensor.begin()) {
    Serial.println("TMP117 init failed");
    while (1);
  }

  // MAX30102 시작
  if (!particleSensor.begin(Wire, I2C_SPEED_STANDARD)) {
    Serial.println("MAX30102 init failed");
    while (1);
  }

  // MAX30102 설정
  // setup(LED brightness, sample average, LED mode, sample rate, pulse width, ADC range)
  particleSensor.setup(60, 4, 2, 100, 411, 4096);
  particleSensor.setPulseAmplitudeRed(0x2A);
  particleSensor.setPulseAmplitudeIR(0x2A);
  particleSensor.setPulseAmplitudeGreen(0);

  // GSR baseline
  gsrBaseline = calibrateGSRBaseline();

  Serial.println("System ready");
  Serial.print("GSR baseline = ");
  Serial.println(gsrBaseline);

  // 시작 알림
  vibrateMotor(120);
}

void loop() {
  unsigned long now = millis();

  // -------- MAX30102 --------
  irValue = particleSensor.getIR();
  bool fingerDetected = (irValue > IR_FINGER_THRESHOLD);

  if (fingerDetected) {
    if (checkForBeat(irValue)) {
      unsigned long delta = now - lastBeat;
      lastBeat = now;

      beatsPerMinute = 60.0 / (delta / 1000.0);

      if (beatsPerMinute > BPM_MIN_VALID && beatsPerMinute < BPM_MAX_VALID) {
        rates[rateSpot++] = (byte)beatsPerMinute;
        rateSpot %= RATE_SIZE;

        if (validRateCount < RATE_SIZE) validRateCount++;

        int sum = 0;
        for (byte i = 0; i < validRateCount; i++) {
          sum += rates[i];
        }
        beatAvg = sum / validRateCount;
      }
    }
  } else {
    beatsPerMinute = 0;
    beatAvg = 0;
    validRateCount = 0;
  }

  // -------- TMP117 --------
  if (now - lastTempRead >= TEMP_INTERVAL) {
    lastTempRead = now;
    tempC = tempSensor.readTempC();
  }

  // -------- GSR --------
  if (now - lastGsrRead >= GSR_INTERVAL) {
    lastGsrRead = now;
    gsrValue = readGSRFiltered();
    gsrDiff = gsrValue - gsrBaseline;
  }

  // -------- 손목 센서값을 벨트로 전송 --------
  if (now - lastSensorSend >= SENSOR_SEND_INTERVAL) {
    lastSensorSend = now;
    sendSensorPacket(fingerDetected);
  }

  // -------- OLED --------
  if (now - lastDisplayUpdate >= DISPLAY_INTERVAL) {
    lastDisplayUpdate = now;
    updateDisplay();
  }

  // -------- 진동 모터: 벨트 판정 결과에만 반응 --------
  if (beltAlertActive()) {
    if (now - lastMotorEvent >= MOTOR_COOLDOWN) {
      lastMotorEvent = now;

      // 짧게 2번 진동
      vibrateMotor(120);
      delay(120);
      vibrateMotor(120);
    }
  }

  // -------- 시리얼 출력 --------
  if (now - lastSerialPrint >= SERIAL_INTERVAL) {
    lastSerialPrint = now;

    Serial.print("Finger=");
    Serial.print(fingerDetected ? "YES" : "NO");

    Serial.print(", IR=");
    Serial.print(irValue);

    Serial.print(", BPM=");
    Serial.print(beatsPerMinute, 1);

    Serial.print(", Avg BPM=");
    Serial.print(beatAvg);

    Serial.print(", Temp=");
    Serial.print(tempC, 2);

    Serial.print(", GSR=");
    Serial.print(gsrValue);

    Serial.print(", GSRdiff=");
    Serial.print(gsrDiff);

    Serial.print(", Alert=");
    Serial.println(beltAlertActive() ? "YES" : "NO");
  }
}
