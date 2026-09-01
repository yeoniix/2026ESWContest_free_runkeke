# HeatSentry V7 TRUE FINAL

이 폴더는 V6에서 확인된 조립 불가/유로/서비스성 문제를 기준으로 형상을 다시 만든 **CAD-level 최종 출력 후보**입니다.
STEP은 Fusion 360에서 직접 불러올 수 있고, STL은 바로 슬라이서에서 사용할 수 있습니다. 전체 형상의 생성 소스는 `HeatSentry_V7_PARAMETRIC_SOURCE.py`입니다.

## 1. 고정 좌표와 외형

- X = 허리 좌우: 본체 240 mm
- Y = 몸에서 바깥 방향 깊이: 본체 72 mm
- Z = 위아래: 본체 90 mm
- 외부/팬 면 = Y 음(-) 방향
- 사람 등/서비스 커버 = Y 양(+) 방향
- 기본 벽 두께 = 2.4 mm
- 좌/우 셸 분할, 각각 독립적으로 220 mm급 프린터에서 출력 가능
- 상부 덕트 riser 높이 = 18 mm

## 2. V6에서 바뀐 핵심 구조

### 셸
- Left/Right shell 모두 **각각 단일 solid**로 다시 생성했습니다.
- 보스, 팬 포켓, 덕트 riser, 격벽, 채널 벽, 가이드가 모두 셸과 실제 Boolean Join되어 있습니다.
- 중앙 이음은 접착제만 의존하지 않습니다.
  - 4개 일체형 alignment tongue/pocket
  - `06_CENTER_BRIDGE_PLATE...` 2개
  - 후면 서비스 커버 10점 체결
  - 중앙 seam에는 얇은 실리콘/가스켓을 추가해 기밀을 잡습니다.

### 팬
- 40 x 40 x 10.3 mm 팬 기준
- 팬은 **외부에서 삽입/교체**합니다.
- 41 mm 정사각 포켓 + 32 x 32 mm M3 피치
- 팬 뒤 Ø37 유효 opening
- 팬 뒤쪽에서 격벽 전면까지 약 **20.55 mm plenum** 확보
- 그릴은 별도 부품이며 팬과 동일한 4개 M3 나사로 체결합니다.
- 그릴과 팬 사이에 44 x 44 mm 정도의 교체식 얇은 필터 폼/메시를 넣을 수 있습니다.

### 공기 유로
- 외부 -> FAN -> plenum -> 45도 turning vane -> 상부 capsule port -> riser -> duct
- 상부 opening은 **40 x 26 mm capsule 형상**입니다.
- 상부 opening 면적 약 894.9 mm²
- 팬 backer Ø37 opening 면적 약 1075.2 mm²
- 상부/팬 opening 면적비 약 **83.2%**로 V6의 Ø25.6 급축소를 제거했습니다.
- 왼쪽/오른쪽 팬은 각각 56 mm 폭의 독립 채널 안에서 동작합니다.
- 덕트와 전자부 사이의 separator는 별도 판이 아니라 셸에 일체형입니다.

### 전자부
- 일체형 separator 후면~rear inner wall 깊이 약 **33.9 mm**
- 140 x 70 x 15 mm power bank 기준 후면 여유 약 **10.2 mm**
- 30 x 55 x 25 mm ESP reference 기준 후면 여유 약 **5.4 mm**
- 배터리는 `04_BATTERY_CRADLE...` + Velcro strap 방식으로 탈착합니다.
- ESP는 `05_ESP_UNIVERSAL_SLED...`에 cable tie로 고정하므로 특정 PCB 나사홀 위치에 종속되지 않습니다.
- 팬 배선은 separator의 Ø8.2 mm 홀을 통과한 뒤 고무 grommet 또는 RTV로 밀봉합니다.
- 우측 하부에는 Ø8.5 mm 실제 관통 cable/grommet port 2개가 있습니다.

### 후면 서비스 커버
두 버전을 제공합니다.

1. `03_SERVICE_COVER_PCM_READY_V7`
   - PCM carrier 체결 보스 포함
2. `03B_SERVICE_COVER_FLAT_NO_PCM_V7`
   - PCM을 쓰지 않을 때 몸쪽이 완전히 평평한 버전

공통:
- 216 x 82 mm
- rear opening 204 x 74 mm
- 10개 M3 체결점
- 안쪽에 gasket groove 포함
- 216 x 82 mm 판은 45도로 회전하면 약 210.7 x 210.7 mm footprint라 220 x 220 mm급 베드에 들어갑니다. brim을 크게 쓰지 않는 것을 권장합니다.

### 벨트
- 셸을 관통하지 않는 별도 50 mm webbing loop 구조
- 좌/우 각 4개 M3 체결
- 벨트가 전자부/송풍부 벽을 뚫지 않습니다.

### PCM
- `10_PCM_CARRIER_UNIVERSAL_V7`
- nominal max reference: 약 160 x 64 x 8 mm
- 고정은 Velcro strap + 4개 M3
- PCM 실제 크기가 더 작으면 strap으로 조절 가능합니다.
- PCM을 사용하지 않으면 flat service cover를 사용하세요.

## 3. 덕트 어댑터

본체 riser 자체는 44 x 30 mm 외형의 capsule 형상입니다.

- `11_DUCT_ADAPTER_TO_32mm_OD_HOSE_V7`
  - 32 mm OD 호스를 끼우는 socket, nominal ID 32.4 mm
  - 기본 추천
- `12_DUCT_ADAPTER_TO_25mm_OD_HOSE_COMPAT_V7`
  - 25 mm OD 호스 호환용, nominal ID 25.4 mm
  - 유로 단면이 다시 작아지므로 **호환성용**입니다.

어댑터는 필요한 규격을 **2개 출력**합니다.

## 4. 출력 수량

필수:
- 01_LEFT_SHELL_V7 x1
- 02_RIGHT_SHELL_V7 x1
- 서비스 커버 둘 중 하나 x1
- 04_BATTERY_CRADLE_140x70_V7 x1
- 05_ESP_UNIVERSAL_SLED_V7 x1
- 06_CENTER_BRIDGE_PLATE_PRINT_2X_V7 x2
- 07_BELT_LOOP_LEFT_50mm_V7 x1
- 08_BELT_LOOP_RIGHT_50mm_V7 x1
- 09_FAN_FILTER_GRILLE_40mm_PRINT_2X_V7 x2
- 선택한 duct adapter x2

선택:
- 10_PCM_CARRIER_UNIVERSAL_V7 x1

## 5. 권장 출력 조건

PETG 권장
- nozzle 0.4 mm
- layer 0.20 mm
- perimeter/wall 4줄 이상
- top/bottom 5 layer 이상
- 일반 부품 infill 25~35%
- belt loop 50~60%
- center bridge 60% 이상
- fan grille 40% 이상

열 삽입 인서트 보스는 인서트 실제 외경에 따라 pilot hole을 0.1~0.3 mm 조정할 수 있습니다. 현재 M3 nominal pilot은 4.2 mm입니다.

## 6. 조립 순서

1. Left/Right shell의 M3 heat-set insert를 먼저 삽입합니다.
2. 오른쪽 tongue pocket에 왼쪽 alignment tongue를 끼워 두 shell을 맞춥니다.
3. 중앙 seam의 전자실 측 둘레와 외기 접촉 seam에 얇은 실리콘 gasket/RTV를 적용합니다.
4. rear opening을 통해 center bridge plate 2개를 상/하단에 설치합니다.
5. 팬 2개를 전면에서 넣고 필터 + fan grille을 M3로 체결합니다.
6. 팬 전선을 separator grommet hole로 넘긴 후 hole을 밀봉합니다.
7. battery cradle을 설치하고 power bank를 Velcro로 고정합니다.
8. ESP universal sled를 설치하고 PCB를 cable tie로 고정합니다.
9. 케이블을 하부 Ø8.5 port로 빼고 실제 사용 grommet/봉합제로 마감합니다.
10. 서비스 커버 gasket을 넣고 M3 10개를 대각선 순서로 조금씩 조입니다.
11. 좌/우 belt loop를 설치하고 50 mm webbing을 통과시킵니다.
12. PCM 사용 시 PCM-ready cover + carrier를 설치합니다.
13. 상부 duct adapter를 2개 끼운 후 호스를 연결합니다.

## 7. 최종 CAD 검증 결과

`V7_GEOMETRY_VALIDATION.txt` / `V7_VALIDATION_FINAL.json` 참조.

- 모든 출력 STL: connected component = 1
- 모든 출력 STL: watertight = True
- Left shell solids = 1
- Right shell solids = 1
- Left/Right shell 의도치 않은 체적 간섭 = 0 mm³
- shell vs service cover = 0 mm³
- shell vs fan reference = 0 mm³
- shell vs power bank reference = 0 mm³
- shell vs ESP reference = 0 mm³
- belt loops vs shells = 0 mm³
- battery/ESP mount vs reference body = 0 mm³

## 8. 중요한 현실 조건

이 V7은 **CAD 형상과 조립 논리 기준 최종본**입니다. 실제 구매한 팬/보조배터리/ESP/호스의 제조 공차는 출력 전에 한 번만 실측하세요.

또한 팬 흡기와 상부 송풍구가 외부에 열려 있으므로 **장치 전체를 IP67이라고 부를 수는 없습니다.** 이 설계의 목표는 송풍부와 전자부를 일체형 separator + gasketed cover로 분리하는 것입니다. 실제 방진/방수 등급은 완성품 누수/침수 시험 없이 보증할 수 없습니다.
