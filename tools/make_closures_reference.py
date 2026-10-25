"""KRX 휴장일 참고표 생성 (일회성 도구, 결과 CSV는 저장소에 포함).

데이터에서 빠진 평일(거래가 없는 평일)이 '결측'이 아니라 '휴장'인지 확인하려고 만든 표다.
- 공휴일 이름: python `holidays` 패키지(KR, 0.107)
- 공휴일 목록에 없는 KRX 휴장: 근로자의 날(5/1, 2023~2025), 연말 휴장일(12월 마지막 거래일 다음 평일)

실행: pip install holidays  →  python tools/make_closures_reference.py
"""
import csv
from pathlib import Path

import holidays
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
trading = pd.read_csv(ROOT / "data/raw/kospi_market_daily.csv", parse_dates=["Date"])["Date"]
trading = pd.DatetimeIndex(trading)
weekdays = pd.bdate_range("2023-01-02", "2026-10-22")
closed = weekdays.difference(trading)

kr = holidays.KR(years=[2023, 2024, 2025, 2026], language="ko")
manual = {
    "2023-05-01": "근로자의 날 (KRX 휴장)",
    "2024-05-01": "근로자의 날 (KRX 휴장)",
    "2025-05-01": "근로자의 날 (KRX 휴장)",
    "2023-12-29": "연말 휴장일 (KRX)",
    "2024-12-31": "연말 휴장일 (KRX)",
    "2025-12-31": "연말 휴장일 (KRX)",
}
rows = []
for d in closed:
    key = d.strftime("%Y-%m-%d")
    reason = kr.get(key) or manual.get(key)
    source = "holidays.KR" if kr.get(key) else ("KRX 규정" if key in manual else "")
    rows.append({"date": key, "weekday": "월화수목금"[d.weekday()], "reason": reason or "", "basis": source})

out = ROOT / "data/reference/krx_closures_2023_2026.csv"
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["date", "weekday", "reason", "basis"], lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
missing = [r["date"] for r in rows if not r["reason"]]
print(f"평일 휴장 {len(rows)}일 기록, 사유 미확인 {len(missing)}일: {missing}")
