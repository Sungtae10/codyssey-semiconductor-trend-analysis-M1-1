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

    def test_relative_performance(self):
        rel = self.res["relative"]
        for p, v in rel["by_year"].items():
            year = p[:4]
            self.expect(f"| {pct(v['diff_pctpt'])}p | {pct(v['relative_pct'])} | {v['log_gap_share_pct']:.0f}% |")
            self.expect(f"{year}년 {v['log_gap_share_pct']:.0f}%")
        self.expect(f"**{rel['skh_over_sec_multiple']:.1f}배**", f"| {pct(rel['total_relative_pct'])} | 100% |")
        first, second = rel["split_2026"]["first"], rel["split_2026"]["second"]
        self.expect(f"SK하이닉스 **{pct(first['skh_pct'])}**, 삼성전자 **{pct(first['sec_pct'])}**",
                    f"(상대 성과 {pct(first['relative_pct'])})",
                    f"SK하이닉스 **{pct(second['skh_pct'])}**, 삼성전자 **{pct(second['sec_pct'])}**",
                    f"(상대 성과 {pct(second['relative_pct'])})",
                    f"**{first['ratio_start']:.2f}배**(2025년 말)")

    def test_calendar_and_bonus(self):
        r = self.res
        self.expect(f"p = {r['month_of_year_test_p']:.2f}", f"p = {r['weekday_test']['kruskal_p_all']:.2f}",
                    f"{r['weekday_test']['kruskal_p_2023_2025']:.2f}",
                    f"평균 {r['month_of_year_unanimous']['expected']:.1f}개", f"실제는 {r['month_of_year_unanimous']['observed']}개")
        s = r["stl"]
        seas = {str(k): v for k, v in s["seasonal_effect_by_month_pct"].items()}
        self.expect(f"추세 강도 **{s['trend_strength']:.2f}**", f"계절성 강도 **{s['seasonal_strength']:.2f}**",
                    f"계절성 강도는 {s['robust_seasonal_strength']:.2f}",
                    f"평균 **{s['year_pair_corr_mean']:+.2f}**", f"**{s['seasonal_2023_2025_vs_full_corr']:+.2f}**",
                    f"6월 {seas['6']:+.1f}%", f"9월 {seas['9']:+.1f}%",
                    f"{s['trend_last_won']:,.0f}원", f"{s['observed_last_won']:,.0f}원", f"{s['trend_end_gap_pct']:.1f}% 높다",
                    f"({s['trend_change_pct']:+.1f}%)", f"({s['observed_change_pct']:+.1f}%)")
        pair = list(s["year_pair_corr"].values())
        self.expect(f"{min(pair):+.2f} ~ {max(pair):+.2f}")
        f = r["forecast"]["fan"]
        self.expect(f"{f['h20_lo95']:,.0f}원", f"{f['h20_hi95']:,.0f}원", f"{f['h20_lo95_pct']:+.0f}%", f"{f['h20_hi95_pct']:+.0f}%",
                    f"{f['sigma_daily_pct']:.1f}%")
        sm = pd.DataFrame(r["forecast"]["summary"])
        for m in ("naive", "drift", "ma20", "ma60"):
            for h in (1, 5, 20):
                self.expect(f"{sm[(sm.method == m) & (sm.h == h)]['mape_pct'].iloc[0]:.1f}%")
        cov = pd.DataFrame(r["forecast"]["coverage"])
        c20 = cov[(cov.h == 20) & (cov.level == 95)].iloc[0]
        c1 = cov[(cov.h == 1) & (cov.level == 95)].iloc[0]
        self.expect(f"**{c20['coverage_pct']:.1f}%**", f"2024년 {c20['coverage_2024_pct']:.1f}%", f"2025년 {c20['coverage_2025_pct']:.1f}%",
                    f"2026년 {c20['coverage_2026_pct']:.1f}%", f"위 {c20['above_pct']:.1f}%, 아래 {c20['below_pct']:.1f}%",
                    f"적중률은 {c1['coverage_pct']:.1f}%")

    def test_quality_numbers(self):
        q = self.res["quality"]
        basis = q["closures"]["reference_basis"]
        self.expect(f"{q['basic']['analysis_trading_days']}거래일", f"{q['closures']['weekday_non_trading_days']}일",
                    f"공휴일 {basis['holidays.KR']}일 + 근로자의 날·연말 휴장 {basis['KRX 규정']}일",
                    f"휴장일인데 거래된 날은 {len(q['closures']['reference_days_that_traded'])}일",
                    f"언론 보도 수치 {q['checkpoints']['n']}개", f"**{q['checkpoints']['passed']}개 모두 허용 오차 안**",
                    f"{q['checkpoints']['max_kospi_close_rel_error_pct']:.2f}%",
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
