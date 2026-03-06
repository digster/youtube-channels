import unittest
from pathlib import Path


class TestDashboardHtml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dashboard_path = Path("dashboard.html")
        cls.contents = cls.dashboard_path.read_text(encoding="utf-8")

    def test_dashboard_file_exists(self):
        self.assertTrue(self.dashboard_path.exists())

    def test_required_columns_declared(self):
        expected_columns = [
            "channel_id",
            "title",
            "description",
            "thumbnail_url",
            "subscribed_at",
            "link",
            "subscribers",
            "subscribers_readable",
            "about",
            "category",
        ]
        for column in expected_columns:
            self.assertIn(f'"{column}"', self.contents)

    def test_expected_ui_controls_present(self):
        expected_ids = [
            'id="csvInput"',
            'id="searchInput"',
            'id="categoryFilter"',
            'id="sortBy"',
            'id="minSubs"',
            'id="maxSubs"',
            'id="categoryChart"',
            'id="subscriberChart"',
            'id="topChannels"',
            'id="auditList"',
            'id="heatmap"',
            'id="tableBody"',
        ]
        for identifier in expected_ids:
            self.assertIn(identifier, self.contents)

    def test_dashboard_uses_cdn_dependencies(self):
        self.assertIn("papaparse", self.contents.lower())
        self.assertIn("chart.umd.min.js", self.contents)


if __name__ == "__main__":
    unittest.main()
