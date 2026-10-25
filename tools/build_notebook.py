"""analysis.ipynb 를 만들고 실행해 출력까지 저장한다.

노트북 본문의 숫자는 계산 결과에서 바로 넣어, 리포트·그림과 같은 숫자를 쓰게 한다.
실행: python tools/build_notebook.py   (저장소 루트 기준, nbformat·nbclient·ipykernel 필요)
"""
from __future__ import annotations

import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import prepare  # noqa: E402
from src.run_all import compute_results  # noqa: E402

stocks, kospi = prepare.load_raw()
daily = prepare.build_daily(stocks, kospi)
R, _ = compute_results(stocks, kospi, daily)
P = R["period"]
Q = R["quality"]


def pct(v, d=1):
    return f"{v:+,.1f}%" if d == 1 else f"{v:+,.{d}f}%"


md, code = nbformat.v4.new_markdown_cell, nbformat.v4.new_code_cell
cells = []

cells.append(md(f"""# 삼성전자 주가 트렌드 분석 노트북 (2023.1 ~ 2026.10)

이 노트북은 [REPORT.md](REPORT.md)의 분석을 처음부터 순서대로 다시 실행한다. 계산 함수는 `src/` 폴더에 있고, 노트북과 `python -m src.run_all` 스크립트가 같은 함수를 쓴다.

| 단계 | 내용 |
|---|---|
| 1 | 데이터 불러오기와 기본 정보 (기간, 컬럼, 결측치) |
| 2 | 결측치·이상치 점검과 처리 기준 |
| 3 | 시계열 지표 계산 (이동평균, 수익률, 변동성, 낙폭, 상관) |
| 4 | 질문 5개에 대한 시각화와 관찰·해석 |
| 5 | 보너스: STL 분해, 베이스라인 예측 |

**실행 방법:** 저장소 루트에서 `jupyter notebook analysis.ipynb`를 열고 위에서부터 차례로 실행한다(약 20초). 그림은 `images/` 폴더에 다시 저장된다.

**분석 질문**
1. Q1 추세: 삼성전자 주가는 어떤 국면을 거쳤고 추세는 언제 바뀌었나?
2. Q2 상대 성과: SK하이닉스·KOSPI와 비교하면 어땠나?
3. Q3 변동성: 변동성은 언제 커졌고, 급변일은 시장 전체 충격과 겹치나?
4. Q4 동조화: 시장·SK하이닉스와 함께 움직인 정도는 어떻게 변했나?
5. Q5 계절성: 특정 달·요일의 반복 패턴이 있나?"""))

cells.append(md("## 0. 준비"))
cells.append(code("""import sys
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "src").exists() else Path.cwd().parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from IPython.display import Image, display

from src import config as C, prepare, quality, metrics as M, advanced as A, plots as P
from src.run_all import compute_results

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 30)
font = P.setup_style()
print("그래프 한글 글꼴:", font)"""))

cells.append(md("## 1. 데이터 불러오기와 기본 정보"))
cells.append(code("""stocks, kospi = prepare.load_raw()
print("종목 원자료:", stocks.shape, "| KOSPI 집계:", kospi.shape)
print("수집 기간:", stocks["Date"].min().date(), "~", stocks["Date"].max().date())
print("종목별 행 수:", stocks.groupby("Name").size().to_dict())
stocks.head(4)"""))
cells.append(code("""print("컬럼과 자료형")
stocks.dtypes.to_frame("dtype").T"""))
cells.append(code("""kospi.tail(3)"""))
cells.append(md(f"""- 원천은 한국거래소(KRX) 전종목 일별 시세이고, 공개 저장소 FinanceData/marcap의 커밋 `eeed081`로 고정했다.
- 분석 기간은 **2023-01-02 ~ 2026-10-22, {Q['basic']['analysis_trading_days']}거래일**이다. 그 앞 125거래일(2022-07-01 ~ 2022-12-29)은 120일 이동평균 계산용 준비 구간이다.
- KOSPI는 같은 원천에서 'KOSPI 보통주의 전일 시가총액 가중 등락률'로 직접 계산했다. 보도된 공식 종가 {Q['checkpoints']['n_kospi_close']}개 시점과 비교한 차이는 최대 {Q['checkpoints']['max_kospi_close_rel_error_pct']:.2f}%다."""))

cells.append(md("""## 2. 결측치·이상치 점검

| 점검 | 기준 | 처리 |
|---|---|---|
| 결측치 | 빈 값 개수 | 0이어야 한다 |
| 거래일 누락 | 공휴일 달력·KRX 규정으로 데이터와 따로 만든 휴장일 목록과 두 방향 대조 | 휴장일이면 결측이 아니므로 채우지 않는다 |
| 오류형 이상치 | 가격 논리, 가격제한폭 ±30%, 전일대비 일관성 | 발견되면 제외 대상 |
| 통계적 극단값 | \\|z\\| > 3 | 실제 사건이므로 지우지 않고 '급변일'로 표시 |
| 교차 출처 대조 | 언론 보도 수치와 비교 | 데이터 신뢰도 확인 |"""))
cells.append(code("""daily = prepare.build_daily(stocks, kospi)
q, cp = quality.run_quality_checks(stocks, kospi, daily)
summary = pd.DataFrame([
    ("결측치(종목 원자료)", sum(q["missing"]["stocks"].values())),
    ("결측치(KOSPI 집계)", sum(q["missing"]["kospi"].values())),
    ("(날짜, 종목) 중복", q["duplicates"]),
    ("데이터에 없는 평일", q["closures"]["weekday_non_trading_days"]),
    ("그중 휴장일로 설명되지 않는 날", len(q["closures"]["unexplained"])),
    ("휴장일인데 거래된 날 (반대 방향 대조)", len(q["closures"]["reference_days_that_traded"])),
    ("가격 논리 위반", q["error_outliers"]["ohlc_logic_violations"]),
    ("가격제한폭(±30%) 초과", q["error_outliers"]["price_limit_violations"]),
    ("전일대비 불일치", q["error_outliers"]["changes_mismatch"]),
    ("등락률 불일치", q["error_outliers"]["ratio_mismatch"]),
    ("교차 대조 통과 / 전체", f"{q['checkpoints']['passed']} / {q['checkpoints']['n']}"),
], columns=["점검", "결과"])
print("모든 필수 점검 통과:", q["all_hard_checks_passed"])
summary"""))
cells.append(code("""closures = pd.read_csv(C.CLOSURES_CSV)
print("휴장 사유 예시")
closures.head(8)"""))
cells.append(code("""ext = pd.DataFrame({k: v["by_year"] for k, v in q["statistical_extremes"].items()}).rename(
    columns={"sec": "삼성전자", "skh": "SK하이닉스", "kospi": "KOSPI"})
ext.loc["합계"] = ext.sum()
print("연도별 급변일(|z| > 3) 개수")
ext"""))
cells.append(code("""print("언론 보도 수치와 대조 (일부)")
cp[["date", "item", "official", "ours", "error", "pass"]].head(12)"""))
cells.append(md(f"""**처리 결정:** 결측과 오류형 이상치가 0건이라 지우거나 고친 값이 없다. 급변일은 삼성전자 {Q['statistical_extremes']['sec']['count']}일인데, 2026-07-31(+26.81%)처럼 보도로 확인되는 실제 사건이므로 유지한다. 지우면 2026년의 위험이 실제보다 작게 계산된다."""))

cells.append(md("## 3. 시계열 지표 계산"))
cells.append(code("""res, extras = compute_results(stocks, kospi, daily)
ps = M.period_summary(daily)
table = ps.pivot(index="period", columns="series", values="return_pct").loc[["2023", "2024", "2025", "2026YTD", "전체"]]
table = table[["SEC", "SKH", "KOSPI"]].rename(columns={"SEC": "삼성전자", "SKH": "SK하이닉스", "KOSPI": "KOSPI(재계산)"})
print("기간 수익률 (%) : 직전 연도 마지막 거래일 종가 대비")
table.round(1)"""))
cells.append(code("""vol = ps.pivot(index="period", columns="series", values="ann_vol_pct").loc[["2023", "2024", "2025", "2026YTD", "전체"]]
mdd = ps.pivot(index="period", columns="series", values="mdd_pct").loc[["2023", "2024", "2025", "2026YTD", "전체"]]
print("연환산 변동성(%)과 최대 낙폭(%)")
pd.concat({"변동성": vol[["SEC", "SKH", "KOSPI"]], "최대 낙폭": mdd[["SEC", "SKH", "KOSPI"]]}, axis=1).round(1)"""))
cells.append(md("""- **이동평균** 20·60·120일, **누적 지수**(2022-12-29 = 100), **고점 대비 낙폭**, **20일 연환산 변동성**(표준편차 × √252), **60일 상관계수**를 `prepare.build_daily`가 한 번에 계산한다.
- 집계 단위: 추세·변동성·급변일은 일 단위(사건 날짜를 맞추려고), 계절성·STL은 월 단위(일 단위 잡음이 커서)."""))

cells.append(md("## 4. 질문별 분석\n\n### Q1. 추세: 네 국면과 전환점"))
cells.append(code("""display(Image(filename=P.fig_price_trend(daily, res)))
pd.DataFrame(res["crossovers"]).assign(date=lambda x: pd.to_datetime(x["date"]).dt.date)"""))
cells.append(md(f"""**관찰:** 연도별 {pct(P['SEC']['2023']['return_pct'])} → {pct(P['SEC']['2024']['return_pct'])} → {pct(P['SEC']['2025']['return_pct'])} → {pct(P['SEC']['2026YTD']['return_pct'])}(10/22까지). 60일선이 120일선 아래로 내려간 2024-09-12부터 다시 올라선 2025-04-10까지가 하락 국면이고, 2026-09-21에 다시 데드 크로스가 났다. 2025년 4월 8~10일에는 두 선이 0.1%도 차이 나지 않아 사흘 새 교차가 세 번 생겼다.

**해석(가설):** 2024년 하락 국면은 3분기 실적 부진과 HBM3E 품질 테스트 미통과 보도 시기와 겹친다. 이동평균 교차는 두 선이 붙어 있을 때 속임수 신호가 잦고, 이미 일어난 변화를 늦게 확인한다."""))

cells.append(md("### Q2. 상대 성과: 같은 사이클, 다른 성과"))
cells.append(code("""display(Image(filename=P.fig_relative_performance(daily, res)))
cz = res["concentration"]
print(f"시가총액 비율(삼성전자 ÷ SK하이닉스): {cz['ratio_start']:.2f}배 → 최저 {cz['ratio_min']:.2f}배({cz['ratio_min_date'].date()}) → {cz['ratio_end']:.2f}배")
print("SK하이닉스가 더 컸던 날:", cz["skh_bigger_days"], "일,", cz["skh_bigger_first"].date(), "~", cz["skh_bigger_last"].date())
rel = pd.DataFrame(res["relative"]["by_year"]).T[["sec_pct", "skh_pct", "diff_pctpt", "relative_pct", "log_gap_share_pct"]]
print("상대 성과 = (1 + 삼성전자) ÷ (1 + SK하이닉스) − 1, 로그 격차 몫 = 4년 격차 중 그해 몫(%)")
rel.astype(float).round(1)"""))
RL = R["relative"]
cells.append(md(f"""**관찰:** 2022년 말 대비 삼성전자 {P['SEC']['전체']['end_value'] / P['SEC']['전체']['base_value']:.1f}배, SK하이닉스 {P['SKH']['전체']['end_value'] / P['SKH']['전체']['base_value']:.1f}배, KOSPI {P['KOSPI']['전체']['end_value'] / P['KOSPI']['전체']['base_value']:.1f}배. 상대 성과로 보면 격차가 가장 크게 벌어진 해는 방향까지 반대였던 2024년({pct(RL['by_year']['2024']['relative_pct'])}, 4년 격차의 {RL['by_year']['2024']['log_gap_share_pct']:.0f}%)이다. 2026년에는 6월 22일까지 다시 벌어졌다가(상대 성과 {pct(RL['split_2026']['first']['relative_pct'])}) 그 뒤 하락장에서 크게 좁혀졌다({pct(RL['split_2026']['second']['relative_pct'])}).

**해석(가설):** AI 가속기용 HBM 공급 경쟁의 차이가 이익 기대 차이로 이어졌을 가능성. 주가만으로는 확인할 수 없어 분기 실적·HBM 매출 데이터로 검증이 필요하다."""))

cells.append(md("### Q3. 변동성과 급변일"))
cells.append(code("""display(Image(filename=P.fig_drawdown(daily, res)))
display(Image(filename=P.fig_volatility(daily, res)))"""))
cells.append(code("""a = prepare.analysis_slice(daily)
ext_days = M.extreme_days(a)
sec_ext = ext_days[ext_days["sec_extreme"]][["sec_ret", "sec_z", "skh_ret", "kospi_ret", "ex2_ret", "ex2_same_dir_2pct"]]
print("삼성전자 급변일과 같은 날 다른 시계열의 수익률(%)")
sec_ext.round(2)"""))
cells.append(md(f"""**관찰:** 삼성전자 하루 수익률 표준편차는 2023~2025년 {R['volatility']['sec']['std_daily_2023_2025_pct']:.2f}%에서 2026년 {R['volatility']['sec']['std_daily_2026_pct']:.2f}%로 커졌다. 급변일 {R['extremes']['sec_count']}일 중 {Q['statistical_extremes']['sec']['by_year']['2026']}일이 2026년이고, {R['extremes']['sec_with_rest_market_same_dir']}일은 두 종목을 뺀 나머지 시장도 같은 방향이었다.

**해석(가설):** 2026년의 급등락은 대부분 시장 전체 충격(중동 전쟁 우려, 레버리지 강제 매도, 미국 긴축 우려 보도)과 겹친다. 레버리지 데이터는 없어 직접 검증하지 못했다."""))

cells.append(md("### Q4. 동조화와 쏠림"))
cells.append(code("""display(Image(filename=P.fig_coupling(daily, res)))
pd.DataFrame(res["yearly_corr"]).round(3)"""))
cells.append(md(f"""**관찰:** 삼성전자·SK하이닉스 상관 {[r for r in R['yearly_corr'] if r['year'] == 2024][0]['corr_sec_skh']:.2f}(2024) → {[r for r in R['yearly_corr'] if r['year'] == 2026][0]['corr_sec_skh']:.2f}(2026). 두 회사의 KOSPI 비중은 {R['concentration']['share_start_pct']:.1f}%에서 최고 {R['concentration']['share_max_pct']:.1f}%까지 올랐다.

**해석(가설):** 두 종목 비중이 커진 시기와 상관이 높아진 시기가 2026년으로 겹친다. 지수 단위 매매와 잦은 시장 전체 충격이 상관을 끌어올렸다는 가설을 세웠다. 나머지 시장과의 상관도 올라 쏠림의 기계적 효과만으로는 설명되지 않는다. 변동성이 큰 시기에는 상관이 높게 측정되는 경향(Forbes & Rigobon, 2002)이 있어 일부는 측정 효과일 수 있다."""))

cells.append(md("### Q5. 계절성: 달력 효과 확인"))
cells.append(code("""display(Image(filename=P.fig_calendar(daily, res, extras["monthly"], extras["weekday"])))
print("월별 차이 Kruskal-Wallis p =", round(res["month_of_year_test_p"], 3))
print("요일별 차이 p (전체 / 2023~2025) =", {k: round(v, 3) for k, v in res["weekday_test"].items()})
extras["weekday"].round(3)"""))
cells.append(md(f"""**관찰:** 6월(4년 모두 상승)과 8월(4년 모두 하락)처럼 보이는 달이 {R['month_of_year_unanimous']['observed']}개지만, 무작위여도 평균 {R['month_of_year_unanimous']['expected']:.1f}개가 생긴다. 월별 p = {R['month_of_year_test_p']:.2f}, 요일별 p = {R['weekday_test']['kruskal_p_all']:.2f}.

**해석:** 4년 표본으로는 달력 효과를 주장할 근거가 없다."""))

cells.append(md("## 5. 보너스\n\n### 5.1 STL 분해"))
cells.append(code("""parts, stl_info = A.stl_decompose(daily)
display(Image(filename=P.fig_stl(parts, stl_info)))
{k: (round(v, 3) if isinstance(v, float) else v) for k, v in stl_info.items() if k not in ("seasonal_effect_by_month_pct", "year_pair_corr")}"""))
cells.append(md(f"""**관찰:** 계절 모양을 매년 같다고 고정(seasonal=999, seasonal_deg=0)하고 분해했다. 추세 강도 {R['stl']['trend_strength']:.2f}, 계절성 강도 {R['stl']['seasonal_strength']:.2f}(robust 분해 {R['stl']['robust_seasonal_strength']:.2f}). 추세를 뺀 월별 값의 연도 간 상관 평균 {R['stl']['year_pair_corr_mean']:+.2f}, 2023~2025년만으로 추정한 모양과의 상관 {R['stl']['seasonal_2023_2025_vs_full_corr']:+.2f}. 마지막 달 추세 {R['stl']['trend_last_won']:,.0f}원은 실제 월평균 {R['stl']['observed_last_won']:,.0f}원보다 {R['stl']['trend_end_gap_pct']:.1f}% 높다(끝점 효과).

**해석(가설):** 계절성은 약하고, 계절 모양(6월 상승·9월 하락)은 2026년 급등락의 영향이 커서 해마다 반복되는 패턴이라는 근거가 없다."""))
cells.append(md("### 5.2 베이스라인 예측과 백테스트"))
cells.append(code("""bt = A.backtest(daily)
bt_sum = A.backtest_summary(bt)
fan, fan_info = A.future_fan(daily)
coverage = A.fan_coverage(daily)
display(Image(filename=P.fig_forecast(daily, bt_sum, fan, fan_info, coverage)))
bt_sum.pivot(index="method", columns="h", values="mape_pct").round(2)"""))
cells.append(code("""print("예측 구간 적중률(%): 같은 방법으로 과거 매 거래일 만든 구간에 실제 종가가 들어간 비율")
coverage.round(1)"""))
CV = {(c["h"], c["level"]): c for c in R["forecast"]["coverage"]}
cells.append(md(f"""**관찰:** Naive(오늘 종가 유지)와 Drift(최근 1년 추세 연장)의 오차는 비슷했고, 20·60일 이동평균은 1·5·20거래일 모두 오차가 더 컸다. 2026-10-22 이후 20거래일의 95% 예측 구간은 {R['forecast']['fan']['h20_lo95']:,.0f}원 ~ {R['forecast']['fan']['h20_hi95']:,.0f}원이다. 같은 방법의 과거 95% 구간에 20거래일 뒤 실제 종가가 들어간 비율은 {CV[(20, 95)]['coverage_pct']:.1f}%로 95%에 못 미쳤다.

**해석(가설):** 이 국면에서는 점 예측이 거의 의미가 없고, 구간도 이름값(95%)보다 자주 빗나간다. 가정(랜덤워크, 변동성 일정, 정규분포 근사)과 한계는 리포트 8.3절에 정리했다."""))

cells.append(md("""## 6. 정리

- 이 기간 삼성전자 주가는 '계절'보다 '국면'으로 더 잘 설명됐다: 2024년 시장보다 깊은 하락(회사 고유 요인이라는 가설), 2025년부터 2026년 6월까지 반도체 랠리, 2026년 시장 전체 급등락.
- 인사이트·결론·한계점·AI 사용 로그는 [REPORT.md](REPORT.md), 기간을 바꿔 보는 탐색은 [웹 대시보드](https://sungtae10.github.io/codyssey-semiconductor-trend-analysis-M1-1/)에서 확인한다."""))

nb = nbformat.v4.new_notebook(cells=cells, metadata={
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
})
client = NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}})
client.execute()
nbformat.write(nb, ROOT / "analysis.ipynb")
print("analysis.ipynb 저장 완료:", len(nb.cells), "셀")
