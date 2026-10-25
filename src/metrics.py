"""시계열 분석 지표 계산.

적용한 기법 (미션 요구: 최소 2가지)
1. 이동평균(20/60/120일)과 골든·데드 크로스: 추세와 추세 전환 시점
2. 수익률·누적수익률(기준일=100): 성과 비교
3. 구간별 통계(연도별 수익률·변동성·최대낙폭): 국면 비교
4. 롤링 변동성(20일, 연환산): 위험 국면 변화
5. 낙폭(drawdown): 고점 대비 하락 깊이
6. 롤링 상관(60일)과 시가총액 쏠림: 동조화
7. 월별·요일별 집계와 비모수 검정: 계절성(달력 효과) 확인
8. 상대 성과(비율)와 로그 격차의 연도별 분해: 성과 격차가 언제 벌어지고 좁혀졌는지
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from . import config as C

SERIES = {
    "SEC": ("sec_close", "sec_ret"),
    "SKH": ("skh_close", "skh_ret"),
    "KOSPI": ("kospi_level", "kospi_ret"),
}
PERIODS = {
    "2023": ("2023-01-01", "2023-12-31"),
    "2024": ("2024-01-01", "2024-12-31"),
    "2025": ("2025-01-01", "2025-12-31"),
    "2026YTD": ("2026-01-01", C.ANALYSIS_END),
    "전체": (C.ANALYSIS_START, C.ANALYSIS_END),
}
WEEKDAYS = ["월", "화", "수", "목", "금"]


# ------------------------------------------------------------------ 기본 함수
def pct_change(series: pd.Series) -> pd.Series:
    return series.pct_change() * 100


def moving_average(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=window).mean()


def drawdown_pct(series: pd.Series) -> pd.Series:
    """고점 대비 낙폭(%). 0이면 신고가, -30이면 고점보다 30% 낮다."""
    return (series / series.cummax() - 1) * 100


def annualized_vol_pct(daily_ret_pct: pd.Series) -> float:
    return float(daily_ret_pct.std() * np.sqrt(C.TRADING_DAYS))


def max_drawdown(series: pd.Series) -> dict:
    dd = drawdown_pct(series)
    trough = dd.idxmin()
    peak = series.loc[:trough].idxmax()
    return {"mdd_pct": float(dd.min()), "peak_date": peak, "trough_date": trough,
            "peak_value": float(series.loc[peak]), "trough_value": float(series.loc[trough])}


def crossovers(short: pd.Series, long: pd.Series) -> pd.DataFrame:
    """단기선이 장기선을 위로 뚫으면 골든 크로스, 아래로 뚫으면 데드 크로스."""
    diff = (short - long).dropna()
    sign = np.sign(diff)
    prev = sign.shift(1)
    golden = (prev <= 0) & (sign > 0)
    dead = (prev >= 0) & (sign < 0)
    rows = [{"date": d, "type": "골든 크로스"} for d in diff.index[golden.fillna(False).to_numpy()]]
    rows += [{"date": d, "type": "데드 크로스"} for d in diff.index[dead.fillna(False).to_numpy()]]
    out = pd.DataFrame(rows, columns=["date", "type"])
    return out.sort_values("date").reset_index(drop=True)


def month_end_returns(close: pd.Series) -> pd.Series:
    """월말 종가 기준 월간 수익률(%). 첫 달은 직전 월말(기준일) 종가 대비."""
    month_end = close.groupby(close.index.to_period("M")).last()
    return (month_end.pct_change() * 100).dropna()


# ------------------------------------------------------------------ 구간 통계
def period_stats(daily: pd.DataFrame, key: str, start: str, end: str) -> dict:
    col_close, col_ret = SERIES[key]
    s = daily[col_close]
    inside = s.loc[start:end]
    first = inside.index[0]
    base_date = s.index[s.index.get_loc(first) - 1]   # 직전 거래일 종가가 출발점
    path = s.loc[base_date:inside.index[-1]]
    r = daily.loc[inside.index, col_ret]
    mdd = max_drawdown(path)
    return {
        "base_date": base_date, "end_date": inside.index[-1],
        "base_value": float(s.loc[base_date]), "end_value": float(inside.iloc[-1]),
        "return_pct": float((inside.iloc[-1] / s.loc[base_date] - 1) * 100),
        "ann_vol_pct": annualized_vol_pct(r),
        "mdd_pct": mdd["mdd_pct"], "mdd_peak_date": mdd["peak_date"], "mdd_trough_date": mdd["trough_date"],
        "best_day": r.idxmax(), "best_day_pct": float(r.max()),
        "worst_day": r.idxmin(), "worst_day_pct": float(r.min()),
        "up_day_ratio_pct": float((r > 0).mean() * 100),
        "n_days": int(r.count()),
        "high": float(inside.max()), "high_date": inside.idxmax(),
        "low": float(inside.min()), "low_date": inside.idxmin(),
    }


def period_summary(daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key in SERIES:
        for pname, (start, end) in PERIODS.items():
            st = period_stats(daily, key, start, end)
            rows.append({"series": key, "period": pname, **st})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ 급변일·변동성
def extreme_days(a: pd.DataFrame) -> pd.DataFrame:
    flag = (a["sec_z"].abs() > C.Z_THRESHOLD) | (a["skh_z"].abs() > C.Z_THRESHOLD)
    cols = ["sec_ret", "sec_z", "skh_ret", "skh_z", "kospi_ret", "ex2_ret"]
    out = a.loc[flag, cols].copy()
    out["sec_extreme"] = out["sec_z"].abs() > C.Z_THRESHOLD
    out["skh_extreme"] = out["skh_z"].abs() > C.Z_THRESHOLD
    out["ex2_same_dir_2pct"] = (np.sign(out["sec_ret"]) == np.sign(out["ex2_ret"])) & (out["ex2_ret"].abs() >= 2)
    return out


def volatility_summary(a: pd.DataFrame) -> dict:
    out = {}
    pre = a.loc[: "2025-12-31"]
    for name in ("sec", "skh", "kospi"):
        v = a[f"{name}_vol20"]
        std_pre = pre[f"{name}_ret"].std()
        out[name] = {
            "vol20_max_pct": float(v.max()), "vol20_max_date": v.idxmax(),
            "vol20_min_pct": float(v.min()), "vol20_min_date": v.idxmin(),
            "std_daily_2023_2025_pct": float(std_pre),
            "std_daily_2026_pct": float(a.loc["2026-01-01":, f"{name}_ret"].std()),
        }
    # 2023~2025 기준 표준편차로 본 2026-07-31 의 크기
    out["sec"]["z_20260731_vs_2023_2025"] = float(
        (a.at[pd.Timestamp("2026-07-31"), "sec_ret"] - pre["sec_ret"].mean()) / pre["sec_ret"].std())
    return out


# ------------------------------------------------------------------ 동조화·쏠림
def yearly_correlations(a: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for year, g in a.groupby(a.index.year):
        rows.append({
            "year": int(year),
            "corr_sec_skh": float(g["sec_ret"].corr(g["skh_ret"])),
            "corr_sec_ex2": float(g["sec_ret"].corr(g["ex2_ret"])),
            "corr_sec_kospi": float(g["sec_ret"].corr(g["kospi_ret"])),
            "share_two_mean_pct": float(g["share_two_pct"].mean()),
        })
    rows.append({
        "year": "전체",
        "corr_sec_skh": float(a["sec_ret"].corr(a["skh_ret"])),
        "corr_sec_ex2": float(a["sec_ret"].corr(a["ex2_ret"])),
        "corr_sec_kospi": float(a["sec_ret"].corr(a["kospi_ret"])),
        "share_two_mean_pct": float(a["share_two_pct"].mean()),
    })
    return pd.DataFrame(rows)


def concentration_summary(a: pd.DataFrame) -> dict:
    share, ratio = a["share_two_pct"], a["mcap_ratio_sec_skh"]
    skh_bigger = a.index[a["skh_mcap"] > a["sec_mcap"]]
    return {
        "share_start_pct": float(share.iloc[0]), "share_start_date": share.index[0],
        "share_2025_end_pct": float(share.loc["2025-12-30"]),
        "share_max_pct": float(share.max()), "share_max_date": share.idxmax(),
        "share_20260622_pct": float(share.loc["2026-06-22"]),
        "share_end_pct": float(share.iloc[-1]),
        "ratio_start": float(ratio.iloc[0]), "ratio_2024_end": float(ratio.loc["2024-12-30"]),
        "ratio_min": float(ratio.min()), "ratio_min_date": ratio.idxmin(),
        "ratio_end": float(ratio.iloc[-1]),
        "skh_bigger_days": int(len(skh_bigger)),
        "skh_bigger_first": skh_bigger.min() if len(skh_bigger) else None,
        "skh_bigger_last": skh_bigger.max() if len(skh_bigger) else None,
        "sec_mcap_end_trillion": float(a["sec_mcap"].iloc[-1] / 1e12),
        "skh_mcap_end_trillion": float(a["skh_mcap"].iloc[-1] / 1e12),
        "sec_mcap_start_trillion": float(a["sec_mcap"].iloc[0] / 1e12),
        "skh_mcap_start_trillion": float(a["skh_mcap"].iloc[0] / 1e12),
    }


def relative_performance(daily: pd.DataFrame, a: pd.DataFrame) -> dict:
    """삼성전자 ÷ SK하이닉스 상대 성과.

    %p 차이(삼성전자 수익률 − SK하이닉스 수익률)는 두 종목이 크게 오른 해일수록 커 보이므로,
    해마다 격차가 얼마나 벌어졌는지는 비율(상대 성과 = (1 + 삼성전자) ÷ (1 + SK하이닉스) − 1)로 잰다.
    로그 격차 ln(1 + SK하이닉스) − ln(1 + 삼성전자)는 연도별로 더하면 전체 격차가 되므로, 연도별 몫(%)을 낼 수 있다.
    """
    years = {}
    total = 0.0
    for pname in ("2023", "2024", "2025", "2026YTD"):
        start, end = PERIODS[pname]
        sec = period_stats(daily, "SEC", start, end)["return_pct"]
        skh = period_stats(daily, "SKH", start, end)["return_pct"]
        log_gap = float(np.log1p(skh / 100) - np.log1p(sec / 100))
        total += log_gap
        years[pname] = {"sec_pct": sec, "skh_pct": skh, "diff_pctpt": sec - skh,
                        "relative_pct": ((1 + sec / 100) / (1 + skh / 100) - 1) * 100, "log_gap": log_gap}
    for v in years.values():
        v["log_gap_share_pct"] = v["log_gap"] / total * 100

    # 2026년: 시가총액 비율이 가장 낮았던 날(SK하이닉스가 앞선 날)을 기준으로 앞뒤를 나눈다
    split = a["mcap_ratio_sec_skh"].idxmin()
    base = period_stats(daily, "SEC", *PERIODS["2026YTD"])["base_date"]
    end = a.index[-1]

    def leg(t0, t1):
        sec = (daily.at[t1, "sec_close"] / daily.at[t0, "sec_close"] - 1) * 100
        skh = (daily.at[t1, "skh_close"] / daily.at[t0, "skh_close"] - 1) * 100
        return {"start": t0, "end": t1, "sec_pct": float(sec), "skh_pct": float(skh),
                "relative_pct": float(((1 + sec / 100) / (1 + skh / 100) - 1) * 100),
                "ratio_start": float(daily.at[t0, "mcap_ratio_sec_skh"]), "ratio_end": float(daily.at[t1, "mcap_ratio_sec_skh"])}

    return {"by_year": years, "total_log_gap": total, "skh_over_sec_multiple": float(np.exp(total)),
            "total_relative_pct": float((np.exp(-total) - 1) * 100),
            "split_2026": {"first": leg(base, split), "second": leg(split, end)}}


# ------------------------------------------------------------------ 계절성(달력 효과)
def monthly_table(daily: pd.DataFrame, col_close: str = "sec_close") -> pd.DataFrame:
    """연도 × 월 수익률 표. 마지막 달(2026-10)은 10/22까지의 부분 월."""
    s = daily[col_close].loc[C.BASE_DATE:C.ANALYSIS_END]
    m = month_end_returns(s)
    t = pd.DataFrame({"year": m.index.year, "month": m.index.month, "ret": m.to_numpy()})
    return t.pivot(index="year", columns="month", values="ret")


def month_of_year_stats(table: pd.DataFrame) -> pd.DataFrame:
    full = table.copy()
    last_year = full.index.max()
    full.loc[last_year, 10] = np.nan            # 부분 월 제외
    rows = []
    for month in range(1, 13):
        v = full[month].dropna()
        rows.append({"month": month, "n_years": int(v.count()), "mean_pct": float(v.mean()),
                     "median_pct": float(v.median()), "up_years": int((v > 0).sum()),
                     "down_years": int((v < 0).sum())})
    return pd.DataFrame(rows)


def weekday_stats(a: pd.DataFrame, col: str = "sec_ret") -> tuple[pd.DataFrame, dict]:
    wd = a.index.weekday
    rows = []
    groups = []
    for i, name in enumerate(WEEKDAYS):
        r = a.loc[wd == i, col]
        groups.append(r.to_numpy())
        se = r.std() / np.sqrt(r.count())
        rows.append({"weekday": name, "n": int(r.count()), "mean_pct": float(r.mean()),
                     "median_pct": float(r.median()), "win_rate_pct": float((r > 0).mean() * 100),
                     "ci95_low": float(r.mean() - 1.96 * se), "ci95_high": float(r.mean() + 1.96 * se)})
    kw_all = stats.kruskal(*groups)
    pre = a.loc[:"2025-12-31"]
    wd_pre = pre.index.weekday
    kw_pre = stats.kruskal(*[pre.loc[wd_pre == i, col].to_numpy() for i in range(5)])
    return pd.DataFrame(rows), {"kruskal_p_all": float(kw_all.pvalue), "kruskal_p_2023_2025": float(kw_pre.pvalue)}


def month_of_year_test(table: pd.DataFrame) -> float:
    full = table.copy()
    full.loc[full.index.max(), 10] = np.nan
    groups = [full[m].dropna().to_numpy() for m in range(1, 13)]
    return float(stats.kruskal(*groups).pvalue)
