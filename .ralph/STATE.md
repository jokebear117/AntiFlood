# 현재 상태

- 상태: CONTINUE
- 완료 라운드: 0
- 목표: 전체 격자 지속 계산, 순차 강우 입력과 요약, 지역별 적응형 주기, 보존적 경계 전달, 실제 비교 및 UI와 문서.
- G01: PENDING. 기존 Reference 분기는 확인했으나 새 변경 후 보존 여부 검증 전이다.
- G02–G07: PENDING. 현재 위험도 선택, 전체 강우 보관, 다중 주기 경계 미구현이다.
- G08–G11: PENDING. 기존 실행·OpenMP·10분 저장·대시보드는 있으나 새 연결과 검증이 필요하다.
- G12: PENDING. 기존 선택적 방식의 측정을 재사용하지 않는다.
- G13–G14: PENDING. 구현 후 고정 README 구조를 지키며 문서와 아키텍처 이미지를 갱신한다.
- G15–G16: PENDING. Windows/WSL 경로와 기존 자료를 유지하고 최종 확인한다.
- 보존 체크포인트: ac0b20d (승인받은 기존 5개 파일의 전용 브랜치 로컬 커밋).
- 이전 GOAL/STATE/PROMPT 사본: .ralph/runtime/pre-adaptive-*.md. 과거 HISTORY는 보존했다.
- 다음 행동: 전체 격자 지속 계산과 Reference를 보존하는 최소 변경부터 구현한다. 강우 소유 구조는 data.load_scenarios, Scenario.intervals, Replay, comparison.run_conditions를 함께 점검한다.
- 실행: python scripts/ralph-loop.py. 기본 6라운드·900초/라운드·5400초/실행·최대 2회 시도. 자동 새 실행과 원격 푸시 금지.
