# RS 프로젝트

한국 주식시장(KOSPI, KOSDAQ, KRX)의 상대강도(RS) 지표를 계산하는 프로젝트.

## 작업 규칙

- **main 브랜치에 직접 push 금지.** 모든 변경은 별도 브랜치에서 PR을 통해 진행한다.

## 현재 상태

### PR 현황

| PR | 작업 | 브랜치 | 상태 |
|----|------|--------|------|
| PR-1 | py 파일 중복 제거 → 공통 모듈 분리 | `refactor-dedup` | **머지 완료** ([#7](https://github.com/dalinaum/rs/pull/7)) |
| PR-2 | 종목별 캔들차트 페이지 생성 | `add-inline-charts` | **리뷰 대기** ([#8](https://github.com/dalinaum/rs/pull/8)) |
| PR-3 | 테이블 가시성 개선 | `improve-table-ux` | **리뷰 대기** ([#9](https://github.com/dalinaum/rs/pull/9)) |
| PR-4 | RS 분포 히스토그램 차트 추가 | `add-rs-chart` | **닫힘** ([#10](https://github.com/dalinaum/rs/pull/10)) — 불필요한 기능으로 판단 |

PR-2, PR-3 모두 `main` base. PR-1 머지 후 병렬 작업 완료.

**머지 순서 주의**: PR-2, PR-3은 모두 `rs_calculator.py`를 다르게 수정했으므로 머지 시 **충돌 해결 필요**. 권장 순서: PR-3 → PR-2 (충돌 범위가 작은 것부터).

### 에이전트 구조
- **메인**: Claude Code (플래닝, 작업 분배, 조율)
- **서브**: `worker` 에이전트 (`.claude/agents/worker.md`)
- 각 worker는 별도의 git worktree에서 독립 작업 → PR 생성 → 사용자 검수

### Worktree 현황
- `rs-worktree-2` → `add-inline-charts` (PR-2)
- `rs-worktree-3` → `improve-table-ux` (PR-3)
- `rs-worktree-4` → `add-rs-chart` (PR-4, 닫힘)

---

## 작업 중 발견한 이슈

### Worker 에이전트 권한 문제
- 백그라운드 worker는 도구 승인 팝업을 띄울 수 없음
- `.claude/settings.local.json`에 `Read`, `Edit`, `Write`, `Bash(git:*)` 등을 미리 allow 해야 함
- `settings.local.json`은 `.gitignore`에 추가됨 (개인 설정, 커밋 방지)
- **그래도 Bash는 worker에서 거부됨** — 커밋은 메인 에이전트가 대신 수행해야 함

### 코드 품질 이슈 (기존 코드)
- `quater` 변수명 오타 → `quarter`가 맞음
- `sorted` 변수명이 Python 내장 함수 `sorted()`를 가림 (shadowing)
- `rs_df[na_index]['RankChange'] = -1` (line 176) — pandas chained assignment, 실제 동작 안 할 수 있음 (`.loc` 사용해야 함)

### PR별 리뷰 포인트
- **PR-2**: `generate_chart_html()`이 종목당 calc_score()를 ~252번 호출 → KOSPI ~900종목이면 약 23만 회 호출. 성능 검증 필요.
- **PR-2**: `c(code)` 함수가 상대 경로 `charts/{code}.html`을 반환 → Jekyll permalink 구조에서 정상 동작하는지 확인 필요
- **PR-3**: Close1, Close2에 `{:,}` 포맷 적용 → float 값이면 `1,234.0` 형태가 될 수 있음. `int()` 변환 확인 필요
### PR-4 폐기 사유
- RS 분포 히스토그램은 실제 사용 시 유용하지 않은 기능으로 판단됨
- AI 에이전트가 사용자의 명시적 확인 없이 기능을 제안·구현한 사례 → `verify-before-build.md` 참고

---

## 추가 개선 아이디어

### 성능
- [ ] PR-2의 차트 생성 시 RS 시계열 계산을 벡터화하거나 캐싱
- [ ] `pd.concat` 루프를 리스트 append 후 한 번에 DataFrame 생성으로 변경 (현재 매 종목마다 concat)

### 기능
- [ ] 종목 검색 기능 (JavaScript로 테이블 필터링)
- [ ] RS 순위 변화 추이 (일주일/한달 단위)
- [ ] 업종별 RS 분석 (섹터별 강도)
- [ ] 차트 페이지에서 다음 금융/네이버 금융 외부 링크 추가 (PR-2에서 제거된 링크 보완)

### 인프라
- [ ] GitHub Actions로 자동 실행 (현재 수동)
- [ ] 기본 테스트 추가 (`calc_score`, `run_market_analysis` 단위 테스트)
- [ ] `quater` → `quarter` 오타 수정, `sorted` 변수명 변경 등 코드 정리 PR

---

## 참고

### 개선 계획 상세
`.claude/plans/improvement-plan.md`

### 설정 파일
- `.claude/settings.local.json` — worker 에이전트 도구 권한 (gitignore됨)
- `.claude/agents/worker.md` — worker 에이전트 정의
