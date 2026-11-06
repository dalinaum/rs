# RS 프로젝트 제품 요구사항

## 프로젝트 개요

한국 주식시장(KOSPI, KOSDAQ, KRX)의 상대강도(RS) 지표를 계산하고, 종목별 캔들차트를 생성하며, Jekyll 블로그 포스트를 자동 생성하는 프로젝트.

### 파일 구조
- `rs_calculator.py` — 공통 모듈 (RS 계산, 차트 생성, 포스트 생성)
- `calc-kospi-rs.py` / `calc-kosdaq-rs.py` / `calc-krx-rs.py` — 시장별 실행 스크립트
- `docs/charts/` — 종목별 차트 HTML (런타임 생성)
- `docs/_posts/` — 날짜별 마크다운 포스트

---

## 버그 수정 (P0)

| 이슈 | 위치 | 설명 |
|------|------|------|
| Chained Assignment | `rs_calculator.py:481` | `rs_df[na_index]['RankChange'] = -1` → `.loc` 사용 필요 |
| 내장함수 섀도잉 | `rs_calculator.py:509` | `sorted` 변수명이 Python 내장 `sorted()`를 가림 → `sorted_df`로 변경 |
| 변수명 오타 | `rs_calculator.py:14` | `quater` → `quarter` (전체 파일 치환) |

---

## 코드 품질 개선 (P1)

| 이슈 | 위치 | 설명 |
|------|------|------|
| pd.concat 루프 | `rs_calculator.py:440-453` | 매 종목마다 `pd.concat` 호출 → 리스트 append 후 한 번에 DataFrame 생성 |
| iterrows 사용 | `rs_calculator.py:93` | `iterrows()` → `itertuples()`로 변경 (성능 향상) |
| 차트 RS 계산 성능 | `rs_calculator.py` | 종목당 ~252회 `calc_score` 호출 → 벡터화 또는 캐싱 |

---

## 기능 개선 (P2)

- [ ] 종목 검색/필터링 (JavaScript로 테이블 필터링)
- [ ] RS 순위 변화 추이 (주간/월간)
- [ ] 업종별 RS 분석 (섹터별 강도)
- [ ] 차트 페이지에 외부 금융 링크 추가 (다음금융, 네이버금융)

---

## 인프라 (P3)

- [ ] GitHub Actions 자동 실행 (현재 수동)
- [ ] 단위 테스트 추가 (`calc_score`, `run_market_analysis`)
- [ ] 3개 calc 파일(`calc-kospi-rs.py`, `calc-kosdaq-rs.py`, `calc-krx-rs.py`) 통합 검토

---

## 완료된 작업

### PR-1: py 파일 중복 제거 (머지됨)
- [#7](https://github.com/dalinaum/rs/pull/7)
- `rs_calculator.py` 공통 모듈 생성, 각 시장별 스크립트를 5줄로 단순화

### PR-2: 종목별 캔들차트 페이지 생성 (리뷰 대기)
- [#8](https://github.com/dalinaum/rs/pull/8)
- TradingView Lightweight Charts v4 기반 캔들차트 + RS 백분위 추이 차트
- 라이트 테마, masthead + toolbar 헤더 구조

### PR-3: 테이블 가시성 개선 (머지됨)
- [#9](https://github.com/dalinaum/rs/pull/9)
- RS 변화량 이모지, 1년 수익률 컬럼, 천단위 구분자

### PR-4: RS 분포 히스토그램 (폐기)
- [#10](https://github.com/dalinaum/rs/pull/10) — 닫힘
- 불필요한 기능으로 판단. 사용자 확인 없이 구현이 진행된 사례 (`verify-before-build.md` 참고)
