# 현재 상태

- 상태: CONTINUE
- 완료 라운드: 4
- 결과: G06–G07: 긴 계산 주기를 건조 Tile에서 유출 임계값에 도달하지 않는 얕은 물까지 확장했어. 기존 WCA2D와 Reference는 보존했고, 저장 메타데이터가 실제 계산 정책을 기록하도록 고쳤어. G01–G09·G11·G15–G16은 추가 검증, G10·G12–G14는 미완료야. G별 근거와 다음 작업은 .ralph/runtime/round4-status.json에 기록했어.
- 검증: 직렬 네이티브 시험에서 질량·비음수·유한값·경계·공통 시각·임계값 전환을 확인했어. 최대 질량 오차 3.30e-12m³. 실제 47개 관측소 강우 3구간을 합성 격자에 적용하면 셀 연산은 64800→16200회, 최대 RMSE는 2.12e-19m였어. 격리 Replay의 저장·입력 해제·reader 닫기, Python 구문 검사와 git diff --check도 통과했어. 증거는 .ralph/runtime/round4-{regional,cutoff,actual-rain,replay}.json, 재현 명령은 round4-status.json에 있어. WSL은 E_ACCESSDENIED로 한 번 실패해 재시도하지 않았어. 실제 DEM·OpenMP·실행 시간 개선·브라우저·최종 독립 검증은 미확인이야. 다음은 저장소 루트에서 wsl -d AntiFlood-Probe -- sh -lc '~/.venvs/antiflood/bin/python scripts/check-regional.py' 실행 후 짧은 실제 DEM의 4스레드 확인이야. 서버·원본·기존 결과·보호 파일은 보존했어.
- 시작 체크포인트: 99cfe91e78c4782095fea4b1ca3343c4cd302248
- 최신 체크포인트: 이 파일을 담은 HEAD (`git rev-parse HEAD`)
- 다음 행동: 다음 독립 세션에서 가장 중요한 미완성 항목을 확인한다.
- 이번 실행 로그: `.ralph/runtime/run-1795577539881292900`
- 실제 복구 해시: `.ralph/runtime/checkpoints.json`. 작업 브랜치: ralph/adaptive-time-stepping
