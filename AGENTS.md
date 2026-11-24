# AntiFlood 개발 지침

모든 개발 작업을 시작하기 전에 [개발 원칙](docs/DEVELOPMENT_PRINCIPLES.md)을 읽고 프로젝트의 목적과 원칙을 준수한다. 이 문서는 구현의 단순성, 사용자 중심 설계, 자율적 개선, 필요한 범위의 검증, 기술적 정직성, 문서 품질을 판단하는 장기 기준이다.

작업 전 `git status`를 확인하고 기존 변경을 보존한다. 명시적인 사용자 요구사항과 기존의 유효한 프로젝트 제약을 지키며, 작업 범위 안에서 문제를 발견하고 개선한다. 현재 동작은 관련 코드와 데이터로 확인한다. 목표 달성에 필요한 변경과 검증을 마치면 작업을 종료한다.

필요에 따라 [실행 안내](docs/RUNNING.md), [시스템 아키텍처](docs/ARCHITECTURE.md), [구현 결정과 검증](docs/DECISIONS.md), [데이터 출처와 범위](Dataset/README.md)를 확인한다.

Ralph 실행은 `python scripts/ralph-loop.py`를 사용한다. 시작 전에 `.ralph/GOAL.md`, `STATE.md`, `PROMPT.md`, `HISTORY.md`를 읽는다. `ralph/` 브랜치에서 작업하며 완료 조건은 유지한다. 커밋·푸시는 외부 컨트롤러가 변경 파일을 검토한 뒤 수행한다. 상세 실행 결과와 복구 해시는 `.ralph/runtime/`에 보관한다.

## README 유지 관리

루트 `README.md`를 작성하거나 수정하기 전에 [README 작성 및 유지 규칙](docs/README_RULES.md)을 반드시 읽고 준수한다.

섹션 구성, 프로젝트 주제 문장, 문체, 시각적 표현 방식은 사용자가 확정한 문서 규격이다. 이 규격을 변경하려면 사용자 승인을 받는다.

구현 변경으로 README를 갱신할 때는 관련 내용만 수정하고 나머지 본문은 보존한다.
