# 현재 상태

- 상태: CONTINUE
- 완료 라운드: 1
- 결과: G02·G03: 위험도 선택 분기를 제거하고 모든 유효 셀의 수평 유동을 매 단계 계산하도록 변경했어. G01: 기존 Reference 커널과 시간 간격을 보존했고 작은 격자에서 시작 HEAD와 결과가 일치했어. 계산 정책·마지막 간격 저장과 표시도 추가했어. G04–G16의 최종 검증은 남아 있으며, 특히 강우 스트리밍과 지역별 다중 주기는 미구현이야. 다음 작업은 Scenario·Replay·비교 해시의 전체 강우 보관 제거야.
- 검증: 39셀 직렬 네이티브 시험에서 닫힌·열린 경계, 질량 보존, 비음수·유한값, 무강우 지역 유입, 강우 종료 후 이동·배수, 공통 시각을 확인했어. 최대 수량 오차 약 2.14e-14 m³, 시작 HEAD Reference 대비 수심 배열 일치. Python 구문·JS 구문·git diff --check 통과. 증거: .ralph/runtime/round1-full-grid.json, 재개 기록·명령·G별 상태: .ralph/runtime/round1-status.json. WSL은 E_ACCESSDENIED로 재시도하지 않았고, Windows Rasterio DLL 차단·libgomp 부재로 데이터 로더를 격리한 직렬 시험만 수행했어. 실데이터·OpenMP·브라우저·성능·최종 독립 검증은 미실행. 외부 확인 명령(저장소 루트): wsl -d AntiFlood-Probe -- sh -lc '~/.venvs/antiflood/bin/python scripts/check-full-grid.py'. 기존 서버·원본·저장 결과·보호 파일은 변경하지 않았어.
- 시작 체크포인트: d159f2628e9fc4a79fba46c20ffd604a1d85a996
- 최신 체크포인트: 이 파일을 담은 HEAD (`git rev-parse HEAD`)
- 다음 행동: 다음 독립 세션에서 가장 중요한 미완성 항목을 확인한다.
- 이번 실행 로그: `.ralph/runtime/run-1795577539881292900`
- 실제 복구 해시: `.ralph/runtime/checkpoints.json`. 작업 브랜치: ralph/adaptive-time-stepping
