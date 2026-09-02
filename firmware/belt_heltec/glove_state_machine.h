#pragma once

// 팬이 연결된 ESP32(일반적으로 벨트의 ESP-NOW 수신/LoRa 송신 보드)에 넣는 로컬 상태기계.
// LoRa/서버가 끊겨도 팬 명령 판단은 이 코드로 계속 동작한다. 장갑 LCD에는 결과를
// ESP-NOW로 되돌려 표시한다. 팬이 장갑에 연결된 배선이라면 장갑 ESP32에 넣어도 된다.
// update()는 1초 주기로 호출하는 것을 기준으로 한다.

#include <stdint.h>
#include <math.h>

enum class GloveState : uint8_t {
  SENSOR_CHECK, BASELINE, NORMAL, CAUTION, COOLING_50, DANGER, EMERGENCY,
};

struct GloveDisplay {
  const char *line1;
  const char *line2;
  uint8_t fanPercent;  // 팬 PWM으로 보낼 목표값: 0, 50, 100
  uint8_t riskScore;  // 진단값이 아닌 0~100 장치 위험 점수
};

class GloveStateMachine {
 public:
  static constexpr uint32_t BASELINE_MS = 180000;     // 3분 안정 기준선 수집
  static constexpr uint32_t ENTER_HOLD_MS = 10000;    // 냉각 진입 유지시간
  static constexpr uint32_t RECOVERY_HOLD_MS = 30000; // 냉각 해제 유지시간

  GloveDisplay update(
      uint8_t bpm, float skinTempC, uint16_t gsr, int16_t gsrDiff,
      bool fingerDetected, uint32_t nowMs, bool manualSos = false) {
    if (manualSos) emergencyLatched_ = true;
    if (emergencyLatched_) return output(GloveState::EMERGENCY, "EMERGENCY", "SOS FAN 100%", 100, 100);

    // BPM=0 또는 Finger=NO이면 위험도 0으로 오해하지 않고 센서 확인을 우선한다.
    if (!fingerDetected || bpm == 0) {
      resetHoldTimers();
      return output(GloveState::SENSOR_CHECK, "SENSOR CHECK", "WEAR GLOVE", 0, 255);
    }

    if (!baselineReady_) {
      addBaseline(bpm, skinTempC, gsr, nowMs);
      if (!baselineReady_) return output(GloveState::BASELINE, "BASELINE", "STAY STILL", 0, 255);
    }

    const uint8_t score = calculateRisk(bpm, skinTempC, gsr, gsrDiff, nowMs);
    const char *cause = dominantCause(bpm, skinTempC, gsr, gsrDiff, nowMs);
    GloveState next = state_;

    if (score >= 85) {
      highRiskSinceMs_ = highRiskSinceMs_ ? highRiskSinceMs_ : nowMs;
      coolingSinceMs_ = 0;
      if (nowMs - highRiskSinceMs_ >= ENTER_HOLD_MS) next = GloveState::DANGER;
      else if (state_ != GloveState::DANGER) next = GloveState::CAUTION;
    } else if (score >= 60) {
      coolingSinceMs_ = coolingSinceMs_ ? coolingSinceMs_ : nowMs;
      highRiskSinceMs_ = 0;
      if (nowMs - coolingSinceMs_ >= ENTER_HOLD_MS) next = GloveState::COOLING_50;
      else if (state_ != GloveState::COOLING_50 && state_ != GloveState::DANGER) next = GloveState::CAUTION;
    } else {
      resetHoldTimers();
      if (score >= 40) {
        recoverySinceMs_ = 0;
        if (state_ != GloveState::COOLING_50 && state_ != GloveState::DANGER) next = GloveState::CAUTION;
      } else if (state_ == GloveState::COOLING_50 || state_ == GloveState::DANGER) {
        recoverySinceMs_ = recoverySinceMs_ ? recoverySinceMs_ : nowMs;
        if (nowMs - recoverySinceMs_ >= RECOVERY_HOLD_MS) next = GloveState::NORMAL;
      } else {
        next = GloveState::NORMAL;
      }
    }

    state_ = next;
    if (state_ == GloveState::DANGER) return output(state_, "DANGER", "FAN 100%", 100, score);
    if (state_ == GloveState::COOLING_50) return output(state_, "COOLING", "FAN 50%", 50, score);
    if (state_ == GloveState::CAUTION) return output(state_, "CAUTION", cause, 0, score);
    return output(state_, "NORMAL", "SENSORS OK", 0, score);
  }

  // Emergency는 자동 해제하지 않는다. 실제 물리 버튼/현장 확인 후에만 호출한다.
  void clearEmergencyAfterPhysicalCheck() { emergencyLatched_ = false; state_ = GloveState::CAUTION; }

 private:
  GloveState state_ = GloveState::BASELINE;
  bool emergencyLatched_ = false;
  bool baselineReady_ = false;
  uint32_t baselineStartMs_ = 0, baselineSamples_ = 0;
  float baselineBpmSum_ = 0, baselineTempSum_ = 0, baselineGsrSum_ = 0;
  float baselineBpm_ = 0, baselineTemp_ = 0, baselineGsr_ = 0;
  float previousTemp_ = 0;
  uint32_t previousTempMs_ = 0, coolingSinceMs_ = 0, highRiskSinceMs_ = 0, recoverySinceMs_ = 0;

  void addBaseline(uint8_t bpm, float temp, uint16_t gsr, uint32_t nowMs) {
    if (baselineSamples_ == 0) baselineStartMs_ = nowMs;
    baselineBpmSum_ += bpm; baselineTempSum_ += temp; baselineGsrSum_ += gsr; baselineSamples_++;
    previousTemp_ = temp; previousTempMs_ = nowMs;
    if (nowMs - baselineStartMs_ >= BASELINE_MS && baselineSamples_ >= 30) {
      baselineBpm_ = baselineBpmSum_ / baselineSamples_;
      baselineTemp_ = baselineTempSum_ / baselineSamples_;
      baselineGsr_ = baselineGsrSum_ / baselineSamples_;
      baselineReady_ = true; state_ = GloveState::NORMAL;
    }
  }

  float tempSlopePerMin(float temp, uint32_t nowMs) const {
    if (previousTempMs_ == 0 || nowMs <= previousTempMs_) return 0;
    return (temp - previousTemp_) * 60000.0f / (nowMs - previousTempMs_);
  }

  uint8_t calculateRisk(uint8_t bpm, float temp, uint16_t gsr, int16_t gsrDiff, uint32_t nowMs) {
    const float slope = tempSlopePerMin(temp, nowMs);
    uint8_t score = 0;
    if (bpm >= baselineBpm_ + 40) score += 60;
    else if (bpm >= baselineBpm_ + 25) score += 40;
    if (temp >= baselineTemp_ + 0.9f || slope >= 0.20f) score += 55;
    else if (temp >= baselineTemp_ + 0.5f || slope >= 0.10f) score += 35;
    const float gsrThreshold = fmaxf(10.0f, baselineGsr_ * 0.05f);
    if (fabsf((float)gsrDiff) >= gsrThreshold || fabsf((float)gsr - baselineGsr_) >= baselineGsr_ * 0.15f) score += 25;
    previousTemp_ = temp; previousTempMs_ = nowMs;
    return score > 100 ? 100 : score;
  }

  const char *dominantCause(uint8_t bpm, float temp, uint16_t gsr, int16_t gsrDiff, uint32_t nowMs) const {
    const float slope = tempSlopePerMin(temp, nowMs);
    if (temp >= baselineTemp_ + 0.5f || slope >= 0.10f) return "TEMP UP";
    if (bpm >= baselineBpm_ + 25) return "HR HIGH";
    const float threshold = fmaxf(10.0f, baselineGsr_ * 0.05f);
    if (fabsf((float)gsrDiff) >= threshold || fabsf((float)gsr - baselineGsr_) >= baselineGsr_ * 0.15f) return "GSR UP";
    return "CHECK BODY";
  }

  void resetHoldTimers() { coolingSinceMs_ = 0; highRiskSinceMs_ = 0; recoverySinceMs_ = 0; }
  GloveDisplay output(GloveState state, const char *line1, const char *line2, uint8_t fan, uint8_t score) {
    state_ = state; return {line1, line2, fan, score};
  }
};
