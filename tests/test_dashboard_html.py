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
            'id="tableSearchInput"',
            'id="pageSize"',
            'id="firstPage"',
            'id="pageNumbers"',
            'id="lastPage"',
            'id="categoryChart"',
            'id="subscriberChart"',
            'id="topChannels"',
            'id="auditList"',
            'id="heatmap"',
            'id="tableBody"',
        ]
        for identifier in expected_ids:
            self.assertIn(identifier, self.contents)

    def test_legacy_top_search_removed(self):
        self.assertNotIn('id="searchInput"', self.contents)

    def test_top_filter_controls_removed(self):
        removed_ids = [
            'id="categoryFilter"',
            'id="sortBy"',
            'id="minSubs"',
            'id="maxSubs"',
            'id="resetFilters"',
        ]
        for identifier in removed_ids:
            self.assertNotIn(identifier, self.contents)
        self.assertNotIn('aria-label="Filtering controls"', self.contents)

    def test_pagination_is_configurable(self):
        self.assertIn("PAGE_SIZE_OPTIONS", self.contents)
        self.assertIn("DEFAULT_PAGE_SIZE", self.contents)
        self.assertIn("function getTotalPages()", self.contents)
        self.assertIn("function renderPageNumbers(totalPages)", self.contents)
        self.assertIn("function handlePageSizeChange()", self.contents)

    def test_table_renders_before_charts(self):
        table_index = self.contents.index('aria-label="Channel table"')
        chart_index = self.contents.index('aria-label="Charts"')
        self.assertLess(table_index, chart_index)

    def test_table_height_is_fixed_and_increased(self):
        self.assertIn("height: 620px;", self.contents)
        self.assertIn("@media (max-width: 680px)", self.contents)
        self.assertIn("height: 460px;", self.contents)

    def test_dashboard_uses_cdn_dependencies(self):
        self.assertIn("papaparse", self.contents.lower())
        self.assertIn("chart.umd.min.js", self.contents)

    def test_charts_use_compact_number_formatting(self):
        self.assertIn("formatCompactNumber", self.contents)
        self.assertIn("notation: \"compact\"", self.contents)
        self.assertIn("maxBarThickness", self.contents)

    def test_canvas_height_is_css_driven(self):
        self.assertNotIn('id=\"categoryChart\" height=', self.contents)
        self.assertNotIn('id=\"subscriberChart\" height=', self.contents)


if __name__ == "__main__":
    unittest.main()
