"""웹 대시보드(docs/)에서 쓰는 데이터 파일을 만든다.

결과: docs/data/dashboard-data.js  (window.DASHBOARD_DATA = {...})
- JSON 대신 JS 파일로 만든 이유: index.html 을 더블클릭해 file:// 로 열어도 브라우저 보안 정책에
  막히지 않고 데이터를 읽게 하려고.
- 대시보드는 이 일별 데이터로 기간 수익률·변동성·최대 낙폭을 브라우저에서 다시 계산한다.
  계산 방식은 src/metrics.py 와 같다(직전 거래일 종가 기준, 표본 표준편차 × √252).
"""
from __future__ import annotations

import json
import math

import pandas as pd

from . import config as C

FIELDS = {
    # 이름: (열, 소수 자릿수)
    "sec_close": ("sec_close", 0), "skh_close": ("skh_close", 0), "kospi_level": ("kospi_level", 2),
    "sec_ret": ("sec_ret", 4), "skh_ret": ("skh_ret", 4), "kospi_ret": ("kospi_ret", 4), "ex2_ret": ("ex2_ret", 4),
    "sec_ma20": ("sec_ma20", 1), "sec_ma60": ("sec_ma60", 1), "sec_ma120": ("sec_ma120", 1),
    "skh_ma20": ("skh_ma20", 1), "skh_ma60": ("skh_ma60", 1), "skh_ma120": ("skh_ma120", 1),
    "kospi_ma20": ("kospi_ma20", 2), "kospi_ma60": ("kospi_ma60", 2), "kospi_ma120": ("kospi_ma120", 2),
    "sec_vol20": ("sec_vol20", 2), "skh_vol20": ("skh_vol20", 2), "kospi_vol20": ("kospi_vol20", 2),
    "corr60_sec_skh": ("corr60_sec_skh", 4), "corr60_sec_ex2": ("corr60_sec_ex2", 4),
    "sec_mcap_tr": ("sec_mcap", 2), "skh_mcap_tr": ("skh_mcap", 2), "kospi_mcap_tr": ("kospi_mcap_total", 2),
}
TRILLION = {"sec_mcap", "skh_mcap", "kospi_mcap_total"}


def _clean(v, digits: int):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    v = round(float(v), digits)
    return int(v) if digits == 0 else v


def build(d: pd.DataFrame, res: dict) -> str:
    out = {"dates": [t.strftime("%Y-%m-%d") for t in d.index]}
    cols = {}
    for name, (col, digits) in FIELDS.items():
        s = d[col] / 1e12 if col in TRILLION else d[col]
        cols[name] = [_clean(v, digits) for v in s.tolist()]
    out["cols"] = cols

    events = pd.read_csv(C.REFERENCE_DIR / "events.csv")
    out["events"] = events.to_dict(orient="records")
    out["meta"] = {
        "analysis_start": C.ANALYSIS_START, "analysis_end": C.ANALYSIS_END, "base_date": C.BASE_DATE,
        "data_ref": C.MARCAP_COMMIT[:7], "kospi_base": C.KOSPI_OFFICIAL_BASE,
        "trading_days_per_year": C.TRADING_DAYS,
    }
    # 브라우저 계산이 파이썬 계산과 같은지 확인할 때 쓰는 기준값 (전체 기간)
    out["check"] = {
        key: {k: round(float(res["period"][key]["전체"][k]), 4) for k in ("return_pct", "ann_vol_pct", "mdd_pct")}
        for key in ("SEC", "SKH", "KOSPI")
    }

    target = C.DOCS_DIR / "data" / "dashboard-data.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    target.write_text("// 자동 생성 파일: python -m src.run_all 로 다시 만든다. 직접 고치지 않는다.\n"
                      f"window.DASHBOARD_DATA = {payload};\n", encoding="utf-8")
    print(f"   - {target.relative_to(C.ROOT).as_posix()} ({target.stat().st_size / 1024:,.0f} KB)")
    return str(target)
