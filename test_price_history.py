import datetime
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import requests

from price_history import (Adjustment, adjust_prices, collect_adjustments, confirm_adjustment,
                           read_adjustments, repair_cache_file, save_prices, share_factor)
from rs_calculator import calc_score, chart_ranks, market_listing, run_market_analysis, score_series


class PriceHistoryTests(unittest.TestCase):
    def setUp(self):
        self.days = pd.bdate_range(end="2026-11-20", periods=255, name="Date")
        self.before, self.day = self.days[-2:].strftime("%Y-%m-%d")
        self.event = Adjustment("304840", self.before, self.day, 561, 1586, 2)
        self.prices = pd.DataFrame(561, index=self.days, columns=["Open", "High", "Low", "Close"])
        self.prices.loc[self.days[-1], :] = 1586
        self.prices["Volume"] = 100

    def test_verified_split_and_ordinary_share_issue(self):
        reference = pd.DataFrame({"Close": [1122, 1586]}, index=self.days[-2:])
        factor = share_factor(25094080, 12547040)
        self.assertEqual(self.event, confirm_adjustment("304840", self.before, self.day, 561,
                                                       1586, factor, reference))
        self.assertIsNone(confirm_adjustment("304840", self.before, self.day, 1122, 1586,
                                             .5, reference))
        self.assertIsNone(share_factor(10, 10))

    def test_legacy_cache_repair_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "304840.csv")
            save_prices(self.prices, path)
            self.assertTrue(repair_cache_file(path, [self.event], self.day, []))
            content = path.read_bytes()
            self.assertFalse(repair_cache_file(path, [self.event], self.day, []))
            self.assertEqual(content, path.read_bytes())
            result = pd.read_csv(path)
            self.assertEqual(result.Open.iloc[-2], 1122)
            self.assertEqual(result.Change.iloc[-1], 1586 / 1122 - 1)
            self.assertTrue(result.Volume.eq(100).all())

    def test_multiple_actions_and_as_of_date(self):
        first = Adjustment("000001", "2026-11-17", "2026-11-18", 1000, 550, .5)
        second = Adjustment("000001", "2026-11-19", "2026-11-20", 500, 1100, 2)
        frame = self.prices.tail(4).copy()
        for col in ["Close", "High", "Open", "Low"]:
            frame[col] = [1000, 550, 500, 1100]
        corrected = adjust_prices(frame, [second, first], self.day)
        self.assertEqual(corrected.Close.tolist(), [1000, 1100, 1000, 1100])
        self.assertEqual(adjust_prices(frame, [second, first], self.before).Close.tolist(),
                         [500, 550, 500])
        pd.testing.assert_frame_equal(corrected, adjust_prices(corrected, [first, second], self.day))

    def test_ambiguous_source_is_preserved(self):
        self.prices.loc[self.days[-2], "Close"] = 810
        messages = []
        result = adjust_prices(self.prices, [self.event], self.day, messages)
        pd.testing.assert_frame_equal(self.prices, result)
        self.assertIn("304840", messages[0])

    def test_missing_reference_is_retried_after_listing_advances(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = dict(pending_path=Path(tmp, "pending.csv"), adjustments_path=Path(tmp, "ledger.csv"))
            old = pd.DataFrame([dict(Code="304840", Market="KOSDAQ", Stocks=20, Close=561)])
            new = old.assign(Stocks=10, Close=1586)
            quote = pd.DataFrame({"Close": [1122, 1586]}, index=self.days[-2:])
            actions = {}
            with patch("price_history.fdr.DataReader", side_effect=[pd.DataFrame(), quote]) as read:
                collect_adjustments(old, new, self.before, self.day, actions, **paths)
                self.assertFalse(actions)
                collect_adjustments(new, new, self.day, "2026-11-23", actions, **paths)
                self.assertEqual(read.call_args.args[0], "YAHOO:304840.KQ")
            self.assertEqual(read_adjustments(paths["adjustments_path"]), {("304840", self.day): self.event})
            self.assertTrue(pd.read_csv(paths["pending_path"]).empty)

    def yahoo_error(self, status, body):
        response = requests.Response()
        response.status_code = status
        response._content = body.encode()
        return requests.HTTPError(f"{status} Client Error", response=response)

    def test_yahoo_no_data_400_stays_pending_and_next_code_proceeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = dict(pending_path=Path(tmp, "pending.csv"), adjustments_path=Path(tmp, "ledger.csv"))
            stale = dict(code="043220", previous_date="2025-12-08", date="2025-12-09",
                         previous_close=171, close=1710, factor=10.0, market="KOSDAQ")
            split = dict(code="304840", previous_date=self.before, date=self.day,
                         previous_close=561, close=1586, factor=2.0, market="KOSDAQ")
            pd.DataFrame([stale, split]).to_csv(paths["pending_path"], index=False)
            listing = pd.DataFrame([dict(Code="043220", Market="KOSDAQ", Stocks=10, Close=171),
                                    dict(Code="304840", Market="KOSDAQ", Stocks=10, Close=1586)])
            no_data = self.yahoo_error(400, '{"chart":{"result":null,"error":{"code":"Bad Request",'
                                       '"description":"Data doesn\'t exist for startDate = 1765152000, '
                                       'endDate = 1765324800"}}}')
            quote = pd.DataFrame({"Close": [1122, 1586]}, index=self.days[-2:])
            actions = {}
            with (patch("price_history.fdr.DataReader", side_effect=[no_data, quote]) as read,
                  self.assertLogs(level="WARNING")):
                collect_adjustments(listing, listing, self.day, "2026-11-23", actions, **paths)
            self.assertEqual(read.call_count, 2)
            self.assertEqual(actions, {("304840", self.day): self.event})
            pending = pd.read_csv(paths["pending_path"], dtype={"code": str})
            self.assertEqual(pending.to_dict("records"), [stale])

    def test_other_yahoo_400_propagates(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = dict(pending_path=Path(tmp, "pending.csv"), adjustments_path=Path(tmp, "ledger.csv"))
            row = dict(code="043220", previous_date="2025-12-08", date="2025-12-09",
                       previous_close=171, close=1710, factor=10.0, market="KOSDAQ")
            listing = pd.DataFrame([dict(Code="043220", Market="KOSDAQ", Stocks=10, Close=171)])
            bodies = ['{"chart":{"result":null,"error":{"code":"Bad Request",'
                      '"description":"Invalid input - interval=1x is not supported"}}}',
                      "<html>Bad Request</html>"]
            for body in bodies:
                pd.DataFrame([row]).to_csv(paths["pending_path"], index=False)
                with patch("price_history.fdr.DataReader", side_effect=self.yahoo_error(400, body)):
                    with self.assertRaises(requests.HTTPError):
                        collect_adjustments(listing, listing, self.day, "2026-11-23", {}, **paths)
                self.assertEqual(len(pd.read_csv(paths["pending_path"])), 1)

    def test_vector_scores_and_chart_ranks(self):
        close = pd.Series(np.linspace(2600, 1900, len(self.days)), index=self.days)
        data = pd.DataFrame({"Close": close})
        self.assertAlmostEqual(score_series(close).iloc[-1], calc_score(data))
        first = pd.Series([0., 1.], index=["a", "b"])
        second = pd.Series([1.], index=["b"])
        ranks = chart_ranks({"first": first, "second": second})
        self.assertEqual(ranks["first"].to_list(), [99, 74])

    def test_daily_listing_uses_trading_session_and_keeps_stale_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "kosdaq.csv")
            listing = pd.DataFrame([dict(Code="001234", Market="KOSDAQ", Stocks=50, Close=561)])
            listing.assign(SnapshotDate=self.before).to_csv(path)
            config = dict(list_filename=path, slug="kosdaq", target="KOSDAQ")
            calendar = pd.DataFrame({"Close": [100, 110]}, index=self.days[-2:])
            with (patch("rs_calculator.fdr.StockListing", side_effect=[listing, listing.assign(Close=565)]),
                  patch("rs_calculator.fdr.DataReader", return_value=calendar),
                  patch("rs_calculator.collect_adjustments") as collect):
                market_listing(config, "2026-11-21", {}, False)
                self.assertEqual(pd.read_csv(path).SnapshotDate[0], self.before)
                market_listing(config, "2026-11-21", {}, False)
                self.assertEqual(pd.read_csv(path).SnapshotDate[0], self.day)
                self.assertEqual(collect.call_args.args[2:4], (self.before, self.day))

    def test_normal_entry_point_preserves_both_market_charts(self):
        # Replay an existing report day offline using its archived constituents.
        from price_history import write_adjustments
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path.cwd()
            os.chdir(tmp)
            try:
                posts = Path("docs/_posts")
                posts.mkdir(parents=True)
                write_adjustments({("304840", self.day): self.event})
                for slug in ("kosdaq", "krx"):
                    (posts / f"{self.day}-{slug}-rs.markdown").write_text(
                        "|[304840](old)|타임X AI|561|1586|98 |\n")
                with (patch("rs_calculator.fdr.StockListing", side_effect=AssertionError),
                      patch("rs_calculator.fdr.DataReader", return_value=self.prices) as read,
                      patch("rs_calculator.dt", wraps=datetime) as clock, patch("rs_calculator.time.sleep"),
                      redirect_stdout(io.StringIO())):
                    clock.date.today.return_value = datetime.date(2026, 11, 22)
                    clock.datetime.strptime.side_effect = datetime.datetime.strptime
                    run_market_analysis("KOSDAQ", self.day)
                    run_market_analysis("KRX", self.day)
                    self.assertEqual(read.call_count, 1)
                    self.assertEqual(read.call_args.args[0], "NAVER:304840")
                for market, folder in [("KOSDAQ", "kosdaq/"), ("KRX", "")]:
                    html = Path(f"docs/charts/{folder}304840.html").read_text()
                    self.assertIn(f"{market} RS 백분위", html)
                    report = (posts / f"{self.day}-{market.lower()}-rs.markdown").read_text()
                    self.assertIn(f"/charts/{folder}304840.html", report)
                    self.assertIn("1,122", report)
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
