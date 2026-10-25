"""전체 파이프라인: 원자료 → 정제·품질 점검 → 지표 → 그림 → 결과표 → 대시보드 데이터.

실행 (저장소 루트에서)
    python -m src.run_all              # 그림 8장, results/, data/processed/, docs/data/ 를 다시 만든다
    python -m src.run_all --no-plots   # 숫자만 다시 계산
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np
import pandas as pd

from . import advanced as A
from . import config as C
from . import metrics as M
from . import prepare, quality


# ------------------------------------------------------------------ JSON 변환
def to_jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d")
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        v = float(obj)
        return None if math.isnan(v) else round(v, 6)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def frame_records(df: pd.DataFrame) -> list[dict]:
    return [to_jsonable(r) for r in df.to_dict(orient="records")]


# ------------------------------------------------------------------ 결과 계산
def compute_results(stocks: pd.DataFrame, kospi: pd.DataFrame, d: pd.DataFrame) -> tuple[dict, dict]:
    a = prepare.analysis_slice(d)
    q, cp = quality.run_quality_checks(stocks, kospi, d)

    ps = M.period_summary(d)
    period = {k: {r["period"]: {kk: vv for kk, vv in r.items() if kk not in ("series", "period")}
                  for r in g.to_dict(orient="records")} for k, g in ps.groupby("series")}

    cx = M.crossovers(d["sec_ma60"], d["sec_ma120"])
    cx = cx[cx["date"] >= pd.Timestamp(C.ANALYSIS_START)]
    above120 = (a["sec_close"] > a["sec_ma120"]).groupby(a.index.year).mean() * 100

    drawdown = {}
    for key, col in (("SEC", "sec_close"), ("SKH", "skh_close"), ("KOSPI", "kospi_level")):
        mdd = M.max_drawdown(d.loc[C.BASE_DATE:C.ANALYSIS_END, col])
        mdd["current_pct"] = float(d.loc[C.ANALYSIS_END, f"{col.split('_')[0]}_dd"])
        drawdown[key] = mdd

    ext = M.extreme_days(a)
    sec_ext = ext[ext["sec_extreme"]]
    yearly_corr = M.yearly_correlations(a)
    monthly = M.monthly_table(d)
    moy = M.month_of_year_stats(monthly)
    wd, wd_test = M.weekday_stats(a)

    parts, stl_info = A.stl_decompose(d)
    bt = A.backtest(d)
    bt_sum = A.backtest_summary(bt)
    fan, fan_info = A.future_fan(d)
    coverage = A.fan_coverage(d)

    res = {
        "meta": {"analysis_period": [C.ANALYSIS_START, C.ANALYSIS_END], "base_date": C.BASE_DATE,
                 "trading_days": int(len(a)), "data_ref": C.MARCAP_COMMIT},
        "quality": q,
        "period": period,
        "sec_high": {"date": a["sec_close"].idxmax(), "value": float(a["sec_close"].max())},
        "sec_low": {"date": a["sec_close"].idxmin(), "value": float(a["sec_close"].min())},
        "skh_peak": {"date": a["skh_close"].idxmax(), "value": float(a["skh_close"].max())},
        "crossovers": [{"date": r.date, "type": r.type} for r in cx.itertuples(index=False)],
        "above_ma120_pct_by_year": {str(k): float(v) for k, v in above120.items()},
        "drawdown": drawdown,
        "volatility": M.volatility_summary(a),
        "extremes": {
            "sec_count": int(len(sec_ext)),
            "sec_with_rest_market_same_dir": int((np.sign(sec_ext["sec_ret"]) == np.sign(sec_ext["ex2_ret"])).sum()),
            "sec_with_rest_market_same_dir_2pct": int(sec_ext["ex2_same_dir_2pct"].sum()),
            "sec_idiosyncratic_days": [t for t, r in sec_ext.iterrows() if not r["ex2_same_dir_2pct"]],
        },
        "yearly_corr": frame_records(yearly_corr),
        "concentration": M.concentration_summary(a),
        "relative": M.relative_performance(d, a),
        "month_of_year": frame_records(moy),
        "month_of_year_test_p": M.month_of_year_test(monthly),
        # 같은 달이 모든 해에 같은 방향(전부 상승 또는 전부 하락)인 경우: 실제 개수 vs 무작위(50:50) 기대 개수
        "month_of_year_unanimous": {
            "observed": int(((moy["up_years"] == moy["n_years"]) | (moy["down_years"] == moy["n_years"])).sum()),
            "expected": float((2 * 0.5 ** moy["n_years"]).sum()),
            "months": [int(m) for m in moy.loc[(moy["up_years"] == moy["n_years"]) | (moy["down_years"] == moy["n_years"]), "month"]],
        },
        "monthly_extremes": {
            "best": {"month": "{}-{:02d}".format(*map(int, monthly.stack().idxmax())), "pct": float(monthly.stack().max())},
            "worst": {"month": "{}-{:02d}".format(*map(int, monthly.stack().idxmin())), "pct": float(monthly.stack().min())},
        },
        "weekday": frame_records(wd),
        "weekday_test": wd_test,
        "stl": stl_info,
        "forecast": {"summary": frame_records(bt_sum), "fan": fan_info, "coverage": frame_records(coverage)},
    }
    tables = {"period_summary": ps, "crossovers": cx, "extreme_days": ext.reset_index(),
              "yearly_correlation": yearly_corr, "monthly_returns_sec": monthly.reset_index(),
              "month_of_year_sec": moy, "weekday_sec": wd, "checkpoint_validation": cp,
              "stl_components": parts.reset_index(names="month"), "forecast_backtest_summary": bt_sum,
              "forecast_fan": fan, "forecast_interval_coverage": coverage}
    extras = {"monthly": monthly, "weekday": wd, "parts": parts, "bt_sum": bt_sum, "fan": fan, "fan_info": fan_info,
              "coverage": coverage, "stl_info": stl_info, "q": q, "cp": cp}
    return res, {"tables": tables, **extras}


def save_tables(tables: dict) -> None:
    C.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        out = df.copy()
        for col in out.columns:
            if pd.api.types.is_datetime64_any_dtype(out[col]):
                out[col] = out[col].dt.strftime("%Y-%m-%d")
        out.to_csv(C.TABLES_DIR / f"{name}.csv", index=False, encoding="utf-8", lineterminator="\n", float_format="%.4f")


def make_plots(d: pd.DataFrame, res: dict, extras: dict) -> list[str]:
    from . import plots as P
    P.setup_style()
    return [
        P.fig_price_trend(d, res),
        P.fig_relative_performance(d, res),
        P.fig_drawdown(d, res),
        P.fig_volatility(d, res),
        P.fig_coupling(d, res),
        P.fig_calendar(d, res, extras["monthly"], extras["weekday"]),
        P.fig_stl(extras["parts"], extras["stl_info"]),
        P.fig_forecast(d, extras["bt_sum"], extras["fan"], extras["fan_info"], extras["coverage"]),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="삼성전자 시계열 트렌드 분석 파이프라인")
    parser.add_argument("--no-plots", action="store_true", help="그림을 다시 그리지 않는다")
    parser.add_argument("--no-dashboard", action="store_true", help="대시보드 데이터를 다시 만들지 않는다")
    args = parser.parse_args(argv)

    print("[1/5] 원자료 읽기와 일별 지표 계산")
    stocks, kospi = prepare.load_raw()
    d = prepare.build_daily(stocks, kospi)
    prepare.save_processed(d)

    print("[2/5] 품질 점검과 분석 지표")
    res, extras = compute_results(stocks, kospi, d)
    quality.save_quality(extras["q"], extras["cp"])
    save_tables(extras["tables"])
    C.METRICS_JSON.write_text(json.dumps(to_jsonable(res), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not args.no_plots:
        print("[3/5] 그림 8장 그리기")
        for p in make_plots(d, res, extras):
            print("   -", p.replace(str(C.ROOT) + "/", ""))
    if not args.no_dashboard:
        print("[4/5] 대시보드 데이터 만들기")
        from . import build_dashboard
        build_dashboard.build(d, res)

    q = extras["q"]
    print("[5/5] 요약")
    print(f"   품질 점검 통과: {q['all_hard_checks_passed']} | 교차 출처 대조 {q['checkpoints']['passed']}/{q['checkpoints']['n']}")
    sec = res["period"]["SEC"]["전체"]
    print(f"   삼성전자 {C.BASE_DATE} {sec['base_value']:,.0f}원 → {C.ANALYSIS_END} {sec['end_value']:,.0f}원 ({sec['return_pct']:+.1f}%)")
    return 0 if q["all_hard_checks_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
