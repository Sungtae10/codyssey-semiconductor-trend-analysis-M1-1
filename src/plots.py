"""시각화: 리포트에 들어가는 PNG 8장을 만든다.

디자인 원칙 (dataviz 체크리스트 적용)
- 한 축만 쓴다(이중 축 금지). 단위가 다른 값은 패널을 나눈다.
- 색은 '종목'을 따른다: 삼성전자 = 파랑, SK하이닉스 = 주황, KOSPI = 회색. 모든 그림에서 같다.
- 선은 얇게, 격자는 옅은 실선, 숫자 라벨은 끝점·극값에만 단다.
- 값 범위가 4배 이상 넓은 가격 그림은 로그 눈금을 써서 앞 구간 변화가 평평하게 보이지 않게 한다.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter, NullLocator

from . import config as C

COL = C.COLORS
BLUE_RAMP = {"250": "#86b6ef", "450": "#2a78d6", "650": "#104281"}
SOURCE = "자료: 한국거래소(KRX) 일별 시세 · FinanceData/marcap 정리본(커밋 eeed081) · 분석 기간 2023-01-02~2026-10-22"
DPI = 150


# ------------------------------------------------------------------ 공통 스타일
def _korean_font() -> str:
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR"):
        if name in available:
            return name
    return "DejaVu Sans"  # 한글 글꼴이 없으면 글자가 네모로 보일 수 있다


def setup_style() -> str:
    font = _korean_font()
    plt.rcParams.update({
        "font.family": font,
        "axes.unicode_minus": False,
        "figure.facecolor": COL["surface"],
        "axes.facecolor": COL["surface"],
        "savefig.facecolor": COL["surface"],
        "axes.edgecolor": COL["axis"],
        "axes.labelcolor": COL["ink2"],
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "xtick.color": COL["ink2"],
        "ytick.color": COL["ink2"],
        "xtick.labelsize": 9.5,
        "ytick.labelsize": 9.5,
        "legend.fontsize": 9.5,
        "legend.frameon": False,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
    })
    return font


def style_ax(ax, grid_y: bool = True) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(COL["axis"])
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(length=3, width=0.8, color=COL["axis"])
    if grid_y:
        ax.grid(axis="y", color=COL["grid"], linewidth=0.8, linestyle="-")
        ax.set_axisbelow(True)


def date_axis(ax, start=C.ANALYSIS_START, end=C.ANALYSIS_END) -> None:
    ax.set_xlim(pd.Timestamp(start) - pd.Timedelta(days=8), pd.Timestamp(end) + pd.Timedelta(days=8))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=(4, 7, 10)))
    ax.xaxis.set_minor_formatter(mdates.DateFormatter("%-m월"))
    ax.tick_params(axis="x", which="minor", labelsize=8, colors=COL["muted"], length=2)


def year_lines(ax) -> None:
    for y in (2024, 2025, 2026):
        ax.axvline(pd.Timestamp(f"{y}-01-01"), color=COL["grid"], linewidth=0.9, zorder=0)


def header(fig, title: str, subtitle: str) -> None:
    fig.text(0.012, 0.985, title, ha="left", va="top", fontsize=15, fontweight="bold", color=COL["ink"])
    fig.text(0.012, 0.935, subtitle, ha="left", va="top", fontsize=10, color=COL["ink2"])


def footer(fig, extra: str = "") -> None:
    text = SOURCE + (f"\n{extra}" if extra else "")
    fig.text(0.012, 0.012, text, ha="left", va="bottom", fontsize=8.2, color=COL["muted"], linespacing=1.5)


def dot(ax, x, y, color, size=7, z=5) -> None:
    ax.plot([x], [y], marker="o", markersize=size, color=color, markeredgecolor=COL["surface"],
            markeredgewidth=1.6, zorder=z, linestyle="none")


def note(ax, x, y, text, dx=0, dy=0, ha="left", va="center", size=9, color=None, weight="normal",
         leader: bool = False) -> None:
    """선택적으로 얇은 지시선(leader line)을 단 주석. 라벨이 선과 겹칠 때 떨어뜨려 놓고 선으로 잇는다."""
    arrow = dict(arrowstyle="-", color=COL["muted"], linewidth=0.8, shrinkA=2, shrinkB=5) if leader else None
    ax.annotate(text, xy=(x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, va=va,
                fontsize=size, color=color or COL["ink"], fontweight=weight, zorder=6, arrowprops=arrow)


def man_won(v, _pos=None) -> str:
    """원 → '만' 단위 눈금 (50000 → 5만)."""
    return f"{v / 10000:,.0f}만"


def save(fig, name: str) -> str:
    C.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    path = C.IMAGES_DIR / name
    fig.savefig(path, dpi=DPI, metadata={"Software": None})
    plt.close(fig)
    return str(path)


def pct(v: float, digits: int = 1, sign: bool = True) -> str:
    return f"{v:+,.{digits}f}%" if sign else f"{v:,.{digits}f}%"


def kdate(ts) -> str:
    ts = pd.Timestamp(ts)
    return f"{ts.year}.{ts.month}.{ts.day}"


# ------------------------------------------------------------------ 1. 가격과 이동평균
def fig_price_trend(d: pd.DataFrame, res: dict) -> str:
    a = d.loc[C.ANALYSIS_START:C.ANALYSIS_END]
    fig, ax = plt.subplots(figsize=(12, 6.6))
    fig.subplots_adjust(left=0.075, right=0.975, top=0.86, bottom=0.12)
    style_ax(ax)
    year_lines(ax)

    ax.plot(a.index, a["sec_close"], color=BLUE_RAMP["250"], linewidth=1.1, label="일별 종가", zorder=2)
    ax.plot(a.index, a["sec_ma60"], color=BLUE_RAMP["450"], linewidth=1.7, label="60일 이동평균(약 3개월)", zorder=3)
    ax.plot(a.index, a["sec_ma120"], color=BLUE_RAMP["650"], linewidth=2.0, label="120일 이동평균(약 6개월)", zorder=3)

    ax.set_yscale("log")
    ticks = [50000, 70000, 100000, 150000, 200000, 300000, 400000]
    ax.yaxis.set_major_locator(FixedLocator(ticks))
    ax.yaxis.set_major_formatter(FuncFormatter(man_won))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_ylim(42000, 470000)
    ax.set_ylabel("종가 (원, 로그 눈금)")
    date_axis(ax)

    # 연도별 수익률 라벨
    for year, (start, end) in {"2023": ("2023-01-01", "2023-12-31"), "2024": ("2024-01-01", "2024-12-31"),
                               "2025": ("2025-01-01", "2025-12-31"), "2026": ("2026-01-01", C.ANALYSIS_END)}.items():
        key = "2026YTD" if year == "2026" else year
        r = res["period"]["SEC"][key]["return_pct"]
        mid = pd.Timestamp(start) + (pd.Timestamp(end) - pd.Timestamp(start)) / 2
        ax.text(mid, 445000, f"{year}년  {pct(r)}" + (" (10/22까지)" if year == "2026" else ""),
                ha="center", va="top", fontsize=9.5, color=COL["ink2"], fontweight="bold")

    # 골든·데드 크로스 표시 (60일선 기준 위치)
    cx = res["crossovers"]
    for row in cx:
        t = pd.Timestamp(row["date"])
        y = a.at[t, "sec_ma60"]
        marker = "^" if row["type"] == "골든 크로스" else "v"
        ax.plot([t], [y], marker=marker, markersize=8.5, color=COL["ink"], markeredgecolor=COL["surface"],
                markeredgewidth=1.4, zorder=6, linestyle="none")
    labels = {
        "2023-10-16": ("데드 23.10.16", 0, -15, "center", False),
        "2023-12-08": ("골든 23.12.8", 0, 15, "center", False),
        "2024-09-12": ("데드 24.9.12", 0, 15, "center", False),
        "2025-04-09": ("25.4.8~10 사흘 새 3번 교차(속임수 신호)", 8, -18, "left", False),
        "2026-09-21": ("데드 26.9.21", -25, -110, "center", True),
    }
    for date, (text, dx, dy, ha, leader) in labels.items():
        t = pd.Timestamp(date)
        note(ax, t, a.at[t, "sec_ma60"], text, dx=dx, dy=dy, ha=ha, size=8.6, color=COL["ink2"], leader=leader)

    # 극값과 마지막 값
    lo, hi = res["sec_low"], res["sec_high"]
    dot(ax, pd.Timestamp(lo["date"]), lo["value"], BLUE_RAMP["450"])
    note(ax, pd.Timestamp(lo["date"]), lo["value"], f"최저 {lo['value']:,.0f}원 ({kdate(lo['date'])})\n4년 5개월 만의 최저",
         dx=-10, dy=-2, ha="right", va="center", size=8.8)
    dot(ax, pd.Timestamp(hi["date"]), hi["value"], BLUE_RAMP["450"])
    note(ax, pd.Timestamp(hi["date"]), hi["value"], f"최고 {hi['value']:,.0f}원 ({kdate(hi['date'])})",
         dx=-8, dy=6, ha="right", size=8.8)
    last_t, last_v = a.index[-1], a["sec_close"].iloc[-1]
    dot(ax, last_t, last_v, BLUE_RAMP["450"])
    note(ax, last_t, last_v, f"{last_v:,.0f}원", dx=0, dy=-14, ha="center", size=8.8, weight="bold")

    handles, lbls = ax.get_legend_handles_labels()
    handles += [Line2D([], [], marker="^", color=COL["ink"], linestyle="none", markersize=8),
                Line2D([], [], marker="v", color=COL["ink"], linestyle="none", markersize=8)]
    lbls += ["골든 크로스(60일선이 120일선 위로)", "데드 크로스(60일선이 120일선 아래로)"]
    ax.legend(handles, lbls, loc="upper left", bbox_to_anchor=(0.0, 0.93), ncol=1, handlelength=2.2)

    header(fig, "삼성전자 주가: 2024년 소외, 2025~2026년 급등, 2026년 9월 추세 꺾임",
           "일별 종가와 60·120거래일 이동평균선. 로그 눈금이라 같은 높이 차이가 같은 비율의 변화를 뜻한다.")
    footer(fig)
    return save(fig, "01_price_trend_ma.png")


# ------------------------------------------------------------------ 2. 상대 성과와 시가총액 비율
def fig_relative_performance(d: pd.DataFrame, res: dict) -> str:
    a = d.loc[C.BASE_DATE:C.ANALYSIS_END]
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(12, 7.6), sharex=True, gridspec_kw={"height_ratios": [2.3, 1]})
    fig.subplots_adjust(left=0.075, right=0.86, top=0.87, bottom=0.10, hspace=0.12)
    for x in (ax, ax2):
        style_ax(x)
        year_lines(x)

    series = [("skh", "SKH"), ("sec", "SEC"), ("kospi", "KOSPI")]
    for col, key in series:
        ax.plot(a.index, a[f"{col}_idx"], color=COL[key], linewidth=1.9 if key != "KOSPI" else 1.6,
                label=C.SERIES_LABELS[key], zorder=3)
    ax.axhline(100, color=COL["axis"], linewidth=0.9, zorder=1)
    ax.set_yscale("log")
    ticks = [70, 100, 200, 500, 1000, 2000, 4000]
    ax.yaxis.set_major_locator(FixedLocator(ticks))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:,.0f}"))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.set_ylim(55, 5200)
    ax.set_ylabel("누적 지수 (2022-12-29 = 100, 로그)")
    ax.legend(loc="upper left", ncol=3, handlelength=2.2)

    end_t = a.index[-1]
    for col, key in series:
        v = a[f"{col}_idx"].iloc[-1]
        dot(ax, end_t, v, COL[key], size=6.5)
        total = res["period"][key]["전체"]["return_pct"]
        note(ax, end_t, v, f"{C.SERIES_LABELS[key]}\n{v / 100:,.1f}배 ({pct(total, 0)})", dx=9, ha="left", size=9)
    pk_t = pd.Timestamp(res["skh_peak"]["date"])
    pk_v = a.at[pk_t, "skh_idx"]
    dot(ax, pk_t, pk_v, COL["SKH"], size=6.5)
    note(ax, pk_t, pk_v, f"SK하이닉스 고점 {pk_v / 100:,.1f}배 ({kdate(pk_t)})", dx=-8, dy=4, ha="right", size=8.8)

    # 아래: 시가총액 비율
    ax2.plot(a.index, a["mcap_ratio_sec_skh"], color=COL["ink2"], linewidth=1.7, zorder=3)
    ax2.axhline(1, color=COL["axis"], linewidth=0.9)
    ax2.text(pd.Timestamp("2023-01-20"), 1.12, "1배 = 두 회사 시가총액이 같다", fontsize=8.6, color=COL["muted"], va="bottom")
    ax2.set_ylim(0, 7)
    ax2.set_ylabel("시가총액 비율 (배)")
    cz = res["concentration"]
    pts = [(pd.Timestamp(C.ANALYSIS_START), cz["ratio_start"], "6.0배"),
           (pd.Timestamp("2024-12-30"), cz["ratio_2024_end"], "2024년 말 2.5배"),
           (pd.Timestamp(cz["ratio_min_date"]), cz["ratio_min"], f"{cz['ratio_min']:.2f}배: SK하이닉스가 앞섬 ({kdate(cz['ratio_min_date'])})"),
           (end_t, cz["ratio_end"], f"{cz['ratio_end']:.2f}배")]
    for t, v, text in pts:
        dot(ax2, t, v, COL["ink2"], size=6)
    note(ax2, pts[0][0], pts[0][1], pts[0][2], dx=8, dy=2, size=8.8)
    note(ax2, pts[1][0], pts[1][1], pts[1][2], dx=0, dy=12, ha="center", size=8.8)
    note(ax2, pts[2][0], pts[2][1], pts[2][2], dx=-8, dy=-12, ha="right", size=8.8)
    note(ax2, pts[3][0], pts[3][1], pts[3][2], dx=9, size=8.8)
    ax2.text(0.0, 1.03, "삼성전자 시가총액 ÷ SK하이닉스 시가총액 (보통주)", transform=ax2.transAxes,
             fontsize=9.5, color=COL["ink2"], fontweight="bold")
    date_axis(ax2, start=C.BASE_DATE)

    sec_x = res["period"]["SEC"]["전체"]["end_value"] / res["period"]["SEC"]["전체"]["base_value"]
    skh_x = res["period"]["SKH"]["전체"]["end_value"] / res["period"]["SKH"]["전체"]["base_value"]
    k_x = res["period"]["KOSPI"]["전체"]["end_value"] / res["period"]["KOSPI"]["전체"]["base_value"]
    header(fig, f"같은 AI 반도체 사이클, 다른 성과: SK하이닉스 {skh_x:.1f}배, 삼성전자 {sec_x:.1f}배, KOSPI {k_x:.1f}배",
           "2022년 마지막 거래일 종가를 100으로 맞춘 누적 지수(로그 눈금). 아래는 두 회사 시가총액의 비율.")
    err = res["quality"]["checkpoints"]["max_kospi_close_rel_error_pct"]
    footer(fig, f"KOSPI(재계산): KOSPI 보통주 전 종목의 전일 시가총액 가중 등락률을 누적한 값 (보도된 공식 종가와 차이 최대 {err:.2f}%)")
    return save(fig, "02_relative_performance.png")


# ------------------------------------------------------------------ 3. 고점 대비 낙폭
def fig_drawdown(d: pd.DataFrame, res: dict) -> str:
    a = d.loc[C.BASE_DATE:C.ANALYSIS_END]
    fig, axes = plt.subplots(3, 1, figsize=(12, 7.8), sharex=True, sharey=True)
    fig.subplots_adjust(left=0.075, right=0.975, top=0.87, bottom=0.10, hspace=0.18)
    for ax, (col, key) in zip(axes, [("sec", "SEC"), ("skh", "SKH"), ("kospi", "KOSPI")]):
        style_ax(ax)
        year_lines(ax)
        dd = a[f"{col}_dd"]
        ax.fill_between(a.index, dd, 0, color=COL[key], alpha=0.12, linewidth=0, zorder=1)
        ax.plot(a.index, dd, color=COL[key], linewidth=1.6, zorder=3)
        ax.axhline(0, color=COL["axis"], linewidth=0.9)
        ax.set_ylim(-68, 6)
        ax.yaxis.set_major_locator(FixedLocator([0, -20, -40, -60]))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0f}%"))
        ax.text(0.003, 0.08, C.SERIES_LABELS[key], transform=ax.transAxes, fontsize=10.5, fontweight="bold", color=COL["ink"])
        m = res["drawdown"][key]
        t = pd.Timestamp(m["trough_date"])
        dot(ax, t, m["mdd_pct"], COL[key], size=6.5)
        end_t, end_v = a.index[-1], dd.iloc[-1]
        if key == "SEC":
            note(ax, t, m["mdd_pct"], f"최대 {m['mdd_pct']:.1f}% (고점 {kdate(m['peak_date'])} → 저점 {kdate(t)})",
                 dx=0, dy=-13, ha="center", va="top", size=8.8)
            sec26 = res["period"]["SEC"]["2026YTD"]
            t26 = pd.Timestamp(sec26["mdd_trough_date"])
            dot(ax, t26, sec26["mdd_pct"], COL[key], size=6)
            note(ax, t26, sec26["mdd_pct"], f"2026년 {sec26['mdd_pct']:.1f}% ({kdate(sec26['mdd_peak_date'])} → {kdate(t26)})",
                 dx=0, dy=-13, ha="right", va="top", size=8.8)
            dot(ax, end_t, end_v, COL[key], size=6)
            note(ax, end_t, end_v, f"현재 {end_v:.1f}%", dx=2, dy=-31, ha="right", va="top", size=8.8, weight="bold")
        else:
            label = f"최대 {m['mdd_pct']:.1f}% (고점 {kdate(m['peak_date'])} → 저점 {kdate(t)})"
            if abs(end_v - m["mdd_pct"]) < 0.05:
                label += " = 현재"
            note(ax, t, m["mdd_pct"], label, dx=-10, dy=0, ha="right", size=8.8)
    axes[1].set_ylabel("고점 대비 낙폭 (%)")
    date_axis(axes[-1], start=C.BASE_DATE)
    header(fig, "고점 대비 낙폭: 삼성전자는 2024년과 2026년에 두 번 40% 넘게 꺾였다",
           "매일 '그날까지의 최고 종가' 대비 몇 % 아래에 있는지. 0%는 신고가, 아래로 갈수록 깊은 하락.")
    footer(fig)
    return save(fig, "03_drawdown.png")


# ------------------------------------------------------------------ 4. 변동성 국면과 급변일
def fig_volatility(d: pd.DataFrame, res: dict) -> str:
    a = d.loc[C.ANALYSIS_START:C.ANALYSIS_END]
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(12, 7.8), sharex=True, gridspec_kw={"height_ratios": [1.15, 1]})
    fig.subplots_adjust(left=0.075, right=0.975, top=0.87, bottom=0.10, hspace=0.16)
    for x in (ax, ax2):
        style_ax(x)
        year_lines(x)

    ax.plot(a.index, a["kospi_vol20"], color=COL["KOSPI"], linewidth=1.5, label=C.SERIES_LABELS["KOSPI"], zorder=2)
    ax.plot(a.index, a["sec_vol20"], color=COL["SEC"], linewidth=1.8, label="삼성전자", zorder=3)
    ax.set_ylim(0, 165)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    ax.set_ylabel("20일 변동성 (연환산)")
    ax.legend(loc="upper left", ncol=2, bbox_to_anchor=(0, 0.86))
    for year, key in (("2023", "2023"), ("2024", "2024"), ("2025", "2025"), ("2026", "2026YTD")):
        start = pd.Timestamp(f"{year}-01-01")
        end = pd.Timestamp(f"{year}-12-31") if year != "2026" else pd.Timestamp(C.ANALYSIS_END)
        mid = start + (end - start) / 2
        v = res["period"]["SEC"][key]["ann_vol_pct"]
        ax.text(mid, 158, f"{year}년 삼성전자 {v:.0f}%", ha="center", va="top", fontsize=9.3, color=COL["ink2"], fontweight="bold")
    vm = res["volatility"]["sec"]
    dot(ax, pd.Timestamp(vm["vol20_max_date"]), vm["vol20_max_pct"], COL["SEC"], size=6.5)
    note(ax, pd.Timestamp(vm["vol20_max_date"]), vm["vol20_max_pct"], f"최고 {vm['vol20_max_pct']:.0f}% ({kdate(vm['vol20_max_date'])})",
         dx=-8, dy=0, ha="right", size=8.8)

    # 아래: 일간 수익률, 급변일 강조
    ext = a["sec_z"].abs() > C.Z_THRESHOLD
    thr = res["quality"]["statistical_extremes"]["sec"]["threshold_abs_pct"]
    mean = res["quality"]["statistical_extremes"]["sec"]["mean_pct"]
    ax2.bar(a.index[~ext], a.loc[~ext, "sec_ret"], width=1.6, color=COL["axis"], linewidth=0, zorder=2)
    ax2.bar(a.index[ext], a.loc[ext, "sec_ret"], width=2.4, color=COL["SEC"], linewidth=0, zorder=3)
    for y in (mean + thr, mean - thr):
        ax2.axhline(y, color=COL["ink2"], linewidth=0.8, zorder=1)
    ax2.text(pd.Timestamp("2023-01-10"), mean + thr + 0.6, f"+3σ ({mean + thr:+.1f}%)", fontsize=8.6, color=COL["ink2"], va="bottom")
    ax2.text(pd.Timestamp("2023-01-10"), mean - thr - 0.6, f"−3σ ({mean - thr:+.1f}%)".replace("+-", "−").replace("-", "−"),
             fontsize=8.6, color=COL["ink2"], va="top")
    ax2.axhline(0, color=COL["axis"], linewidth=0.8)
    ax2.set_ylim(-17, 31)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    ax2.set_ylabel("삼성전자 일간 수익률")
    for date, dx, dy, ha in (("2024-08-05", 6, -4, "left"), ("2026-03-04", -6, -4, "right"),
                             ("2026-07-28", -6, -6, "right"), ("2026-07-31", 6, 0, "left"), ("2026-05-06", -6, 4, "right")):
        t = pd.Timestamp(date)
        v = a.at[t, "sec_ret"]
        note(ax2, t, v, f"{t.month}/{t.day} {v:+.1f}%" if t.year == 2026 else f"{t.year}.{t.month}.{t.day} {v:+.1f}%",
             dx=dx, dy=dy, ha=ha, size=8.6)
    n_ext = res["quality"]["statistical_extremes"]["sec"]["count"]
    n26 = res["quality"]["statistical_extremes"]["sec"]["by_year"]["2026"]
    ax2.text(0.0, 1.03, f"파란 막대 = 급변일(|z| > 3, 평균에서 표준편차 3배 이상 벗어난 날) {n_ext}일, 이 중 {n26}일이 2026년",
             transform=ax2.transAxes, fontsize=9.5, color=COL["ink2"], fontweight="bold")
    date_axis(ax2)
    ratio = vm["std_daily_2026_pct"] / vm["std_daily_2023_2025_pct"]
    header(fig, f"2026년 변동성 국면 전환: 하루 변동폭(표준편차)이 2023~2025년의 {ratio:.1f}배",
           "위: 최근 20거래일 수익률의 표준편차를 연환산한 값. 아래: 삼성전자 하루 수익률 막대.")
    footer(fig, "z = (그날 수익률 − 분석 기간 평균) ÷ 분석 기간 표준편차. 급변일은 실제 시장 사건이라 지우지 않고 표시만 했다.")
    return save(fig, "04_volatility_regime.png")


# ------------------------------------------------------------------ 5. 동조화와 쏠림
def fig_coupling(d: pd.DataFrame, res: dict) -> str:
    a = d.loc[C.ANALYSIS_START:C.ANALYSIS_END]
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(12, 7.8), sharex=True, gridspec_kw={"height_ratios": [1, 1]})
    fig.subplots_adjust(left=0.075, right=0.975, top=0.87, bottom=0.10, hspace=0.2)
    for x in (ax, ax2):
        style_ax(x)
        year_lines(x)

    ax.plot(a.index, a["corr60_sec_ex2"], color=COL["KOSPI"], linewidth=1.7, label="삼성전자 ↔ 나머지 시장(KOSPI에서 두 종목 제외)", zorder=2)
    ax.plot(a.index, a["corr60_sec_skh"], color=COL["SKH"], linewidth=1.8, label="삼성전자 ↔ SK하이닉스", zorder=3)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("60일 상관계수")
    ax.legend(loc="lower left", ncol=2, bbox_to_anchor=(0, -0.02))
    yc = {r["year"]: r for r in res["yearly_corr"]}
    for year in (2023, 2024, 2025, 2026):
        start = pd.Timestamp(f"{year}-01-01")
        end = pd.Timestamp(f"{year}-12-31") if year != 2026 else pd.Timestamp(C.ANALYSIS_END)
        mid = start + (end - start) / 2
        ax.text(mid, 1.06, f"{year}년  SK하이닉스 {yc[year]['corr_sec_skh']:.2f} · 나머지 시장 {yc[year]['corr_sec_ex2']:.2f}",
                ha="center", va="top", fontsize=8.8, color=COL["ink2"], fontweight="bold")
    ax.text(0.0, 1.03, "삼성전자와 함께 움직인 정도 (1에 가까울수록 같은 방향으로 함께 움직임)", transform=ax.transAxes,
            fontsize=9.5, color=COL["ink2"], fontweight="bold")

    sec_share = a["sec_mcap"] / a["kospi_mcap_total"] * 100
    skh_share = a["skh_mcap"] / a["kospi_mcap_total"] * 100
    # 쌓은 영역: 옅은 면(약 25%) + 위 경계선. 큰 면을 진한 색으로 채우지 않는다.
    ax2.fill_between(a.index, 0, sec_share, color=COL["SEC"], alpha=0.25, linewidth=0, label="삼성전자", zorder=2)
    ax2.fill_between(a.index, sec_share, sec_share + skh_share, color=COL["SKH"], alpha=0.25, linewidth=0, label="SK하이닉스", zorder=2)
    ax2.plot(a.index, sec_share, color=COL["SEC"], linewidth=1.5, zorder=3)
    ax2.plot(a.index, sec_share + skh_share, color=COL["SKH"], linewidth=1.5, zorder=3)
    ax2.set_ylim(0, 65)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    ax2.set_ylabel("KOSPI 시가총액 중 비중")
    ax2.legend(loc="upper left", ncol=2)
    cz = res["concentration"]
    for t, v, text, dx, dy, ha in (
            (pd.Timestamp(C.ANALYSIS_START), cz["share_start_pct"], f"두 종목 합계 {cz['share_start_pct']:.1f}%", 6, 10, "left"),
            (pd.Timestamp("2025-12-30"), cz["share_2025_end_pct"], f"2025년 말 {cz['share_2025_end_pct']:.1f}%", -6, 10, "right"),
            (pd.Timestamp(cz["share_max_date"]), cz["share_max_pct"], f"최고 {cz['share_max_pct']:.1f}% ({kdate(cz['share_max_date'])})", -8, 4, "right"),
            (a.index[-1], cz["share_end_pct"], f"{cz['share_end_pct']:.1f}%", -4, 16, "center")):
        dot(ax2, t, v, COL["ink"], size=5.5)
        note(ax2, t, v, text, dx=dx, dy=dy, ha=ha, size=8.8)
    date_axis(ax2)
    header(fig, f"두 종목이 KOSPI의 절반 가까이 되자 함께 움직였다: 삼성전자·SK하이닉스 상관 {yc[2024]['corr_sec_skh']:.2f}(2024) → {yc[2026]['corr_sec_skh']:.2f}(2026)",
           "위: 최근 60거래일 하루 수익률의 상관계수. 아래: KOSPI 전체 시가총액(우선주 포함)에서 두 회사 보통주가 차지하는 비중.")
    footer(fig, "'나머지 시장'은 두 종목을 뺀 KOSPI 보통주의 시가총액 가중 수익률이다. 두 종목 비중이 커질수록 KOSPI와의 상관이 저절로 높아지는 효과를 빼려고 썼다.")
    return save(fig, "05_coupling_concentration.png")


# ------------------------------------------------------------------ 6. 달력 효과
def fig_calendar(d: pd.DataFrame, res: dict, monthly: pd.DataFrame, weekday: pd.DataFrame) -> str:
    fig = plt.figure(figsize=(12, 8.2))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.25, 1], hspace=0.30, left=0.075, right=0.975, top=0.80, bottom=0.10)
    ax = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])

    cmap = LinearSegmentedColormap.from_list("kr_div", [COL["down"], COL["neutral"], COL["up"]])
    norm = TwoSlopeNorm(vmin=-30, vcenter=0, vmax=30)
    vals = monthly.to_numpy(dtype=float)
    years = list(monthly.index)
    ax.imshow(np.clip(vals, -30, 30), cmap=cmap, norm=norm, aspect="auto")
    ax.xaxis.tick_top()
    ax.set_xticks(range(12), [f"{m}월" for m in range(1, 13)])
    ax.set_yticks(range(len(years)), [f"{y}년" for y in years])
    ax.tick_params(length=0)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.set_xticks(np.arange(-0.5, 12, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(years), 1), minor=True)
    ax.grid(which="minor", color=COL["surface"], linewidth=2.5)
    ax.tick_params(which="minor", length=0)
    for i, y in enumerate(years):
        for j in range(12):
            v = vals[i, j]
            if np.isnan(v):
                continue
            strong = abs(v) >= 18
            txt = f"{v:+.1f}" + ("*" if (y == years[-1] and j == 9) else "")
            ax.text(j, i, txt, ha="center", va="center", fontsize=9,
                    color="#ffffff" if strong else COL["ink"], fontweight="bold" if strong else "normal")
    moy = {r["month"]: r for r in res["month_of_year"]}
    for j in range(12):
        r = moy[j + 1]
        ax.text(j, len(years) - 0.38, f"상승 {r['up_years']}/{r['n_years']}", ha="center", va="top", fontsize=8.4, color=COL["ink2"])
    ax.set_ylim(len(years) - 0.5 + 0.55, -0.5)
    ax.text(0.0, 1.16, "삼성전자 월간 수익률 (%) · 빨강 = 상승, 파랑 = 하락 (국내 증시 표기 관례) · *2026년 10월은 22일까지",
            transform=ax.transAxes, fontsize=9.5, color=COL["ink2"], fontweight="bold")

    style_ax(ax2)
    x = np.arange(len(weekday))
    ax2.axhline(0, color=COL["axis"], linewidth=0.9)
    for i, r in weekday.iterrows():
        ax2.plot([i, i], [r["ci95_low"], r["ci95_high"]], color=COL["SEC"], linewidth=2.0, zorder=2)
        dot(ax2, i, r["mean_pct"], COL["SEC"], size=8)
        ax2.text(i + 0.07, r["mean_pct"], f"평균 {r['mean_pct']:+.2f}%\n상승일 비율 {r['win_rate_pct']:.0f}%",
                 ha="left", va="center", fontsize=8.8, color=COL["ink"])
    ax2.set_xticks(x, [f"{w}요일" for w in weekday["weekday"]])
    ax2.set_xlim(-0.4, len(weekday) - 0.25)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.1f}%"))
    ax2.set_ylabel("하루 평균 수익률")
    p_w = res["weekday_test"]["kruskal_p_all"]
    ax2.text(0.0, 1.05, f"요일별 평균과 95% 신뢰구간 · 요일 간 차이 검정 p = {p_w:.2f} (0.05보다 크면 '우연히 생길 만한 차이')",
             transform=ax2.transAxes, fontsize=9.5, color=COL["ink2"], fontweight="bold")
    p_m = res["month_of_year_test_p"]
    un = res["month_of_year_unanimous"]
    header(fig, f"달력 효과는 확인되지 않았다: 월별 차이 p = {p_m:.2f}, 요일별 차이 p = {p_w:.2f}",
           f"'6월은 매년 상승, 8월은 매년 하락'처럼 보이는 달이 {un['observed']}개지만, 동전 던지기처럼 무작위여도 평균 {un['expected']:.1f}개는 생긴다.")
    footer(fig, "검정: Kruskal–Wallis(순위 기반, 극단값에 덜 흔들림). 월별 검정은 2026년 10월(부분 월)을 뺀 45개월로 계산했다.")
    return save(fig, "06_calendar_effects.png")


# ------------------------------------------------------------------ 7. STL 분해 (보너스)
def fig_stl(parts: pd.DataFrame, info: dict) -> str:
    fig = plt.figure(figsize=(12, 7.6))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.55, 1], height_ratios=[1.6, 1], hspace=0.38, wspace=0.18,
                          left=0.075, right=0.975, top=0.86, bottom=0.10)
    ax1 = fig.add_subplot(gs[0, 0])
    ax3 = fig.add_subplot(gs[1, 0], sharex=ax1)
    ax2 = fig.add_subplot(gs[:, 1])
    for x in (ax1, ax2, ax3):
        style_ax(x)

    obs = np.exp(parts["observed"])
    trend = np.exp(parts["trend"])
    ax1.plot(parts.index, obs, color=BLUE_RAMP["250"], linewidth=1.6, marker="o", markersize=3.5, label="월평균 종가(관측값)")
    ax1.plot(parts.index, trend, color=BLUE_RAMP["650"], linewidth=2.0, label="추세 성분")
    ax1.set_yscale("log")
    ax1.yaxis.set_major_locator(FixedLocator([50000, 70000, 100000, 200000, 300000]))
    ax1.yaxis.set_major_formatter(FuncFormatter(man_won))
    ax1.yaxis.set_minor_locator(NullLocator())
    ax1.legend(loc="upper left")
    ax1.text(0.0, 1.04, f"관측값과 추세 · 추세 강도 F_T = {info['trend_strength']:.2f}", transform=ax1.transAxes,
             fontsize=9.5, color=COL["ink2"], fontweight="bold")

    resid = (np.exp(parts["resid"]) - 1) * 100
    ax3.bar(parts.index, resid, width=20, color=COL["axis"], linewidth=0)
    ax3.axhline(0, color=COL["ink2"], linewidth=0.8)
    ax3.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    ax3.text(0.0, 1.06, f"나머지(설명되지 않은 부분) · 표준편차 {info['resid_std_pct']:.1f}%", transform=ax3.transAxes,
             fontsize=9.5, color=COL["ink2"], fontweight="bold")
    ax3.xaxis.set_major_locator(mdates.YearLocator())
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(ax1.get_xticklabels(), visible=False)

    seas = info["seasonal_effect_by_month_pct"]
    months = np.arange(1, 13)
    ax2.bar(months, [seas[m] for m in months], width=0.55, color=COL["SEC"], alpha=0.35, linewidth=0, label="계절 성분(4년 평균 모양)", zorder=2)
    detr = (np.exp(parts["observed"] - parts["trend"]) - 1) * 100
    marks = {2023: "o", 2024: "s", 2025: "D", 2026: "^"}
    for year, mk in marks.items():
        v = detr[detr.index.year == year]
        ax2.plot(v.index.month, v.to_numpy(), marker=mk, linestyle="none", markersize=5.5, color=COL["ink2"],
                 markerfacecolor=COL["surface"], markeredgewidth=1.2, label=f"{year}년 실제 편차", zorder=3)
    ax2.axhline(0, color=COL["ink2"], linewidth=0.8)
    ax2.set_ylim(-36, 52)
    ax2.set_xticks(months, [str(m) for m in months])
    ax2.set_xlabel("월")
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    ax2.legend(loc="lower left", fontsize=8.6)
    ax2.text(0.0, 1.022, "계절 성분 vs 해마다 실제 모양", transform=ax2.transAxes, fontsize=9.5, color=COL["ink2"], fontweight="bold")
    ax2.text(0.02, 0.97, f"계절성 강도 F_S = {info['seasonal_strength']:.2f}\n연도 간 모양 상관 평균 {info['year_pair_corr_mean']:+.2f}\n"
                         f"2023~25년만으로 추정한 모양과의 상관 {info['seasonal_2023_2025_vs_full_corr']:+.2f}",
             transform=ax2.transAxes, fontsize=8.8, color=COL["ink"], va="top")
    header(fig, f"STL 분해: 추세가 대부분을 설명하고(F_T {info['trend_strength']:.2f}), 계절 모양은 해마다 반복되지 않았다",
           "월평균 로그 종가(2023.1~2026.9, 45개월)를 추세 + 12개월 계절성 + 나머지로 분해. 계절 모양은 '매년 같음'으로 고정해 추정.")
    footer(fig, "강도 지표: F = 1 − Var(나머지) ÷ Var(성분 + 나머지). 연도 간 모양 상관이 0 근처·음수면 '같은 달에 같은 일이 반복된다'는 근거가 없다는 뜻이다.")
    return save(fig, "07_stl_decomposition.png")


# ------------------------------------------------------------------ 8. 베이스라인 예측 (보너스)
def fig_forecast(d: pd.DataFrame, summary: pd.DataFrame, fan: pd.DataFrame, finfo: dict) -> str:
    from .advanced import METHOD_LABELS, METHODS, HORIZONS
    fig = plt.figure(figsize=(12, 7.8))
    gs_top = fig.add_gridspec(1, 3, wspace=0.08, left=0.15, right=0.975, top=0.86, bottom=0.585)
    gs = fig.add_gridspec(1, 1, left=0.075, right=0.975, top=0.445, bottom=0.10)
    order = ["naive", "drift", "ma20", "ma60"]
    short = {"naive": "Naive (오늘 종가 유지)", "drift": "Drift (1년 추세 연장)", "ma20": "20일 이동평균", "ma60": "60일 이동평균"}
    for k, h in enumerate(HORIZONS):
        ax = fig.add_subplot(gs_top[0, k])
        style_ax(ax, grid_y=False)
        ax.grid(axis="x", color=COL["grid"], linewidth=0.8)
        ax.set_axisbelow(True)
        s = summary[summary["h"] == h].set_index("method").loc[order]
        ys = np.arange(len(order))[::-1]
        for y, m in zip(ys, order):
            v = s.at[m, "mape_pct"]
            is_best = m == s["mape_pct"].idxmin()
            ax.plot([0, v], [y, y], color=COL["grid"], linewidth=2.2, zorder=1)
            ax.plot([v], [y], marker="o", markersize=8, color=COL["SEC"] if is_best else COL["muted"],
                    markeredgecolor=COL["surface"], markeredgewidth=1.5, zorder=3)
            ax.text(v + s["mape_pct"].max() * 0.04, y, f"{v:.1f}%", va="center", fontsize=9, color=COL["ink"],
                    fontweight="bold" if is_best else "normal")
        ax.set_yticks(ys, [short[m] for m in order] if k == 0 else [""] * len(order))
        ax.set_ylim(-0.6, len(order) - 0.4)
        ax.set_xlim(0, s["mape_pct"].max() * 1.35)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:g}%"))
        ax.tick_params(axis="y", length=0)
        ax.set_title(f"{h}거래일 뒤 예측 오차(MAPE)", fontsize=10, color=COL["ink"], loc="left", fontweight="bold")

    ax = fig.add_subplot(gs[0, 0])
    style_ax(ax)
    hist = d["sec_close"].loc[:C.ANALYSIS_END].iloc[-120:]
    ax.plot(hist.index, hist, color=COL["SEC"], linewidth=1.8, label="삼성전자 종가 (최근 120거래일)", zorder=3)
    ax.fill_between(fan["date"], fan["lo95"], fan["hi95"], color=COL["SEC"], alpha=0.10, linewidth=0, label="95% 예측 구간", zorder=1)
    ax.fill_between(fan["date"], fan["lo80"], fan["hi80"], color=COL["SEC"], alpha=0.18, linewidth=0, label="80% 예측 구간", zorder=2)
    ax.plot(fan["date"], fan["naive"], color=COL["ink"], linewidth=1.8, label="Naive 예측(오늘 종가 유지)", zorder=4)
    ax.plot(fan["date"], fan["drift"], color=COL["muted"], linewidth=1.6, label="Drift 예측(최근 1년 추세 연장)", zorder=4)
    last_t = fan["date"].iloc[-1]
    note(ax, last_t, finfo["h20_hi95"], f"95% 상단 {finfo['h20_hi95']:,.0f}원 ({finfo['h20_hi95_pct']:+.0f}%)", dx=-4, dy=8, ha="right", size=8.8)
    note(ax, last_t, finfo["h20_lo95"], f"95% 하단 {finfo['h20_lo95']:,.0f}원 ({finfo['h20_lo95_pct']:+.0f}%)", dx=-4, dy=-9, ha="right", size=8.8)
    ax.yaxis.set_major_formatter(FuncFormatter(man_won))
    ax.set_ylim(110000, 450000)
    ax.set_ylabel("종가 (원)")
    ax.legend(loc="upper left", ncol=3, fontsize=8.8)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y.%-m"))
    ax.set_xlim(hist.index[0] - pd.Timedelta(days=3), last_t + pd.Timedelta(days=3))
    ax.text(0.0, 1.03, f"{kdate(finfo['last_date'])} 이후 20거래일 예측 범위 · 최근 60일 하루 변동성 {finfo['sigma_daily_pct']:.1f}%가 그대로라고 가정",
            transform=ax.transAxes, fontsize=9.5, color=COL["ink2"], fontweight="bold")
    best20 = summary[(summary["h"] == 20)].set_index("method")["mape_pct"]
    header(fig, f"가장 단순한 예측이 가장 정확했다: 20거래일 뒤 평균 오차 Naive {best20['naive']:.1f}% vs 60일 이동평균 {best20['ma60']:.1f}%",
           "롤링 원점 백테스트(예측 시점 2024-01-02~, 시점마다 1·5·20거래일 뒤 종가 예측). 점이 왼쪽일수록 오차(MAPE)가 작다.")
    footer(fig, "MAPE = |예측 − 실제| ÷ 실제의 평균. 예측 구간은 랜덤워크·변동성 일정 가정의 결과일 뿐 실제 확률을 보장하지 않는다. 투자 권유가 아니다.")
    return save(fig, "08_baseline_forecast.png")
