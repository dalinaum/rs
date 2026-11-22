"""Apply changes of share unit verified by two independent FinanceDataReader series."""

from dataclasses import asdict, dataclass, fields
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from tempfile import NamedTemporaryFile
import csv
import os
import logging

import FinanceDataReader as fdr
import numpy as np
import pandas as pd


OHLC = ["Open", "High", "Low", "Close"]
ADJUSTMENTS = Path("price-adjustments.csv")


@dataclass(frozen=True)
class Adjustment:
    code: str
    previous_date: str
    date: str
    previous_close: float
    close: float
    factor: float


def read_adjustments(path=ADJUSTMENTS):
    if not path.exists():
        return {}
    with path.open() as f:
        rows = [Adjustment(r["code"], r["previous_date"], r["date"],
                           float(r["previous_close"]), float(r["close"]), float(r["factor"]))
                for r in csv.DictReader(f)]
    return {(r.code, r.date): r for r in rows}


@contextmanager
def atomic_csv(path):
    path = Path(path)
    temp = NamedTemporaryFile("w", dir=path.parent, delete=False, newline="", encoding="utf-8")
    try:
        with temp as f:
            yield f
        os.replace(temp.name, path)
    finally:
        Path(temp.name).unlink(missing_ok=True)


def write_adjustments(actions, path=ADJUSTMENTS):
    with atomic_csv(path) as f:
        writer = csv.DictWriter(f, fieldnames=[field.name for field in fields(Adjustment)],
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(asdict(actions[key]) for key in sorted(actions))


def share_factor(old_shares, new_shares):
    if old_shares <= 0 or new_shares <= 0 or old_shares == new_shares:
        return None
    # Fractional shares are cancelled on a consolidation. Recover the quoted
    # ratio only if it explains the recorded share counts to within one share.
    ratio = Fraction(int(old_shares), int(new_shares)).limit_denominator(1000)
    if ratio != 1 and abs(old_shares / ratio - new_shares) <= 1:
        return float(ratio)
    return None


def confirm_adjustment(code, before, after, old_close, new_close, factor, reference):
    """A share issue alone is not a split. Check the change of unit in adjusted closes."""
    close = reference.Close.reindex(pd.to_datetime([before, after]))
    if len(close.dropna()) != 2 or min(old_close, new_close, *close) <= 0:
        return None
    # Ratios at the two sessions cancel later splits in the reference series.
    prior_in_new_units = new_close * close.iloc[0] / close.iloc[1]
    if abs(prior_in_new_units - old_close) <= 1:
        return None
    if abs(prior_in_new_units - old_close * factor) > 1:
        return None
    return Adjustment(code, before, after, float(old_close), float(new_close), factor)


def adjust_prices(prices, actions, as_of, unresolved=None):
    """Apply only missing conversions; an upstream revision may already include them."""
    prices = prices.loc[:as_of].copy()
    if prices.empty:
        return prices
    changed = False
    for action in sorted(actions, key=lambda a: a.date):
        if action.date > as_of or prices.index[0] >= pd.Timestamp(action.date):
            continue
        if action.previous_date not in prices.index or action.date not in prices.index:
            note = f"{action.code} {action.date}: 보정 검증에 필요한 거래일 누락"
            if unresolved is None:
                raise ValueError(note)
            unresolved.append(note)
            continue
        old = prices.at[action.previous_date, "Close"]
        new = prices.at[action.date, "Close"]
        if not np.isfinite([old, new]).all() or min(old, new) <= 0:
            note = f"{action.code} {action.date}: 유효한 전후 종가 없음"
            if unresolved is None:
                raise ValueError(note)
            unresolved.append(note)
            continue
        implied = (old / new) * action.close
        adjusted_old = action.previous_close * action.factor
        if np.isclose(implied, adjusted_old, atol=1, rtol=0.002):
            continue
        if abs(implied - action.previous_close) > 1:
            note = f"{action.code} {action.date}: 가격 단위를 검증할 수 없음"
            if unresolved is None:
                raise ValueError(note)
            unresolved.append(note)
            continue
        prices[OHLC] = prices[OHLC].astype(float)
        prices.loc[prices.index < action.date, OHLC] *= action.factor
        changed = True
    if changed:
        prices["Change"] = prices.Close.pct_change()
    return prices


def collect_adjustments(previous, current, previous_day, day, actions, *,
                        pending_path=Path("pending-price-checks.csv"), adjustments_path=ADJUSTMENTS):
    """Recheck unverified observations even after the daily listing file advances."""
    previous = previous.set_index("Code")
    current = current.set_index("Code")
    candidates = {}
    if pending_path.exists():
        with pending_path.open() as f:
            for row in csv.DictReader(f):
                candidates[row["code"], row["date"]] = row
    for code in previous.index.intersection(current.index):
        old, new = previous.loc[code], current.loc[code]
        factor = share_factor(old.Stocks, new.Stocks)
        if factor is None or min(old.Close, new.Close) <= 0:
            continue
        candidates[code, day] = {"code": code, "previous_date": previous_day, "date": day,
                                 "previous_close": old.Close, "close": new.Close,
                                 "factor": factor, "market": new.Market}
    pending = []
    count = len(actions)
    for key, row in candidates.items():
        if key in actions:
            continue
        code, date = key
        if code not in current.index:
            pending.append(row)
            continue
        before = row["previous_date"]
        suffix = "KS" if row["market"] == "KOSPI" else "KQ"
        try:
            reference = fdr.DataReader(f"YAHOO:{code}.{suffix}", before,
                                       pd.Timestamp(date) + pd.Timedelta(days=1))
        except (OSError, KeyError) as exc:
            # FDR's Yahoo reader raises HTTPError (an OSError) for missing
            # symbols and KeyError("timestamp") for an empty chart.
            if (getattr(getattr(exc, "response", None), "status_code", None) != 404
                    and exc.args != ("timestamp",)):
                raise
            reference = pd.DataFrame()
        dates = reference.loc[before:date].index if not reference.empty else []
        if list(dates) != list(pd.to_datetime([before, date])) or reference.loc[before:date, "Close"].isna().any():
            logging.warning("%s %s: FDR 전후 거래일 확인 보류", code, date)
            pending.append(row)
            continue
        action = confirm_adjustment(code, before, date, float(row["previous_close"]),
                                    float(row["close"]), float(row["factor"]), reference)
        if action:
            actions[key] = action
        else:
            before_close, after_close = reference.loc[before:date, "Close"]
            if after_close <= 0 or abs(float(row["close"]) * before_close / after_close
                                       - float(row["previous_close"])) > 1:
                pending.append(row)
                logging.warning("%s %s: FDR 종가와 주식수 변동 비율 불일치", code, date)
    if len(actions) != count:
        write_adjustments(actions, adjustments_path)
    if candidates or pending_path.exists():
        columns = ["code", "previous_date", "date", "previous_close", "close", "factor", "market"]
        with atomic_csv(pending_path) as f:
            pd.DataFrame(pending, columns=columns).to_csv(f, index=False)


def save_prices(prices, path):
    with atomic_csv(path) as f:
        prices.to_csv(f, index_label="Date")


def repair_cache_file(path, actions, as_of, unresolved):
    cached = pd.read_csv(path, index_col="Date", parse_dates=["Date"])
    corrected = adjust_prices(cached, actions, as_of, unresolved)
    if corrected.equals(cached):
        return False
    save_prices(corrected, path)
    return True


if __name__ == "__main__":
    import argparse
    from collections import defaultdict
    from datetime import date

    parser = argparse.ArgumentParser(description="Repair verified unit changes in local daily price caches.")
    parser.add_argument("cache", type=Path, help="DATA directory containing dated subdirectories")
    root = parser.parse_args().cache
    groups = defaultdict(list)
    for event in read_adjustments().values():
        groups[event.code].append(event)
    unresolved = []
    count = 0
    for path in root.glob("*/*.csv"):
        day = date.fromisoformat(path.parent.name).isoformat()
        events = groups.get(path.name.split("-")[0], [])
        if any(e.date <= day for e in events):
            count += repair_cache_file(path, events, day, unresolved)
    for message in dict.fromkeys(unresolved):
        print(message)
    print(f"가격 캐시 {count}개 수정")
