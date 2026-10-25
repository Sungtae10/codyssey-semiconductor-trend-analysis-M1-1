"""보너스 분석: (A) 시계열 분해(STL), (B) 베이스라인 예측과 백테스트.

(A) STL 분해
    월평균 로그 종가(2023-01~2026-09, 완결된 45개월)를 추세 + 계절성(12개월) + 나머지로 나눈다.
    로그를 쓰는 이유: 가격이 4배 가까이 오르면 같은 10% 변동도 원 단위 폭이 커지므로,
    비율 변화를 같은 크기로 보려면 로그 척도가 맞다.
    강도 지표(Hyndman & Athanasopoulos): 0에 가까우면 약하고 1에 가까우면 강하다.
        추세 강도   F_T = max(0, 1 - Var(나머지) / Var(추세 + 나머지))
        계절성 강도 F_S = max(0, 1 - Var(나머지) / Var(계절성 + 나머지))

(B) 베이스라인 예측
    정확도 경쟁이 아니라 '가정과 한계'를 보이기 위한 단순 방법 4가지를 같은 조건으로 비교한다.
        naive : 내일 이후 종가 = 오늘 종가 (랜덤워크 가정)
        drift : 최근 250거래일 평균 로그수익률만큼 매일 오른다고 가정
        ma20  : 최근 20거래일 평균 종가
        ma60  : 최근 60거래일 평균 종가
    롤링 원점 백테스트: 매 거래일을 예측 시점으로 삼아 h일 뒤 종가를 맞혀 보고 MAPE를 잰다.
    적중률 점검: 앞으로 20거래일 예측 범위(future_fan)와 같은 방법으로 과거 매 거래일 구간을 만들어,
    실제 종가가 그 구간에 들어간 비율이 구간의 확률(80%, 95%)과 맞는지 확인한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

from . import config as C

HORIZONS = (1, 5, 20)
METHODS = ("naive", "drift", "ma20", "ma60")
METHOD_LABELS = {"naive": "Naive(오늘 종가 유지)", "drift": "Drift(최근 1년 추세 연장)",
                 "ma20": "20일 이동평균", "ma60": "60일 이동평균"}


# ------------------------------------------------------------------ (A) STL
def monthly_log_price(daily: pd.DataFrame, col: str = "sec_close") -> pd.Series:
    s = daily.loc[C.ANALYSIS_START:"2026-09-30", col]
    m = np.log(s).groupby(s.index.to_period("M")).mean()
    m.index = m.index.to_timestamp()
    return m


def _strengths(trend: pd.Series, seasonal: pd.Series, resid: pd.Series) -> tuple[float, float]:
    var_r = resid.var()
    f_t = max(0.0, 1 - var_r / (trend + resid).var())
    f_s = max(0.0, 1 - var_r / (seasonal + resid).var())
    return float(f_t), float(f_s)


def _fit_stl(y: pd.Series, robust: bool = False):
    # 완결된 연도가 3~4개뿐이라 계절 모양이 해마다 바뀌도록 두면 잡음까지 계절성으로 흡수한다.
    # 그래서 계절 모양을 '매년 같음'으로 고정한다.
    #   seasonal=999   : 같은 달 값들을 사실상 전 기간에 걸쳐 평활
    #   seasonal_deg=0 : 그 평활을 상수(평균)로. statsmodels 기본값 seasonal_deg=1 이면 같은 달 값이
    #                    해마다 직선으로 바뀔 수 있어 '고정'이 아니다(독립 검토에서 발견해 고침).
    # robust=False 가 기본이다. robust=True 는 민감도 점검으로만 함께 계산한다.
    return STL(y, period=12, seasonal=999, seasonal_deg=0, robust=robust).fit()


def stl_decompose(daily: pd.DataFrame, col: str = "sec_close") -> tuple[pd.DataFrame, dict]:
    y = monthly_log_price(daily, col)
    res = _fit_stl(y)
    parts = pd.DataFrame({"observed": y, "trend": res.trend, "seasonal": res.seasonal, "resid": res.resid})
    f_t, f_s = _strengths(parts["trend"], parts["seasonal"], parts["resid"])
    seas_by_month = parts["seasonal"].groupby(parts.index.month).mean()
    res_robust = _fit_stl(y, robust=True)
    f_t_rob, f_s_rob = _strengths(res_robust.trend, res_robust.seasonal, res_robust.resid)

    # 반복성 점검 1: 추세를 뺀 월별 값이 해마다 비슷한 모양인가 (연도 쌍별 상관의 평균)
    detrended = parts["observed"] - parts["trend"]
    table = pd.DataFrame({"year": detrended.index.year, "month": detrended.index.month,
                          "v": detrended.to_numpy()}).pivot(index="month", columns="year", values="v")
    corr = table.corr()
    pairs = [corr.iloc[i, j] for i in range(len(corr)) for j in range(i + 1, len(corr))]
    # 반복성 점검 2: 2023~2025년만으로 추정한 계절 모양과 전체 기간 모양이 같은가
    res_pre = _fit_stl(y.loc[:"2025-12-31"])
    seas_pre = res_pre.seasonal.groupby(res_pre.seasonal.index.month).mean()

    info = {
        "n_months": int(len(y)), "period": 12, "seasonal_window": 999, "seasonal_deg": 0, "robust": False,
        "trend_strength": f_t, "seasonal_strength": f_s,
        "robust_trend_strength": f_t_rob, "robust_seasonal_strength": f_s_rob,
        "seasonal_effect_by_month_pct": {int(m): float((np.exp(v) - 1) * 100) for m, v in seas_by_month.items()},
        "seasonal_peak_month": int(seas_by_month.idxmax()), "seasonal_trough_month": int(seas_by_month.idxmin()),
        # 추세 성분의 첫 달 → 마지막 달 변화. 끝부분은 추세가 직전 급등을 따라 실제보다 높게 남는
        # '끝점 효과'가 있어, 실제 월평균 변화(observed_change_pct)와 함께 본다.
        "trend_change_pct": float((np.exp(parts["trend"].iloc[-1] - parts["trend"].iloc[0]) - 1) * 100),
        "observed_change_pct": float((np.exp(parts["observed"].iloc[-1] - parts["observed"].iloc[0]) - 1) * 100),
        "last_month": parts.index[-1],
        "trend_last_won": float(np.exp(parts["trend"].iloc[-1])),
        "observed_last_won": float(np.exp(parts["observed"].iloc[-1])),
        "trend_end_gap_pct": float((np.exp(parts["trend"].iloc[-1] - parts["observed"].iloc[-1]) - 1) * 100),
        "resid_std_pct": float(parts["resid"].std() * 100),
        "year_pair_corr_mean": float(np.mean(pairs)),
        "year_pair_corr": {f"{corr.index[i]}-{corr.columns[j]}": float(corr.iloc[i, j])
                           for i in range(len(corr)) for j in range(i + 1, len(corr))},
        "seasonal_2023_2025_vs_full_corr": float(seas_pre.corr(seas_by_month)),
    }
    return parts, info


# ------------------------------------------------------------------ (B) 예측
def _forecast(close: np.ndarray, logret: np.ndarray, t: int, h: int, method: str) -> float:
    last = close[t]
    if method == "naive":
        return last
    if method == "drift":
        mu = logret[max(1, t - 249): t + 1].mean()
        return last * np.exp(mu * h)
    if method == "ma20":
        return close[t - 19: t + 1].mean()
    if method == "ma60":
        return close[t - 59: t + 1].mean()
    raise ValueError(method)


def backtest(daily: pd.DataFrame, col: str = "sec_close", start: str = "2024-01-02") -> pd.DataFrame:
    """예측 시점(origin)마다 h일 뒤를 예측하고 오차를 기록한다."""
    s = daily[col].dropna()
    close = s.to_numpy(dtype=float)
    logret = np.r_[np.nan, np.diff(np.log(close))]
    dates = s.index
    first = int(np.searchsorted(dates, pd.Timestamp(start)))
    rows = []
    for h in HORIZONS:
        for t in range(max(first, 250), len(close) - h):
            actual = close[t + h]
            for m in METHODS:
                f = _forecast(close, logret, t, h, m)
                rows.append({"origin": dates[t], "target": dates[t + h], "h": h, "method": m,
                             "forecast": f, "actual": actual,
                             "ape_pct": abs(f / actual - 1) * 100, "err": f - actual})
    return pd.DataFrame(rows)


def backtest_summary(bt: pd.DataFrame) -> pd.DataFrame:
    bt = bt.assign(origin_year=bt["origin"].dt.year)
    g = bt.groupby(["h", "method"]).agg(mape_pct=("ape_pct", "mean"), mae=("err", lambda e: e.abs().mean()), n=("ape_pct", "size"))
    by_year = bt.groupby(["h", "method", "origin_year"])["ape_pct"].mean().unstack("origin_year")
    by_year.columns = [f"mape_{c}" for c in by_year.columns]
    out = g.join(by_year).reset_index()
    naive = out[out["method"] == "naive"].set_index("h")["mape_pct"]
    out["vs_naive"] = out.apply(lambda r: r["mape_pct"] / naive.loc[r["h"]], axis=1)
    return out


def future_fan(daily: pd.DataFrame, col: str = "sec_close", horizon: int = 20, vol_window: int = 60) -> tuple[pd.DataFrame, dict]:
    """마지막 날 이후 20거래일 예측 범위 (랜덤워크 + 최근 60일 변동성 일정 가정)."""
    s = daily[col].dropna()
    last_date, last = s.index[-1], float(s.iloc[-1])
    logret = np.log(s).diff().dropna()
    sigma = float(logret.iloc[-vol_window:].std())
    mu = float(logret.iloc[-250:].mean())
    future = pd.bdate_range(last_date + pd.Timedelta(days=1), periods=horizon)
    h = np.arange(1, horizon + 1)
    fan = pd.DataFrame({
        "date": future, "h": h,
        "naive": last,
        "drift": last * np.exp(mu * h),
        "lo80": last * np.exp(-1.2816 * sigma * np.sqrt(h)),
        "hi80": last * np.exp(1.2816 * sigma * np.sqrt(h)),
        "lo95": last * np.exp(-1.96 * sigma * np.sqrt(h)),
        "hi95": last * np.exp(1.96 * sigma * np.sqrt(h)),
    })
    info = {"last_date": last_date, "last_close": last, "sigma_daily_pct": sigma * 100,
            "mu_daily_pct": mu * 100, "vol_window": vol_window,
            "h20_lo95": float(fan["lo95"].iloc[-1]), "h20_hi95": float(fan["hi95"].iloc[-1]),
            "h20_lo95_pct": float((fan["lo95"].iloc[-1] / last - 1) * 100),
            "h20_hi95_pct": float((fan["hi95"].iloc[-1] / last - 1) * 100),
            "h20_drift": float(fan["drift"].iloc[-1]),
            "h20_drift_pct": float((fan["drift"].iloc[-1] / last - 1) * 100)}
    return fan, info


def fan_coverage(daily: pd.DataFrame, col: str = "sec_close", start: str = "2024-01-02", vol_window: int = 60) -> pd.DataFrame:
    """future_fan 과 같은 방법(오늘 종가 중심, 최근 60일 변동성)으로 과거 매 거래일 예측 구간을 만들고,
    h일 뒤 실제 종가가 구간 안에 들어간 비율(적중률)을 잰다. 구간이 말하는 확률(80%, 95%)과 비교하려는 점검이다."""
    s = daily[col].dropna()
    close = s.to_numpy(dtype=float)
    logret = np.r_[np.nan, np.diff(np.log(close))]
    dates = s.index
    first = int(np.searchsorted(dates, pd.Timestamp(start)))
    rows = []
    for h in HORIZONS:
        for t in range(max(first, 250), len(close) - h):
            sigma = np.std(logret[t - vol_window + 1: t + 1], ddof=1)
            for z, level in ((1.2816, 80), (1.96, 95)):
                lo = close[t] * np.exp(-z * sigma * np.sqrt(h))
                hi = close[t] * np.exp(z * sigma * np.sqrt(h))
                actual = close[t + h]
                rows.append({"h": h, "level": level, "origin_year": dates[t].year,
                             "inside": lo <= actual <= hi, "above": actual > hi, "below": actual < lo})
    r = pd.DataFrame(rows)
    out = r.groupby(["h", "level"]).agg(coverage_pct=("inside", "mean"), above_pct=("above", "mean"),
                                        below_pct=("below", "mean"), n=("inside", "size"))
    by_year = r.groupby(["h", "level", "origin_year"])["inside"].mean().unstack("origin_year")
    by_year.columns = [f"coverage_{c}_pct" for c in by_year.columns]
    out = out.join(by_year)
    pct_cols = [c for c in out.columns if c.endswith("_pct")]
    out[pct_cols] = out[pct_cols] * 100
    return out.reset_index()
