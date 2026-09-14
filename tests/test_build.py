import importlib.util
import pathlib
import sys
import unittest
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("bidledger_build", ROOT / "scripts" / "build.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class RssTests(unittest.TestCase):
    def test_feed_is_valid_rss_and_newest_first(self):
        items = [
            {"id": "old", "t": "Older & tender", "p": "2026-08-01", "d": "2026-10-01",
             "c": "ITA", "b": "Buyer <one>"},
            {"id": "new", "t": "Newer tender", "p": "2026-09-01", "d": "2026-11-01",
             "c": "DEU", "b": "Buyer two"},
        ]
        root = ET.fromstring(build.rss("Test & feed", "/s/45.html", items))
        self.assertEqual(root.tag, "rss")
        feed_items = root.findall("./channel/item")
        self.assertEqual([item.findtext("guid") for item in feed_items], ["new", "old"])
        for item in feed_items:
            self.assertIsNotNone(parsedate_to_datetime(item.findtext("pubDate")))

    def test_retired_services_are_absent_from_public_sources(self):
        sources = [ROOT / "config.json", ROOT / "README.md", ROOT / "scripts" / "build.py"]
        text = "\n".join(path.read_text(encoding="utf-8").lower() for path in sources)
        self.assertNotIn("gumroad", text)
        self.assertNotIn("daily email", text)

    def test_notice_cpv_link_always_has_a_generated_destination(self):
        self.assertEqual(build.cpv_notice_url("45000000", {"45000000"}),
                         "/cpv/45000000.html")
        self.assertEqual(build.cpv_notice_url("12345678", {"45000000"}),
                         "/cpv.html?q=12345678")


if __name__ == "__main__":
    unittest.main()
