"""저장소에 들어 있는 원자료가 분석에 쓴 그대로인지, 품질 기준을 모두 통과하는지 확인한다.

실행: python -m unittest discover -s tests -v
"""
import hashlib
import json
import unittest

from src import config as C
from src import prepare, quality


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestRawData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stocks, cls.kospi = prepare.load_raw()
        cls.daily = prepare.build_daily(cls.stocks, cls.kospi)
        cls.q, cls.cp = quality.run_quality_checks(cls.stocks, cls.kospi, cls.daily)

    def test_raw_files_match_manifest(self):
        manifest = json.loads(C.MANIFEST_JSON.read_text(encoding="utf-8"))
        for item in manifest["outputs"].values():
            self.assertEqual(sha256(C.ROOT / item["path"]), item["sha256"], item["path"])

    def test_period_and_size(self):
        self.assertEqual(self.q["basic"]["analysis_trading_days"], 927)
        self.assertEqual(self.q["basic"]["trading_days_by_year"], {"2023": 245, "2024": 244, "2025": 242, "2026": 196})
        self.assertGreaterEqual(self.q["basic"]["analysis_trading_days"], 100)   # 미션 조건: 100개 이상

    def test_no_missing_or_duplicates(self):
        self.assertEqual(sum(self.q["missing"]["stocks"].values()), 0)
        self.assertEqual(sum(self.q["missing"]["kospi"].values()), 0)
        self.assertEqual(self.q["duplicates"], 0)
        self.assertTrue(self.q["calendar_aligned"])

    def test_every_missing_weekday_is_a_market_holiday(self):
        c = self.q["closures"]
        self.assertEqual(c["weekday_non_trading_days"], 67)
        self.assertEqual(c["unexplained"], [])

    def test_no_trading_on_reference_holidays(self):
        # 참고표는 데이터와 무관하게 공휴일 달력 + KRX 규정으로 만든다. 반대 방향 대조.
        c = self.q["closures"]
        self.assertEqual(c["reference_days"], 67)
        self.assertEqual(c["reference_basis"], {"holidays.KR": 61, "KRX 규정": 6})
        self.assertEqual(c["reference_days_that_traded"], [])

    def test_no_data_error_outliers(self):
        e = self.q["error_outliers"]
        for key in ("ohlc_logic_violations", "nonpositive_price_or_volume", "price_limit_violations",
                    "changes_mismatch", "ratio_mismatch"):
            self.assertEqual(e[key], 0, key)

    def test_cross_source_checkpoints(self):
        cp = self.q["checkpoints"]
        self.assertEqual(cp["passed"], cp["n"])
        self.assertTrue(cp["stock_values_exact"])
        self.assertLess(cp["max_kospi_close_rel_error_pct"], 0.2)

    def test_base_anchor_is_not_counted_as_a_check(self):
        cp = self.q["checkpoints"]
        self.assertEqual((cp["n_reference_rows"], cp["n"]), (52, 51))
        anchor = self.cp[self.cp["role"] != "대조"]
        self.assertEqual(anchor[["date", "item"]].values.tolist(), [[C.BASE_DATE, "kospi_close"]])

    def test_all_hard_checks(self):
        self.assertTrue(self.q["all_hard_checks_passed"])


if __name__ == "__main__":
    unittest.main()
