# Ralph 실행 기록

최신 상태는 STATE.md를 따른다. 라운드 1의 CLI 장애 이후 외부 담당 세션이 수행한 제품 확인은 문서 끝에 별도로 기록했다.

## 초기 구성 — 2026-11-24 KST

- 요청 범위: 기존 제품 완료 확인과 최대 6회의 독립 CLI 반복 시스템 구성.
- 기준: main 및 origin/main = 21f4d5387884653867edea2358dde9b18cedc49b. 기존 변경 없음. 전용 브랜치 ralph/completion-check 생성.
- 기존 구현: README 네 섹션, API·UI 설정 및 기록 재사용, Rasterio 다중 FABDEM, WCA2D 세션, Windows 실행기를 소스에서 확인.
- 환경: Codex CLI 0.166.0, ChatGPT 로그인, exec·stdin·JSON Schema·출력 파일·모델 및 config 옵션 지원 확인. 로컬 모델 목록에서 gpt-6.1-sol과 medium 지원 확인.
- 재사용 판단: 기존 scripts/launch.sh와 Python 표준 라이브러리 subprocess·urllib·argparse를 사용한다. 추가 패키지나 오케스트레이션 서비스가 필요하지 않아 패키지 설치와 외부 프레임워크 검색은 생략했다.
- CLI 근거: 설치된 `codex --help`, `codex exec --help`, `codex login status`; [공식 비대화형 실행](https://learn.chatgpt.com/docs/non-interactive-mode), [추론 설정](https://learn.chatgpt.com/docs/config-file/config-reference).
- 현재 서버: 127.0.0.1:8000, health의 engine/data/replay/map 준비 true, 실행 상태 ready. AntiFlood-Probe는 기본 WSL이며 Python 3.12.3과 기존 엔진 파일 확인.
- 검증 범위: 기존 기록은 과거 증거로만 취급한다. 이번 실데이터 실행 결과는 라운드 이후에 기록한다.

체크포인트 해시는 자기 자신을 파일에 포함할 수 없으므로, STATE의 HEAD 표기는 해당 파일을 담은 커밋을 뜻한다. 컨트롤러는 커밋 직후 실제 최신·마지막 정상 해시와 원격 결과를 `.ralph/runtime/checkpoints.json`에 저장하며, 다음 라운드 기록에 시작 HEAD도 남긴다. 로그와 생성 결과는 Git에서 제외한다.

- 구성 검증: Python 구문 검사, --help, diff --check 통과. 작은 임시 저장소와 subprocess로 경로·비밀 파일 거절, 공백·한글 경로, 비정상 종료 코드와 시간 초과 처리를 확인했다. 미커밋 변경이 있는 상태에서는 실제 컨트롤러가 시작을 거절했다. WSL에서 기존 서버 PID 864와 HTTP health 200을 확인했다.

## 컨트롤러 라운드 1

- 시작 HEAD: 36fa20efe6c067b328e67350b54ac84c74089a16
- 상태: BLOCKED
- 결과: 로컬 실행 환경 장애로 라운드 1을 진행하지 못했어. 파일을 읽지 못해 완료 여부를 판단하지 않았고, 소스와 STATE·HISTORY도 변경하지 않았어.
- 검증: 실행 시도: exec_command는 프로세스 생성 단계에서 실패했고, 대체 Node 런타임도 초기화에 실패했어. 지침·GOAL·상태·소스·Git 이력 확인과 테스트는 미실행이야. 로컬 런타임 복구 후 시작 HEAD 36fa20efe6c067b328e67350b54ac84c74089a16 및 작업 트리 상태부터 확인해야 해.

## 라운드 1 이후 외부 확인 — 2026-11-24 KST

- 독립 CLI 세션: 01a209eb-5d9a-7d40-a4bb-ec6236af2858. 로그 머리에서 gpt-6.1-sol, reasoning effort medium, workspace-write, approval never 확인. 시작 구성 커밋 36fa20efe6c067b328e67350b54ac84c74089a16, BLOCKED 체크포인트 250e00ef23cca2708c5d1a2aa946bc662f2cec49. 둘 다 전용 원격 브랜치에 푸시했다.
- 장애: 셸은 registered Core launch requires an installed app, Node는 app runtime provisioning service is unavailable; refusing helper fallback으로 실패했다. codex doctor 0.166.0은 elevated Windows sandbox provisioning 불완전/오래됨과 stale background server를 보고했다. 인증과 provider 접속은 정상이었다. 앱용 런타임 상속 문제 가능성이 있으나 확정하지 않았다. 시스템·보안 설정 변경과 동일 실패 재실행은 하지 않았다.
- 외부 실행: `wsl -d AntiFlood-Probe -- sh -lc '~/.venvs/antiflood/bin/python scripts/ralph-verify.py'`, 종료 코드 0. 실행 ID 14b8b5156545467a91fa3bb22e701954. 경도 126.999–127.001°, 위도 37.499–37.501°, 가정 배수 2mm/h, 스레드 2, 닫힌 경계. 실제 연속 관측을 끝까지 계산해 프레임 104개를 남겼다.
- 마지막 결과: 강우 14137.199999999979m³, 배수 1326.0563856496883m³, 외곽 유출 0m³, 잔류 수량 12811.143614350316m³, 수량 오차 2.546585164964199e-11m³. OpenMP 작업자 2명, 누적 셀 갱신 834792회. 생성된 모든 수심 배열의 유한값·비음수와 프레임별 수량 허용 오차를 검사했다.
- 기능 확인: 일시정지·재개·초기화, 초기화 후 저장 기록·PNG·지점 수심, 같은 설정의 별도 실행 ID, 서부 지역 사전 확인, 잘못된 스레드 요청 422, Solar 키 미설정 503. launch.sh는 기존 서버 PID 864를 그대로 사용했다. 검증에서 만든 실행만 초기화했고 원본·이전 기록은 보존했다.
- 결과 범위: A1–A7은 STATE의 코드·HTTP 실행 범위에서 충족. 새 브라우저 렌더링, Windows 브라우저 창 열기, 유료 Solar 응답, 실측 수심 정확도는 이번에 검증하지 않았다. 기존 제품 소스에는 변경이 없다. 전체 Ralph 상태는 CLI 도구 장애로 BLOCKED다.
- 검증 스크립트에서 관측한 닫힌 경계 유출 0·양수 배수와 Solar 503 조건을 명시적으로 검사하도록 보강했다. 이미 확보한 결과와 대조했으며 전체 실데이터 실행은 반복하지 않았다.
- 다음 행동: 사용자가 독립 CLI의 Windows 런타임을 복구한 뒤 현재 깨끗한 전용 브랜치에서 `python scripts/ralph-loop.py`를 실행할 수 있다. CLI 도구 실행이 계속 불가능하다면 추가 제품 변경 없이 중단한다. main 병합·배포는 수행하지 않았다.

## Windows 독립 CLI 복구

- 같은 npm CLI 0.166.0에 Desktop 실행 변수를 상속했을 때 첫 셸 호출이 `registered Core launch requires an installed app`으로 실패했다. Desktop 패키지 등록은 `Ok`, 별도 Primary Runtime 패키지는 `NotAvailable`로 조회됐다. 앱 등록 상태와 독립 CLI의 프로세스 생성은 별개다.
- Desktop의 등록 Core·패키지·도구 연결 변수를 자식 프로세스 환경에서 빼자 `workspace-write`에서 테스트 파일을 생성하고 `RALPH_WRITE_OK`를 읽은 뒤 삭제했다. 외부 확인에서도 파일이 사라져 있었다. 근거는 `.ralph/runtime/cli-inherited.log`와 `.ralph/runtime/cli-standalone.log`다. 별도의 공식 MXC 검사도 `MXC_OK`를 반환했다.
- 재개 명령은 깨끗한 `ralph/` 브랜치에서 `python scripts/ralph-loop.py`다. 기본 한도는 실행당 6라운드, 총 90분, 라운드당 15분, 라운드당 최대 2회 CLI 시도다. 등록 Core 등 명시적인 실행 환경 오류는 즉시 멈춘다. `.ralph/runtime/run-*`의 라운드 로그와 `controller-error.json`을 확인한다. 실패한 변경은 작업 트리에 남겨 검토할 수 있다. DONE의 실데이터 확인에는 `wsl -d AntiFlood-Probe -- sh scripts/launch.sh`로 준비한 대기 상태의 서버가 필요하다.

## 컨트롤러 라운드 2

- 시작 HEAD: b37743fa1140ed21ce773048fc0042562d88e1b1
- 상태: DONE
- 결과: 완료 조건 A1–A7을 현재 소스·Git 이력·기존 검증 기록과 대조했고, 추가 수정이 필요한 실제 결함은 확인하지 못했다. 제품 변경 없이 DONE 후보로 보고한다.
- 검증: 실행: 현재 서버 health 정상, simulation/state 대기 상태 확인. 저장 기록 재열기·설정 보존·PNG HTTP 200 확인. 코드에서 UI 제어·프레임 표시·WCA2D/OpenMP·입력 제한·실행기·Solar 읽기 전용 연결 확인. 첫 기록 조회는 PowerShell 배열 처리 오류로 실패한 뒤 명령을 수정해 성공했다. WSL 접근은 E_ACCESSDENIED로 실패했다. 미실행: 전체 검증 스크립트, 새 계산, 브라우저 렌더링. 기존 104프레임 실데이터 검증은 HISTORY의 과거 근거로만 참조했다. / 독립 컨트롤러: {"passed": ["A1", "A2", "A3", "A4", "A5", "A6", "A7"], "run_id": "504869473b214decac562940b75f3319", "bounds": [126.999, 37.499, 127.001, 37.501], "frames": 104, "last_frame": {"frame_source": "computed", "id": "504869473b214decac562940b75f3319_00103", "time": "2022-08-08T22:30:00Z", "rain_observed_at": "2022-08-08T22:29:00Z", "rain_interval_mm": [0.0], "rain_max_mm": 0.0, "max_depth_m": 3.0034755218192317, "active_tile_count": 6, "active_cell_count": 42, "cumulative_cell_updates": 834792, "worker_count": 2, "rain_m3": 14137.199999999979, "drain_m3": 1326.0563856496883, "boundary_outflow_m3": 0.0, "water_m3": 12811.143614350316, "mass_error_m3": 2.546585164964199e-11}, "point": {"tile_id": "1999_4445", "depth_m": 0.0, "time": "2022-08-08T22:30:00Z", "active": true, "rain": [{"station_id": "2402", "name": "반포펌프장", "mm": 0.0}]}, "launcher_reused_pid": "26", "limits": "UI wiring and HTTP flow checked; no fresh browser rendering or paid Solar response asserted"}

## 라운드 2 이후 재현한 대시보드 결함

라운드 2와 별도 실데이터 검증은 A1–A7을 확인했다. 그 실행 범위에 없던 다음 두 결함을 실제 `web/app.js` 함수와 이벤트 처리 코드를 실행하는 Node 재현으로 확인했다. GOAL의 기존 동작 범위에서 한 라운드에 하나씩 수정한다.

- A3 입력 복구. 스레드 값 0으로 영역 확인 요청이 422를 받으면 값을 4로 바로잡아도 시작 버튼을 다시 쓸 수 없다. 입력을 고친 뒤 유효한 영역에서 시작할 수 있어야 한다.
- A4 저장 결과 전환. 저장 결과 A를 요청한 뒤 B를 열 때 B가 먼저 응답하면 뒤늦게 도착한 A가 화면을 덮어쓴다. 마지막으로 요청한 결과가 화면에 남아야 한다.

재현 명령은 `node .ralph/runtime/dashboard-repro.cjs`다. 수정 전 두 경우 모두 실패했다. 테스트는 DOM과 응답 순서를 제어하고 기존 앱 코드를 실행한다. 어느 하나를 수정하면 그 항목의 PASS를 확인하고, 남은 항목은 다음 라운드로 넘긴다. 재현 파일은 로컬 런타임에 있다.

## 컨트롤러 라운드 3

- 시작 HEAD: 9dddfcfe93b4382e55f31844cbecb70055733ade
- 상태: CONTINUE
- 결과: A3 입력 복구 결함을 수정했다. 배수율·스레드·경계 변경 시 기존 영역 확인을 다시 실행해, 잘못된 값을 고친 뒤 시작할 수 있다. A4 저장 결과 전환 경쟁 문제는 다음 라운드에 남겼다.
- 검증: node .ralph/runtime/dashboard-repro.cjs: validationRecovery 수정 전 FAIL → 수정 후 PASS, historyRace는 여전히 FAIL. node --check web/app.js와 git diff --check 통과. 기존 서버 ready 확인. 전체 검증·새 계산·브라우저 렌더링은 실행하지 않았다.

## 컨트롤러 라운드 4

- 시작 HEAD: af271f14eb68baabb96593d3ec197547bd42c5ef
- 상태: CONTINUE
- 결과: A4 저장 결과 전환 경쟁 결함을 수정했어. 마지막 열기 요청만 화면에 반영하고, 실시간 복귀나 실행 조작 뒤 도착한 이전 응답은 무시해.
- 검증: node .ralph/runtime/dashboard-repro.cjs: 수정 전 historyRace FAIL, 수정 후 두 항목 PASS. 보완한 DOM 모형에서 화면·버튼 유지, 오래된 오류 무시, 실시간 복귀 후 요청 무효화 PASS. 초기 보완 검증은 모형의 closest() 누락으로 실패했고 보완 후 통과. node --check web/app.js와 git diff --check 통과. 서버 ready 확인. 전체 검증·새 계산·브라우저 렌더링은 미실행.

## 라운드 4 후 확인한 입력 복구 회귀

스레드·배수율·경계를 변경하면 영역의 강우 목록을 다시 받아 온다. 라운드 3 변경 이후 두 번째 시나리오를 선택한 상태에서 스레드를 4에서 8로 바꾸면 첫 번째 시나리오가 자동으로 선택된다. 기존 사용자가 고른 시나리오가 여전히 목록에 있을 때는 그대로 유지해야 한다. `node .ralph/runtime/dashboard-repro.cjs`에서 `settingsKeepScenario`가 실패하고 기존 두 항목은 통과하는 것을 확인했다. 다음 라운드에서 이 회귀를 수정한 뒤 독립 세션에서 완료 여부를 확인한다.

## 컨트롤러 라운드 5

- 시작 HEAD: 487accca3a66db9e91bebe0fedbe57783a9b2636
- 상태: CONTINUE
- 결과: A3 설정 변경 시 강우 시나리오 선택이 초기화되는 회귀를 수정했어. 새 목록에 기존 시나리오가 있으면 선택을 유지해.
- 검증: node .ralph/runtime/dashboard-repro.cjs: 수정 전 settingsKeepScenario FAIL, 수정 후 세 항목 모두 PASS. node --check web/app.js와 git diff --check 통과. 서버 ready 확인. 전체 검증·새 계산·브라우저 렌더링은 미실행.

## 컨트롤러 라운드 6

- 시작 HEAD: 9dceffb84cca56a75e272362311604ce4b149fdc
- 상태: DONE
- 결과: A1–A7을 현재 소스·Git 이력·기존 검증 기록과 대조했고, 추가 수정이 필요한 실제 결함은 확인하지 못했어. 변경 없이 DONE 후보로 보고해.
- 검증: 실행: node .ralph/runtime/dashboard-repro.cjs의 세 항목 모두 PASS. 서버 health 정상·ready, 저장 기록 재열기·설정 보존·PNG HTTP 200 확인. 최초 기록 조회는 PowerShell 배열 처리 오류로 실패했고 명령 수정 후 성공했어. 미실행: 전체 ralph-verify.py, 새 계산, WSL 실행기, 브라우저 렌더링. 작업 트리는 깨끗해. / 독립 컨트롤러: {"passed": ["A1", "A2", "A3", "A4", "A5", "A6", "A7"], "run_id": "aabb5f1a9bac41a2afde85946e559ab0", "bounds": [126.999, 37.499, 127.001, 37.501], "frames": 104, "last_frame": {"frame_source": "computed", "id": "aabb5f1a9bac41a2afde85946e559ab0_00103", "time": "2022-08-08T22:30:00Z", "rain_observed_at": "2022-08-08T22:29:00Z", "rain_interval_mm": [0.0], "rain_max_mm": 0.0, "max_depth_m": 3.0034755218192317, "active_tile_count": 6, "active_cell_count": 42, "cumulative_cell_updates": 834792, "worker_count": 2, "rain_m3": 14137.199999999979, "drain_m3": 1326.0563856496883, "boundary_outflow_m3": 0.0, "water_m3": 12811.143614350316, "mass_error_m3": 2.546585164964199e-11}, "point": {"tile_id": "1999_4445", "depth_m": 0.0, "time": "2022-08-08T22:30:00Z", "active": true, "rain": [{"station_id": "2402", "name": "반포펌프장", "mm": 0.0}]}, "launcher_reused_pid": "26", "limits": "UI wiring and HTTP flow checked; no fresh browser rendering or paid Solar response asserted"}

## 새 개선 명세 초기 설정 — 2026-11-25 KST

사용자가 전체 격자 지속 계산과 지역별 Adaptive Time Stepping, bounded-memory 강우 처리, G01–G16 완료 조건을 지정했다. 별도 개선 방향도 전달받았고 docs/DEVELOPMENT_SPEC.md에 정리했다. 실행 지침 원문은 docs/AUTONOMOUS_DEVELOPMENT.md에 보존했다. 이전 HTML 설계에는 대체 안내를 넣었다.

기존 5개 파일 변경은 사용자 로컬 커밋 승인에 따라 ralph/adaptive-time-stepping의 ac0b20d에 보존했다. 과거 GOAL/STATE/PROMPT는 runtime/pre-adaptive-*.md에 복사했다. 새 목표를 위해 STATE의 이전 DONE과 라운드 수를 초기화했다. 기본 6라운드, 900초/라운드, 5400초/실행, 최대 2회 시도를 유지하며 원격 푸시는 승인받지 않았다.

읽기 전용 search-first 조사에서 기존 Tile 집계, OpenMP/WCA2D, 10분 저장과 RMSE/IoU 비교를 재사용할 수 있음을 확인했다. 전체 강우 상주는 data.load_scenarios와 Scenario.intervals에서 발생한다. 기존 유출 부피의 비례 재사용에는 안전 근거가 없다. Sliding Window는 현재 UI에 용도가 있으므로 명확히 구분해 정리한다. 현재 목표의 구현과 성능은 아직 검증하지 않았다.

## 컨트롤러 라운드 1

- 시작 HEAD: d159f2628e9fc4a79fba46c20ffd604a1d85a996
- 상태: CONTINUE
- 결과: G02·G03: 위험도 선택 분기를 제거하고 모든 유효 셀의 수평 유동을 매 단계 계산하도록 변경했어. G01: 기존 Reference 커널과 시간 간격을 보존했고 작은 격자에서 시작 HEAD와 결과가 일치했어. 계산 정책·마지막 간격 저장과 표시도 추가했어. G04–G16의 최종 검증은 남아 있으며, 특히 강우 스트리밍과 지역별 다중 주기는 미구현이야. 다음 작업은 Scenario·Replay·비교 해시의 전체 강우 보관 제거야.
- 검증: 39셀 직렬 네이티브 시험에서 닫힌·열린 경계, 질량 보존, 비음수·유한값, 무강우 지역 유입, 강우 종료 후 이동·배수, 공통 시각을 확인했어. 최대 수량 오차 약 2.14e-14 m³, 시작 HEAD Reference 대비 수심 배열 일치. Python 구문·JS 구문·git diff --check 통과. 증거: .ralph/runtime/round1-full-grid.json, 재개 기록·명령·G별 상태: .ralph/runtime/round1-status.json. WSL은 E_ACCESSDENIED로 재시도하지 않았고, Windows Rasterio DLL 차단·libgomp 부재로 데이터 로더를 격리한 직렬 시험만 수행했어. 실데이터·OpenMP·브라우저·성능·최종 독립 검증은 미실행. 외부 확인 명령(저장소 루트): wsl -d AntiFlood-Probe -- sh -lc '~/.venvs/antiflood/bin/python scripts/check-full-grid.py'. 기존 서버·원본·저장 결과·보호 파일은 변경하지 않았어.

## 컨트롤러 라운드 2

- 시작 HEAD: ef021467a7f38d80768a59b5401d57cf289dd0ad
- 상태: CONTINUE
- 결과: G04 강우 스트리밍을 구현했어. Scenario의 전체 강우 보관을 제거하고, 시나리오 목록·Replay·비교 해시를 순차 읽기로 바꿨어. 처리한 입력 참조는 저장 후 해제하며, UI용 최근 60분 합계는 별도 복사본으로 유지해. G01–G03은 보존했고, G05의 주기 결정 활용과 G06–G07 다중 주기·경계 처리는 미완료야. G01–G16별 근거와 다음 작업은 .ralph/runtime/round2-status.json에 기록했어.
- 검증: 실제 47개 관측소 139구간과 반포 관측소 286구간이 시작 HEAD의 강우·시각·시나리오 목록과 일치했어. 6셀·2구간 직렬 네이티브 Replay에서 Reference 일치, 질량·공통 저장 시각, 입력 참조 해제와 중단 시 reader 닫기를 확인했어. 구문 검사와 git diff --check 통과. 증거: .ralph/runtime/round2-rain-stream.json. 재현: .venv/Scripts/python.exe .ralph/runtime/round2-check.py. Rasterio 관련 코드는 격리했으며 OpenMP·실서버·브라우저·성능·최종 독립 검증은 미실행이야. WSL은 E_ACCESSDENIED로 재시도하지 않았어. 외부 확인 명령: wsl -d AntiFlood-Probe -- sh -lc '~/.venvs/antiflood/bin/python scripts/check-rain-stream.py'. 원본·기존 결과·보호 파일과 서버는 변경하지 않았어.

## 컨트롤러 라운드 3

- 시작 HEAD: 1ec91afc1889a69211f7b5e5c2028a06748e2694
- 상태: CONTINUE
- 결과: G05–G07의 첫 구현으로, 물이 도달할 수 없는 건조 Tile은 30·60초마다 계산하고 나머지는 기존 CFL 주기로 계산하도록 바꿨어. 모든 Tile을 공통 시각에 동기화하고 실제 주기를 저장해. Reference는 보존했어. G01–G09·G11·G15–G16은 추가 검증이 필요하고, G10·G12–G14는 미완료야. G별 근거와 다음 작업은 .ralph/runtime/round3-status.json에 남겼어.
- 검증: 539셀 직렬 네이티브 시험에서 질량·비음수·유한값·경계·공통 시각과 436회의 주기 간 경계 유량 검사를 통과했어. 최대 질량 오차 2.73e-12m³, Reference 대비 최대 RMSE 0.00241m였으며 허용 기준은 확정하지 않았어. 셀 연산은 줄었지만 실행 시간 개선은 입증하지 못했어. 실제 47개 관측소 강우 3구간을 합성 격자에 적용했을 때 Reference는 시작 HEAD와 일치했고, 개선 방식의 계산량 절감은 없었어. 증거: .ralph/runtime/round3-regional.json, round3-actual-rain.json. 재현: .venv/Scripts/python.exe .ralph/runtime/round3-check.py. 구문 검사와 git diff --check 통과. WSL은 E_ACCESSDENIED, OpenMP는 libgomp 부재로 미검증이야. 다음은 준비된 WSL에서 scripts/check-regional.py 실행 후 짧은 실제 DEM 입력으로 적용 범위와 4스레드 성능을 확인하는 작업이야. 브라우저·서울 전체 비교·최종 독립 검증은 미실행이며 서버·원본·기존 결과·보호 파일은 보존했어.

## 컨트롤러 라운드 4

- 시작 HEAD: 99cfe91e78c4782095fea4b1ca3343c4cd302248
- 상태: CONTINUE
- 결과: G06–G07: 긴 계산 주기를 건조 Tile에서 유출 임계값에 도달하지 않는 얕은 물까지 확장했어. 기존 WCA2D와 Reference는 보존했고, 저장 메타데이터가 실제 계산 정책을 기록하도록 고쳤어. G01–G09·G11·G15–G16은 추가 검증, G10·G12–G14는 미완료야. G별 근거와 다음 작업은 .ralph/runtime/round4-status.json에 기록했어.
- 검증: 직렬 네이티브 시험에서 질량·비음수·유한값·경계·공통 시각·임계값 전환을 확인했어. 최대 질량 오차 3.30e-12m³. 실제 47개 관측소 강우 3구간을 합성 격자에 적용하면 셀 연산은 64800→16200회, 최대 RMSE는 2.12e-19m였어. 격리 Replay의 저장·입력 해제·reader 닫기, Python 구문 검사와 git diff --check도 통과했어. 증거는 .ralph/runtime/round4-{regional,cutoff,actual-rain,replay}.json, 재현 명령은 round4-status.json에 있어. WSL은 E_ACCESSDENIED로 한 번 실패해 재시도하지 않았어. 실제 DEM·OpenMP·실행 시간 개선·브라우저·최종 독립 검증은 미확인이야. 다음은 저장소 루트에서 wsl -d AntiFlood-Probe -- sh -lc '~/.venvs/antiflood/bin/python scripts/check-regional.py' 실행 후 짧은 실제 DEM의 4스레드 확인이야. 서버·원본·기존 결과·보호 파일은 보존했어.
