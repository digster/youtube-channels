import argparse
import io
import os
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from scripts.enrich_channels import (
    YouTubeClient,
    build_about_summary,
    enrich_rows,
    format_subscribers,
    infer_categories,
    main,
)


class FakeClient:
    def __init__(self, channels, uploads):
        self.channels = channels
        self.uploads = uploads

    def fetch_channels(self, channel_ids):
        return {channel_id: self.channels[channel_id] for channel_id in channel_ids if channel_id in self.channels}

    def fetch_recent_titles(self, uploads_playlist_id, max_videos):
        return self.uploads.get(uploads_playlist_id, [])[:max_videos]


class TestYouTubeClient(unittest.TestCase):
    def test_fetch_recent_titles_handles_missing_uploads_playlist(self):
        body = (
            b'{"error":{"code":404,"message":"The playlist identified with the request\'s '
            b'playlistId parameter cannot be found.","errors":[{"reason":"playlistNotFound"}]}}'
        )
        error = HTTPError(
            url="https://www.googleapis.com/youtube/v3/playlistItems?playlistId=UUmissing",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=io.BytesIO(body),
        )
        client = YouTubeClient(
            api_key="token",
            retries=0,
            timeout_seconds=1,
            sleep_seconds=0,
        )

        with patch("scripts.enrich_channels.urlopen", side_effect=error):
            self.assertEqual(
                client.fetch_recent_titles("UUmissing", 3),
                [],
            )


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


class TestApiKeyLoading(unittest.TestCase):
    def test_main_loads_api_key_from_dotenv(self):
        args = argparse.Namespace(
            input="subscriptions.csv",
            output="subscriptions.enriched.csv",
            api_key_env="YOUTUBE_API_KEY",
            max_recent_videos=3,
            top_categories=5,
            sleep_ms=0,
            retries=0,
            log_level="INFO",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("YOUTUBE_API_KEY=dotenv-token\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                with patch("scripts.enrich_channels.parse_args", return_value=args):
                    with patch(
                        "scripts.enrich_channels.read_rows",
                        return_value=(
                            ["channel_id"],
                            [{"channel_id": "UC123"}],
                        ),
                    ):
                        with patch(
                            "scripts.enrich_channels.enrich_rows",
                            return_value=(
                                ["channel_id"],
                                [{"channel_id": "UC123"}],
                            ),
                        ):
                            with patch("scripts.enrich_channels.write_rows"):
                                with patch("scripts.enrich_channels.YouTubeClient") as mock_client:
                                    previous_cwd = os.getcwd()
                                    os.chdir(temp_dir)
                                    try:
                                        exit_code = main()
                                    finally:
                                        os.chdir(previous_cwd)

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                mock_client.call_args.kwargs["api_key"],
                "dotenv-token",
            )


if __name__ == "__main__":
    unittest.main()
