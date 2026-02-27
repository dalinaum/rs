#!/usr/bin/env python
"""KRX API 장애 시 기존 CSV 데이터로 오프라인 실행."""
import os
import sys
import numpy as np
import pandas as pd
import datetime as dt
import textwrap
from rs_calculator import (
    calc_score, generate_chart_html, quater,
    RS_DF_COLUMNS, MARKET_CONFIGS, c, DATA_DIR_ROOT
)

def run_offline(market_key):
    config = MARKET_CONFIGS[market_key]
    display_name = config['display_name']
    slug = config['slug']
    list_filename = config['list_filename']

    stock_list = pd.read_csv(list_filename, index_col=0)
    stock_list['Code'] = stock_list['Code'].astype(str).str.zfill(6)
    print(f"{display_name} 종목 수: {len(stock_list)}")

    # 가장 최근 데이터 폴더 사용
    dates = sorted(d for d in os.listdir(DATA_DIR_ROOT) if d.startswith('20') and os.path.isdir(os.path.join(DATA_DIR_ROOT, d)))
    latest_date = dates[-1]
    data_dir = os.path.join(DATA_DIR_ROOT, latest_date)
    print(f"데이터 날짜: {latest_date}")

    date = latest_date  # 포스트 날짜를 데이터 날짜로
    now = dt.datetime.strptime(date, "%Y-%m-%d")

    rs_df = pd.DataFrame(columns=RS_DF_COLUMNS)
    stock_data_cache = {}
    daily_raw_scores = {}

    for i in stock_list.itertuples():
        filename = f"{i.Code}-{i.Name}.csv"
        file_path = os.path.join(data_dir, filename)
        if not os.path.exists(file_path):
            continue
        data = pd.read_csv(file_path)
        today_score = calc_score(data)
        yesterday_score = calc_score(data, -2)

        if today_score != -1:
            stock_data_cache[i.Code] = (i.Name, data)

            today_row = data.loc[data.index[-1]]
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
                'Close2': today_row.Close,
                'MA50': ma_50,
                'MA150': ma_150,
                'MA200': ma_200,
                'LastMonthMA200': last_month_ma_200,
                'Min52W': min_52w,
                'Max52W': max_52w,
            }])], ignore_index=True)

            total_len = len(data)
            min_required = quater * 4
            mask = data['Close'].notna()
            dates_all = data.loc[mask, 'Date'].astype(str).str.split(' ').str[0].tolist()
            for day_offset in range(-min_required, 0):
                score = calc_score(data, day=day_offset)
                if score != -1:
                    abs_idx = total_len + day_offset
                    date_str = dates_all[abs_idx]
                    if date_str not in daily_raw_scores:
                        daily_raw_scores[date_str] = {}
                    daily_raw_scores[date_str][i.Code] = score

        print(f"({i.Index}) {i.Code} {i.Name}: {today_score:.4f}" if today_score != -1 else f"({i.Index}) {i.Code} SKIP")

    rs_df['Rank'] = rs_df['Score'].rank()
    rs_df['RS'] = (rs_df['Rank'] * 98 / len(rs_df)).apply(np.int64) + 1
    rs_df['YesterdayRank'] = rs_df['YesterdayScore'].rank()
    rs_df['YesterdayRS'] = (rs_df['YesterdayRank'] * 98 / len(rs_df)).apply(np.int64) + 1
    na_index = rs_df['YesterdayRS'].isna()
    rs_df['RankChange'] = rs_df['RS'] - rs_df['YesterdayRS']
    rs_df[na_index]['RankChange'] = -1

    # 일별 백분위 계산
    daily_percentiles = {}
    for date_str, scores in daily_raw_scores.items():
        scores_series = pd.Series(scores)
        ranks = scores_series.rank()
        percentiles = (ranks * 98 / len(scores_series)).apply(np.int64) + 1
        daily_percentiles[date_str] = percentiles.to_dict()

    # 차트 생성
    charts_dir = os.path.join("docs", "charts")
    sorted_dates = list(daily_percentiles.keys())
    sorted_dates.sort()
    for code, (name, data) in stock_data_cache.items():
        rs_percentile_series = []
        for date_str in sorted_dates:
            if code in daily_percentiles[date_str]:
                rs_percentile_series.append({
                    'time': date_str,
                    'value': int(daily_percentiles[date_str][code])
                })
        try:
            generate_chart_html(code, name, data, charts_dir, display_name, rs_percentile_series)
        except Exception as e:
            print(f"{code} 차트 실패: {e}")

    sorted_df = rs_df.sort_values('Rank', ascending=False)

    posts_dir = os.path.join("docs", "_posts")
    os.makedirs(posts_dir, exist_ok=True)

    # RS 포스트
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

        |종목코드|이름|1년 전|종가|상대강도|
        |------|---|-----|--|------|
        '''
        f.write(textwrap.dedent(comment))
        for i in sorted_df.itertuples():
            if i.RankChange == 0:
                change = ""
            elif i.RankChange > 0:
                change = f"(+{i.RankChange})"
            else:
                change = f"({i.RankChange})"
            f.write(f"|{c(i.Code)}|{i.Name}|{i.Close1}|{i.Close2}|{i.RS} {change}|\n")

    # 트렌드 템플릿 포스트
    result_file_path = os.path.join(posts_dir, f"{date}-{slug}-trend-template.markdown")
    minervini = sorted_df[sorted_df.RS >= 70]
    minervini = minervini[minervini.Close2 > minervini.MA50]
    minervini = minervini[minervini.Close2 > minervini.MA150]
    minervini = minervini[minervini.Close2 > minervini.MA200]
    minervini = minervini[minervini.MA50 > minervini.MA150]
    minervini = minervini[minervini.MA150 > minervini.MA200]
    minervini = minervini[minervini.MA200 > minervini.LastMonthMA200]
    minervini = minervini[minervini.Close2 > minervini.Min52W * 1.3]
    minervini = minervini[minervini.Close2 > minervini.Max52W * 0.75]

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
            f.write(f"|{c(i.Code)}|{i.Name}|{i.Close2}|{i.RS}|{i.Max52W}, {i.Min52W}|{i.MA50}, {i.MA150}, {i.MA200}|\n")
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

    print(f"\n완료: {date}-{slug}-rs.markdown, {date}-{slug}-trend-template.markdown")
    print(f"차트: {len(stock_data_cache)}개 생성")


if __name__ == '__main__':
    markets = sys.argv[1:] if len(sys.argv) > 1 else ['KOSPI']
    for m in markets:
        run_offline(m)
