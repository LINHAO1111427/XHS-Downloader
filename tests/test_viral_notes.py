import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from pydantic import ValidationError

from viral_notes import (
    CST,
    CollectionStopped,
    PlatformError,
    ViralError,
    ViralRules,
    ViralSchedule,
    ViralService,
    ViralStore,
    XhsDiscoveryClient,
    collect_notes,
    export_csv,
    follower_count,
    normalize_note,
    parse_count,
    publication_start,
    rank_note,
)

NOW = 1788584400.0
NOTE = "6123456789abcdef01234567"
AUTHOR = "5123456789abcdef01234567"
TOKEN = "test-token+/="


def card(note_id=NOTE, **overrides):
    return {
        "note_id": note_id,
        "title": "sample note",
        "desc": "sample body",
        "time": (NOW - 3600) * 1000,
        "type": "normal",
        "user": {"user_id": AUTHOR, "nickname": "sample author"},
        "interact_info": {
            "liked_count": "600",
            "collected_count": "200",
            "comment_count": "100",
            "share_count": "100",
        },
        "tag_list": [{"name": "sample"}],
        "image_list": [],
    } | overrides


class FixtureClient:
    def __init__(self, settings=None, stop=None):
        self.searches = []
        self.details = []
        self.authors = []
        self.closed = False
        self.stop = stop or Event()

    def search(self, keyword, page, search_id):
        self.searches.append((keyword, page, search_id))
        return {
            "items": [{"id": NOTE, "model_type": "note", "xsec_token": TOKEN}],
            "has_more": False,
        }

    def detail(self, note_id, token):
        self.details.append((note_id, token))
        return card(note_id)

    def author(self, author_id):
        self.authors.append(author_id)
        return {"interactions": [{"type": "fans", "count": "2000"}]}

    def close(self):
        self.closed = True


class ViralParsingTests(unittest.TestCase):
    def test_counts_preserve_zero_and_unknown(self):
        for value, expected in [
            (0, 0),
            ("0", 0),
            ("1.2万+", 12000),
            ("3,200", 3200),
            ("1.2w", 12000),
            ("2K", 2000),
            ("1亿", 100000000),
            ("", None),
            (None, None),
            (True, None),
            (-1, None),
            ("NaN", None),
            ("unknown", None),
        ]:
            with self.subTest(value=value):
                self.assertEqual(parse_count(value), expected)
        self.assertIsNone(
            follower_count({"interactions": [{"type": "follows", "count": 99}]})
        )
        self.assertEqual(
            follower_count({"interactions": [{"type": "fans", "count": 0}]}), 0
        )

    def test_rules_validate_limits_and_normalize_keywords(self):
        self.assertEqual(ViralRules(keywords=[" home ", "home"]).keywords, ["home"])
        for payload in [
            {"keywords": []},
            {"keywords": [" "]},
            {"keywords": ["x" * 51]},
            {"keywords": ["x"], "pages": 4},
            {"keywords": ["x"], "candidate_limit": 101},
            {"keywords": ["x"], "min_ratio": float("inf")},
            {"keywords": ["x"], "hours": 0},
        ]:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                ViralRules(**payload)
        with self.assertRaises(ValidationError):
            ViralSchedule(at="24:00")

    def test_normalize_snake_and_camel_fields_and_cover_hosts(self):
        note = normalize_note(card(), TOKEN)
        self.assertEqual(note["published_at"], NOW - 3600)
        self.assertIn("xsec_token=test-token%2B%2F%3D", note["url"])
        camel = {
            "noteId": NOTE,
            "user": {"userId": AUTHOR, "nickName": "author"},
            "time": NOW - 3600,
            "interactInfo": {
                "likedCount": "600",
                "collectedCount": "200",
                "commentCount": "100",
                "shareCount": "100",
            },
        }
        self.assertEqual(normalize_note(camel, TOKEN)["likes"], 600)
        self.assertEqual(
            normalize_note(
                card(
                    image_list=[
                        {"url_default": "http://sns-webpic-qc.xhscdn.com/a.jpg"}
                    ]
                ),
                TOKEN,
            )["cover"],
            "https://sns-webpic-qc.xhscdn.com/a.jpg",
        )
        self.assertEqual(
            normalize_note(
                card(
                    image_list=[
                        {"url_default": "https://xhscdn.com.evil.example/a.jpg"}
                    ]
                ),
                TOKEN,
            )["cover"],
            "",
        )

    def test_thresholds_time_edges_and_missing_data(self):
        rules = ViralRules(
            keywords=["x"], max_followers=2000, min_interactions=1000, min_ratio=0.5
        )
        note = normalize_note(card(), TOKEN)
        self.assertEqual(rank_note(note, 2000, rules, NOW)["interactions"], 1000)
        self.assertIsNone(rank_note(note, 2001, rules, NOW))
        self.assertIsNone(rank_note(note, None, rules, NOW))
        for changed in [
            {"published_at": NOW + 1},
            {"published_at": NOW - 86401},
            {"published_at": None},
            {"likes": None},
        ]:
            self.assertIsNone(rank_note(note | changed, 2000, rules, NOW))
        self.assertIsNotNone(
            rank_note(note | {"published_at": NOW - 86400}, 2000, rules, NOW)
        )
        self.assertIsNotNone(rank_note(note, 0, rules, NOW))

    def test_score_favors_fresh_low_follower_notes(self):
        rules = ViralRules(keywords=["x"])
        note = normalize_note(card(), TOKEN)
        ranked = rank_note(note, 1000, rules, NOW)
        self.assertGreater(ranked["score"], rank_note(note, 2000, rules, NOW)["score"])
        self.assertGreater(
            ranked["score"],
            rank_note(note | {"published_at": NOW - 7200}, 1000, rules, NOW)["score"],
        )

    def test_today_is_shanghai_midnight_not_rolling_24_hours(self):
        now = datetime(2026, 9, 5, 9, 0, tzinfo=CST).timestamp()
        midnight = datetime(2026, 9, 5, 0, 0, tzinfo=CST).timestamp()
        rules = ViralRules(
            keywords=["x"],
            time_range="today",
            max_followers=999,
            min_likes=500,
            min_interactions=0,
            min_ratio=0,
        )
        note = normalize_note(card(), TOKEN)
        self.assertEqual(publication_start(rules, now), midnight)
        self.assertIsNotNone(
            rank_note(note | {"published_at": midnight}, 999, rules, now)
        )
        self.assertIsNone(
            rank_note(note | {"published_at": midnight - 1}, 999, rules, now)
        )
        self.assertIsNone(rank_note(note | {"published_at": now + 1}, 999, rules, now))
        rolling = rules.model_copy(update={"time_range": "rolling"})
        self.assertIsNotNone(
            rank_note(note | {"published_at": midnight - 1}, 999, rolling, now)
        )

    def test_under_one_thousand_and_at_least_five_hundred_likes(self):
        rules = ViralRules(
            keywords=["x"],
            max_followers=999,
            min_likes=500,
            min_interactions=0,
            min_ratio=0,
        )
        note = normalize_note(card(), TOKEN) | {"likes": 500}
        self.assertIsNotNone(rank_note(note, 999, rules, NOW))
        self.assertIsNone(rank_note(note, 1000, rules, NOW))
        self.assertIsNone(
            rank_note(note | {"likes": 499, "collects": 10000}, 999, rules, NOW)
        )
        self.assertIsNone(rank_note(note | {"likes": None}, 999, rules, NOW))

    def test_new_rules_validate_and_old_rules_keep_their_meaning(self):
        old = ViralRules(keywords=["x"])
        self.assertEqual(old.min_likes, 0)
        self.assertEqual(old.time_range, "rolling")
        for fields in [{"min_likes": -1}, {"time_range": "yesterday"}]:
            with self.assertRaises(ValidationError):
                ViralRules(keywords=["x"], **fields)

    def test_csv_utf8_bom_quotes_and_formula_protection(self):
        note = rank_note(
            normalize_note(card(title="=1+1", desc='body, "quoted"\nnext'), TOKEN),
            2000,
            ViralRules(keywords=["x"]),
            NOW,
        )
        result = export_csv(
            {"items": [note | {"keywords": ["x"], "collected_at": NOW}]}
        )
        self.assertTrue(result.startswith(b"\xef\xbb\xbf"))
        text = result.decode("utf-8-sig")
        self.assertIn("'=1+1", text)
        self.assertIn('"body, ""quoted""\nnext"', text)
        self.assertIn("+08:00", text)


class ViralCollectorTests(unittest.TestCase):
    def collect(self, client, **changes):
        return collect_notes(
            client,
            ViralRules(keywords=["home", "kitchen"], **changes),
            Event(),
            lambda result: None,
            NOW,
        )

    def test_deduplicates_notes_and_keeps_all_keywords(self):
        client = FixtureClient()
        result = self.collect(client, pages=3)
        self.assertEqual(len(client.searches), 2)
        self.assertEqual(len(client.details), 1)
        self.assertEqual(len(client.authors), 1)
        self.assertEqual(result["items"][0]["keywords"], ["home", "kitchen"])
        self.assertEqual(result["scanned"], 1)

    def test_pagination_budget_and_author_cache(self):
        client = FixtureClient()
        client.search = Mock(
            return_value={
                "items": [
                    {"id": f"{index:024x}", "xsec_token": TOKEN} for index in range(20)
                ],
                "has_more": True,
            }
        )
        result = self.collect(client, pages=2, candidate_limit=3, limit=2)
        self.assertEqual(client.search.call_count, 4)
        self.assertEqual(len(client.details), 3)
        self.assertEqual(len(client.authors), 1)
        self.assertEqual(result["matched"], 3)
        self.assertEqual(len(result["items"]), 2)
        self.assertTrue(result["truncated"])

    def test_missing_followers_are_excluded(self):
        client = FixtureClient()
        client.author = Mock(return_value={"interactions": []})
        result = self.collect(client)
        self.assertEqual(result["unknown"], 1)
        self.assertEqual(result["items"], [])

    def test_like_and_calendar_filters_apply_before_author_lookup(self):
        now = datetime(2026, 9, 5, 9, 0, tzinfo=CST).timestamp()
        midnight = datetime(2026, 9, 5, 0, 0, tzinfo=CST).timestamp()
        rules = ViralRules(
            keywords=["x"], time_range="today", max_followers=999, min_likes=500
        )
        for detail in [
            card(time=(midnight - 1) * 1000),
            card(
                time=(now - 60) * 1000,
                interact_info={
                    "liked_count": 499,
                    "collected_count": 10000,
                    "comment_count": 0,
                    "share_count": 0,
                },
            ),
        ]:
            client = FixtureClient()
            client.detail = Mock(return_value=detail)
            result = collect_notes(client, rules, Event(), lambda result: None, now)
            self.assertEqual(result["items"], [])
            self.assertEqual(client.authors, [])
            self.assertEqual(result["window_start"], midnight)
            self.assertEqual(result["window_end"], now)

    def test_outdated_and_low_interaction_notes_skip_author_requests(self):
        for details in [
            card(time=NOW - 90000),
            card(
                interact_info={
                    "liked_count": 1,
                    "collected_count": 1,
                    "comment_count": 1,
                    "share_count": 0,
                }
            ),
        ]:
            client = FixtureClient()
            client.detail = Mock(return_value=details)
            self.assertEqual(self.collect(client)["items"], [])
            self.assertEqual(client.authors, [])

    def test_keyword_failure_retains_other_results(self):
        client = FixtureClient()
        original = client.search
        client.search = Mock(
            side_effect=[
                PlatformError("search unavailable"),
                original("kitchen", 1, "id"),
            ]
        )
        result = self.collect(client)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(len(result["items"]), 1)

    def test_fatal_challenge_stops_all_further_requests(self):
        client = FixtureClient()
        client.search = Mock(side_effect=PlatformError("login required", True))
        result = self.collect(client)
        self.assertTrue(result["fatal"])
        self.assertEqual(client.search.call_count, 1)
        self.assertEqual(client.details, [])

    def test_cancel_before_network_and_malformed_search(self):
        client = FixtureClient()
        stop = Event()
        stop.set()
        with self.assertRaises(CollectionStopped):
            collect_notes(
                client, ViralRules(keywords=["x"]), stop, lambda result: None, NOW
            )
        self.assertEqual(client.searches, [])
        client.search = Mock(return_value={})
        self.assertEqual(len(self.collect(client)["errors"]), 2)


class ViralTransportTests(unittest.TestCase):
    def test_missing_cookie_fails_before_network(self):
        with patch("viral_notes.Session") as session, self.assertRaises(PlatformError):
            XhsDiscoveryClient({}, Event())
        session.assert_not_called()

    def test_real_signer_and_serialized_body_match(self):
        with patch("viral_notes.Session") as session:
            response = session.return_value.post.return_value
            response.status_code = 200
            response.json.return_value = {
                "success": True,
                "code": 0,
                "data": {"items": [], "has_more": False},
            }
            client = XhsDiscoveryClient(
                {"cookie": "a1=test-browser-id; web_session=test-session"}, Event()
            )
            client.search("厨房", 1, "search-id")
            args, kwargs = session.return_value.post.call_args
            self.assertEqual(
                args[0], "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes"
            )
            self.assertIn("x-s", kwargs["headers"])
            self.assertIn("x-t", kwargs["headers"])
            self.assertIn('"keyword":"厨房"', kwargs["data"].decode("utf-8"))
            self.assertEqual(json.loads(kwargs["data"])["sort"], "time_descending")
            client.close()

    def test_challenge_and_invalid_json_are_explicit(self):
        for code in [403, 429, 461]:
            with patch("viral_notes.Session") as session:
                session.return_value.post.return_value.status_code = code
                client = XhsDiscoveryClient(
                    {"cookie": "a1=test; web_session=test"}, Event()
                )
                with self.assertRaises(PlatformError) as caught:
                    client.search("x", 1, "id")
                self.assertTrue(caught.exception.fatal)
                self.assertIn(str(code), str(caught.exception))
                self.assertNotIn("web_session", str(caught.exception))
                client.close()


class ViralServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ViralStore(Path(self.temp.name) / "viral.db")
        self.service = ViralService(self.store, lambda: {}, FixtureClient)

    def tearDown(self):
        self.service.shutdown()
        self.temp.cleanup()

    def test_run_persisted_and_reopened(self):
        with patch("viral_notes.time", return_value=NOW):
            run = self.service.submit(ViralRules(keywords=["x"]))
            self.service.worker.join(5)
        result = ViralStore(self.store.path).get_run(run["id"])
        self.assertEqual(result["state"], "success")
        self.assertEqual(len(result["items"]), 1)
        self.assertIsNotNone(result["finished_at"])

    def test_concurrent_run_rejected_and_cancellation_persisted(self):
        started = Event()

        class SlowClient(FixtureClient):
            def search(self, *args):
                started.set()
                self.stop.wait(5)
                raise CollectionStopped("cancelled")

        self.service.client_factory = SlowClient
        run = self.service.submit(ViralRules(keywords=["x"]))
        self.assertTrue(started.wait(2))
        with self.assertRaises(ViralError):
            self.service.submit(ViralRules(keywords=["x"]))
        self.service.cancel(run["id"])
        self.service.worker.join(5)
        self.assertEqual(self.store.get_run(run["id"])["state"], "cancelled")
        self.assertIsNone(self.service.active_id)

    def test_daily_runs_once_per_shanghai_day_and_settings_persist(self):
        config = ViralSchedule(
            enabled=True, at="09:00", rules=ViralRules(keywords=["home"])
        )
        self.service.configure(config)
        before = datetime(2026, 9, 5, 8, 59, tzinfo=CST)
        due = datetime(2026, 9, 5, 9, 0, tzinfo=CST)
        self.service.tick(before)
        self.assertEqual(self.store.runs(), [])
        self.service.tick(due)
        self.service.worker.join(5)
        self.service.tick(due)
        self.assertEqual(len(self.store.runs()), 1)
        self.assertEqual(self.store.config()["last_date"], "2026-09-05")
        self.assertEqual(self.store.runs()[0]["source"], "daily")
        self.service.configure(config)
        self.service.tick(due)
        self.assertEqual(len(self.store.runs()), 1)
        self.service.tick(datetime(2026, 9, 6, 9, 0, tzinfo=CST))
        self.service.worker.join(5)
        self.assertEqual(len(self.store.runs()), 2)

    def test_daily_cookie_failure_recorded_without_retry_storm(self):
        self.service.client_factory = XhsDiscoveryClient
        self.service.configure(ViralSchedule(enabled=True))
        now = datetime(2026, 9, 5, 12, 0, tzinfo=CST)
        self.service.tick(now)
        self.service.tick(now)
        self.assertEqual(len(self.store.runs()), 1)
        self.assertEqual(self.store.runs()[0]["state"], "failed")
        self.assertIn("Cookie", self.store.runs()[0]["message"])

    def test_restart_marks_unfinished_runs_interrupted(self):
        with patch("viral_notes.time", return_value=NOW):
            run = self.service.submit(ViralRules(keywords=["x"]))
            self.service.worker.join(5)
        unfinished = copy.deepcopy(self.store.get_run(run["id"]))
        unfinished["state"] = "processing"
        self.store.save_run(unfinished)
        self.service.start()
        self.assertEqual(self.store.get_run(run["id"])["state"], "interrupted")


if __name__ == "__main__":
    unittest.main()
