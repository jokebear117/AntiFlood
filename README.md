# Anti-Flood

Anti-Flood는 서울 강남역 주변 지형에 2022년 8월 서울시 강우 기록을 적용해 침수 수심이 변하는 과정을 보여 줍니다. 비가 오거나 물이 남아 있는 곳과 인접 구역을 골라 CPU 여러 코어로 계산하고, 결과를 같은 표고 자료로 만든 3D 지도에 겹쳐 표시합니다.

## 실행

Windows에서는 WSL Ubuntu에서 아래 명령을 실행합니다. Python 3.11 이상, CMake 3.20 이상, OpenMP를 지원하는 C++ 컴파일러, WebGL 2를 지원하는 브라우저가 필요합니다. 이 작업 환경에서는 WSL Ubuntu와 Python 3.12를 검증했습니다.

리포지토리 루트에서 실행합니다.

```bash
sudo apt update
sudo apt install g++ cmake make python3 python3-venv ca-certificates

python3 -m venv ~/.venvs/antiflood
source ~/.venvs/antiflood/bin/activate
python -m pip install -e .
python -m antiflood.prepare

cmake -S engine -B build/engine-linux -DCMAKE_BUILD_TYPE=Release
cmake --build build/engine-linux
python -m antiflood.api
```

[http://127.0.0.1:8000](http://127.0.0.1:8000)을 열어 **시작**을 누릅니다. 기본 시나리오는 2022년 8월 8일 00:00부터 9일 07:10까지 한국시간입니다. 일시정지와 재개로 계산을 제어하고, 시간 슬라이더로 저장된 지도를 볼 수 있습니다. 지도에서 위치를 선택하면 그때의 셀 수심과 Tile 상태가 표시됩니다. **도로 지도**를 켜면 OpenStreetMap에 연결합니다.

준비 명령은 서울시 강우와 관측소 위치, FABDEM의 대상 타일, MapLibre 배포 파일을 내려받습니다. 기존 파일이 있으면 재사용합니다. 초기 다운로드가 끝나면 지형, 재생, 수심 지도는 로컬에서 작동합니다. [입력 자료와 이용 조건](Dataset/README.md)

### 실행 설정

기본값으로 실행할 때는 `.env`가 필요 없습니다. 설정을 바꾸려면 `.env.example`을 `.env`로 복사해 사용합니다. 경로는 서버를 실행하는 환경에서 접근할 수 있어야 합니다.

| 환경 변수 | 동작 |
| --- | --- |
| `ANTIFLOOD_THREADS` | OpenMP 스레드 수입니다. 기본값은 4입니다. |
| `ANTIFLOOD_BOUNDS` | 서·남·동·북 경위도를 쉼표로 구분합니다. 생략하면 강남역 주변의 동경 127.005–127.065°, 북위 37.470–37.535°를 사용합니다. 범위는 확보한 FABDEM 타일과 강우 관측소의 적용 범위에 들어야 합니다. |
| `ANTIFLOOD_DRAIN_MM_H` | 유효 배수율 가정값입니다. 기본값은 5 mm/h입니다. |
| `ANTIFLOOD_DRAIN_RASTER` | 지역별 유효 배수율을 담은 단일 밴드 GeoTIFF 경로입니다. 단위는 mm/h이며 CRS와 NoData를 지정합니다. NoData에는 기본값을 적용합니다. |
| `ANTIFLOOD_DRAIN_RASTER_SOURCE` | 지역별 배수율의 출처를 `assumed`(기본값) 또는 `observed`로 표시합니다. |
| `ANTIFLOOD_BOUNDARY` | 기본값 `open`은 바로 바깥의 지형이 있는 곳에서 유출을 허용합니다. `closed`는 외곽 유출을 막습니다. |
| `ANTIFLOOD_DATASET`, `ANTIFLOOD_OUTPUT` | 입력과 결과 경로를 변경합니다. 기본값은 `Dataset/`, `outputs/`입니다. |
| `ANTIFLOOD_PORT`, `ANTIFLOOD_FRAME_WAIT` | 로컬 포트(기본 8000)와 프레임 발행 후 화면 표시를 위한 대기 시간(기본 0.15초)을 바꿉니다. |
| `UPSTAGE_API_KEY`, `UPSTAGE_MODEL` | 선택 기능입니다. 키를 설정하면 Solar가 최신 계산 상태와 지정 Tile을 조회해 한국어로 설명합니다. 기본 모델은 `solar-mini4`입니다. |

## 계산 과정과 결과

- FABDEM을 30 m 정사각형 격자(EPSG:5181)로 변환합니다. 셀 중심을 기준으로 100 m × 100 m Tile을 구성합니다.
- 각 셀에 가장 가까운 서울시 관측소의 10분 우량을 적용합니다. 구간 안에서는 강우 강도를 일정하게 둡니다. 필요한 관측이 비어 있는 구간에서 시나리오를 나눕니다.
- 강우와 가용 수량 내 배수를 반영한 뒤 [CADDIES WCA2Dv1 유출 커널](https://github.com/WaterDesk/caflood/blob/ef408ee3b6126fadd85cb7c3a2bc73adfc3d8011/Source/apps/caddies-flood/outflowWCA2Dv1.ca)을 실행합니다. 이전 수심을 이어 쓰고 Tile 경계의 같은 유량을 한 셀에서 빼고 이웃 셀에 더합니다.
- 결과는 `outputs/frames/<실행 ID>/`에 저장됩니다. `run.json`에는 좌표계, 격자와 입력 설정이 있고, `valid.npy`는 계산 영역 마스크입니다. 각 프레임에 NumPy 수심 배열(m), 지도용 PNG, UTC 시각과 수량을 담은 JSON이 있습니다. 초기화 후에도 이전 실행 파일은 남습니다.

`src/antiflood/`는 데이터 처리, 강우 재생, Tile 선택, API를 담당합니다. `engine/`에는 OpenMP 계산 어댑터와 MIT 라이선스가 명시된 공개 커널을 두었습니다. `web/`은 MapLibre 지도와 재생 화면입니다. [시스템 아키텍처](docs/ARCHITECTURE.md) · [개발 명세](docs/DEVELOPMENT_SPEC.html) · [구현 결정과 검증](docs/DECISIONS.md)

## 계산 범위와 한계

기본 분석 범위는 강남역 주변입니다. 확보한 서울시 관로 자료는 수위와 시설 위치를 담고 있어 사건 당시 시간별 하수 배출량은 확인할 수 없습니다. 기본 배수율은 균일한 5 mm/h입니다. 계산 범위 바깥에서 들어오는 물과 실제 하수관망 흐름은 모의하지 않습니다. 외곽 유출은 인접 FABDEM 표고로 계산하며, 바깥 표고가 없으면 해당 경계를 닫아 둡니다. 30 m 지형은 연석이나 지하 진입부의 높이 차이를 표현하기 어렵습니다. 관측 수심과의 일치도는 검증하지 않았습니다.
