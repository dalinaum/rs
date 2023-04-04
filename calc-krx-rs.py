#!/usr/bin/env python

import FinanceDataReader as fdr
import os
import os.path
import time
import numpy as np
import pandas as pd
import datetime as dt
import textwrap


LIST_FILENAME = "krx-list.csv"
TARGET = 'KRX'
DATA_DIR_ROOT = "DATA"

print("KRX 리스트를 가져옵니다.")
krx_list = fdr.StockListing(TARGET)
krx_list.to_csv(LIST_FILENAME)

print(krx_list.shape)

now = dt.datetime.now()
date = now.strftime("%Y-%m-%d")

data_dir = os.path.join(DATA_DIR_ROOT, date)
os.makedirs(data_dir, exist_ok=True)

for i in krx_list.itertuples():
    print(f"작업({i.Index}): {i.Code} / {i.Name}")
    filename = f"{i.Code}-{i.Name}.csv"
    file_path = os.path.join(data_dir, filename)

    if os.path.exists(file_path):
        print(f"{file_path}가 이미 있습니다.\n가져오지 않습니다.")
    else:
        print(f"{i.Code}를 가져옵니다.")
        data = fdr.DataReader(i.Code, "2022")
        data.to_csv(file_path)
        print(f"{i.Code}를 가져왔습니다. 잠시 대기합니다.")
        time.sleep(np.random.uniform(0.1, 0.9))

print("모든 항목을 가져왔습니다.")

quater = 21 * 3
# 1 year = 252 = 21 * 3 * 4
# https://www.prorealcode.com/topic/relative-strength-rank-screener/
# https://www.investopedia.com/ask/answers/021015/how-can-you-calculate-volatility-excel.asp
# https://www.investopedia.com/articles/06/historicalvolatility.asp

rs_df = pd.DataFrame(columns=[
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
])


def c(code):
    link = f"https://finance.daum.net/quotes/A{code}"
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


for i in krx_list.itertuples():
    print(f"작업({i.Index}): {i.Code} / {i.Name}")
    filename = f"{i.Code}-{i.Name}.csv"
    file_path = os.path.join(data_dir, filename)
    data = pd.read_csv(file_path)
    today_score = calc_score(data)
    yesterday_score = calc_score(data, -2)

    if today_score != -1:
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

        rs_df = rs_df.append({
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
        }, ignore_index=True)
    print(f"today score: {today_score} / yesterday score: {yesterday_score}")

rs_df['Rank'] = rs_df['Score'].rank()
rs_df['RS'] = (rs_df['Rank'] * 98 / len(rs_df)).apply(np.int64) + 1

rs_df['YesterdayRank'] = rs_df['YesterdayScore'].rank()
rs_df['YesterdayRS'] = (rs_df['YesterdayRank'] * 98 /
                        len(rs_df)).apply(np.int64) + 1

na_index = rs_df['YesterdayRS'].isna()
rs_df['RankChange'] = rs_df['RS'] - rs_df['YesterdayRS']
rs_df[na_index]['RankChange'] = -1

sorted = rs_df.sort_values('Rank', ascending=False)

posts_dir = os.path.join("docs", "_posts")
result_file_path = os.path.join(posts_dir, f"{date}-krx-rs.markdown")

with open(result_file_path, "w") as f:
    header_start = '''\
    ---
    layout: single
    '''
    f.write(textwrap.dedent(header_start))
    f.write(now.strftime('title: "KRX 상대강도 %Y년 %-m월 %-d일"\n'))
    f.write(now.strftime("date: %Y-%m-%d %H:%M:%S +0900\n"))
    header_end = '''\
    categories: rs
    ---
    '''
    f.write(textwrap.dedent(header_end))

    comment = '''\
    KRX 전 종목의 상대강도를 계산했다.

    [윌리엄 오닐의 Relative Strength Rating](https://www.williamoneil.com/proprietary-ratings-and-rankings/)에 기반하여 상대 강도를 계산했다.

    ## KRX 상대강도
    
    |종목코드|이름|1년 전|종가|상대강도|
    |------|---|-----|--|------|
    '''
    f.write(textwrap.dedent(comment))

    for i in sorted.itertuples():
        if i.RankChange == 0:
            change = ""
        elif i.RankChange > 0:
            change = f"(+{i.RankChange})"
        else:
            change = f"({i.RankChange})"
        f.write(
            f"|{c(i.Code)}|{i.Name}|{i.Close1}|{i.Close2}|{i.RS} {change}|\n")


result_file_path = os.path.join(
    posts_dir, f"{date}-krx-trend-template.markdown")

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
    f.write(now.strftime('title: "KRX 미너비니 트렌드 템플릿 %Y년 %-m월 %-d일"\n'))
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
        f.write(
            f"|{c(i.Code)}|{i.Name}|{i.Close2}|{i.RS}|{i.Max52W}, {i.Min52W}|{i.MA50}, {i.MA150}, {i.MA200}|\n")
    
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
     1. The relative strength ranking (as reported in Investor’s Business Daily) is no less than 70, and preferably in the 80s or 90s, which will generally be the case with the better selections.
    '''
    f.write(textwrap.dedent(footer))
