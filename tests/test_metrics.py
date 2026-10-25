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
