"""리포트 숫자 감사: 원자료에서 처음부터 다시 계산한 값이 REPORT.md 본문에 그대로 적혀 있는지 확인한다.

리포트 문장을 고치다가 숫자를 잘못 옮기거나, 데이터가 바뀌었는데 리포트를 안 고친 경우를 잡아낸다.
실행: python -m unittest discover -s tests -v
"""
import json
import unittest

import pandas as pd

from src import config as C
from src import prepare
from src.run_all import compute_results

REPORT = (C.ROOT / "REPORT.md").read_text(encoding="utf-8")


def pct(v, d=1):
    return f"{v:+,.{d}f}%"


class TestReportNumbers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stocks, kospi = prepare.load_raw()
        cls.d = prepare.build_daily(stocks, kospi)
        cls.res, _ = compute_results(stocks, kospi, cls.d)

    def expect(self, *texts):
        for t in texts:
            with self.subTest(text=t):
                self.assertTrue(t in REPORT, f"REPORT.md 에 '{t}' 가 없음")

    def test_returns(self):
        P = self.res["period"]
        for key in ("SEC", "SKH", "KOSPI"):
            for period in ("2023", "2024", "2025", "2026YTD", "전체"):
                self.expect(pct(P[key][period]["return_pct"]))
        for key in ("SEC", "SKH", "KOSPI"):
            st = P[key]["전체"]
            self.expect(f"{st['end_value'] / st['base_value']:.1f}배")

    def test_volatility_and_drawdown(self):
        P = self.res["period"]
        for period in ("2023", "2024", "2025", "2026YTD"):
            self.expect(f"{P['SEC'][period]['ann_vol_pct']:.1f}%")
        self.expect(f"{P['SEC']['2024']['mdd_pct']:.1f}%", f"{P['SEC']['2026YTD']['mdd_pct']:.1f}%",
                    f"{P['SKH']['전체']['mdd_pct']:.1f}%", f"{P['KOSPI']['2024']['mdd_pct']:.1f}%")
        v = self.res["volatility"]["sec"]
        self.expect(f"{v['std_daily_2023_2025_pct']:.2f}%", f"{v['std_daily_2026_pct']:.2f}%",
                    f"{v['std_daily_2026_pct'] / v['std_daily_2023_2025_pct']:.1f}배",
                    f"{v['z_20260731_vs_2023_2025']:.1f} 표준편차",
                    f"{v['vol20_max_pct']:.1f}%", f"{v['vol20_min_pct']:.1f}%")

    def test_trend_points(self):
        r = self.res
        self.expect(f"{r['sec_low']['value']:,.0f}원", f"{r['sec_high']['value']:,.0f}원",
                    f"{r['drawdown']['SEC']['current_pct']:.1f}%")
        dates = {pd.Timestamp(c["date"]).strftime("%Y-%m-%d") for c in r["crossovers"]}
        april = {"2025-04-08", "2025-04-09", "2025-04-10"}
        self.assertTrue(april <= dates)          # 2025년 4월 사흘 연속 교차는 리포트에 '2025-04-08~10'으로 적었다
        self.expect("2025-04-08~10", *sorted(dates - april))
        for y, v in r["above_ma120_pct_by_year"].items():
            self.expect(f"{v:.1f}%")

    def test_extremes_and_coupling(self):
        r = self.res
        q = r["quality"]["statistical_extremes"]
        self.expect(f"급변일(|z| > 3) {q['sec']['count']}일 중 **{q['sec']['by_year']['2026']}일이 2026년**")
        self.expect(f"**{r['extremes']['sec_with_rest_market_same_dir']}일**", f"**{r['extremes']['sec_with_rest_market_same_dir_2pct']}일**")
        yc = {row["year"]: row for row in r["yearly_corr"]}
        for y in (2023, 2024, 2025, 2026):
            self.expect(f"| {y} | {yc[y]['corr_sec_skh']:.2f} | {yc[y]['corr_sec_ex2']:.2f} | {yc[y]['corr_sec_kospi']:.2f} |")
        cz = r["concentration"]
        self.expect(f"{cz['share_start_pct']:.1f}%", f"{cz['share_2025_end_pct']:.1f}%", f"{cz['share_max_pct']:.1f}%",
                    f"{cz['share_end_pct']:.1f}%", f"{cz['share_20260622_pct']:.2f}%",
                    f"{cz['ratio_start']:.1f}배", f"{cz['ratio_2024_end']:.1f}배", f"{cz['ratio_min']:.2f}배", f"{cz['ratio_end']:.2f}배")

    def test_calendar_and_bonus(self):
        r = self.res
        self.expect(f"p = {r['month_of_year_test_p']:.2f}", f"p = {r['weekday_test']['kruskal_p_all']:.2f}",
                    f"{r['weekday_test']['kruskal_p_2023_2025']:.2f}",
                    f"평균 {r['month_of_year_unanimous']['expected']:.1f}개", f"실제는 {r['month_of_year_unanimous']['observed']}개")
        s = r["stl"]
        self.expect(f"**{s['trend_strength']:.2f}**", f"**{s['seasonal_strength']:.2f}**",
                    f"**{s['year_pair_corr_mean']:.2f}**", f"**{s['seasonal_2023_2025_vs_full_corr']:.2f}**",
                    f"{s['trend_change_pct']:+.1f}%")
        f = r["forecast"]["fan"]
        self.expect(f"{f['h20_lo95']:,.0f}원", f"{f['h20_hi95']:,.0f}원", f"{f['h20_lo95_pct']:+.0f}%", f"{f['h20_hi95_pct']:+.0f}%",
                    f"{f['sigma_daily_pct']:.1f}%")
        sm = pd.DataFrame(r["forecast"]["summary"])
        for m in ("naive", "drift", "ma20", "ma60"):
            for h in (1, 5, 20):
                self.expect(f"{sm[(sm.method == m) & (sm.h == h)]['mape_pct'].iloc[0]:.1f}%")

    def test_quality_numbers(self):
        q = self.res["quality"]
        self.expect(f"{q['basic']['analysis_trading_days']}거래일", f"{q['closures']['weekday_non_trading_days']}일",
                    f"{q['checkpoints']['n']}개", f"{q['checkpoints']['max_kospi_close_rel_error_pct']:.2f}%",
                    f"{q['checkpoints']['mean_kospi_close_rel_error_pct']:.2f}%",
                    f"{q['checkpoints']['max_kospi_change_abs_error_pctpt']:.3f}%p",
                    f"{q['checkpoints']['n_stock_items']}개")

    def test_committed_results_are_current(self):
        saved = json.loads(C.METRICS_JSON.read_text(encoding="utf-8"))
        for key in ("SEC", "SKH", "KOSPI"):
            self.assertAlmostEqual(saved["period"][key]["전체"]["return_pct"], self.res["period"][key]["전체"]["return_pct"], places=4)
        js = (C.DOCS_DIR / "data" / "dashboard-data.js").read_text(encoding="utf-8")
        data = json.loads(js[js.index("{"): js.rstrip().rindex("}") + 1])
        for key in ("SEC", "SKH", "KOSPI"):
            self.assertAlmostEqual(data["check"][key]["mdd_pct"], self.res["period"][key]["전체"]["mdd_pct"], places=3)


if __name__ == "__main__":
    unittest.main()
