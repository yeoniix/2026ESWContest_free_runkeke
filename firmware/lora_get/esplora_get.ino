#include "LoRaWan_APP.h"
#include "Arduino.h"

// =====================================================
// LoRa settings - Belt와 반드시 동일
// =====================================================
#define RF_FREQUENCY          922300000
#define LORA_BANDWIDTH        0
#define LORA_SPREADING_FACTOR 7
#define LORA_CODINGRATE       1
#define LORA_PREAMBLE_LENGTH  8
#define LORA_SYMBOL_TIMEOUT   0
#define LORA_FIX_LENGTH_PAYLOAD_ON false
#define LORA_IQ_INVERSION_ON       false

// =====================================================
// 35 byte packet
//
// version 2:
// airTemp_x10:
//   high = DeviceState
//   low  = Cause
//
// humidity_x10:
//   high = CoolingStage
//   low  = RiskIndex
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

TelemetryPacket rxData;
static RadioEvents_t RadioEvents;

const char* getStateName(uint8_t state) {
  switch (state) {
    case 0: return "BOOT";
    case 1: return "BASELINE";
    case 2: return "NORMAL";
    case 3: return "CAUTION";
    case 4: return "COOLING";
    case 5: return "EMERGENCY";
    case 6: return "SENSOR CHECK";
    default: return "UNKNOWN";
  }
}

const char* getCauseName(uint8_t cause) {
  switch (cause) {
    case 0: return "NONE";
    case 1: return "HR HIGH";
    case 2: return "HR CHANGE";
    case 3: return "TEMP UP";
    case 4: return "GSR UP";
    case 5: return "HOT ENV";
    case 6: return "ACTIVE";
    case 7: return "SENSOR";
    default: return "UNKNOWN";
  }
}

const char* getStageName(uint8_t stage) {
  switch (stage) {
    case 0: return "C0";
    case 1: return "C1";
    case 2: return "C2";
    case 3: return "C3";
    case 4: return "C4";
    default: return "C?";
  }
}

// Python bridge reads only this line.
void printRawPacket(
  const uint8_t *payload,
  uint16_t size,
  int16_t rssi,
  int8_t snr
) {
  Serial.print("HSRAW,");

  for (uint16_t i = 0; i < size; i++) {
    if (payload[i] < 0x10) {
      Serial.print("0");
    }

    Serial.print(
      payload[i],
      HEX
    );
  }

  Serial.print(",");
  Serial.print(rssi);
  Serial.print(",");
  Serial.println(snr);
}

void OnRxDone(
  uint8_t *payload,
  uint16_t size,
  int16_t rssi,
  int8_t snr
) {
  if (size != sizeof(TelemetryPacket)) {
    Serial.printf(
      "[ERROR] PACKET SIZE %u / expected %u\n",
      size,
      (unsigned)sizeof(TelemetryPacket)
    );

    Radio.Rx(0);
    return;
  }

  memcpy(
    &rxData,
    payload,
    sizeof(rxData)
  );

  if (rxData.magic != 0xA55A) {
    Serial.println(
      "[ERROR] INVALID MAGIC"
    );

    Radio.Rx(0);
    return;
  }

  // Dashboard bridge raw packet
  printRawPacket(
    payload,
    size,
    rssi,
    snr
  );

  uint16_t stateCauseWord =
    (uint16_t)rxData.airTemp_x10;

  uint8_t stateCode =
    (uint8_t)(
      (stateCauseWord >> 8) & 0xFF
    );

  uint8_t causeCode =
    (uint8_t)(
      stateCauseWord & 0xFF
    );

  uint16_t stageRiskWord =
    rxData.humidity_x10;

  uint8_t coolingStage =
    (uint8_t)(
      (stageRiskWord >> 8) & 0xFF
    );

  uint8_t riskIndex =
    (uint8_t)(
      stageRiskWord & 0xFF
    );

  bool gloveValid =
    rxData.flags & (1 << 0);

  bool gpsValid =
    rxData.flags & (1 << 2);

  bool finger =
    rxData.flags & (1 << 3);

  bool emergency =
    rxData.flags & (1 << 4);

  bool fanOn =
    rxData.flags & (1 << 5);

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

  Serial.printf(
    "Bytes         : %u\n",
    size
  );

  Serial.printf(
    "RSSI / SNR    : %d dBm / %d dB\n",
    rssi,
    snr
  );

  Serial.println();
  Serial.println("[ SYSTEM ]");

  Serial.printf(
    "Version       : %u\n",
    rxData.version
  );

  Serial.printf(
    "Node ID       : %u\n",
    rxData.nodeId
  );

  Serial.printf(
    "Sequence      : %u\n",
    rxData.seq
  );

  Serial.printf(
    "Flags         : 0x%02X\n",
    rxData.flags
  );

  Serial.println();
  Serial.println("[ FSM ]");

  Serial.printf(
    "State         : %s\n",
    getStateName(stateCode)
  );

  Serial.printf(
    "CoolingStage  : %s\n",
    getStageName(coolingStage)
  );

  Serial.printf(
    "Cause         : %s\n",
    getCauseName(causeCode)
  );

  if (riskIndex <= 100) {
    Serial.printf(
      "RiskIndex     : %u\n",
      riskIndex
    );
  }
  else {
    Serial.println(
      "RiskIndex     : INVALID"
    );
  }

  Serial.println();
  Serial.println("[ BELT ]");

  Serial.printf(
    "Emergency     : %s\n",
    emergency
      ? "ACTIVE"
      : "NORMAL"
  );

  Serial.printf(
    "Fan           : %s\n",
    fanOn
      ? "ON"
      : "OFF"
  );

  Serial.println();
  Serial.println("[ GLOVE / ESP32U ]");

  if (gloveValid) {
    Serial.printf(
      "BPM           : %u\n",
      rxData.bpm
    );

    Serial.printf(
      "Skin Temp     : %.2f C\n",
      rxData.skinTemp_x100 / 100.0f
    );

    Serial.printf(
      "GSR           : %u\n",
      rxData.gsr
    );

    Serial.printf(
      "GSR Diff      : %d\n",
      rxData.gsrDiff
    );

    Serial.printf(
      "IR            : %lu\n",
      rxData.ir
    );

    Serial.printf(
      "Finger        : %s\n",
      finger
        ? "YES"
        : "NO"
    );
  }
  else {
    Serial.println("NO GLOVE DATA");
  }

  Serial.println();
  Serial.println("[ GPS ]");

  if (gpsValid) {
    Serial.printf(
      "Latitude      : %.6f\n",
      rxData.latitude_e7 / 10000000.0
    );

    Serial.printf(
      "Longitude     : %.6f\n",
      rxData.longitude_e7 / 10000000.0
    );

    Serial.printf(
      "Satellites    : %u\n",
      rxData.satellites
    );

    Serial.printf(
      "Altitude      : %.1f m\n",
      rxData.altitude_dm / 10.0f
    );

    Serial.printf(
      "Speed         : %.1f km/h\n",
      rxData.speed_x10 / 10.0f
    );
  }
  else {
    Serial.printf(
      "NO GPS FIX (Satellites: %u)\n",
      rxData.satellites
    );
  }

  Serial.println(
    "================================="
  );

  Radio.Rx(0);
}

void OnRxTimeout() {
  Radio.Rx(0);
}

void OnRxError() {
  Serial.println("[LoRa] RX ERROR");
  Radio.Rx(0);
}

void setup() {
  Serial.begin(115200);
  delay(2000);

  Serial.println();
  Serial.println(
    "================================"
  );

  Serial.println(
    " HEATSENTRY BASE - LoRa RX"
  );

  Serial.println(
    " Unified 7-State + C0~C4"
  );

  Serial.println(
    "================================"
  );

  Mcu.begin(
    HELTEC_BOARD,
    SLOW_CLK_TPYE
  );

  Serial.println("[OK] MCU");

  RadioEvents.RxDone = OnRxDone;
  RadioEvents.RxTimeout = OnRxTimeout;
  RadioEvents.RxError = OnRxError;

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

  Serial.println("[OK] LoRa RX");

  Serial.printf(
    "Frequency      : %.4f MHz\n",
    RF_FREQUENCY / 1000000.0f
  );

  Serial.printf(
    "Expected bytes : %u\n",
    (unsigned)sizeof(TelemetryPacket)
  );

  Serial.println(
    "Waiting for belt data..."
  );

  Radio.Rx(0);
}

void loop() {
  Radio.IrqProcess();
}
