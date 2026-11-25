# 독립 Ralph 개발 라운드

AGENTS.md, docs/DEVELOPMENT_PRINCIPLES.md, docs/DEVELOPMENT_SPEC.md, docs/AUTONOMOUS_DEVELOPMENT.md와 .ralph/GOAL.md, STATE.md, HISTORY.md를 읽는다. 이전 완료 기록은 과거 선택적 영역 계산 검증이다. 새 G01–G16에 재사용 가능한 근거와 새 검증이 필요한 부분을 구분한다.

ANALYZE → SELECT → IMPLEMENT → VERIFY → RECORD 순으로 가장 중요한 미완료 요구사항을 실제 코드로 해결한다. 후속 라운드는 STATE와 HISTORY를 사용해 필요한 코드만 읽는다. 핵심 물리, 강우 스트리밍, 경계 안전성, 계산량과 정확성, API와 대시보드, 문서 순으로 진행한다. 전체 격자 지속 계산과 Reference 보존을 우선한다. 위험도 선택의 이름만 바꾸거나 과거 유출 부피에 dt 비율만 곱하는 근거 없는 구현은 요구를 충족하지 않는다.

기존 NumPy, 표준 라이브러리, C++와 OpenMP, Tile 묶음, 결과 저장과 비교를 재사용한다. 초기 search-first 조사: Scenario.intervals와 load_scenarios의 values가 전체 강우를 보관한다. Replay와 comparison.run_conditions도 함께 바꿔야 한다. Sliding Window에는 현재 UI 용도가 있으므로 제거 시 관련 표시도 실제 구현과 맞춘다. Reference는 이미 최대 15초 가변 간격이다. 실제 셀 연산량과 동일 자원의 실행 시간을 따로 확인한다.

작은 격자에서 질량, 비음수, 유한값, 경계 유량, 공통 시각부터 검증한 뒤 실제 입력을 확인한다. 구현 확정 전 서울 전체 벤치마크를 반복하지 않는다. 후보 2~3개와 4스레드 및 추가 1~2개 설정 예산을 따른다. 정확성 허용 한도를 임의로 확정하지 않는다. 실제 입력·설정·명령·결과 파일 위치를 남긴다. 미실행 브라우저와 측정을 통과로 표시하지 않는다. 최종 독립 검증의 증거 계약은 scripts/ralph-verify.py 모듈 설명을 따른다. 그 증거는 실제 수행한 확인으로만 작성한다.

WSL은 AntiFlood-Probe와 ~/.venvs/antiflood를 사용한다. 8000 포트의 서버 상태를 먼저 확인하고 기존 실행 중 계산은 중단하지 않는다. 소스 변경 후 서버를 갱신해야 한다면 대기 상태를 확인해 해당 프로젝트 서버만 갱신한다. 원본과 저장 결과를 보존한다. WSL 명령은 저장소 루트에서 실행한다. Windows Launch.cmd와 WSL 경로를 유지한다. CLI 셸 자체가 WSL을 거절하면 반복하지 말고 외부 컨트롤러가 확인할 명령과 미검증 부분을 보고한다.

GOAL, PROMPT, 컨트롤러, 독립 검증 스크립트, AGENTS, .gitignore, 두 사용자 명세는 보호 파일이다. 라운드에서 수정하지 않는다. STATE와 HISTORY도 읽기 전용이며 컨트롤러가 기록한다. Git 커밋·푸시·브랜치 전환·배포는 하지 않는다. 기존 사용자 변경은 ac0b20d에 보존되어 있다. 새 연구와 무관한 디자인 변경, 비밀·인증 파일 조회, 한도 및 승인 절차 완화는 하지 않는다.

라운드 종료 summary와 verification에는 실제 변경, G별 상태와 근거, 다음 작업을 담는다. 컨트롤러가 STATE와 HISTORY에 남기므로 재개 가능한 경로와 명령을 포함한다. 최종 JSON은 status(CONTINUE/DONE/BLOCKED/FAILED), summary, changed_files(상대 경로), verification, failure_reason 필드를 쓴다. 진행 가능한 미완료 작업이 있으면 CONTINUE, 근본적인 장애만 BLOCKED로 보고한다. 핵심 알고리즘이 미구현이면 DONE으로 응답하지 않는다.

CONTINUE와 DONE의 failure_reason은 빈 문자열로 쓴다. 진행을 막지 않는 환경 제한과 미실행 검증은 verification에 기록한다. failure_reason에 값이 있으면 컨트롤러는 해당 라운드를 실패로 거절한다. BLOCKED와 FAILED일 때만 실제 중단 원인을 그 필드에 기록한다.
