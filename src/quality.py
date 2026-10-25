"""데이터 품질 점검: 결측치·이상치를 '기준을 정해' 확인하고 결과를 기록한다.

점검 항목과 처리 기준
1. 결측치: 원자료 빈 값 개수 → 0이어야 한다.
2. 거래일 누락: 공휴일 달력과 KRX 휴장 규정으로 따로 만든 휴장일 참고표와 두 방향으로 대조
   → 데이터에 없는데 휴장일이 아닌 날 0일, 휴장일인데 거래된 날 0일.
3. 중복: (날짜, 종목) 중복 → 0건.
4. 데이터 오류형 이상치 (발견 시 제외 대상):
   - 가격 논리: 저가 ≤ 시가·종가 ≤ 고가, 가격·거래량 > 0
   - 가격제한폭: 하루 등락률 |r| ≤ 30%
   - 일관성: 전일대비(Changes) = 오늘 종가 − 어제 종가, 등락률 = 계산 수익률(반올림 오차 0.005%p 이내)
5. 통계적 극단값 (유지, 표시만): |z| > 3 인 날 → 실제 시장 사건이므로 삭제하지 않는다.
6. 교차 출처 대조: 언론 보도의 공식 수치(종가·등락률·시가총액)와 비교.
   기준일(2022-12-29) KOSPI 종가는 재계산의 출발값이라 대조 개수에서 뺀다.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import config as C


def _closures() -> pd.DataFrame:
    return pd.read_csv(C.CLOSURES_CSV, parse_dates=["date"])


def _checkpoints() -> pd.DataFrame:
    return pd.read_csv(C.CHECKPOINTS_CSV, parse_dates=["date"])


def checkpoint_table(stocks: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """공식 수치와 우리 데이터의 차이를 항목별로 계산한다."""
    s = stocks.set_index(["Date", "Code"])
    rows = []
    for cp in _checkpoints().itertuples(index=False):
        d = cp.date
        item = cp.item
        if item == "kospi_close":
            ours, tol, kind = daily.at[d, "kospi_level"], 0.30, "rel_pct"
        elif item == "kospi_change_pct":
            ours, tol, kind = daily.at[d, "kospi_ret"], 0.02, "abs"
        elif item == "kospi_mcap_total_trillion":
            ours, tol, kind = daily.at[d, "kospi_mcap_total"] / 1e12, 0.0001, "abs"
        elif item in ("sec_close", "skh_close"):
            code = C.SEC if item.startswith("sec") else C.SKH
            ours, tol, kind = float(s.at[(d, code), "Close"]), 0.0, "abs"
        elif item in ("sec_change_pct", "skh_change_pct"):
            code = C.SEC if item.startswith("sec") else C.SKH
            ours, tol, kind = float(s.at[(d, code), "ChangesRatio"]), 0.0, "abs"
        elif item in ("sec_mcap_trillion", "skh_mcap_trillion"):
            code = C.SEC if item.startswith("sec") else C.SKH
            ours, tol, kind = float(s.at[(d, code), "Marcap"]) / 1e12, 0.0001, "abs"
        else:
            raise ValueError(f"알 수 없는 항목: {item}")
        official = float(cp.official_value)
        if kind == "rel_pct":
            err = (ours / official - 1) * 100
        else:
            err = ours - official
        passed = abs(round(err, 6)) <= tol + 1e-9
        # 기준일 KOSPI 종가는 재계산 지수의 출발값이라 정의상 오차가 0이다. 출처 기록용으로만 두고 대조 개수에서 뺀다.
        is_anchor = item == "kospi_close" and d == pd.Timestamp(C.BASE_DATE)
        rows.append({
            "date": d.strftime("%Y-%m-%d"), "item": item, "role": "기준점(대조 제외)" if is_anchor else "대조",
            "official": official, "ours": round(float(ours), 4), "error": round(float(err), 4),
            "error_kind": "상대오차(%)" if kind == "rel_pct" else "차이",
            "tolerance": tol, "pass": bool(passed), "source": cp.source_title,
        })
    return pd.DataFrame(rows)


def run_quality_checks(stocks: pd.DataFrame, kospi: pd.DataFrame, daily: pd.DataFrame) -> dict:
    q: dict = {}
    a_start, a_end = pd.Timestamp(C.ANALYSIS_START), pd.Timestamp(C.ANALYSIS_END)

    # 1. 기본 정보
    q["basic"] = {
        "stocks_rows": int(len(stocks)),
        "kospi_rows": int(len(kospi)),
        "columns": list(stocks.columns),
        "fetch_period": [str(stocks["Date"].min().date()), str(stocks["Date"].max().date())],
        "analysis_period": [C.ANALYSIS_START, C.ANALYSIS_END],
        "analysis_trading_days": int(daily["in_analysis"].sum()),
        "rows_per_code": {code: int(n) for code, n in stocks.groupby("Code").size().items()},
        "trading_days_by_year": {str(y): int(n) for y, n in
                                 daily.loc[daily["in_analysis"]].groupby(daily.loc[daily["in_analysis"]].index.year).size().items()},
    }

    # 2. 결측치
    q["missing"] = {
        "stocks": {c: int(v) for c, v in stocks.isna().sum().items()},
        "kospi": {c: int(v) for c, v in kospi.isna().sum().items()},
    }

    # 3. 중복과 거래일 정렬
    dates_by_code = {code: set(g["Date"]) for code, g in stocks.groupby("Code")}
    q["duplicates"] = int(stocks.duplicated(["Date", "Code"]).sum())
    q["calendar_aligned"] = bool(dates_by_code[C.SEC] == dates_by_code[C.SKH] == set(kospi["Date"]))

    # 4. 거래가 없는 평일 = 휴장일인지 두 방향으로 확인
    #    참고표는 데이터와 무관하게 공휴일 달력(holidays.KR)과 KRX 휴장 규정으로 만든 '휴장이어야 하는 평일' 목록이다.
    #    ① 데이터에 없는 평일이 모두 참고표에 있는가  ② 참고표의 날에 거래가 있었는가
    trading = pd.DatetimeIndex(sorted(dates_by_code[C.SEC]))
    weekdays = pd.bdate_range(a_start, a_end)
    closed = weekdays.difference(trading)
    ref = _closures()
    ref_dates = pd.DatetimeIndex(ref["date"])
    q["closures"] = {
        "weekday_non_trading_days": int(len(closed)),
        "reference_days": int(len(ref_dates)),
        "reference_basis": {str(k): int(v) for k, v in ref["basis"].value_counts().items()},
        "explained_by_reference": int(closed.isin(ref_dates).sum()),
        "unexplained": [d.strftime("%Y-%m-%d") for d in closed[~closed.isin(ref_dates)]],
        "reference_days_that_traded": [d.strftime("%Y-%m-%d") for d in ref_dates[ref_dates.isin(trading)]],
    }

    # 5. 데이터 오류형 이상치
    s = stocks.sort_values(["Code", "Date"]).copy()
    s["prev_close"] = s.groupby("Code")["Close"].shift(1)
    s["calc_pct"] = (s["Close"] / s["prev_close"] - 1) * 100
    has_prev = s["prev_close"].notna()
    ohlc_bad = (s["Low"] > s[["Open", "Close"]].min(axis=1)) | (s["High"] < s[["Open", "Close"]].max(axis=1))
    nonpos = (s[["Open", "High", "Low", "Close", "Volume"]] <= 0).any(axis=1)
    limit_bad = s["ChangesRatio"].abs() > C.PRICE_LIMIT_PCT
    chg_bad = has_prev & (s["Changes"] != (s["Close"] - s["prev_close"]))
    ratio_bad = has_prev & ((s["calc_pct"] - s["ChangesRatio"]).abs() > 0.0051)
    q["error_outliers"] = {
        "ohlc_logic_violations": int(ohlc_bad.sum()),
        "nonpositive_price_or_volume": int(nonpos.sum()),
        "price_limit_violations": int(limit_bad.sum()),
        "changes_mismatch": int(chg_bad.sum()),
        "ratio_mismatch": int(ratio_bad.sum()),
        "max_abs_ratio_diff_pctpt": round(float((s.loc[has_prev, "calc_pct"] - s.loc[has_prev, "ChangesRatio"]).abs().max()), 4),
        "max_abs_daily_change_pct": round(float(s["ChangesRatio"].abs().max()), 2),
        "kospi_ret_abs_max_pct": round(float(kospi["ret_kospi_pct"].abs().max()), 4),
    }

    # 6. 통계적 극단값 (|z|>3) : 표시만 하고 유지
    a = daily.loc[daily["in_analysis"]]
    ext = {}
    for name in ("sec", "skh", "kospi"):
        flag = a[f"{name}_z"].abs() > C.Z_THRESHOLD
        by_year = flag.groupby(a.index.year).sum()
        ext[name] = {
            "count": int(flag.sum()),
            "by_year": {str(y): int(v) for y, v in by_year.items()},
            "mean_pct": round(float(a[f"{name}_ret"].mean()), 4),
            "std_pct": round(float(a[f"{name}_ret"].std()), 4),
            "threshold_abs_pct": round(float(C.Z_THRESHOLD * a[f"{name}_ret"].std()), 2),
        }
    q["statistical_extremes"] = ext

    # 7. 교차 출처 대조 (기준점 1줄은 출발값이라 개수·오차 통계에서 뺀다)
    cp = checkpoint_table(stocks, daily)
    chk = cp[cp["role"] == "대조"]
    kc = chk[chk["item"] == "kospi_close"]
    kd = chk[chk["item"] == "kospi_change_pct"]
    q["checkpoints"] = {
        "n": int(len(chk)),
        "passed": int(chk["pass"].sum()),
        "n_reference_rows": int(len(cp)),
        "base_anchor_date": C.BASE_DATE,
        "n_kospi_close": int(len(kc)),
        "mean_kospi_close_rel_error_pct": round(float(kc["error"].abs().mean()), 3),
        "n_kospi_change": int(len(kd)),
        "n_stock_items": int(chk["item"].str.match(r"(sec|skh)_").sum()),
        "max_kospi_close_rel_error_pct": round(float(kc["error"].abs().max()), 3),
        "max_kospi_change_abs_error_pctpt": round(float(kd["error"].abs().max()), 3),
        "stock_values_exact": bool(chk.loc[chk["item"].str.match(r"(sec|skh)_(close|change_pct)"), "error"].abs().max() == 0),
    }

    hard_ok = (
        sum(q["missing"]["stocks"].values()) == 0 and sum(q["missing"]["kospi"].values()) == 0
        and q["duplicates"] == 0 and q["calendar_aligned"]
        and not q["closures"]["unexplained"] and not q["closures"]["reference_days_that_traded"]
        and all(v == 0 for k, v in q["error_outliers"].items() if k.endswith(("violations", "mismatch", "volume")))
        and q["checkpoints"]["passed"] == q["checkpoints"]["n"]
    )
    q["all_hard_checks_passed"] = bool(hard_ok)
    return q, cp


def save_quality(q: dict, cp: pd.DataFrame) -> None:
    C.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    C.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    C.QUALITY_JSON.write_text(json.dumps(q, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cp.to_csv(C.TABLES_DIR / "checkpoint_validation.csv", index=False, encoding="utf-8", lineterminator="\n")
