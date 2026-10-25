"""프로젝트 공통 설정: 경로, 분석 대상, 기간, 색상.

숫자와 날짜를 여기 한 곳에 모아 두면 노트북과 스크립트가 같은 기준으로 계산한다.
"""
from pathlib import Path

# ---------------------------------------------------------------- 경로
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REFERENCE_DIR = DATA_DIR / "reference"
CACHE_DIR = DATA_DIR / "cache"
IMAGES_DIR = ROOT / "images"
RESULTS_DIR = ROOT / "results"
TABLES_DIR = RESULTS_DIR / "tables"
DOCS_DIR = ROOT / "docs"

RAW_STOCKS_CSV = RAW_DIR / "krx_daily_005930_000660.csv"
RAW_KOSPI_CSV = RAW_DIR / "kospi_market_daily.csv"
PROCESSED_CSV = PROCESSED_DIR / "analysis_daily.csv"
CLOSURES_CSV = REFERENCE_DIR / "krx_closures_2023_2026.csv"
CHECKPOINTS_CSV = REFERENCE_DIR / "official_checkpoints.csv"
MANIFEST_JSON = DATA_DIR / "manifest.json"
METRICS_JSON = RESULTS_DIR / "metrics.json"
QUALITY_JSON = RESULTS_DIR / "quality_report.json"

# ---------------------------------------------------------------- 데이터 출처
# FinanceData/marcap: 한국거래소(KRX) 전종목 일별 시세를 연도별 parquet 파일로 정리해
# GitHub에 매일 자동 업데이트하는 공개 저장소. 재현성을 위해 특정 커밋으로 고정한다.
MARCAP_REPO = "FinanceData/marcap"
MARCAP_COMMIT = "eeed0817d1478597b738a3a6149c170ec7e3f4cb"  # 2026-10-23 자동 업데이트
MARCAP_URL = "https://raw.githubusercontent.com/{repo}/{ref}/data/marcap-{year}.parquet"
MARCAP_YEARS = (2022, 2023, 2024, 2025, 2026)
# 고정 커밋 파일의 SHA-256. 다운로드한 파일이 분석에 쓴 파일과 같은지 확인한다.
MARCAP_SHA256 = {
    2022: "179650f5d1bd6abecb03d1b8eddf5f59c5ca6a0402e7bf2578635790b9ca811c",
    2023: "08f96990358f5afc4e17321613cef7126e2f0bd4290b82db952b7808d87f9c22",
    2024: "b0c38943e67637d5faf88429880092cf0f46a394be39860dd3bcd0b04231bccb",
    2025: "2bfd93c217eb74263bc5020b23fa6debb6b02531c11eaccc2826639bc191559e",
    2026: "ecbba74c6ddacece3b0224de7776d3b4c3f561675c58abcef23816c8c3cada36",
}

# ---------------------------------------------------------------- 분석 대상과 기간
SEC = "005930"  # 삼성전자 (보통주)
SKH = "000660"  # SK하이닉스
STOCK_NAMES = {SEC: "삼성전자", SKH: "SK하이닉스"}

FETCH_START = "2022-07-01"     # 120일 이동평균을 분석 첫날부터 계산하기 위한 준비 구간 시작
BASE_DATE = "2022-12-29"       # 누적 수익률 기준일: 2022년 마지막 거래일 종가 = 100
ANALYSIS_START = "2023-01-02"  # 분석 기간 첫 거래일
ANALYSIS_END = "2026-10-22"    # 분석 기간 마지막 거래일 (고정 커밋 데이터의 마지막 날)
KOSPI_OFFICIAL_BASE = 2236.40  # 2022-12-29 KOSPI 공식 종가 (재계산 지수의 출발값)

MA_WINDOWS = (20, 60, 120)     # 약 1개월, 3개월, 6개월 거래일
VOL_WINDOW = 20                # 변동성: 최근 20거래일(약 1개월)
CORR_WINDOW = 60               # 상관계수: 최근 60거래일(약 3개월)
TRADING_DAYS = 252             # 연환산 기준 거래일 수
Z_THRESHOLD = 3.0              # 급변일 판정 기준 |z| > 3
PRICE_LIMIT_PCT = 30.0         # KRX 일일 가격제한폭 ±30%

# ---------------------------------------------------------------- 색상 (검증된 팔레트)
# dataviz 팔레트 검증 스크립트로 두 계열 색의 색각이상 구분도와 대비를 확인했다.
COLORS = {
    "SEC": "#2a78d6",      # 삼성전자: 파랑 (주 시계열)
    "SKH": "#eb6834",      # SK하이닉스: 주황 (비교 시계열)
    "KOSPI": "#898781",    # KOSPI: 회색 (시장 기준선)
    "ink": "#0b0b0b",
    "ink2": "#52514e",
    "muted": "#898781",
    "grid": "#e1e0d9",
    "axis": "#c3c2b7",
    "surface": "#fcfcfb",
    "up": "#e34948",       # 국내 증시 관례: 상승 = 빨강
    "down": "#2a78d6",     # 하락 = 파랑
    "neutral": "#f0efec",
}
SERIES_LABELS = {"SEC": "삼성전자", "SKH": "SK하이닉스", "KOSPI": "KOSPI(재계산)"}
