"""원자료(raw CSV)를 읽어 분석용 일별 테이블을 만든다.

정제 원칙
- 결측: 원자료에 빈 값이 없음을 quality.py 로 확인한다. 거래가 없는 평일은 결측이 아니라 휴장일이다.
- 이상치: 데이터 오류(가격 논리 위반, 가격제한폭 초과, 전일대비 불일치)는 0건이어서 고칠 값이 없다.
  통계적 극단값(|z|>3)은 실제 시장 사건이므로 지우거나 바꾸지 않고 '급변일'로 표시만 한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C


def load_raw() -> tuple[pd.DataFrame, pd.DataFrame]:
    stocks = pd.read_csv(C.RAW_STOCKS_CSV, dtype={"Code": str}, parse_dates=["Date"])
    kospi = pd.read_csv(C.RAW_KOSPI_CSV, parse_dates=["Date"])
    return stocks, kospi


def _wide(stocks: pd.DataFrame, column: str) -> pd.DataFrame:
    w = stocks.pivot(index="Date", columns="Code", values=column)
    return w.rename(columns={C.SEC: "sec", C.SKH: "skh"})[["sec", "skh"]]


def build_daily(stocks: pd.DataFrame, kospi: pd.DataFrame) -> pd.DataFrame:
    """분석에 쓰는 모든 일별 지표를 한 테이블로 만든다 (날짜 1행 = 1거래일)."""
    close = _wide(stocks, "Close").astype(float)
    mcap = _wide(stocks, "Marcap").astype(float)
    k = kospi.set_index("Date").sort_index()

    d = pd.DataFrame(index=close.index.sort_values())
    d.index.name = "Date"
    d["in_analysis"] = d.index >= pd.Timestamp(C.ANALYSIS_START)

    # 가격·수익률 (수익률 단위: %)
    d["sec_close"] = close["sec"]
    d["skh_close"] = close["skh"]
    d["sec_ret"] = close["sec"].pct_change() * 100
    d["skh_ret"] = close["skh"].pct_change() * 100
    d["kospi_ret"] = k["ret_kospi_pct"]
    d["ex2_ret"] = k["ret_ex2_pct"]

    # KOSPI 재계산 지수: 2022-12-29 공식 종가(2,236.40)에서 출발해 일별 수익률을 누적
    growth = (1 + d["kospi_ret"] / 100).cumprod()
    d["kospi_level"] = growth / growth.loc[C.BASE_DATE] * C.KOSPI_OFFICIAL_BASE

    # 시가총액 (원) 과 쏠림
    d["sec_mcap"] = mcap["sec"]
    d["skh_mcap"] = mcap["skh"]
    d["kospi_mcap_total"] = k["mcap_kospi_total"].astype(float)
    d["share_two_pct"] = (d["sec_mcap"] + d["skh_mcap"]) / d["kospi_mcap_total"] * 100
    d["mcap_ratio_sec_skh"] = d["sec_mcap"] / d["skh_mcap"]

    # 이동평균 (20/60/120 거래일)
    for w in C.MA_WINDOWS:
        d[f"sec_ma{w}"] = close["sec"].rolling(w, min_periods=w).mean()
        d[f"skh_ma{w}"] = close["skh"].rolling(w, min_periods=w).mean()
        d[f"kospi_ma{w}"] = d["kospi_level"].rolling(w, min_periods=w).mean()

    # 기준일(2022-12-29) = 100 정규화 지수와 고점 대비 낙폭(%)
    base = pd.Timestamp(C.BASE_DATE)
    after = d.index >= base
    for name, series in (("sec", d["sec_close"]), ("skh", d["skh_close"]), ("kospi", d["kospi_level"])):
        idx = series / series.loc[base] * 100
        d[f"{name}_idx"] = idx.where(after)
        peak = series.where(after).cummax()
        d[f"{name}_dd"] = ((series / peak - 1) * 100).where(after)

    # 변동성: 최근 20거래일 수익률 표준편차 × √252 (연환산, %)
    for name in ("sec", "skh", "kospi"):
        d[f"{name}_vol20"] = d[f"{name}_ret"].rolling(C.VOL_WINDOW, min_periods=C.VOL_WINDOW).std() * np.sqrt(C.TRADING_DAYS)

    # 동조화: 최근 60거래일 수익률 상관계수
    w = C.CORR_WINDOW
    d["corr60_sec_skh"] = d["sec_ret"].rolling(w, min_periods=w).corr(d["skh_ret"])
    d["corr60_sec_ex2"] = d["sec_ret"].rolling(w, min_periods=w).corr(d["ex2_ret"])
    d["corr60_sec_kospi"] = d["sec_ret"].rolling(w, min_periods=w).corr(d["kospi_ret"])

    # 급변일 판정용 z-점수 (분석 기간 평균·표준편차 기준)
    a = d.loc[d["in_analysis"]]
    for name in ("sec", "skh", "kospi", "ex2"):
        r = a[f"{name}_ret"]
        d[f"{name}_z"] = ((d[f"{name}_ret"] - r.mean()) / r.std()).where(d["in_analysis"])
    return d


def analysis_slice(daily: pd.DataFrame) -> pd.DataFrame:
    return daily.loc[daily["in_analysis"]].copy()


def save_processed(daily: pd.DataFrame) -> None:
    C.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = daily.reset_index()
    out["Date"] = out["Date"].dt.strftime("%Y-%m-%d")
    out.to_csv(C.PROCESSED_CSV, index=False, encoding="utf-8", lineterminator="\n", float_format="%.6f")
