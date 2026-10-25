"""대시보드 자동 점검 + 시나리오 스크린샷 (Playwright, 헤드리스 Chromium).

무엇을 확인하나
1. 페이지가 콘솔 오류 없이 열리는가
2. 브라우저가 계산한 전체 기간 수익률·변동성·최대 낙폭이 파이썬 계산(results/metrics.json)과 같은가
3. 기간 버튼(2024)을 누르면 숫자 표가 그 기간의 파이썬 계산과 같게 바뀌는가
4. 시나리오별 화면을 docs/screenshots/ 에 저장한다 (보너스 제출 3번 형식)

실행
    pip install playwright && python -m playwright install chromium   # 처음 한 번
    python tools/check_dashboard.py                  # 점검 + 스크린샷
    python tools/check_dashboard.py --fonts <fontsource 폴더>   # 웹폰트를 로컬 파일로 대신 (오프라인 환경용)
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import re
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SHOTS = DOCS / "screenshots"
METRICS = json.loads((ROOT / "results" / "metrics.json").read_text(encoding="utf-8"))


def serve(directory: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):  # 접속 기록은 출력하지 않는다
            pass
    handler = functools.partial(Quiet, directory=str(directory))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def pct(text: str) -> float:
    m = re.search(r"([+-]?[\d,]+\.\d)%", text)
    return float(m.group(1).replace(",", "")) if m else float("nan")


def kpi_rows(page) -> dict:
    rows = {}
    for tr in page.query_selector_all("#kpi-table tbody tr"):
        cells = [td.inner_text() for td in tr.query_selector_all("td")]
        rows[cells[0].strip()] = {"return": pct(cells[2]), "vol": pct(cells[3]), "mdd": pct(cells[4])}
    return rows


def expect_period(rows: dict, period: str, problems: list) -> None:
    names = {"SEC": "삼성전자", "SKH": "SK하이닉스", "KOSPI": "KOSPI(재계산)"}
    for key, name in names.items():
        ref = METRICS["period"][key][period]
        got = rows.get(name)
        if not got:
            problems.append(f"{period} {name}: 표에 행이 없음")
            continue
        for field, ref_key in (("return", "return_pct"), ("vol", "ann_vol_pct"), ("mdd", "mdd_pct")):
            want = round(ref[ref_key], 1)
            if abs(got[field] - want) > 0.05 + 1e-9:
                problems.append(f"{period} {name} {field}: 화면 {got[field]} vs 파이썬 {want}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", help="fontsource ibm-plex-sans-kr 패키지 폴더(400.css 등이 있는 곳)")
    ap.add_argument("--no-shots", action="store_true")
    args = ap.parse_args()

    httpd, port = serve(DOCS)
    base = f"http://127.0.0.1:{port}/index.html"
    problems: list[str] = []
    console_errors: list[str] = []
    SHOTS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=1.5, locale="ko-KR",
                                  color_scheme="light")
        if args.fonts:
            fdir = Path(args.fonts)
            css = "".join((fdir / f"{w}.css").read_text(encoding="utf-8") for w in (400, 500, 600, 700))
            css = css.replace("url(./files/", "url(https://fonts.local/files/")

            def fonts_css(route):
                route.fulfill(status=200, content_type="text/css", body=css)

            def font_file(route):
                name = route.request.url.split("/files/")[-1]
                route.fulfill(status=200, content_type="font/woff2", path=str(fdir / "files" / name))

            ctx.route("https://fonts.googleapis.com/**", fonts_css)
            ctx.route("https://fonts.local/files/**", font_file)
        else:
            ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        ctx.route("https://fonts.gstatic.com/**", lambda r: r.abort())

        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        page.goto(base, wait_until="networkidle")
        page.wait_for_selector("#main-chart .main-svg")
        page.evaluate("document.fonts.ready")

        # 1) 브라우저 계산 vs 파이썬 계산 (전체 기간)
        check = page.evaluate("window.__dashboardSelfCheck()")
        for key, fields in check.items():
            for name, (got, want) in fields.items():
                if abs(got - want) > 0.01:
                    problems.append(f"자체 점검 {key} {name}: 브라우저 {got:.4f} vs 파이썬 {want:.4f}")
        expect_period(kpi_rows(page), "전체", problems)
        readout = page.inner_text("#readout-text")

        def shot(name: str, selector: str | None = None, full: bool = False):
            if args.no_shots:
                return
            target = SHOTS / name
            if selector:
                page.locator(selector).screenshot(path=str(target))
            else:
                page.screenshot(path=str(target), full_page=full)

        # 시나리오 1: 첫 화면
        shot("01_overview.png")

        # 시나리오 2: 2024년만 보기 (삼성전자 하락 vs SK하이닉스 상승)
        page.click("#period-presets button[data-preset='2024']")
        page.wait_for_timeout(400)
        expect_period(kpi_rows(page), "2024", problems)
        readout_2024 = page.inner_text("#readout-text")
        page.evaluate("window.scrollTo(0, 0)")
        shot("02_period_2024.png")

        # 시나리오 3: 주가 + 이동평균, 삼성전자만, 전체 기간
        page.click("#period-presets button[data-preset='all']")
        page.click("#metric-buttons button[data-metric='price']")
        page.uncheck("#series-checks input[value='SKH']")
        page.uncheck("#series-checks input[value='KOSPI']")
        page.click("#ma-buttons button[data-ma='20']")
        page.wait_for_timeout(400)
        page.locator("#chart-title").scroll_into_view_if_needed()
        shot("03_price_ma_sec.png", selector="main > section:nth-of-type(2)")

        # 시나리오 4: 동조화(60일 상관), SK하이닉스·KOSPI 켜기
        page.check("#series-checks input[value='SKH']")
        page.check("#series-checks input[value='KOSPI']")
        page.click("#metric-buttons button[data-metric='corr']")
        page.wait_for_timeout(400)
        shot("04_coupling_corr.png", selector="main > section:nth-of-type(2)")

        # 시나리오 5: 사건 '사상 최대 일간 상승(2026-07-31)' 전후 보기 + 고점 대비 낙폭
        page.click("#metric-buttons button[data-metric='dd']")
        items = page.query_selector_all("#event-list li")
        target = next(li for li in items if "2026-07-31" in li.query_selector("time").get_attribute("datetime"))
        target.query_selector("button").click()
        page.wait_for_timeout(600)
        start_val = page.input_value("#start-date")
        end_val = page.input_value("#end-date")
        if (start_val, end_val) != ("2026-06-01", "2026-09-29"):
            problems.append(f"전후 보기 기간 이상: {start_val} ~ {end_val}")
        page.evaluate("window.scrollTo(0, 0)")
        if not args.no_shots:
            box = page.locator("main > section:nth-of-type(2)").bounding_box()
            page.screenshot(path=str(SHOTS / "05_event_window_drawdown.png"), full_page=True,
                            clip={"x": 0, "y": 0, "width": 1280, "height": box["y"] + box["height"] + 24})

        # 시나리오 6: 표로 보기 (그래프의 접근성 대체 수단)
        page.click("#table-toggle")
        page.wait_for_timeout(300)
        n_rows = page.eval_on_selector_all("#chart-table tbody tr", "els => els.length")
        if n_rows < 50:
            problems.append(f"표로 보기 행 수가 너무 적음: {n_rows}")
        shot("06_table_view.png", selector="main > section:nth-of-type(2)")

        # 시나리오 7: 휴대폰 화면 + 어두운 화면
        mob = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, locale="ko-KR", color_scheme="dark")
        if args.fonts:
            mob.route("https://fonts.googleapis.com/**", fonts_css)
            mob.route("https://fonts.local/files/**", font_file)
        else:
            mob.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        mp = mob.new_page()
        mp.on("pageerror", lambda e: console_errors.append(str(e)))
        mp.goto(base, wait_until="networkidle")
        mp.wait_for_selector("#main-chart .main-svg")
        overflow = mp.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        if overflow > 0:
            problems.append(f"휴대폰 폭에서 가로 스크롤 발생: {overflow}px")
        if not args.no_shots:
            mp.screenshot(path=str(SHOTS / "07_mobile_dark.png"))
        mob.close()
        browser.close()
    httpd.shutdown()

    print("첫 화면 문장:", readout)
    print("2024년 문장:", readout_2024)
    print("콘솔 오류:", console_errors or "없음")
    print("문제:", problems or "없음")
    return 0 if not problems and not console_errors else 1


if __name__ == "__main__":
    sys.exit(main())
