"""KRX 일별 시세 수집 스크립트 (재현용).

무엇을 하나
    1) FinanceData/marcap 저장소(고정 커밋)에서 연도별 KRX 전종목 시세 parquet 파일을 내려받는다.
    2) 삼성전자(005930)·SK하이닉스(000660)의 일별 시세만 뽑아 data/raw/ 에 CSV로 저장한다.
    3) KOSPI 상장 보통주 전체로 '전일 시가총액 가중 등락률'을 계산해 KOSPI 시장 수익률을 재계산한다.
       (공식 KOSPI 지수는 무료 공개 경로가 API 키를 요구해서, 같은 KRX 원천 데이터로 직접 계산했다.
        공식 종가와의 오차는 data/README.md 의 검증표 참고: 누적 0.2% 이내)

실행
    python -m src.fetch_data                 # 고정 커밋 → 저장소에 들어 있는 CSV와 똑같이 재생성
    python -m src.fetch_data --ref master --end 2026-12-31   # 최신 데이터로 갱신(리포트 수치는 달라짐)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

from . import config as C

STOCK_COLUMNS = ["Date", "Code", "Name", "Open", "High", "Low", "Close", "Volume", "Amount",
                 "Changes", "ChangesRatio", "Marcap", "Stocks", "Market"]
INT_COLUMNS = ["Open", "High", "Low", "Close", "Volume", "Amount", "Changes", "Marcap", "Stocks"]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_year(year: int, ref: str, retries: int = 3) -> Path:
    """연도별 parquet 파일을 캐시에 내려받고 경로를 돌려준다. 고정 커밋이면 해시까지 확인한다."""
    cache = C.CACHE_DIR / ref[:7]
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"marcap-{year}.parquet"
    expected = C.MARCAP_SHA256.get(year) if ref == C.MARCAP_COMMIT else None

    if path.exists() and (expected is None or sha256_of(path) == expected):
        return path

    url = C.MARCAP_URL.format(repo=C.MARCAP_REPO, ref=ref, year=year)
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            print(f"  내려받는 중: {url} (시도 {attempt}/{retries})")
            tmp = path.with_suffix(".part")
            with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as out:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
            tmp.replace(path)
            break
        except Exception as exc:  # 네트워크 오류는 잠시 쉬고 다시 시도
            last_error = exc
            time.sleep(2 * attempt)
    else:
        raise RuntimeError(f"{year}년 파일을 내려받지 못했습니다: {last_error}")

    if expected is not None:
        actual = sha256_of(path)
        if actual != expected:
            raise RuntimeError(f"{year}년 파일 해시 불일치: {actual} (기대값 {expected})")
    return path


def load_marcap(ref: str) -> pd.DataFrame:
    frames = []
    for year in C.MARCAP_YEARS:
        path = download_year(year, ref)
        df = pd.read_parquet(path, columns=STOCK_COLUMNS)
        frames.append(df)
    data = pd.concat(frames, ignore_index=True)
    data["Date"] = pd.to_datetime(data["Date"]).dt.normalize().astype("datetime64[ns]")
    data["Code"] = data["Code"].astype(str)
    return data


def extract_stocks(data: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    s = data[data["Code"].isin([C.SEC, C.SKH])]
    s = s[(s["Date"] >= start) & (s["Date"] <= end)].copy()
    for col in INT_COLUMNS:
        if not (s[col] == s[col].round()).all():
            raise ValueError(f"{col} 열에 정수가 아닌 값이 있습니다")
        s[col] = s[col].astype("int64")
    s["ChangesRatio"] = s["ChangesRatio"].round(2)
    s = s.drop(columns=["Market"]).sort_values(["Date", "Code"]).reset_index(drop=True)
    return s


def kospi_market_daily(data: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """KOSPI 시장 수익률 재계산.

    하루 수익률 = Σ(전일 시가총액 × 당일 KRX 등락률) / Σ(전일 시가총액)
    대상: KOSPI 상장 보통주(종목코드 끝자리 0) 중 전일과 당일 모두 거래된 종목.
    - 신규 상장 첫날·거래정지 후 첫날은 전일 가중치가 없으므로 그날 계산에서 빠진다.
    - KRX 등락률은 권리락·액면분할 기준가 조정이 반영된 공식 값이라 기업 이벤트 왜곡이 작다.
    - ex2: 삼성전자·SK하이닉스를 뺀 '나머지 시장' 수익률(두 종목의 기계적 영향 제거용).
    """
    k = data.loc[data["Market"].eq("KOSPI"), ["Date", "Code", "ChangesRatio", "Marcap"]].copy()
    k = k.sort_values(["Code", "Date"])
    trading_dates = pd.DatetimeIndex(sorted(data["Date"].unique()))
    prev_trading = pd.Series(trading_dates[:-1], index=trading_dates[1:])

    k["is_common"] = k["Code"].str[-1].eq("0")
    k["prev_marcap"] = k.groupby("Code")["Marcap"].shift(1)
    k["prev_date"] = k.groupby("Code")["Date"].shift(1)
    k["expected_prev"] = k["Date"].map(prev_trading)
    valid = (k["is_common"] & k["prev_date"].eq(k["expected_prev"])
             & (k["prev_marcap"] > 0) & k["ChangesRatio"].notna())
    v = k.loc[valid].copy()
    v["w_r"] = v["prev_marcap"] * v["ChangesRatio"]

    g_all = v.groupby("Date").agg(w=("prev_marcap", "sum"), wr=("w_r", "sum"), n=("Code", "size"))
    v_ex = v[~v["Code"].isin([C.SEC, C.SKH])]
    g_ex = v_ex.groupby("Date").agg(w=("prev_marcap", "sum"), wr=("w_r", "sum"))

    out = pd.DataFrame(index=trading_dates)
    out.index.name = "Date"
    out["n_constituents"] = g_all["n"]
    out["ret_kospi_pct"] = g_all["wr"] / g_all["w"]
    out["ret_ex2_pct"] = g_ex["wr"] / g_ex["w"]
    out["mcap_kospi_total"] = k.groupby("Date")["Marcap"].sum()               # 우선주 포함 전체
    out["mcap_kospi_common"] = k[k["is_common"]].groupby("Date")["Marcap"].sum()
    out = out.loc[start:end].copy()
    out["n_constituents"] = out["n_constituents"].astype("int64")
    out["ret_kospi_pct"] = out["ret_kospi_pct"].round(6)
    out["ret_ex2_pct"] = out["ret_ex2_pct"].round(6)
    out["mcap_kospi_total"] = out["mcap_kospi_total"].round().astype("int64")
    out["mcap_kospi_common"] = out["mcap_kospi_common"].round().astype("int64")
    return out.reset_index()


def file_info(path: Path, df: pd.DataFrame) -> dict:
    return {
        "path": path.relative_to(C.ROOT).as_posix(),
        "sha256": sha256_of(path),
        "rows": int(len(df)),
        "date_min": str(pd.to_datetime(df["Date"]).min().date()),
        "date_max": str(pd.to_datetime(df["Date"]).max().date()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KRX 일별 시세 수집 (FinanceData/marcap)")
    parser.add_argument("--ref", default=C.MARCAP_COMMIT, help="marcap 저장소 커밋 또는 브랜치 (기본: 고정 커밋)")
    parser.add_argument("--start", default=C.FETCH_START)
    parser.add_argument("--end", default=C.ANALYSIS_END)
    args = parser.parse_args(argv)

    print(f"[1/3] marcap 데이터 불러오기 (ref={args.ref[:12]})")
    data = load_marcap(args.ref)

    print("[2/3] 삼성전자·SK하이닉스 일별 시세 추출")
    stocks = extract_stocks(data, args.start, args.end)
    print("[3/3] KOSPI 시장 수익률 재계산")
    kospi = kospi_market_daily(data, args.start, args.end)

    C.RAW_DIR.mkdir(parents=True, exist_ok=True)
    stocks.assign(Date=stocks["Date"].dt.strftime("%Y-%m-%d")).to_csv(
        C.RAW_STOCKS_CSV, index=False, encoding="utf-8", lineterminator="\n")
    kospi.assign(Date=kospi["Date"].dt.strftime("%Y-%m-%d")).to_csv(
        C.RAW_KOSPI_CSV, index=False, encoding="utf-8", lineterminator="\n", float_format="%.6f")

    manifest = {
        "source": {
            "name": "KRX 전종목 일별 시세 (한국거래소 정보데이터시스템)",
            "collected_via": f"https://github.com/{C.MARCAP_REPO}",
            "ref": args.ref,
            "files": [f"data/marcap-{y}.parquet" for y in C.MARCAP_YEARS],
            "sha256": {str(y): C.MARCAP_SHA256[y] for y in C.MARCAP_YEARS} if args.ref == C.MARCAP_COMMIT else None,
        },
        "outputs": {
            "stocks": file_info(C.RAW_STOCKS_CSV, stocks),
            "kospi_market": file_info(C.RAW_KOSPI_CSV, kospi),
        },
        "period": {"fetch_start": args.start, "end": args.end},
    }
    C.MANIFEST_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"완료: {C.RAW_STOCKS_CSV.name} {len(stocks)}행, {C.RAW_KOSPI_CSV.name} {len(kospi)}행")
    return 0


if __name__ == "__main__":
    sys.exit(main())
