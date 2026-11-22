"""Restate archived market cohorts from cached, single-symbol FDR NAVER histories."""

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from math import prod
from pathlib import Path
import re

import numpy as np
import pandas as pd

from price_history import adjust_prices, read_adjustments
from rs_calculator import (MARKET_CONFIGS, chart_directory, chart_points, chart_ranks,
                           generate_chart_html, quater, score_series)


@dataclass
class History:
    dates: list
    close: np.ndarray
    score: np.ndarray
    actions: list


def histories_from(directory, actions, as_of):
    groups = defaultdict(list)
    for action in actions.values():
        groups[action.code].append(action)
    histories = {}
    for path in sorted(directory.glob("*.csv*")):
        code = path.name[:6]
        frame = pd.read_csv(path, index_col="Date", parse_dates=["Date"])
        if frame.empty:
            continue
        issues = []
        corrected = adjust_prices(frame, groups[code], as_of, issues)
        for issue in issues:
            print(issue)
        actions_checked = [a for a in groups[code] if not any(a.date in msg for msg in issues)]
        close = corrected.Close
        histories[code] = History(close.index.strftime("%Y-%m-%d").tolist(),
                                  close.to_numpy(), score_series(close).to_numpy(), actions_checked)
    return histories


def missing_factor(old, last, history, end):
    first = end - 4 * quater
    expected = history.close[first] * last / history.close[end]
    if abs(expected - old) <= max(1, old * .002):
        return None
    inside = [a.factor for a in history.actions
              if history.dates[first] < a.date <= history.dates[end]]
    for size in range(1, len(inside) + 1):
        for factors in combinations(inside, size):
            factor = prod(factors)
            if abs(expected / factor - old) <= max(.51, old * .001):
                return factor
    return None


REPORT_ROW = re.compile(r"^\|(?:\[[A-Z0-9]{6}\]\(|[A-Z0-9]{6}\|)")


def report_rows(lines):
    return [line.split("|") for line in lines if REPORT_ROW.match(line)]


def symbol(cell):
    return cell.lstrip("[")[:6]


def percentile(values):
    return (pd.Series(values).rank() * 98 / len(values)).astype(int).to_numpy() + 1


def rank_cell(rank, diff, modern):
    if modern:
        change = f"🔺(+{diff})" if diff > 0 else f"🔻({diff})" if diff < 0 else "▬"
    else:
        change = f"({diff:+})" if diff else ""
    return f"{rank} {change}"


def display_price(value, modern):
    value = round(float(value), 3)
    if value.is_integer():
        value = int(value)
    return format(value, "," if modern else "")


def replace_table(path, lines, rows, note):
    # Some early trend reports have zero rows. Keep their explanatory footer.
    start = next(i for i, line in enumerate(lines) if line.startswith("|------")) + 1
    end = start
    while end < len(lines) and REPORT_ROW.match(lines[end]):
        end += 1
    lines[start:end] = rows
    if note not in lines:
        heading = next(i for i, line in enumerate(lines) if line.startswith("## "))
        lines[heading:heading] = [note, ""]
    path.write_text("\n".join(lines) + "\n")


def trend_row(cells, history, end, scale, last, rs, diff, modern):
    if rs < 70:
        return None
    # Express all derived prices in the units of the original report-day close.
    values = history.close[max(0, end - 259):end + 1] * scale
    values[-1] = last
    ma50, ma150, ma200 = (int(values[-n:].mean()) for n in (50, 150, 200))
    prior_ma = int(values[-220:][:200].mean())
    high, low = values.max(), values.min()
    if not (last > ma50 > ma150 > ma200 > prior_ma and last > 1.3 * low and last > .75 * high):
        return None
    px = lambda x: display_price(x, modern)
    rank = rank_cell(rs, diff, True) if modern else str(rs)
    return "|".join(["", *cells[1:3], cells[4], rank, f"{px(high)}, {px(low)}",
                     f"{px(ma50)}, {px(ma150)}, {px(ma200)}", ""])


def repair_report(path, histories, as_of, write, output_dir):
    lines = path.read_text().splitlines()
    rows = report_rows(lines)
    if not rows:
        return "no quoted symbols"
    day = path.name[:10]
    modern = any("|1년 수익률|" in line for line in lines)
    positions = []
    affected = {}
    for i, cells in enumerate(rows):
        code = symbol(cells[1])
        history = histories.get(code)
        end = bisect_right(history.dates, day) - 1 if history else -1
        positions.append((history, end))
        if end < 4 * quater or not history.actions:
            continue
        old, last = (float(s.replace(",", "")) for s in cells[3:5])
        factor = missing_factor(old, last, history, end)
        if factor is not None:
            affected[i] = factor
    if not affected:
        return "no confirmed mixed units"
    if any(end < 4 * quater or not np.isfinite(h.score[end]) for h, end in positions):
        raise ValueError(f"{path}: incomplete historical cohort")

    scales, today = [], []
    agreement = 0
    for i, (h, end) in enumerate(positions):
        old, last = (float(s.replace(",", "")) for s in rows[i][3:5])
        first = h.close[end - 4 * quater]
        adjusted = old * affected.get(i, 1)
        scale = adjusted / first
        # The report may have been generated before the closing auction. Retain
        # its observed last price and anchor past quotes on the published year-ago price.
        if abs(first - adjusted) < 0.000001:
            scale = 1.0
        elif last > 0 and abs(first * last / h.close[end] - adjusted) < .500001:
            scale = last / h.close[end]
        scales.append(scale)
        agreement += (abs(first - adjusted) <= 1 or
                      abs(first * last / h.close[end] - adjusted) <= max(1, adjusted * .002))
        q1, q2, q3 = (h.close[end - n * quater] for n in (1, 2, 3))
        today.append(2 * (last / (q1 * scale)) + q1 / q2 + q2 / q3 + q3 / first)
    if agreement * 2 <= len(rows):
        return f"session needs verification ({path.name})"
    ranks = percentile(today)
    yesterday = percentile([h.score[end-1] if end > 4 * quater else -1 for h, end in positions])
    order = sorted(range(len(rows)), key=lambda i: -today[i])
    rs_rows, trend_rows = [], []
    for i in order:
        cells = rows[i]
        h, end = positions[i]
        old, last = (float(s.replace(",", "")) for s in cells[3:5])
        # Correct the original quote in the report's own currency units.
        if i in affected:
            adjusted = old * affected[i]
            cells[3] = display_price(adjusted, modern)
            if modern:
                cells[5] = f"{(last / adjusted - 1) * 100:+.1f}%"
        diff = ranks[i] - yesterday[i]
        cells[-2] = rank_cell(ranks[i], diff, modern)
        rs_rows.append("|".join(cells))
        trend = trend_row(cells, h, end, scales[i], last, ranks[i], diff, modern)
        if trend:
            trend_rows.append(trend)
    if write:
        note = (f"> 주식 단위 변경이 누락된 과거 가격을 정정했습니다. RS와 트렌드 템플릿은 "
                f"{as_of}까지의 FDR 일봉을 사용해 당시 시장 구성 종목으로 다시 계산했습니다.")
        replace_table(output_dir / path.name, lines, rs_rows, note)
        trend_path = path.with_name(path.name.replace("-rs.markdown", "-trend-template.markdown"))
        if trend_path.exists():
            replace_table(output_dir / trend_path.name, trend_path.read_text().splitlines(), trend_rows, note)
    return "restated"


def rebuild_charts(prices, histories, actions, archive, as_of):
    sources = {path.name[:6]: path for path in prices.glob("*.csv*")}
    by_code = defaultdict(list)
    for action in actions.values():
        by_code[action.code].append(action)
    for market, config in MARKET_CONFIGS.items():
        slug = config["slug"]
        done = set()
        # A delisted symbol's latest chart uses its last published market cohort.
        for post in sorted(archive.glob(f"*-{slug}-rs.markdown"), reverse=True):
            day = post.name[:10]
            if day > as_of:
                continue
            content = post.read_text()
            if "{{ site.baseurl }}/charts/" not in content:
                continue
            names = {symbol(row[1]): row[2] for row in report_rows(content.splitlines())}
            needed = names.keys() - done
            if not needed:
                continue
            raw = {}
            for code in names:
                history = histories[code]
                end = bisect_right(history.dates, day)
                window = slice(max(0, end - 4 * quater), end)
                raw[code] = pd.Series(history.score[window], index=history.dates[window])
            ranks = chart_ranks(raw)
            for code in needed:
                frame = pd.read_csv(sources[code], index_col="Date", parse_dates=["Date"])
                adjusted = adjust_prices(frame, by_code[code], day, [])
                generate_chart_html(code, names[code], adjusted.reset_index(), chart_directory(market),
                                    chart_points(ranks[code]), market)
            done.update(needed)
        if market != "KRX":
            link = re.compile(r"(\{\{ site.baseurl \}\}/charts/)([A-Z0-9]{6}\.html)")
            for post in Path("docs/_posts").glob(f"*-{slug}-*.markdown"):
                content = post.read_text()
                updated = link.sub(rf"\g<1>{slug}/\g<2>", content)
                if updated != content:
                    post.write_text(updated)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prices", type=Path, help="FDR NAVER CSVs named CODE.csv.gz or CODE-Name.csv")
    parser.add_argument("--as-of", required=True, help="last date included in the input price set")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--original-posts", type=Path, default=Path("docs/_posts"))
    parser.add_argument("--charts", action="store_true", help="also rebuild the latest chart for each market and symbol")
    args = parser.parse_args()
    actions = read_adjustments()
    histories = histories_from(args.prices, actions, args.as_of)
    counts = Counter()
    for path in sorted(args.original_posts.glob("*-rs.markdown")):
        if path.name[:10] <= args.as_of:
            counts[repair_report(path, histories, args.as_of, args.write, Path("docs/_posts"))] += 1
    print(counts)
    if args.charts and args.write:
        rebuild_charts(args.prices, histories, actions, args.original_posts, args.as_of)


if __name__ == "__main__":
    main()
