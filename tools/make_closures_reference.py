"""KRX 휴장일 참고표 생성 (일회성 도구, 결과 CSV는 저장소에 포함).

데이터를 읽지 않고, 공휴일 달력과 KRX 휴장 규정만으로 '휴장이어야 하는 평일' 목록을 만든다.
데이터에서 빈 날을 거꾸로 찾아 사유를 붙이는 방식이 아니므로, src/quality.py 가 두 방향으로 대조할 수 있다.
    ① 데이터에 없는 평일이 모두 이 목록에 있는가 (설명 안 되는 결측이 없는가)
    ② 이 목록의 날에 거래가 있었는가 (휴장일인데 데이터가 있는 이상한 날이 없는가)

- 공휴일: python `holidays` 패키지(KR, 0.107). 대체공휴일·선거일·임시공휴일 포함
- 공휴일 목록에 없는 KRX 휴장: 근로자의 날(5/1, 2023~2025; 2026년부터는 '노동절'로 공휴일 목록에 있음),
  연말 휴장일(12월 마지막 거래일 다음 평일)

실행: pip install holidays  →  python tools/make_closures_reference.py
"""
import csv
from pathlib import Path

import holidays
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
START, END = "2023-01-02", "2026-10-22"

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
for d in pd.bdate_range(START, END):          # 평일만
    key = d.strftime("%Y-%m-%d")
    if key in kr:
        reason, basis = kr.get(key), "holidays.KR"
    elif key in manual:
        reason, basis = manual[key], "KRX 규정"
    else:
        continue
    rows.append({"date": key, "weekday": "월화수목금"[d.weekday()], "reason": reason, "basis": basis})

out = ROOT / "data/reference/krx_closures_2023_2026.csv"
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["date", "weekday", "reason", "basis"], lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
n_kr = sum(r["basis"] == "holidays.KR" for r in rows)
print(f"휴장이어야 하는 평일 {len(rows)}일 기록 (공휴일 {n_kr}일 + KRX 규정 {len(rows) - n_kr}일)")
