"""REPORT.md 에 넣는 표를 계산 결과(results/)에서 바로 만든다. 손으로 숫자를 옮기다 생기는 오타를 막기 위함.

실행: python tools/report_tables.py > results/report_tables.md
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
R = json.loads((ROOT / "results" / "metrics.json").read_text(encoding="utf-8"))
P = R["period"]
NAMES = {"SEC": "삼성전자", "SKH": "SK하이닉스", "KOSPI": "KOSPI(재계산)"}
PERIODS = [("2023", "2023"), ("2024", "2024"), ("2025", "2025"), ("2026YTD", "2026(10/22까지)"), ("전체", "전체(2022.12.29 대비)")]


def pct(v, d=1, sign=True):
    return (f"{v:+,.{d}f}%" if sign else f"{v:,.{d}f}%")


def kdate(s):
    y, m, d = s.split("-")
    return f"{y}.{int(m)}.{int(d)}"


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


print("### 연도별 수익률\n")
rows = []
for key, label in PERIODS:
    s, k, m = P["SEC"][key], P["SKH"][key], P["KOSPI"][key]
    gap = s["return_pct"] - k["return_pct"]
    rows.append([label, pct(s["return_pct"]), pct(k["return_pct"]), pct(m["return_pct"]), f"{gap:+,.1f}%p"])
print(table(["기간", "삼성전자", "SK하이닉스", "KOSPI(재계산)", "삼성전자 − SK하이닉스"], rows))

print("\n### 연도별 변동성과 최대 낙폭\n")
rows = []
for key, label in PERIODS:
    row = [label]
    for s in ("SEC", "SKH", "KOSPI"):
        st = P[s][key]
        row.append(f"{st['ann_vol_pct']:.1f}% / {st['mdd_pct']:.1f}%")
    rows.append(row)
print(table(["기간", "삼성전자 변동성 / 최대 낙폭", "SK하이닉스", "KOSPI(재계산)"], rows))

print("\n### 연도별 상관계수(하루 수익률)와 두 종목 비중\n")
rows = []
for r in R["yearly_corr"]:
    rows.append([str(r["year"]), f"{r['corr_sec_skh']:.2f}", f"{r['corr_sec_ex2']:.2f}", f"{r['corr_sec_kospi']:.2f}", f"{r['share_two_mean_pct']:.1f}%"])
print(table(["연도", "삼성전자 ↔ SK하이닉스", "삼성전자 ↔ 나머지 시장", "삼성전자 ↔ KOSPI", "두 종목 비중(연평균)"], rows))

print("\n### 요일별 하루 수익률 (삼성전자)\n")
rows = [[w["weekday"] + "요일", str(w["n"]), pct(w["mean_pct"], 2), pct(w["median_pct"], 2), f"{w['win_rate_pct']:.1f}%",
         f"{w['ci95_low']:+.2f} ~ {w['ci95_high']:+.2f}%"] for w in R["weekday"]]
print(table(["요일", "일수", "평균", "중앙값", "상승일 비율", "평균의 95% 신뢰구간"], rows))

print("\n### 베이스라인 예측 백테스트 (MAPE, 예측 시점 2024-01-02~)\n")
sm = pd.DataFrame(R["forecast"]["summary"])
labels = {"naive": "Naive(오늘 종가 유지)", "drift": "Drift(최근 1년 추세 연장)", "ma20": "20일 이동평균", "ma60": "60일 이동평균"}
rows = []
for m in ("naive", "drift", "ma20", "ma60"):
    row = [labels[m]]
    for h in (1, 5, 20):
        v = sm[(sm["method"] == m) & (sm["h"] == h)]["mape_pct"].iloc[0]
        row.append(f"{v:.1f}%")
    v20 = sm[(sm["method"] == m) & (sm["h"] == 20)].iloc[0]
    row.append(f"{v20['mape_2024']:.1f}% / {v20['mape_2025']:.1f}% / {v20['mape_2026']:.1f}%")
    rows.append(row)
print(table(["방법", "1거래일 뒤", "5거래일 뒤", "20거래일 뒤", "20거래일 뒤 (2024 / 2025 / 2026)"], rows))

print("\n### KOSPI 재계산 검증 (보도된 공식 종가와 비교)\n")
cp = pd.read_csv(ROOT / "results" / "tables" / "checkpoint_validation.csv")
k = cp[(cp["item"] == "kospi_close") & (cp["date"] != "2022-12-29")]
rows = [[kdate(r.date), f"{r.official:,.2f}", f"{r.ours:,.2f}", f"{r.error:+.2f}%"] for r in k.itertuples()]
print(table(["날짜", "공식 종가(보도)", "재계산", "차이"], rows))

print("\n### 품질 점검 요약 숫자\n")
q = R["quality"]
print(json.dumps({"checkpoints": q["checkpoints"], "closures": q["closures"]["weekday_non_trading_days"],
                  "extremes": {k: v["count"] for k, v in q["statistical_extremes"].items()},
                  "threshold_sec": q["statistical_extremes"]["sec"]["threshold_abs_pct"]}, ensure_ascii=False))
