#!/usr/bin/env python

import FinanceDataReader as fdr
import json
import os
import os.path
import time
import numpy as np
import pandas as pd
import datetime as dt
import textwrap
from pathlib import Path
from collections import defaultdict

from price_history import (adjust_prices, atomic_csv, collect_adjustments, read_adjustments,
                           repair_cache_file, save_prices)


quater = 21 * 3
# 1 year = 252 = 21 * 3 * 4
# https://www.prorealcode.com/topic/relative-strength-rank-screener/
# https://www.investopedia.com/ask/answers/021015/how-can-you-calculate-volatility-excel.asp
# https://www.investopedia.com/articles/06/historicalvolatility.asp

DATA_DIR_ROOT = "DATA"

RS_DF_COLUMNS = [
    'Code',
    'Name',
    'Score',
    'YesterdayScore',
    'Close1',
    'Close2',
    'MA50',
    'MA150',
    'MA200',
    'LastMonthMA200',
    'Min52W',
    'Max52W'
]

MARKET_CONFIGS = {
    'KOSPI': {
        'target': 'KOSPI',
        'list_filename': 'kospi-list.csv',
        'display_name': '코스피',
        'slug': 'kospi',
        'fetch_message': '코스피 리스트를 가져옵니다.',
    },
    'KOSDAQ': {
        'target': 'KOSDAQ',
        'list_filename': 'kosdaq-list.csv',
        'display_name': '코스닥',
        'slug': 'kosdaq',
        'fetch_message': '코스닥 리스트를 가져옵니다.',
    },
    'KRX': {
        'target': 'KRX',
        'list_filename': 'krx-list.csv',
        'display_name': 'KRX',
        'slug': 'krx',
        'fetch_message': 'KRX 리스트를 가져옵니다.',
    },
}


def chart_directory(market):
    root = Path("docs/charts")
    return root if market == "KRX" else root / MARKET_CONFIGS[market]["slug"]


def c(code, market):
    path = chart_directory(market).relative_to("docs") / f"{code}.html"
    link = "{{ site.baseurl }}/" + path.as_posix()
    return f"[{code}]({link})"


def calc_score(data, day=-1):
    try:
        today = data.loc[data.index[day]]
        one_quarter_ago = data.loc[data.index[day - (quater)]]
        two_quarter_ago = data.loc[data.index[day - (quater * 2)]]
        three_quarter_ago = data.loc[data.index[day - (quater * 3)]]
        four_quarter_ago = data.loc[data.index[day - (quater * 4)]]

        score_1 = today.Close / one_quarter_ago.Close
        score_2 = one_quarter_ago.Close / two_quarter_ago.Close
        score_3 = two_quarter_ago.Close / three_quarter_ago.Close
        score_4 = three_quarter_ago.Close / four_quarter_ago.Close

        # https://www.williamoneil.com/proprietary-ratings-and-rankings/
        total_score = (score_1 * 2) + score_2 + score_3 + score_4
        return total_score

    except IndexError as e:
        print(f"날짜가 충분하지 않은 것 같습니다. {e}")
        return -1


def score_series(close):
    q1, q2, q3, q4 = (close.shift(n * quater) for n in range(1, 5))
    return 2 * (close / q1) + q1 / q2 + q2 / q3 + q3 / q4


def chart_ranks(per_symbol):
    raw = pd.DataFrame(per_symbol).sort_index()
    return raw.rank(axis=1).mul(98).div(raw.count(axis=1), axis=0).apply(np.trunc) + 1


def chart_points(ranks):
    return [{"time": day, "value": int(value)} for day, value in ranks.dropna().items()]


def generate_chart_html(code, name, data, charts_dir, rs_percentile_series, market):
    """종목별 캔들차트 + RS 백분위 추이 HTML 파일 생성."""
    dates = data["Date"].astype(str).str.split(" ").str[0]
    valid = data[["Open", "High", "Low", "Close"]].gt(0).all(axis=1) & data.Date.notna()
    candles = data.loc[valid, ["Open", "High", "Low", "Close"]].astype(float)
    candles.columns = ["open", "high", "low", "close"]
    candles.insert(0, "time", dates[valid])
    candle_data = candles.to_dict("records")
    mask = data.Close.notna()
    closes, dates_all = data.Close[mask], dates[mask]

    def calc_ma(closes, dates, period):
        average = closes.rolling(period).mean().dropna()
        return [{"time": day, "value": round(value, 2)}
                for day, value in zip(dates.loc[average.index], average)]

    ma50_data = calc_ma(closes, dates_all, 50)
    ma150_data = calc_ma(closes, dates_all, 150)
    ma200_data = calc_ma(closes, dates_all, 200)

    # 외부에서 전달받은 RS 백분위 시계열 사용
    rs_series = rs_percentile_series

    # RS 데이터 시작일 기준으로 캔들/MA 데이터 트리밍 (시간축 동기화)
    if rs_series:
        rs_start_date = rs_series[0]['time']
        candle_data = [d for d in candle_data if d['time'] >= rs_start_date]
        ma50_data = [d for d in ma50_data if d['time'] >= rs_start_date]
        ma150_data = [d for d in ma150_data if d['time'] >= rs_start_date]
        ma200_data = [d for d in ma200_data if d['time'] >= rs_start_date]

    candle_json = json.dumps(candle_data)
    ma50_json = json.dumps(ma50_data)
    ma150_json = json.dumps(ma150_data)
    ma200_json = json.dumps(ma200_data)
    rs_json = json.dumps(rs_series)

    title = f"{name} ({code}) · {market}"
    site_title = "달리나음의 상대 강도"

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: #ffffff;
      color: #333333;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
    }}
    .masthead {{
      padding: 12px 16px;
      background: #93c7c4;
      display: flex;
      align-items: center;
      gap: 16px;
      flex-shrink: 0;
    }}
    .masthead .site-title {{
      font-size: 18px;
      font-weight: 700;
      color: #fff;
      text-decoration: none;
      letter-spacing: -0.5px;
    }}
    .masthead .site-title:hover {{ opacity: 0.85; }}
    .toolbar {{
      padding: 6px 16px;
      background: #f8f9fa;
      border-bottom: 1px solid #e0e3eb;
      display: flex;
      align-items: center;
      gap: 16px;
      flex-shrink: 0;
    }}
    .toolbar h1 {{
      font-size: 15px;
      font-weight: 600;
      color: #333333;
    }}
    .toolbar a {{
      color: #2196f3;
      text-decoration: none;
      font-size: 13px;
    }}
    .toolbar a:hover {{ text-decoration: underline; }}
    .chart-label {{
      padding: 4px 16px;
      font-size: 11px;
      color: #787b86;
      background: #f8f9fa;
      border-bottom: 1px solid #e0e3eb;
      flex-shrink: 0;
    }}
    .chart-container {{
      flex: 1;
      min-height: 0;
      display: flex;
      flex-direction: column;
    }}
    #candle-chart {{
      height: calc(60vh - 40px);
    }}
    .divider {{
      height: 4px;
      background: #e0e3eb;
    }}
    #rs-chart-label {{
      padding: 4px 16px;
      font-size: 11px;
      color: #787b86;
      background: #f8f9fa;
      border-top: 1px solid #e0e3eb;
    }}
    #rs-chart {{
      height: calc(40vh - 40px);
    }}
    .legend {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
    }}
    .legend-dot {{
      width: 10px;
      height: 3px;
      border-radius: 2px;
    }}
  </style>
</head>
<body>
  <div class="masthead">
    <a href="{'../' if market == 'KRX' else '../../'}" class="site-title">{site_title}</a>
  </div>
  <div class="toolbar">
    <a href="{'../' if market == 'KRX' else '../../'}">&larr; 목록</a>
    <h1>{title}</h1>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:#2196f3"></div>MA50</div>
      <div class="legend-item"><div class="legend-dot" style="background:#ff9800"></div>MA150</div>
      <div class="legend-item"><div class="legend-dot" style="background:#f44336"></div>MA200</div>
    </div>
  </div>
  <div class="chart-label">캔들차트 + 이동평균</div>
  <div class="chart-container">
    <div id="candle-chart"></div>
    <div class="divider"></div>
    <div id="rs-chart-label">{market} RS 백분위 추이</div>
    <div id="rs-chart"></div>
  </div>

  <script>
    const candleData = {candle_json};
    const ma50Data = {ma50_json};
    const ma150Data = {ma150_json};
    const ma200Data = {ma200_json};
    const rsData = {rs_json};

    const chartOptions = {{
      layout: {{
        background: {{ color: '#ffffff' }},
        textColor: '#333333',
      }},
      grid: {{
        vertLines: {{ color: '#e0e3eb' }},
        horzLines: {{ color: '#e0e3eb' }},
      }},
      crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
      rightPriceScale: {{ borderColor: '#d1d4dc' }},
      timeScale: {{ borderColor: '#d1d4dc', timeVisible: true, fixLeftEdge: true, fixRightEdge: true }},
    }};

    // 캔들차트
    const candleEl = document.getElementById('candle-chart');
    const candleChart = LightweightCharts.createChart(candleEl, {{
      ...chartOptions,
      autoSize: true,
    }});

    const candleSeries = candleChart.addSeries(LightweightCharts.CandlestickSeries, {{
      upColor: '#ef5350',
      downColor: '#2196f3',
      borderDownColor: '#2196f3',
      borderUpColor: '#ef5350',
      wickDownColor: '#2196f3',
      wickUpColor: '#ef5350',
    }});
    candleSeries.setData(candleData);

    const ma50Series = candleChart.addSeries(LightweightCharts.LineSeries, {{ color: '#2196f3', lineWidth: 1, priceLineVisible: false }});
    ma50Series.setData(ma50Data);

    const ma150Series = candleChart.addSeries(LightweightCharts.LineSeries, {{ color: '#ff9800', lineWidth: 1, priceLineVisible: false }});
    ma150Series.setData(ma150Data);

    const ma200Series = candleChart.addSeries(LightweightCharts.LineSeries, {{ color: '#f44336', lineWidth: 1, priceLineVisible: false }});
    ma200Series.setData(ma200Data);

    candleChart.timeScale().fitContent();

    // RS 점수 차트
    const rsEl = document.getElementById('rs-chart');
    const rsChart = LightweightCharts.createChart(rsEl, {{
      ...chartOptions,
      autoSize: true,
    }});

    const rsSeries = rsChart.addSeries(LightweightCharts.LineSeries, {{
      color: '#7b1fa2',
      lineWidth: 2,
      priceLineVisible: false,
    }});
    rsSeries.setData(rsData);
    rsChart.timeScale().fitContent();

    // 두 차트 시간축 동기화 (같은 날짜 범위이므로 logical range 사용)
    let syncing = false;
    candleChart.timeScale().subscribeVisibleLogicalRangeChange(range => {{
      if (syncing || !range) return;
      syncing = true;
      rsChart.timeScale().setVisibleLogicalRange(range);
      syncing = false;
    }});
    rsChart.timeScale().subscribeVisibleLogicalRangeChange(range => {{
      if (syncing || !range) return;
      syncing = true;
      candleChart.timeScale().setVisibleLogicalRange(range);
      syncing = false;
    }});
  </script>
</body>
</html>
"""

    os.makedirs(charts_dir, exist_ok=True)
    html_path = os.path.join(charts_dir, f"{code}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)


def market_listing(config, date, actions, historical):
    path = Path(config["list_filename"])
    reports = Path("docs/_posts")
    slug = config["slug"]
    previous = pd.read_csv(path, index_col=0, dtype={"Code": str}) if path.exists() else None
    if historical:
        report = reports / f"{date}-{slug}-rs.markdown"
        if report.exists():
            rows = []
            for line in report.read_text().splitlines():
                if line.startswith("|"):
                    cells = line.split("|")
                    code = cells[1].lstrip("[")[:6]
                    if len(code) == 6 and code.isascii() and code.isalnum():
                        rows.append((code, cells[2]))
            if rows:
                return pd.DataFrame(rows, columns=["Code", "Name"])
        print(f"{date} 당시 시장 목록을 찾을 수 없어 현재 구성 종목을 사용합니다.")
    try:
        current = fdr.StockListing(config["target"])
    except Exception:
        if previous is None:
            raise
        print(f"FDR 상장 목록 조회 실패. {path}의 마지막 목록을 사용합니다.")
        return previous
    if historical:
        return current

    previous_day = date
    if previous is not None:
        if "SnapshotDate" in previous:
            previous_day = str(previous.SnapshotDate.iloc[0])
        else:
            previous_day = max((p.name[:10] for p in reports.glob(f"*-{slug}-rs.markdown")),
                               default=date)
    start = pd.Timestamp(previous_day) - pd.Timedelta(days=21)
    calendar = fdr.DataReader("NAVER:005930", start, date)
    prior_sessions = calendar.loc[:previous_day]
    if prior_sessions.empty:
        raise ValueError("FDR에서 상장 목록의 거래 기준일을 확인할 수 없습니다.")
    previous_day = prior_sessions.index[-1].date().isoformat()
    snapshot_day = calendar.index[-1].date().isoformat()
    if previous is not None and previous_day < snapshot_day:
        fields = ["Close", "Stocks"]
        if previous.set_index("Code")[fields].sort_index().equals(
                current.set_index("Code")[fields].sort_index()):
            return current
        collect_adjustments(previous, current, previous_day, snapshot_day, actions)
    if previous is not None and previous_day == snapshot_day:
        # Listings and quotes can refresh at different times on the same run.
        # Keep the last verified observation for the next comparison.
        return current
    with atomic_csv(path) as f:
        current.assign(SnapshotDate=snapshot_day).to_csv(f)
    return current


def run_market_analysis(market_key, target_date=None):
    config = MARKET_CONFIGS[market_key]
    display_name = config['display_name']
    slug = config['slug']
    fetch_message = config['fetch_message']

    if target_date:
        now = dt.datetime.strptime(target_date, "%Y-%m-%d")
    else:
        now = dt.datetime.now()
    date = now.strftime("%Y-%m-%d")
    actions = read_adjustments()
    print(fetch_message)
    historical = bool(target_date and date < dt.date.today().isoformat())
    stock_list = market_listing(config, date, actions, historical)
    print(stock_list.shape)

    by_code = defaultdict(list)
    for action in actions.values():
        by_code[action.code].append(action)
    unresolved = []

    data_dir = os.path.join(DATA_DIR_ROOT, date)
    os.makedirs(data_dir, exist_ok=True)

    for i in stock_list.itertuples():
        print(f"작업({i.Index}): {i.Code} / {i.Name}")
        filename = f"{i.Code}-{i.Name}.csv"
        file_path = os.path.join(data_dir, filename)

        if not os.path.exists(file_path):
            print(f"{i.Code}를 가져옵니다.")
            data = fdr.DataReader(f"NAVER:{i.Code}", "2022", date)
            if by_code[i.Code]:
                data = adjust_prices(data, by_code[i.Code], date, unresolved)
            save_prices(data, file_path)
            print(f"{i.Code}를 가져왔습니다. 잠시 대기합니다.")
            time.sleep(np.random.uniform(0.1, 0.9))
        elif by_code[i.Code]:
            # The cache can predate either a disclosure or this correction.
            repair_cache_file(file_path, by_code[i.Code], date, unresolved)

    print("모든 항목을 가져왔습니다.")
    for note in unresolved:
        print(f"가격 보정 미검증: {note}")

    rs_df = pd.DataFrame(columns=RS_DF_COLUMNS)
    stock_data_cache = {}      # {code: (name, data_df)}
    daily_raw_scores = {}      # {date_str: {code: raw_score}}

    for i in stock_list.itertuples():
        print(f"작업({i.Index}): {i.Code} / {i.Name}")
        filename = f"{i.Code}-{i.Name}.csv"
        file_path = os.path.join(data_dir, filename)
        data = pd.read_csv(file_path)
        if target_date:
            # 기준일 이후 행을 잘라내 과거 날짜로 재계산할 수 있게 한다.
            data = data[pd.to_datetime(data['Date'], format='ISO8601').dt.normalize() <= pd.Timestamp(target_date)]
            data = data.reset_index(drop=True)
        today_score = calc_score(data)
        yesterday_score = calc_score(data, -2)

        if today_score != -1:
            stock_data_cache[i.Code] = (i.Name, data)

            today = data.loc[data.index[-1]]
            four_quarter_ago = data.loc[data.index[-1 - (quater * 4)]]

            data_260 = data.tail(260)
            data_260_close = data_260.Close
            max_52w = data_260_close.max()
            min_52w = data_260_close.min()
            data_220_close = data_260_close.tail(220)
            last_month_ma_200 = int(data_220_close.head(200).mean())
            data_200_close = data_220_close.tail(200)
            ma_200 = int(data_200_close.mean())
            data_150_close = data_200_close.tail(150)
            ma_150 = int(data_150_close.mean())
            data_50_close = data_150_close.tail(50)
            ma_50 = int(data_50_close.mean())

            rs_df = pd.concat([rs_df, pd.DataFrame([{
                'Code': i.Code,
                'Name': i.Name,
                'Score': today_score,
                'YesterdayScore': yesterday_score,
                'Close1': four_quarter_ago.Close,
                'Close2': today.Close,
                'MA50': ma_50,
                'MA150': ma_150,
                'MA200': ma_200,
                'LastMonthMA200': last_month_ma_200,
                'Min52W': min_52w,
                'Max52W': max_52w,
            }])], ignore_index=True)

            close = data.set_index("Date").Close
            daily_raw_scores[i.Code] = score_series(close).tail(4 * quater)

        print(f"today score: {today_score} / yesterday score: {yesterday_score}")

    rs_df['Rank'] = rs_df['Score'].rank()
    rs_df['RS'] = (rs_df['Rank'] * 98 / len(rs_df)).apply(np.int64) + 1

    rs_df['YesterdayRank'] = rs_df['YesterdayScore'].rank()
    rs_df['YesterdayRS'] = (rs_df['YesterdayRank'] * 98 /
                            len(rs_df)).apply(np.int64) + 1

    na_index = rs_df['YesterdayRS'].isna()
    rs_df['RankChange'] = rs_df['RS'] - rs_df['YesterdayRS']
    rs_df.loc[na_index, 'RankChange'] = -1

    newer_reports = any(p.name[:10] > date for p in Path("docs/_posts").glob(f"*-{slug}-rs.markdown"))
    if not historical or not newer_reports:
        daily_percentiles = chart_ranks(daily_raw_scores)
        charts_dir = chart_directory(market_key)
        for code, (name, data) in stock_data_cache.items():
            rs_percentile_series = chart_points(daily_percentiles[code])
            try:
                generate_chart_html(code, name, data, charts_dir, rs_percentile_series, market_key)
                print(f"{code} 차트 생성 완료")
            except Exception as e:
                print(f"{code} 차트 생성 실패: {e}")

    sorted = rs_df.sort_values('Rank', ascending=False)

    posts_dir = os.path.join("docs", "_posts")
    result_file_path = os.path.join(posts_dir, f"{date}-{slug}-rs.markdown")

    with open(result_file_path, "w") as f:
        header_start = '''\
        ---
        layout: single
        '''
        f.write(textwrap.dedent(header_start))
        f.write(now.strftime(f'title: "{display_name} 상대강도 %Y년 %-m월 %-d일"\n'))
        f.write(now.strftime("date: %Y-%m-%d %H:%M:%S +0900\n"))
        header_end = '''\
        categories: rs
        ---
        '''
        f.write(textwrap.dedent(header_end))

        comment = f'''\
        {display_name} 전 종목의 상대강도를 계산했다.

        [윌리엄 오닐의 Relative Strength Rating](https://www.williamoneil.com/proprietary-ratings-and-rankings/)에 기반하여 상대 강도를 계산했다.
        계산 방식에 대한 자세한 내용은 [여기](https://dalinaum.github.io/investment/2024/08/26/how-i-calculated-relative-strength.html)를 참고하라.

        ## {display_name} 상대강도

        |종목코드|이름|1년 전|종가|1년 수익률|상대강도|
        |------|---|-----|--|--------|------|
        '''
        f.write(textwrap.dedent(comment))

        for i in sorted.itertuples():
            if i.RankChange == 0:
                change = "▬"
            elif i.RankChange > 0:
                change = f"🔺(+{i.RankChange})"
            else:
                change = f"🔻({i.RankChange})"
            pct = (i.Close2 - i.Close1) / i.Close1 * 100
            if pct >= 0:
                pct_str = f"+{pct:.1f}%"
            else:
                pct_str = f"{pct:.1f}%"
            f.write(
                f"|{c(i.Code, market_key)}|{i.Name}|{i.Close1:,}|{i.Close2:,}|{pct_str}|{i.RS} {change}|\n")

    result_file_path = os.path.join(
        posts_dir, f"{date}-{slug}-trend-template.markdown")

    minervini = sorted[sorted.RS >= 70]
    minervini = minervini[minervini.Close2 > minervini.MA50]
    minervini = minervini[minervini.Close2 > minervini.MA150]
    minervini = minervini[minervini.Close2 > minervini.MA200]
    minervini = minervini[minervini.MA50 > minervini.MA150]
    minervini = minervini[minervini.MA150 > minervini.MA200]
    minervini = minervini[minervini.MA200 > minervini.LastMonthMA200]
    minervini = minervini[minervini.Close2 > minervini.Min52W * 1.3]
    minervini = minervini[minervini.Close2 > minervini.Max52W * 0.75]

    # Close > MA50, Close > MA150, Close > MA200
    # MA50 > MA150 > MA200
    # 1달전 MA200 < 오늘 MA200
    # Close > 52-low * 1.3
    # Close <= 52-high * 0.75
    # RS 70점 이상

    with open(result_file_path, "w") as f:
        header_start = '''\
        ---
        layout: single
        '''
        f.write(textwrap.dedent(header_start))
        f.write(now.strftime(f'title: "{display_name} 미너비니 트렌드 템플릿 %Y년 %-m월 %-d일"\n'))
        f.write(now.strftime("date: %Y-%m-%d %H:%M:%S +0900\n"))
        header_end = '''\
        categories: minervini
        ---
        '''
        f.write(textwrap.dedent(header_end))

        comment = '''\
        마크 미니버니(Mark Minervini)의 트렌드 템플릿(Trend Template)을 계산하여 만족한 결과만 나열하였습니다. 필터링에 걸린 종목은 아래에 나열되어 있지 않습니다.

        아래 기술된 미너비니 트렌드 템플릿 계산 방식으로 계산합니다. 계산 방법에서 RS 값이 최소 70이상이고 80, 90이면 좋다고 하고 있는데 70이상만 결과로 표기하고 80이나 90에 대해서 특별히 더 자세히 보이지는 않습니다.

        ## 미너비니 트렌드 템플릿

        |종목코드|이름|종가|RS|신고가,신저가|MA50,150,200|
        |------|---|---|--|---------|------------|
        '''
        f.write(textwrap.dedent(comment))

        for i in minervini.itertuples():
            if i.RankChange == 0:
                trend_change = "▬"
            elif i.RankChange > 0:
                trend_change = f"🔺(+{i.RankChange})"
            else:
                trend_change = f"🔻({i.RankChange})"
            f.write(
                f"|{c(i.Code, market_key)}|{i.Name}|{i.Close2:,}|{i.RS} {trend_change}|{i.Max52W:,}, {i.Min52W:,}|{i.MA50:,}, {i.MA150:,}, {i.MA200:,}|\n")

        f.write("\n")
        footer = '''\
        ## 미너비니 트렌드 템플릿 계산 방식

        "Trade Like a Stock Market Wizard: How to Achieve Super Performance in Stocks in Any Market"에서

         1. The current stock price is above both the 150-day (30-week) and the 200-day (40-week) moving average price lines.
         1. The 150-day moving average is above the 200-day moving average.
         1. The 200-day moving average line is trending up for at least 1 month (preferably 4–5 months minimum in most cases).
         1. The 50-day (10-week) moving average is above both the 150-day and 200-day moving averages.
         1. The current stock price is trading above the 50-day moving average.
         1. The current stock price is at least 30 percent above its 52-week low. (Many of the best selections will be 100 percent, 300 percent, or greater above their 52-week low before they emerge from a solid consolidation period and mount a large scale advance.)
         1. The current stock price is within at least 25 percent of its 52-week high (the closer to a new high the better).
         1. The relative strength ranking (as reported in Investor's Business Daily) is no less than 70, and preferably in the 80s or 90s, which will generally be the case with the better selections.
        '''
        f.write(textwrap.dedent(footer))
