import unittest

from scripts.enrich_channels import (
    build_about_summary,
    enrich_rows,
    format_subscribers,
    infer_categories,
)


class FakeClient:
    def __init__(self, channels, uploads):
        self.channels = channels
        self.uploads = uploads

    def fetch_channels(self, channel_ids):
        return {channel_id: self.channels[channel_id] for channel_id in channel_ids if channel_id in self.channels}

    def fetch_recent_titles(self, uploads_playlist_id, max_videos):
        return self.uploads.get(uploads_playlist_id, [])[:max_videos]


class TestFormatting(unittest.TestCase):
    def test_format_subscribers(self):
        self.assertEqual(format_subscribers(None), "")
        self.assertEqual(format_subscribers(532), "532")
        self.assertEqual(format_subscribers(1_200), "1.2K")
        self.assertEqual(format_subscribers(12_500), "12.5K")
        self.assertEqual(format_subscribers(1_234_567), "1.23M")
        self.assertEqual(format_subscribers(245_000_000), "245M")


class TestCategoryInference(unittest.TestCase):
    def test_hybrid_ranking_prefers_topic_and_keywords(self):
        categories = infer_categories(
            title="Premier League Tactical Breakdown",
            description="Weekly football match analysis and strategy lessons",
            recent_titles=["Champions League review", "Best pressing systems in soccer"],
            topic_categories=["Sports"],
            top_n=3,
        )
        self.assertGreaterEqual(len(categories), 1)
        self.assertEqual(categories[0], "Sports")


class TestAboutSummary(unittest.TestCase):
    def test_build_about_summary_with_recent_keywords(self):
        summary = build_about_summary(
            channel_title="Data Deep Dives",
            description="Clear explainers about machine learning and analytics.",
            recent_titles=["Neural networks in 10 minutes", "Data pipelines and model drift"],
            categories=["Technology", "Education"],
        )
        self.assertIn("machine learning", summary.lower())
        self.assertIn("recent uploads focus on", summary.lower())


class TestEnrichmentPipeline(unittest.TestCase):
    def test_enrich_rows_adds_new_columns(self):
        rows = [
            {
                "channel_id": "UC123",
                "title": "Fallback Title",
                "description": "Fallback description",
                "thumbnail_url": "https://example.com/thumb.jpg",
                "subscribed_at": "2026-01-01T00:00:00Z",
            }
        ]
        fake_channels = {
            "UC123": {
                "id": "UC123",
                "snippet": {"title": "Real Channel", "description": "Business and startup interviews."},
                "statistics": {"subscriberCount": "98765", "hiddenSubscriberCount": False},
                "contentDetails": {"relatedPlaylists": {"uploads": "UU123"}},
                "topicDetails": {"topicCategories": ["https://en.wikipedia.org/wiki/Technology"]},
            }
        }
        fake_uploads = {"UU123": ["Startup fundraising mistakes", "Building a SaaS in 2026"]}
        client = FakeClient(fake_channels, fake_uploads)

        fieldnames, enriched_rows = enrich_rows(rows, client, max_recent_videos=2, top_categories=4)

        self.assertIn("link", fieldnames)
        self.assertIn("subscribers", fieldnames)
        self.assertIn("subscribers_readable", fieldnames)
        self.assertIn("about", fieldnames)
        self.assertIn("category", fieldnames)

        enriched = enriched_rows[0]
        self.assertEqual(enriched["link"], "https://www.youtube.com/channel/UC123")
        self.assertEqual(enriched["subscribers"], "98765")
        self.assertEqual(enriched["subscribers_readable"], "98.8K")
        self.assertIn("business", enriched["category"].lower())


if __name__ == "__main__":
    unittest.main()
