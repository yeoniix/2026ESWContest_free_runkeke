#include "LoRaWan_APP.h"
#include "Arduino.h"

// =====================================================
// LoRa 설정 (Belt 송신기와 반드시 동일)
// =====================================================
#define RF_FREQUENCY              922300000
#define LORA_BANDWIDTH            0
#define LORA_SPREADING_FACTOR     7
#define LORA_CODINGRATE           1
#define LORA_PREAMBLE_LENGTH      8
#define LORA_SYMBOL_TIMEOUT       0
#define LORA_FIX_LENGTH_PAYLOAD_ON false
#define LORA_IQ_INVERSION_ON      false

// =====================================================
// Belt 송신기와 반드시 동일
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

TelemetryPacket rxData;
static RadioEvents_t RadioEvents;

// =====================================================
// LoRa 수신 완료
// =====================================================
void OnRxDone(uint8_t *payload, uint16_t size, int16_t rssi, int8_t snr) {

  Serial.println();
  Serial.println("=================================");
  Serial.println("       DASHBOARD RECEIVED");
  Serial.println("=================================");
  Serial.printf("Bytes : %d  |  RSSI : %d dBm  |  SNR : %d dB\n",
                size, rssi, snr);

  // 패킷 크기 검사
  if (size != sizeof(TelemetryPacket)) {
    Serial.println("ERROR: PACKET SIZE MISMATCH");
    Radio.Rx(0);
    return;
  }

  memcpy(&rxData, payload, sizeof(rxData));

  // 패킷 식별
  if (rxData.magic != 0xA55A) {
    Serial.println("ERROR: INVALID MAGIC");
    Radio.Rx(0);
    return;
  }

  // ===================================================
  // SYSTEM STATUS
  // ===================================================
  Serial.println();
  Serial.println("[ SYSTEM ]");
  Serial.printf("Version       : %d\n",   rxData.version);
  Serial.printf("Node ID       : %d\n",   rxData.nodeId);
  Serial.printf("Sequence      : %d\n",   rxData.seq);
  Serial.printf("Flags         : 0x%02X\n", rxData.flags);

  // ===================================================
  // RISK STATE  (airTemp_x10 재활용: high=state, low=cause)
  // ===================================================
  Serial.println();
  Serial.println("[ RISK STATE ]");

  uint8_t stateCode = (uint8_t)((rxData.airTemp_x10 >> 8) & 0xFF);
  uint8_t causeCode = (uint8_t)( rxData.airTemp_x10        & 0xFF);

  // 0=BOOT 1=BASELINE 2=NORMAL 3=CAUTION
  // 4=COOLING_50 5=DANGER 6=EMERGENCY 7=SENSOR_CHECK
  const char* stateNames[] = {
    "BOOT", "BASELINE", "NORMAL", "CAUTION",
    "COOLING 50%", "DANGER", "EMERGENCY", "SENSOR CHECK"
  };
  const char* causeNames[] = {
    "NONE", "HR HIGH", "HR CHANGE", "TEMP UP",
    "GSR UP", "HOT ENV", "ACTIVE", "SENSOR"
  };

  const char* stateTxt = (stateCode < 8) ? stateNames[stateCode] : "UNKNOWN";
  const char* causeTxt = (causeCode < 8) ? causeNames[causeCode] : "UNKNOWN";

  // 긴급 상태 강조
  if (stateCode == 6) {           // STATE_EMERGENCY
    Serial.println("!!! EMERGENCY !!!");
  } else if (stateCode == 5) {    // STATE_DANGER
    Serial.println("!! DANGER !!");
  } else if (stateCode == 4) {    // STATE_COOLING_50
    Serial.println("! COOLING 50% !");
  }

  Serial.printf("State         : %s\n", stateTxt);
  Serial.printf("Cause         : %s\n", causeTxt);

  // ===================================================
  // BELT STATUS (비상 / 팬)
  // ===================================================
  Serial.println();
  Serial.println("[ BELT STATUS ]");

  bool emergency = rxData.flags & (1 << 4);
  bool fansOn    = rxData.flags & (1 << 5);

  if (emergency) {
    Serial.println("!!! EMERGENCY : ACTIVE !!!");
  } else {
    Serial.println("Emergency     : NORMAL");
  }

  Serial.printf("Fan           : %s\n", fansOn ? "ON" : "OFF");

  // ===================================================
  // GLOVE / ESP32U
  // ===================================================
  Serial.println();
  Serial.println("[ GLOVE / ESP32U ]");

  if (rxData.flags & (1 << 0)) {
    Serial.printf("BPM           : %d\n",        rxData.bpm);
    Serial.printf("Skin Temp     : %.2f C\n",    rxData.skinTemp_x100 / 100.0f);
    Serial.printf("GSR           : %d\n",        rxData.gsr);
    Serial.printf("GSR Diff      : %d\n",        rxData.gsrDiff);
    Serial.printf("IR            : %lu\n",       rxData.ir);
    Serial.printf("Finger        : %s\n",
                  (rxData.flags & (1 << 3)) ? "YES" : "NO");
  } else {
    Serial.println("NO GLOVE DATA");
  }

  // ===================================================
  // GPS
  // ===================================================
  Serial.println();
  Serial.println("[ GPS ]");

  if (rxData.flags & (1 << 2)) {
    Serial.printf("Latitude      : %.6f\n",  rxData.latitude_e7  / 10000000.0);
    Serial.printf("Longitude     : %.6f\n",  rxData.longitude_e7 / 10000000.0);
    Serial.printf("Satellites    : %d\n",    rxData.satellites);
    Serial.printf("Altitude      : %.1f m\n", rxData.altitude_dm / 10.0f);
    Serial.printf("Speed         : %.1f km/h\n", rxData.speed_x10 / 10.0f);
  } else {
    Serial.printf("NO GPS FIX  (Satellites: %d)\n", rxData.satellites);
  }

  Serial.println();
  Serial.println("=================================");

  Radio.Rx(0);
}

// =====================================================
// Timeout / Error
// =====================================================
void OnRxTimeout() {
  Serial.println("[LoRa] RX TIMEOUT");
  Radio.Rx(0);
}

void OnRxError() {
  Serial.println("[LoRa] RX ERROR");
  Radio.Rx(0);
}

// =====================================================
// SETUP
// =====================================================
void setup() {
  Serial.begin(115200);
  delay(2000);

  Serial.println();
  Serial.println("================================");
  Serial.println(" BASE STATION — LoRa RX");
  Serial.println("================================");

  Mcu.begin(HELTEC_BOARD, SLOW_CLK_TPYE);
  Serial.println("[OK] MCU");

  RadioEvents.RxDone    = OnRxDone;
  RadioEvents.RxTimeout = OnRxTimeout;
  RadioEvents.RxError   = OnRxError;

  Radio.Init(&RadioEvents);
  Radio.SetChannel(RF_FREQUENCY);
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
    0, 0,
    LORA_IQ_INVERSION_ON,
    true
  );

  Serial.println("[OK] LoRa RX");
  Serial.printf("Expected bytes : %d\n", (int)sizeof(TelemetryPacket));
  Serial.println("Waiting for belt data...");

  Radio.Rx(0);
}

// =====================================================
// LOOP
// =====================================================
void loop() {
  Radio.IrqProcess();
}
