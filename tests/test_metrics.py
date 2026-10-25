"""지표 계산 함수 단위 테스트: 손으로 계산할 수 있는 작은 예제로 정의가 맞는지 확인한다.

실행: python -m unittest discover -s tests -v
"""
import math
import unittest

import numpy as np
import pandas as pd

from src import config as C
from src import metrics as M
from src.fetch_data import kospi_market_daily


class TestBasics(unittest.TestCase):
    def test_moving_average_needs_full_window(self):
        s = pd.Series([1.0, 2, 3, 4, 5])
        ma = M.moving_average(s, 3)
        self.assertTrue(math.isnan(ma.iloc[0]) and math.isnan(ma.iloc[1]))
        self.assertEqual(ma.iloc[2:].tolist(), [2.0, 3.0, 4.0])

    def test_drawdown_and_max_drawdown(self):
        idx = pd.date_range("2024-01-01", periods=5, freq="D")
        s = pd.Series([100.0, 120, 90, 130, 65], index=idx)
        self.assertEqual(M.drawdown_pct(s).round(6).tolist(), [0.0, 0.0, -25.0, 0.0, -50.0])
        mdd = M.max_drawdown(s)
        self.assertAlmostEqual(mdd["mdd_pct"], -50.0)
        self.assertEqual(mdd["peak_date"], idx[3])
        self.assertEqual(mdd["trough_date"], idx[4])

    def test_annualized_vol_uses_sample_std_and_sqrt_252(self):
        r = pd.Series([1.0, -1.0, 1.0, -1.0])
        expected = np.std([1, -1, 1, -1], ddof=1) * math.sqrt(252)
        self.assertAlmostEqual(M.annualized_vol_pct(r), expected)

    def test_crossovers(self):
        idx = pd.date_range("2024-01-01", periods=6, freq="D")
        short = pd.Series([1, 1, 3, 3, 1, 1.0], index=idx)
        long = pd.Series([2, 2, 2, 2, 2, 2.0], index=idx)
        cx = M.crossovers(short, long)
        self.assertEqual(cx["type"].tolist(), ["골든 크로스", "데드 크로스"])
        self.assertEqual(cx["date"].tolist(), [idx[2], idx[4]])

    def test_month_end_returns(self):
        idx = pd.to_datetime(["2023-12-28", "2024-01-15", "2024-01-31", "2024-02-29"])
        s = pd.Series([100.0, 90, 110, 99], index=idx)
        r = M.month_end_returns(s).round(6)
        self.assertEqual(r.tolist(), [10.0, -10.0])


class TestPeriodStats(unittest.TestCase):
    def test_period_return_starts_from_previous_trading_day(self):
        idx = pd.to_datetime(["2023-12-28", "2024-01-02", "2024-01-03", "2024-01-04"])
        close = pd.Series([100.0, 110, 99, 121], index=idx)
        d = pd.DataFrame({"sec_close": close, "sec_ret": close.pct_change() * 100})
        st = M.period_stats(d, "SEC", "2024-01-01", "2024-12-31")
        self.assertEqual(st["base_date"], idx[0])
        self.assertAlmostEqual(st["return_pct"], 21.0)
        self.assertAlmostEqual(st["mdd_pct"], -10.0)        # 110 → 99
        self.assertEqual(st["n_days"], 3)
        self.assertAlmostEqual(st["up_day_ratio_pct"], 200 / 3)


class TestRelativePerformance(unittest.TestCase):
    def test_relative_returns_and_log_gap_shares(self):
        # 연도별 마지막 거래일만 둔 작은 예제. 직전 거래일 종가가 출발점이다.
        idx = pd.to_datetime(["2022-12-29", "2023-12-28", "2024-12-30", "2025-12-30", "2026-06-22", "2026-10-22"])
        sec = pd.Series([100.0, 150, 75, 150, 300, 240], index=idx)      # +50%, -50%, +100%, +60%
        skh = pd.Series([100.0, 200, 150, 450, 1350, 810], index=idx)    # +100%, -25%, +200%, +80%
        d = pd.DataFrame({"sec_close": sec, "skh_close": skh,
                          "sec_ret": sec.pct_change() * 100, "skh_ret": skh.pct_change() * 100,
                          "mcap_ratio_sec_skh": sec / skh})
        out = M.relative_performance(d, d.loc["2023-01-02":])
        rel = {k: round(v["relative_pct"], 6) for k, v in out["by_year"].items()}
        self.assertEqual(rel, {"2023": -25.0, "2024": round(-100 / 3, 6), "2025": round(-100 / 3, 6), "2026YTD": round(-100 / 9, 6)})
        self.assertAlmostEqual(sum(v["log_gap_share_pct"] for v in out["by_year"].values()), 100.0)
        self.assertAlmostEqual(out["skh_over_sec_multiple"], 8.1 / 2.4)       # 8.1배 ÷ 2.4배
        first, second = out["split_2026"]["first"], out["split_2026"]["second"]
        self.assertEqual((first["start"], first["end"], second["end"]), (idx[3], idx[4], idx[5]))
        self.assertAlmostEqual(first["relative_pct"], -100 / 3)                # 2배 ÷ 3배 − 1
        self.assertAlmostEqual(second["relative_pct"], 100 / 3)                # 0.8배 ÷ 0.6배 − 1


class TestBonusMethods(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src import advanced as A
        from src import prepare
        stocks, kospi = prepare.load_raw()
        cls.d = prepare.build_daily(stocks, kospi)
        cls.A = A

    def test_stl_seasonal_shape_is_fixed_across_years(self):
        parts, info = self.A.stl_decompose(self.d)
        spread = parts["seasonal"].groupby(parts.index.month).agg(lambda v: v.max() - v.min())
        self.assertLess(spread.max(), 1e-3)          # 같은 달 계절 성분이 해마다 같다(로그 0.1% 미만 차이)
        self.assertEqual(info["seasonal_deg"], 0)

    def test_interval_coverage_is_a_share_of_backtest_origins(self):
        cov = self.A.fan_coverage(self.d)
        bt = self.A.backtest(self.d)
        for h in self.A.HORIZONS:
            n_bt = int((bt[(bt["h"] == h) & (bt["method"] == "naive")]).shape[0])
            row = cov[(cov["h"] == h) & (cov["level"] == 95)].iloc[0]
            self.assertEqual(int(row["n"]), n_bt)
            self.assertAlmostEqual(row["coverage_pct"] + row["above_pct"] + row["below_pct"], 100.0)


class TestKospiProxy(unittest.TestCase):
    def test_cap_weighting_excludes_preferred_and_new_listing(self):
        rows = [
            # 날짜, 코드, 등락률(%), 시가총액, 시장
            ("2024-01-02", "000010", 0.0, 300.0, "KOSPI"),
            ("2024-01-02", "000020", 0.0, 100.0, "KOSPI"),
            ("2024-01-02", "000015", 0.0, 50.0, "KOSPI"),    # 우선주(끝자리 5): 제외
            ("2024-01-03", "000010", 10.0, 330.0, "KOSPI"),
            ("2024-01-03", "000020", -10.0, 90.0, "KOSPI"),
            ("2024-01-03", "000015", 30.0, 65.0, "KOSPI"),
            ("2024-01-03", "000030", 30.0, 999.0, "KOSPI"),  # 신규 상장 첫날: 전일 가중치 없음 → 제외
            ("2024-01-03", "000040", 50.0, 10.0, "KOSDAQ"),  # 다른 시장: 제외
        ]
        df = pd.DataFrame(rows, columns=["Date", "Code", "ChangesRatio", "Marcap", "Market"])
        df["Date"] = pd.to_datetime(df["Date"])
        out = kospi_market_daily(df, "2024-01-03", "2024-01-03").iloc[0]
        # (300×10 + 100×(−10)) / 400 = 5.0%
        self.assertAlmostEqual(out["ret_kospi_pct"], 5.0)
        self.assertEqual(out["n_constituents"], 2)
        # 시가총액 합계는 우선주 포함(삼성·SK 비중 계산용)
        self.assertEqual(out["mcap_kospi_total"], 330 + 90 + 65 + 999)


if __name__ == "__main__":
    unittest.main()
