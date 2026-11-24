# 독립 Ralph 라운드

AGENTS.md와 docs/DEVELOPMENT_PRINCIPLES.md를 먼저 읽고 `.ralph/GOAL.md`, STATE.md, HISTORY.md, 현재 소스와 Git 이력을 확인한다. 이 세션은 외부 컨트롤러가 시작한 새 Codex CLI 라운드다.

ANALYZE → SELECT → IMPLEMENT → VERIFY 순으로 기존 완료 조건을 대조한다. 가장 중요한 실제 미완성 항목 하나만 수정한다. 기존 구현이 완료되어 있으면 추가 제품 작업 없이 DONE 후보로 보고한다. 기존 기능을 찾기 전에 미구현이라고 판단하지 않는다.

검증은 필요한 최소 범위로 수행하고 실행·미실행·실패를 구분한다. 컨트롤러는 DONE 후보에 대해 `scripts/ralph-verify.py`를 별도로 실행하므로 같은 전체 검증을 반복할 필요는 없다. 서버 상태를 읽을 수 있으나 기존 계산·원본 Dataset·기존 결과는 보존한다. WSL은 AntiFlood-Probe와 ~/.venvs/antiflood를 사용한다. 8000 포트의 준비된 서버를 재사용한다.

변경은 저장소 안의 관련 파일에 제한한다. GOAL, 컨트롤러, 검증 스크립트, AGENTS, .gitignore는 이 라운드에서 수정하지 않는다. Git 커밋·푸시·브랜치 변경·배포는 외부 컨트롤러가 담당한다. 사용자 변경이나 보호 브랜치를 건드리지 않는다. 비밀 값과 인증 파일은 읽거나 기록하지 않는다.

STATE와 HISTORY는 읽기 전용이다. 컨트롤러가 라운드 결과와 시작 HEAD를 기록하고 검증을 통과한 변경을 로컬에 커밋한다. 계산·설정·결과 조회 등 기존 사용자 흐름에서 재현되는 결함을 우선한다. 변경했다면 관련 동작을 직접 검증한 뒤 CONTINUE로 보고해 다음 독립 세션에서 남은 일을 판단하게 한다. 관련 코드와 검증 명령은 결과에 간결히 남긴다.

최종 응답은 제공된 JSON Schema에 맞춘다. status는 CONTINUE/DONE/BLOCKED/FAILED 중 하나, summary는 실제 결과, changed_files는 이번 작업 파일의 상대 경로 배열, verification은 실행 근거, failure_reason은 실패 원인(없으면 빈 문자열)이다. 완료 조건 변경이나 새 요구사항 추가로 반복을 연장하지 않는다.
