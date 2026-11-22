# 달리나음의 코스피 상대 강도 등급

[윌리엄 오닐의 Relative Strength Rating](https://www.williamoneil.com/proprietary-ratings-and-rankings/)에 기반한 사이트를 만들었다.

 * [달리나음의 코스피 상대 강도](https://dalinaum.github.io/rs/)

해당 사이트에 월요일부터 금요일 오후 4시 전후에 자동으로 코스피 상대 경도를 올릴 예정이다. 4시 반까지도 올라오지 않는다면 시스템의 오류가 있는 것이다.

## 윌리엄 오닐의 상대 강도 등급

계산 방식에 대한 윌리엄 오닐 사이트의 설명은 다음과 같다.

RELATIVE STRENGTH RATING

This technical tool is one of the most popular ways for clients to see the market’s top performers. The Relative Strength Rating is the result of calculating a stock’s percentage price change over the last 12 months. A 40% weight is assigned to the latest three-month period; the remaining three quarters each receive 20% weight. All stocks are arranged in order of greatest price percentage change and assigned a percentile rank from 99 (highest) to 1 (lowest).

마켓 주도주를 알고 싶은 사람에게 가장 유용한 방법을 제공하는 기술적 도구이다. 상대 강도 등급(Reative Strehing)은 최근 12개월 동안 주식의 가격 변동률을 계산한 결과이다. 최근 3개월 기간에 40%의 가중치가 할당된다. 나머지 세 분기는 각각 20%의 가중치를 받는다. 모든 종목은 가격 변동율이 큰 순서대로 정렬되고 99(최고)부터 1(최저)의 백분위 순위가 할당된다.

## 사이트의 계산 방식

오닐의 설명에 따라 4분기의 가격 변동률을 계산해 최근 1분기만 2배로 반영하고 나머지는 균등하게 반영하고 순위를 매겼다. 1등에게 99점 꼴등에게 1점을 할당하도록 균등하게 점수를 매겼다.

계산 방식에 대한 자세한 내용은 [여기](https://dalinaum.github.io/)를 참고하라.

## 주식 병합·분할과 가격 캐시

세 시장의 수집기는 FinanceDataReader로 상장 목록과 일봉을 가져온다. 상장주식수가 변하면 전후 거래일의 목록 종가와 FDR의 Yahoo 단일 종목 `Close`를 대조한다. 주식수 비율과 수정 시세가 일치하면 `price-adjustments.csv`에 기록한다. 수집한 네이버 일봉에서 해당 변경이 빠진 경우에만 변경일 전 시가·고가·저가·종가를 같은 단위로 환산한다. 거래량은 거래 당시 주식 수량으로 보존한다. 검증에 필요한 비교 시세가 없으면 `pending-price-checks.csv`에 남겨 다음 수집에서 다시 확인한다.

기존 로컬 캐시는 `uv run python price_history.py DATA`로 일괄 정정한다. 각 날짜의 캐시에는 그날까지 효력이 발생한 변경을 적용한다. 이미 보정된 파일은 다시 실행해도 같은 값을 유지한다.

과거 리포트는 `uv run python repair_reports.py <가격자료 디렉터리> --as-of YYYY-MM-DD`로 검사한다. 입력은 상장폐지 종목을 포함한 FDR 네이버 일봉이며 파일명은 `종목코드.csv.gz` 또는 `종목코드-종목명.csv`이다. `--write`로 정정을 적용하고 `--charts`를 함께 지정하면 시장별 차트도 재생성한다. `--original-posts`로 정정 전 게시물 디렉터리를 지정할 수 있다. 당일 시장 구성과 발표 종가를 보존하고, 1년 전 종가에서 확인된 주식 단위 변경과 같은 배율의 누락이 발견된 시장·날짜를 다시 계산한다. 같은 날짜의 모든 종목을 순위에 포함한다.

2026년 11월 20일까지의 정정에는 프로젝트가 보관한 FDR 상장 목록 729개를 사용했다. 2026년 2월 27일부터 11월 5일 사이에는 연속된 목록이 없어 그 기간에 새로 발생한 변경을 전수 확인할 수 없었다. 전후 거래일의 가격 단위를 판별할 수 없었던 41건은 기존 시세를 유지했다.
