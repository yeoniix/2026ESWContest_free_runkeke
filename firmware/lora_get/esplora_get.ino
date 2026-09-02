#include "LoRaWan_APP.h"
#include "Arduino.h"

// =====================================================
// LoRa 설정
// Belt Heltec와 반드시 동일해야 함
// =====================================================
#define RF_FREQUENCY 922300000

#define LORA_BANDWIDTH 0
#define LORA_SPREADING_FACTOR 7
#define LORA_CODINGRATE 1
#define LORA_PREAMBLE_LENGTH 8
#define LORA_SYMBOL_TIMEOUT 0

#define LORA_FIX_LENGTH_PAYLOAD_ON false
#define LORA_IQ_INVERSION_ON false

// =====================================================
// Belt -> Base
// 35 byte telemetry packet
// =====================================================
struct __attribute__((packed)) TelemetryPacket {

  uint16_t magic;
  uint8_t version;
  uint8_t nodeId;

  uint16_t seq;

  uint8_t bpm;
  int16_t skinTemp_x100;

  uint16_t gsr;
  int16_t gsrDiff;

  uint32_t ir;

  // 최신 HeatSentry 코드에서는
  // 이 16bit 필드를 state/cause로 재사용
  int16_t airTemp_x10;

  uint16_t humidity_x10;   // ★ Belt RiskIndex (0~100, 255=INVALID)

  int32_t latitude_e7;
  int32_t longitude_e7;

  uint8_t satellites;

  int16_t altitude_dm;
  uint16_t speed_x10;

  uint8_t flags;
};

static_assert(
  sizeof(TelemetryPacket) == 35,
  "TelemetryPacket must be 35 bytes"
);

TelemetryPacket rxData;

static RadioEvents_t RadioEvents;

// =====================================================
// State 이름 변환
// =====================================================
const char* getStateName(uint8_t state) {

  switch (state) {

    case 0:
      return "BOOT";

    case 1:
      return "BASELINE";

    case 2:
      return "NORMAL";

    case 3:
      return "CAUTION";

    case 4:
      return "COOLING 50%";

    case 5:
      return "DANGER";

    case 6:
      return "EMERGENCY";

    case 7:
      return "SENSOR CHECK";

    default:
      return "UNKNOWN";
  }
}

// =====================================================
// Cause 이름 변환
// =====================================================
const char* getCauseName(uint8_t cause) {

  switch (cause) {

    case 0:
      return "NONE";

    case 1:
      return "HR HIGH";

    case 2:
      return "HR CHANGE";

    case 3:
      return "TEMP UP";

    case 4:
      return "GSR UP";

    case 5:
      return "HOT ENV";

    case 6:
      return "ACTIVE";

    case 7:
      return "SENSOR";

    default:
      return "UNKNOWN";
  }
}

// =====================================================
// Python Dashboard Bridge용 RAW 출력
//
// 형식:
// HSRAW,<35byte HEX>,<RSSI>,<SNR>
//
// 예:
// HSRAW,5AA501..., -97,-2
// 실제 출력에는 불필요한 공백 없음
// =====================================================
void printRawPacket(
  const uint8_t *payload,
  uint16_t size,
  int16_t rssi,
  int8_t snr
) {

  Serial.print("HSRAW,");

  for (uint16_t i = 0; i < size; i++) {

    // 0x01 같은 값도 반드시 01로 출력
    if (payload[i] < 0x10) {
      Serial.print("0");
    }

    Serial.print(
      payload[i],
      HEX
    );
  }

  Serial.print(",");

  Serial.print(
    rssi
  );

  Serial.print(",");

  Serial.println(
    snr
  );
}

// =====================================================
// LoRa 수신 완료
// =====================================================
void OnRxDone(
  uint8_t *payload,
  uint16_t size,
  int16_t rssi,
  int8_t snr
) {

  // ---------------------------------------------------
  // 크기 검사
  // ---------------------------------------------------
  if (
    size != sizeof(TelemetryPacket)
  ) {

    Serial.println();

    Serial.print(
      "[ERROR] PACKET SIZE : "
    );

    Serial.print(
      size
    );

    Serial.print(
      " / EXPECTED : "
    );

    Serial.println(
      sizeof(TelemetryPacket)
    );

    Radio.Rx(0);

    return;
  }

  // ---------------------------------------------------
  // 구조체 복사
  // ---------------------------------------------------
  memcpy(
    &rxData,
    payload,
    sizeof(rxData)
  );

  // ---------------------------------------------------
  // Magic 검사
  // ---------------------------------------------------
  if (
    rxData.magic != 0xA55A
  ) {

    Serial.println(
      "[ERROR] INVALID MAGIC"
    );

    Radio.Rx(0);

    return;
  }

  // ===================================================
  // ★ 중요
  // Python bridge에서 사용하는 한 줄
  // ===================================================
  printRawPacket(
    payload,
    size,
    rssi,
    snr
  );

  // ===================================================
  // 사람이 확인하는 기존 Serial 로그
  // ===================================================
  Serial.println();
  Serial.println(
    "================================="
  );

  Serial.println(
    " DASHBOARD RECEIVED"
  );

  Serial.println(
    "================================="
  );

  Serial.print(
    "Bytes : "
  );

  Serial.print(
    size
  );

  Serial.print(
    "  |  RSSI : "
  );

  Serial.print(
    rssi
  );

  Serial.print(
    " dBm  |  SNR : "
  );

  Serial.print(
    snr
  );

  Serial.println(
    " dB"
  );

  // ===================================================
  // SYSTEM
  // ===================================================
  Serial.println();
  Serial.println(
    "[ SYSTEM ]"
  );

  Serial.print(
    "Version       : "
  );

  Serial.println(
    rxData.version
  );

  Serial.print(
    "Node ID       : "
  );

  Serial.println(
    rxData.nodeId
  );

  Serial.print(
    "Sequence      : "
  );

  Serial.println(
    rxData.seq
  );

  Serial.print(
    "Flags         : 0x"
  );

  if (rxData.flags < 0x10) {
    Serial.print("0");
  }

  Serial.println(
    rxData.flags,
    HEX
  );

  // ===================================================
  // RISK STATE
  //
  // airTemp_x10 16bit 재활용
  //
  // 상위 8bit = state
  // 하위 8bit = cause
  // ===================================================
  uint16_t packedState =
    (uint16_t)rxData.airTemp_x10;

  uint8_t stateCode =
    (uint8_t)(
      (packedState >> 8) &
      0xFF
    );

  uint8_t causeCode =
    (uint8_t)(
      packedState &
      0xFF
    );

  Serial.println();
  Serial.println(
    "[ RISK STATE ]"
  );

  if (stateCode == 6) {

    Serial.println(
      "!!! EMERGENCY !!!"
    );
  }

  else if (stateCode == 5) {

    Serial.println(
      "!! DANGER !!"
    );
  }

  else if (stateCode == 4) {

    Serial.println(
      "! COOLING 50% !"
    );
  }

  Serial.print(
    "State         : "
  );

  Serial.println(
    getStateName(stateCode)
  );

  Serial.print(
    "Cause         : "
  );

  Serial.println(
    getCauseName(causeCode)
  );

  // ===================================================
  // BELT RISK INDEX
  // humidity_x10 필드를 재활용해 Belt의 실제 RiskIndex 수신
  // ===================================================
  uint16_t beltRiskIndex = rxData.humidity_x10;

  Serial.print(
    "RiskIndex     : "
  );

  if (beltRiskIndex <= 100) {
    Serial.println(beltRiskIndex);
  }
  else {
    Serial.println("INVALID");
  }

  // ===================================================
  // BELT
  // ===================================================
  bool emergency =
    (
      rxData.flags &
      (1 << 4)
    );

  bool fansOn =
    (
      rxData.flags &
      (1 << 5)
    );

  Serial.println();
  Serial.println(
    "[ BELT STATUS ]"
  );

  Serial.print(
    "Emergency     : "
  );

  Serial.println(
    emergency
      ? "ACTIVE"
      : "NORMAL"
  );

  Serial.print(
    "Fan           : "
  );

  Serial.println(
    fansOn
      ? "ON"
      : "OFF"
  );

  // ===================================================
  // GLOVE
  // ===================================================
  Serial.println();
  Serial.println(
    "[ GLOVE / ESP32U ]"
  );

  bool gloveValid =
    (
      rxData.flags &
      (1 << 0)
    );

  bool finger =
    (
      rxData.flags &
      (1 << 3)
    );

  if (gloveValid) {

    Serial.print(
      "BPM           : "
    );

    Serial.println(
      rxData.bpm
    );

    Serial.print(
      "Skin Temp     : "
    );

    Serial.print(
      rxData.skinTemp_x100 /
      100.0f,
      2
    );

    Serial.println(
      " C"
    );

    Serial.print(
      "GSR           : "
    );

    Serial.println(
      rxData.gsr
    );

    Serial.print(
      "GSR Diff      : "
    );

    Serial.println(
      rxData.gsrDiff
    );

    Serial.print(
      "IR            : "
    );

    Serial.println(
      rxData.ir
    );

    Serial.print(
      "Finger        : "
    );

    Serial.println(
      finger
        ? "YES"
        : "NO"
    );
  }

  else {

    Serial.println(
      "NO GLOVE DATA"
    );
  }

  // ===================================================
  // GPS
  // ===================================================
  Serial.println();
  Serial.println(
    "[ GPS ]"
  );

  bool gpsValid =
    (
      rxData.flags &
      (1 << 2)
    );

  if (gpsValid) {

    Serial.print(
      "Latitude      : "
    );

    Serial.println(
      rxData.latitude_e7 /
      10000000.0,
      6
    );

    Serial.print(
      "Longitude     : "
    );

    Serial.println(
      rxData.longitude_e7 /
      10000000.0,
      6
    );

    Serial.print(
      "Satellites    : "
    );

    Serial.println(
      rxData.satellites
    );

    Serial.print(
      "Altitude      : "
    );

    Serial.print(
      rxData.altitude_dm /
      10.0f,
      1
    );

    Serial.println(
      " m"
    );

    Serial.print(
      "Speed         : "
    );

    Serial.print(
      rxData.speed_x10 /
      10.0f,
      1
    );

    Serial.println(
      " km/h"
    );
  }

  else {

    Serial.print(
      "NO GPS FIX  (Satellites: "
    );

    Serial.print(
      rxData.satellites
    );

    Serial.println(
      ")"
    );
  }

  Serial.println(
    "================================="
  );

  // 계속 수신
  Radio.Rx(0);
}

// =====================================================
// LoRa timeout
// =====================================================
void OnRxTimeout() {

  Serial.println(
    "[LoRa] RX TIMEOUT"
  );

  Radio.Rx(0);
}

// =====================================================
// LoRa error
// =====================================================
void OnRxError() {

  Serial.println(
    "[LoRa] RX ERROR"
  );

  Radio.Rx(0);
}

// =====================================================
// SETUP
// =====================================================
void setup() {

  Serial.begin(
    115200
  );

  delay(
    2000
  );

  Serial.println();
  Serial.println(
    "================================"
  );

  Serial.println(
    " HEATSENTRY BASE - LoRa RX"
  );

  Serial.println(
    " Python Dashboard Bridge READY"
  );

  Serial.println(
    "================================"
  );

  // Heltec V4 초기화
  Mcu.begin(
    HELTEC_BOARD,
    SLOW_CLK_TPYE
  );

  Serial.println(
    "[OK] MCU"
  );

  // LoRa callback
  RadioEvents.RxDone =
    OnRxDone;

  RadioEvents.RxTimeout =
    OnRxTimeout;

  RadioEvents.RxError =
    OnRxError;

  // LoRa init
  Radio.Init(
    &RadioEvents
  );

  Radio.SetChannel(
    RF_FREQUENCY
  );

  Radio.SetRxConfig(
    MODEM_LORA,

    LORA_BANDWIDTH,

    LORA_SPREADING_FACTOR,

    LORA_CODINGRATE,

    0,

    LORA_PREAMBLE_LENGTH,

    LORA_SYMBOL_TIMEOUT,

    LORA_FIX_LENGTH_PAYLOAD_ON,

    0,

    true,

    0,

    0,

    LORA_IQ_INVERSION_ON,

    true
  );

  Serial.println(
    "[OK] LoRa RX"
  );

  Serial.print(
    "Frequency      : "
  );

  Serial.print(
    RF_FREQUENCY /
    1000000.0f,
    4
  );

  Serial.println(
    " MHz"
  );

  Serial.print(
    "Expected bytes : "
  );

  Serial.println(
    sizeof(TelemetryPacket)
  );

  Serial.println(
    "Waiting for belt data..."
  );

  Radio.Rx(0);
}

// =====================================================
// LOOP
// =====================================================
void loop() {

  Radio.IrqProcess();
}
