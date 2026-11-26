# 현재 상태

- 상태: FAILED
- 완료 라운드: 5
- 실행 결과: 자동 컨트롤러는 4라운드까지 커밋한 뒤 5라운드의 CONTINUE와 비어 있지 않은 failure_reason 조합을 거절했다. 5라운드 변경은 외부 담당 세션이 검토하고 보존했다. 여섯 번째 CLI 세션과 새 루프는 시작하지 않았다. 완료 라운드 5는 시도한 작업과 외부 검토를 포함하며 자동 합격을 뜻하지 않는다.
- 제품 상태: 미완료. 첫 서울 전역 비교에서 계산량은 줄었지만 계산 시간은 늘었다. 전체 DONE 조건을 충족하지 않았다.
- 작업 브랜치: ralph/adaptive-time-stepping. 원격 푸시와 배포는 하지 않았다.
- 기존 변경 보존: ac0b20d. 준비 설정: d159f26. 마지막 자동 체크포인트: 96e32c5f47e230641c6d292ad81af8bbafe5a46d. 최신 외부 검토 체크포인트는 이 파일을 담은 HEAD이며 실제 해시는 runtime/checkpoints.json에 기록한다.
- 결정과 측정의 본문: docs/DECISIONS.md 12절. 사용자 명세와 G01–G16은 유지했다.

| 조건 | 상태 | 근거와 남은 범위 |
| --- | --- | --- |
| G01 | VERIFIED | 원래 C++ 커널과 Reference 시간 규칙 보존, 시작 HEAD 대비 작은 입력 일치, 공통 시각 검사 |
| G02 | VERIFIED | 모든 Tile의 양수 계산 간격, 서울 전역 139프레임의 전체 격자와 동기 시각 확인 |
| G03 | VERIFIED | 위험도 선택 분기 제거. 물리적 무유량 조건에서도 최대 60초마다 모든 셀 계산 |
| G04 | VERIFIED | 실제 47관측소·139구간 입력 일치, 이전 배열 해제, Replay reader 종료와 입력 참조 해제 |
| G05 | VERIFIED | 0.8 감쇠를 짧은 주기의 보조 조건으로 사용. 물을 제거하지 않음 |
| G06 | VERIFIED | 15초 이하의 CFL 주기와 최대 60초의 지역별 주기가 실제로 동작. 적용 범위는 무유입·유동 기준 미만 Tile |
| G07 | IN_PROGRESS | 경계·수량·비음수·유한값·시각 검사 통과. Reference 오차의 최종 허용 판단은 미확정 |
| G08 | VERIFIED | 기존 OpenMP 엔진의 실제 2·4작업자와 대시보드 4스레드 실행 확인. 추가 스레드 성능 비교는 G12에 남음 |
| G09 | VERIFIED | 서울 전역 139개 10분 프레임, 모든 Tile의 같은 물리 시각, 전체 원래 격자 크기 확인 |
| G10 | VERIFIED | Edge의 실제 수심·간격 레이어·비교 성능·시간 이동 확인. 원본 이미지와 구분해 이전 방식 제목 유지 |
| G11 | VERIFIED | 브라우저 시작·정지·재개·187프레임 완료·초기화·저장 결과 재열기·설정 재사용, 과거 결과 조회 확인 |
| G12 | IN_PROGRESS | 실제 동일 자원 1회 비교 완료. 개선 시간 141.083초, Reference 76.329초로 성능 목표 미달. 반복 중앙값·추가 스레드는 미확인 |
| G13 | IN_PROGRESS | README의 고정 5섹션과 주제 문장은 유지했으나 이전 알고리즘 설명을 새 구현에 맞춰 갱신해야 함 |
| G14 | PENDING | 아키텍처 이미지와 관련 문서의 이전 선택적 방식 설명 갱신 필요 |
| G15 | IN_PROGRESS | WSL 실행기와 서버 재사용 확인, Launch.cmd 연결 보존. Windows 실행기 직접 실행은 미확인 |
| G16 | VERIFIED | 기존 8849개 원본·저장 파일의 경로·크기·수정 시각 변화 없음. 전체 내용 해시 검사는 아님 |

## 증거와 재개

- 실행 로그: .ralph/runtime/run-1795577539881292900/
- 실패 응답 원문: 위 폴더의 round-5.json, .ralph/runtime/controller-error.json. 원문을 바꿔 합격 처리하지 않았다.
- 서울 비교: .ralph/runtime/outer-benchmark-4-1-{reference,streaming}.json. Reference 87b9af0a1dba4ac58bed551b6c9291de, 개선 방식 e17aa02ffe86431a983246a8c0051d08. 동일 입력·소스 해시와 측정 범위는 JSON과 DECISIONS 12절 참조.
- 입력·시각·안전성: outer-round2-real-stream.json, outer-round4-regional.json, outer-final-reference-clock.json, outer-final-stream-check.json, outer-full-seoul-clocks.json.
- 브라우저: outer-ui-{before,running,comparison,periods,narrow,final}.jpg, outer-ui-run.json. 좁은 화면은 390×844, 기본 화면은 기존 1432×768이었다. 뷰포트는 복원했다.
- 보존 확인: outer-preservation.json. 기존 파일과 다른 포트의 서버는 유지했으며 현재 8000 서버는 ready, run_id 없음.
- 선택 결과: 대시보드 저장 결과의 서울 전역 / 비교 (e17aa0). Launch.cmd 또는 http://127.0.0.1:8000 으로 연다.
- 다음 행동: 우선 NumPy 이웃 의존 범위 관리의 비용과 전체 짧은 주기 영역의 불필요한 분류 비용을 줄일 수 있는지 확인한다. 물리 조건을 완화하거나 위험도 제외를 되살리지 않는다. 변경 후 작은 검사와 같은 자원의 실제 비교를 수행하고, 구현 확정 뒤 반복·추가 스레드 측정과 문서·이미지를 마친다.
- 환경: 독립 CLI에서는 WSL E_ACCESSDENIED와 Windows DLL 제한이 있었지만 외부 담당 세션의 WSL·기존 OpenMP·CMake는 정상 동작했다. 환경을 재설치하거나 보안 정책을 바꾸지 않았다.
- 재개는 새 사용자 실행 지시 후 진행한다. 원래 6개 CLI 세션 예산에서 남은 한 세션만 이어가려면 깨끗한 현재 브랜치에서 python scripts/ralph-loop.py --max-rounds 1 --max-seconds 900 을 사용한다. 기본 한도를 확대하거나 자동 재시작하지 않는다.
