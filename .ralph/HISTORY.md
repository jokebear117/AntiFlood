# Ralph 실행 기록

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
