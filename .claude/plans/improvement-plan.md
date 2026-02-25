# RS 프로젝트 개선 계획

## 현황 분석

### 파일 구조
- `rs_calculator.py` - 공통 모듈 (PR-1에서 생성, PR-2/3/4에서 각각 수정)
- `calc-kospi-rs.py` - KOSPI 처리 (5줄, rs_calculator 호출)
- `calc-kosdaq-rs.py` - KOSDAQ 처리 (5줄, rs_calculator 호출)
- `calc-krx-rs.py` - KRX 처리 (5줄, rs_calculator 호출)
- `docs/charts/` - 종목별 차트 HTML (PR-2, 런타임 생성)
- `docs/_posts/` - 날짜별 마크다운 포스트

---

## 완료된 작업

### PR-1: py 파일 중복 제거 ✅ (머지됨)
- **PR**: [#7](https://github.com/dalinaum/rs/pull/7)
- `rs_calculator.py` 공통 모듈 생성 (286줄)
- `calc-kospi-rs.py`, `calc-kosdaq-rs.py`, `calc-krx-rs.py` → 각 5줄로 단순화
- `DATA/` 디렉토리 `.gitignore` 추가

### PR-2: 종목별 캔들차트 페이지 생성 ✅ (리뷰 대기)
- **PR**: [#8](https://github.com/dalinaum/rs/pull/8)
- **worktree**: rs-worktree-2, **브랜치**: add-inline-charts
- `generate_chart_html()` 함수 추가 (270줄)
  - TradingView Lightweight Charts v4 (CDN)
  - 캔들차트 + MA50(파란)/MA150(주황)/MA200(빨간) 오버레이
  - RS 점수 추이 라인차트 (하단)
  - 두 차트 시간축 동기화, 반응형
- 라이트 테마 적용 (배경 #ffffff, 텍스트 #333333)
- masthead(#93c7c4, 사이트 타이틀) + toolbar(종목명, 범례) 헤더 구조
- `c(code)` 함수: `finance.daum.net` → `/charts/{code}.html` 절대 경로로 변경
- `.gitignore`에 `docs/charts/*.html` 추가
- `docs/charts/.gitkeep` 생성
- Jekyll 로컬 테스트로 차트 링크 정상 동작 확인 완료

### PR-3: 테이블 가시성 개선 ✅ (머지 완료)
- **PR**: [#9](https://github.com/dalinaum/rs/pull/9)
- **worktree**: rs-worktree-3, **브랜치**: improve-table-ux (삭제됨)
- RS 변화량 이모지: 🔺(상승), 🔻(하락), ▬(변화없음)
- RS 포스트에 1년 수익률 컬럼 추가 (`+123.4%` 형식)
- 가격에 천단위 구분자 (`19320` → `19,320`)
- 트렌드 템플릿에도 이모지 + 천단위 구분자 적용

### PR-4: RS 분포 히스토그램 차트 추가 ❌ (폐기)
- **PR**: [#10](https://github.com/dalinaum/rs/pull/10) — 닫힘
- 실제 사용 시 유용하지 않은 기능으로 판단되어 폐기
- 사용자가 필요성을 확인하기 전에 구현이 진행된 사례
- 교훈: `verify-before-build.md`

---

## 머지 전략

**PR-3 머지 완료.** PR-2 머지 시 `rs_calculator.py` 충돌 해결 필요.

**남은 머지:**
1. **PR-2** (캔들차트) — 사용자 리뷰 후 머지. main에 rebase하여 PR-3 변경사항과 충돌 해결.

---

## 향후 개선 아이디어

### 성능 개선
- `pd.concat` 루프 → 리스트 append 후 한 번에 DataFrame 생성
- PR-2 차트 생성 시 RS 시계열 계산 벡터화/캐싱 (현재 종목당 ~252회 calc_score 호출)

### 기능 추가
- 종목 검색/필터링 (JavaScript)
- RS 순위 변화 추이 (주간/월간)
- 업종별 RS 분석
- 차트 페이지에 외부 금융 링크 추가 (다음금융, 네이버금융 등)

### 코드 품질
- `quater` → `quarter` 오타 수정
- `sorted` → `sorted_df` 등으로 변수명 변경 (Python builtin shadowing)
- `rs_df[na_index]['RankChange'] = -1` → `rs_df.loc[na_index, 'RankChange'] = -1`
- 기본 테스트 추가

### 인프라
- GitHub Actions 자동 실행
- Jekyll 빌드 검증

---

## Worker 에이전트 운용 기록

### 교훈
1. **백그라운드 worker의 Bash 권한**: `settings.local.json`에 `Bash(git:*)` 추가해도 worker에서는 Bash가 거부됨. 코드 수정은 worker가 하고, **커밋은 메인 에이전트가 대신** 수행.
2. **settings.local.json**: `.gitignore`에 추가 필수 (실수로 `git add .` 하면 커밋됨).
3. **PR base 브랜치**: PR-1이 이미 머지된 상태에서 PR 생성 시 base를 `main`으로 지정해야 함 (머지된 브랜치는 base로 사용 불가).
