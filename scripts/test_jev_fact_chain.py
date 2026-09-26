import hashlib
import json
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

from jev_fact_chain import collect_rule_document, collect_source, main as fact_chain_main, run_review as actual_run_review


NOW = datetime(2026, 9, 25, 18, 0, tzinfo=timezone.utc)
SOURCE_URL = "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm"
BRIEFINGS_URL = "https://www.whitehouse.gov/briefings-statements/2026/09/congressional-bill-h-r-5334-signed-into-law/"
FEED = f"""<rss><channel><item><title>Federal Reserve issues FOMC statement</title>
<link>{SOURCE_URL}</link><pubDate>Wed, 16 Sep 2026 18:00:00 GMT</pubDate>
</item></channel></rss>"""
BRIEFINGS_FEED = f"""<rss><channel><item><title>Congressional Bill H.R. 5334 Signed into Law</title>
<link>{BRIEFINGS_URL}</link><pubDate>Fri, 18 Sep 2026 21:43:23 +0000</pubDate>
</item></channel></rss>"""
ARTICLE = "<html><body><main>The Committee decided to maintain the target range for the federal funds rate at 3-1/2 to 3-3/4 percent.</main></body></html>"
ARTICLE_TEXT = "The Committee decided to maintain the target range for the federal funds rate at 3-1/2 to 3-3/4 percent."
SENATE_VOTE_URL = "https://www.senate.gov/legislative/LIS/roll_call_votes/vote1192/vote_119_2_00241.xml"
SENATE_MENU = """<vote_summary><congress>119</congress><session>2</session><congress_year>2026</congress_year><votes>
<vote><vote_number>00241</vote_number><vote_date>23-Sep</vote_date><result>Confirmed</result>
<title>Confirmation: Angela Veronica Colmenero</title></vote></votes></vote_summary>"""
SENATE_VOTE = """<roll_call_vote><congress>119</congress><session>2</session><congress_year>2026</congress_year>
<vote_number>241</vote_number><vote_date>September 23, 2026,  02:16 PM</vote_date>
<modify_date>September 23, 2026,  03:46 PM</modify_date>
<vote_question_text>On the Nomination PN999-1</vote_question_text>
<vote_document_text>Angela Veronica Colmenero to be United States District Judge</vote_document_text>
<vote_result>Nomination Confirmed</vote_result><vote_title>Confirmation: Angela Veronica Colmenero</vote_title>
</roll_call_vote>"""


def market(question="Will the Fed maintain interest rates after the September meeting?"):
    return {
        "id": "4620900", "slug": "fed-september-rates", "conditionId": "0xabc", "question": question,
        "createdAt": "2026-09-10T16:18:52Z",
        "description": "Resolves Yes if the Federal Reserve maintains its target range after its September 2026 meeting.",
        "active": True, "closed": False, "acceptingOrders": True,
        "enableOrderBook": True, "restricted": False,
        "outcomes": '["Yes", "No"]', "clobTokenIds": '["yes-token", "no-token"]',
        "feesEnabled": False,
    }


def case():
    return {
        "market_slug": "fed-september-rates", "category": "finance",
        "source_kind": "federal_reserve_monetary", "source_url": SOURCE_URL,
        "rule_review": {
            "resolution_rules_sha256": hashlib.sha256(market()["description"].encode()).hexdigest(),
            "source_content_sha256": hashlib.sha256(ARTICLE_TEXT.encode()).hexdigest(),
            "complete": True, "reviewed_by": "researcher", "reviewed_at": "2026-09-25T17:00:00+00:00",
            "evidence_verdict": "QUALIFIES", "evidence_reason": "The official statement matches the stated resolution event.",
        },
        "rule_checks": [{
            "criterion": "September FOMC target range remained unchanged",
            "rule_quote": "Resolves Yes if the Federal Reserve maintains its target range",
            "evidence_quote": "The Committee decided to maintain the target range",
            "status": "CONFIRMED", "reviewed_by": "researcher",
            "reviewed_at": "2026-09-25T17:00:00+00:00",
        }],
    }


def run_review(supplied, now, fetch_fn, http_fn, *args, **kwargs):
    """Provide confirmed Gamma topic tags to tests focused on later chain stages."""
    category = supplied.get("category")

    def with_tags(url, *http_args, **http_kwargs):
        if url.endswith("/markets/4620900/tags"):
            return [{"slug": "politics" if category == "politics" else "economy"}]
        return http_fn(url, *http_args, **http_kwargs)

    return actual_run_review(supplied, now, fetch_fn, with_tags, *args, **kwargs)


class JevFactChainTest(unittest.TestCase):
    def test_external_rule_document_url_must_be_approved_pdf(self):
        for url in (
            "https://example.com/market_products/rules.pdf",
            "http://polymarket-upload.s3.us-east-2.amazonaws.com/market_products/rules.pdf",
            "https://polymarket-upload.s3.us-east-2.amazonaws.com/other/rules.pdf",
            "https://polymarket-upload.s3.us-east-2.amazonaws.com/market_products/rules.html",
        ):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "approved Polymarket PDF"):
                collect_rule_document(url)

    def test_multiple_external_full_rule_documents_do_not_enter_jev(self):
        rules = (market()["description"]
                 + " For full rules, see: https://polymarket-upload.s3.us-east-2.amazonaws.com/market_products/one.pdf"
                 + " and https://polymarket-upload.s3.us-east-2.amazonaws.com/market_products/two.pdf")

        def http(url, body=None, api_key=None):
            if "/markets/slug/" in url:
                return {**market(), "description": rules}
            self.fail(f"Jev or book called without both full rule documents: {url}")

        result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE,
                            http, "secret", rule_document_fn=lambda url: self.fail(f"PDF fetched: {url}"))

        self.assertEqual("RULE_REVIEW_REQUIRED", result["status"])
        self.assertIn("multiple external full rules", result["reason"])
        self.assertNotIn("jev", result)

    def test_official_feed_item_and_article_are_recorded(self):
        def fetch(url):
            return FEED if url.endswith("press_monetary.xml") else ARTICLE

        source = collect_source("federal_reserve_monetary", SOURCE_URL, NOW, fetch)

        self.assertEqual("2026-09-16T18:00:00+00:00", source["published_at"])
        self.assertEqual(SOURCE_URL, source["source_url"])
        self.assertIn("Committee decided", source["text"])
        self.assertEqual(64, len(source["content_sha256"]))

    def test_official_feed_pubdate_without_timezone_is_rejected(self):
        undated_feed = FEED.replace("18:00:00 GMT", "18:00:00")

        with self.assertRaisesRegex(ValueError, "time zone"):
            collect_source("federal_reserve_monetary", SOURCE_URL, NOW,
                           lambda target: undated_feed if target.endswith(".xml") else self.fail("article fetched"))

        result = run_review(case(), NOW,
                            lambda target: undated_feed if target.endswith(".xml") else self.fail("article fetched"),
                            lambda target: market(), "secret")
        self.assertEqual("SOURCE_UNAVAILABLE", result["status"])
        self.assertIn("time zone", result["reason"])
        self.assertNotIn("jev", result)

    def test_white_house_official_feed_is_supported_for_politics(self):
        url = "https://www.whitehouse.gov/presidential-actions/2026/09/example-action/"
        feed = f"<rss><channel><item><title>Example action</title><link>{url}</link><pubDate>Fri, 18 Sep 2026 22:02:43 +0000</pubDate></item></channel></rss>"

        source = collect_source("white_house_presidential", url, NOW, lambda target: feed if target.endswith("/feed/") else "<main>Official action text</main>")

        self.assertEqual(url, source["source_url"])
        self.assertIn("Official action text", source["text"])

    def test_white_house_briefings_feed_verifies_dated_signing_statement(self):
        article = "<html><body><main>On Friday, September 18, 2026, the President signed into law: H.R. 5334.</main></body></html>"
        fetched = []

        def fetch(url):
            fetched.append(url)
            return BRIEFINGS_FEED if url.endswith("/briefings-statements/feed/") else article

        source = collect_source("white_house_briefings", BRIEFINGS_URL, NOW, fetch)

        self.assertEqual("white_house_briefings", source["publisher"])
        self.assertEqual("2026-09-18T21:43:23+00:00", source["published_at"])
        self.assertEqual("Congressional Bill H.R. 5334 Signed into Law", source["title"])
        self.assertEqual(["https://www.whitehouse.gov/briefings-statements/feed/", BRIEFINGS_URL], fetched)
        self.assertIn("signed into law: H.R. 5334", source["text"])

    def test_white_house_briefings_requires_feed_membership(self):
        fetched = []

        def fetch(url):
            fetched.append(url)
            return "<rss><channel></channel></rss>" if url.endswith("/feed/") else self.fail("article fetched")

        with self.assertRaisesRegex(ValueError, "official feed"):
            collect_source("white_house_briefings", BRIEFINGS_URL, NOW, fetch)
        self.assertEqual(["https://www.whitehouse.gov/briefings-statements/feed/"], fetched)

    def test_senate_vote_is_dated_and_verified_against_official_menu(self):
        fetched = []

        def fetch(url):
            fetched.append(url)
            return SENATE_MENU if "vote_menu_119_2.xml" in url else SENATE_VOTE

        source = collect_source("senate_roll_call", SENATE_VOTE_URL, NOW, fetch)

        self.assertEqual("2026-09-23T18:16:00+00:00", source["published_at"])
        self.assertEqual("vote_date", source["time_basis"])
        self.assertEqual("2026-09-23T19:46:00+00:00", source["source_modified_at"])
        self.assertEqual(SENATE_VOTE_URL, source["source_url"])
        self.assertIn("Nomination Confirmed", source["text"])
        self.assertIn("Angela Veronica Colmenero", source["text"])
        self.assertEqual(hashlib.sha256(source["text"].encode()).hexdigest(), source["content_sha256"])
        self.assertEqual(hashlib.sha256(SENATE_VOTE.encode()).hexdigest(), source["raw_xml_sha256"])
        self.assertEqual(2, len(fetched))

    def test_senate_vote_missing_from_menu_is_not_fetched(self):
        fetched = []

        def fetch(url):
            fetched.append(url)
            return SENATE_MENU.replace("00241", "00242")

        with self.assertRaisesRegex(ValueError, "official vote menu"):
            collect_source("senate_roll_call", SENATE_VOTE_URL, NOW, fetch)
        self.assertEqual(1, len(fetched))

    def test_senate_vote_identity_date_or_result_mismatch_is_rejected(self):
        for detail in (
            SENATE_VOTE.replace("<vote_number>241</vote_number>", "<vote_number>242</vote_number>"),
            SENATE_VOTE.replace("September 23", "September 24"),
            SENATE_VOTE.replace("Nomination Confirmed", "Nomination Rejected"),
            SENATE_VOTE.replace("Nomination Confirmed", "Nomination Not Confirmed"),
        ):
            with self.subTest(detail=detail):
                with self.assertRaisesRegex(ValueError, "Senate vote"):
                    collect_source("senate_roll_call", SENATE_VOTE_URL, NOW,
                                   lambda url: SENATE_MENU if "vote_menu_119_2.xml" in url else detail)

    def test_senate_vote_rejects_nonofficial_or_noncanonical_url(self):
        for url in (
            SENATE_VOTE_URL.replace("www.senate.gov", "example.com"),
            SENATE_VOTE_URL.replace("www.senate.gov", "www.senate.gov:444"),
            SENATE_VOTE_URL + "?redirect=example.com",
            SENATE_VOTE_URL.replace("vote_119_2", "vote_118_2"),
        ):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "Senate vote URL"):
                collect_source("senate_roll_call", url, NOW, lambda target: self.fail(target))

    def test_senate_vote_rejects_missing_early_or_future_modification_time(self):
        for detail in (
            SENATE_VOTE.replace("<modify_date>September 23, 2026,  03:46 PM</modify_date>", ""),
            SENATE_VOTE.replace("03:46 PM", "01:46 PM"),
            SENATE_VOTE.replace("September 23, 2026,  03:46 PM", "September 26, 2026,  03:46 PM"),
        ):
            with self.subTest(detail=detail), self.assertRaisesRegex(ValueError, "Senate vote modification time"):
                collect_source("senate_roll_call", SENATE_VOTE_URL, NOW,
                               lambda url: SENATE_MENU if "vote_menu_119_2.xml" in url else detail)

    def test_reviewed_senate_vote_can_reach_read_only_jev_and_one_side_book(self):
        source = collect_source("senate_roll_call", SENATE_VOTE_URL, NOW,
                                lambda url: SENATE_MENU if "vote_menu_119_2.xml" in url else SENATE_VOTE)
        slug = "angela-colmenero-confirmed-by-september-30"
        rules = "Resolves Yes if Angela Veronica Colmenero is confirmed by the Senate as District Judge by September 30, 2026."
        political_market = {**market("Will Angela Veronica Colmenero be confirmed as District Judge by September 30?"),
                            "id": "241", "slug": slug, "description": rules}
        reviewed = {
            "market_slug": slug, "category": "politics", "source_kind": "senate_roll_call", "source_url": SENATE_VOTE_URL,
            "rule_review": {
                "resolution_rules_sha256": hashlib.sha256(rules.encode()).hexdigest(),
                "source_content_sha256": source["content_sha256"], "complete": True,
                "reviewed_by": "test researcher", "reviewed_at": "2026-09-25T17:00:00+00:00",
                "evidence_verdict": "QUALIFIES", "evidence_reason": "Synthetic fixture: same nominee, office and deadline.",
            },
            "rule_checks": [{
                "criterion": "Senate confirmed the named nominee for the named office before the deadline",
                "rule_quote": "Angela Veronica Colmenero is confirmed by the Senate as District Judge by September 30, 2026",
                "evidence_quote": "Nomination Confirmed", "status": "CONFIRMED",
                "reviewed_by": "test researcher", "reviewed_at": "2026-09-25T17:00:00+00:00",
            }],
        }
        calls = []

        def http(url, body=None, api_key=None):
            calls.append(url)
            if "/markets/slug/" in url:
                return political_market
            if "/markets/241/tags" in url:
                return [{"slug": "politics"}]
            if "systemone" in url:
                self.assertEqual(NOW.isoformat(), body["state"]["evidence"][0]["observed_at"])
                self.assertEqual("2026-09-23T18:16:00+00:00", body["state"]["evidence"][0]["published_at"])
                self.assertEqual("vote_date", body["state"]["evidence"][0]["time_basis"])
                self.assertIn("Angela Veronica Colmenero", body["state"]["evidence"][0]["source_title"])
                self.assertIn("Angela Veronica Colmenero to be United States District Judge", body["state"]["evidence"][0]["text"])
                self.assertIn("Nomination Confirmed", body["state"]["evidence"][0]["text"])
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            return {"market": "0xabc", "asset_id": "yes-token",
                    "timestamp": str(int(NOW.timestamp() * 1000)), "min_order_size": "5",
                    "asks": [{"price": "0.60", "size": "20"}]}

        result = actual_run_review(reviewed, NOW,
                                   lambda url: SENATE_MENU if "vote_menu_119_2.xml" in url else SENATE_VOTE,
                                   http, "test-key", quote_now_fn=lambda: NOW)

        self.assertEqual("REVIEW_CANDIDATE", result["status"])
        self.assertEqual("Yes", result["candidate_outcome"])
        self.assertEqual("senate_roll_call", result["source"]["publisher"])
        self.assertEqual(NOW.isoformat(), result["jev_evidence"][0]["observed_at"])
        self.assertEqual(source["text"], result["jev_evidence"][0]["text"])
        self.assertTrue(calls[-1].endswith("token_id=yes-token"))
        self.assertNotIn("test-key", json.dumps(result, default=str))

    def test_official_article_text_uses_main_content_not_navigation(self):
        url = "https://www.whitehouse.gov/presidential-actions/2026/09/example-action/"
        feed = f"<rss><channel><item><link>{url}</link><pubDate>Fri, 18 Sep 2026 22:02:43 +0000</pubDate></item></channel></rss>"
        html = "<header>" + ("Navigation Crypto Claims " * 1500) + "</header><main><p>Official action text</p></main><footer>Unrelated footer</footer>"

        source = collect_source("white_house_presidential", url, NOW, lambda target: feed if target.endswith("/feed/") else html)

        self.assertEqual("Official action text", source["text"])
        self.assertNotIn("Navigation Crypto Claims", source["text"])
        self.assertNotIn("Unrelated footer", source["text"])

    def test_navigation_changes_do_not_invalidate_main_text_review(self):
        first = "<header>Old navigation</header><main><p>Official action text</p></main><footer>Old footer</footer>"
        second = "<header>New navigation</header><main><p>Official action text</p></main><footer>New footer</footer>"
        url = "https://www.whitehouse.gov/presidential-actions/2026/09/example-action/"
        feed = f"<rss><channel><item><link>{url}</link><pubDate>Fri, 18 Sep 2026 22:02:43 +0000</pubDate></item></channel></rss>"

        def source(html):
            return collect_source("white_house_presidential", url, NOW, lambda target: feed if target.endswith("/feed/") else html)

        original, updated = source(first), source(second)
        self.assertEqual(hashlib.sha256(b"Official action text").hexdigest(), original["content_sha256"])
        self.assertEqual(original["content_sha256"], updated["content_sha256"])
        self.assertNotEqual(original["raw_html_sha256"], updated["raw_html_sha256"])

    def test_long_official_main_text_is_not_silently_truncated(self):
        long_text = ("Official action detail. " * 1100).strip()
        html = f"<main>{long_text}</main>"

        source = collect_source("federal_reserve_monetary", SOURCE_URL, NOW,
                                lambda target: FEED if target.endswith(".xml") else html)

        self.assertEqual(long_text, source["text"])
        self.assertEqual(hashlib.sha256(long_text.encode()).hexdigest(), source["content_sha256"])

    def test_federal_reserve_article_uses_main_role_container(self):
        html = "<nav>Unrelated rate prediction</nav><div id='content' role='main'><p>The Committee decided to maintain the target range.</p></div><footer>Other releases</footer>"

        source = collect_source("federal_reserve_monetary", SOURCE_URL, NOW, lambda target: FEED if target.endswith(".xml") else html)

        self.assertEqual("The Committee decided to maintain the target range.", source["text"])

    def test_official_article_without_main_content_is_not_accepted(self):
        with self.assertRaisesRegex(ValueError, "main content"):
            collect_source("federal_reserve_monetary", SOURCE_URL, NOW,
                           lambda target: FEED if target.endswith(".xml") else "<nav>Only navigation</nav>")

    def test_unreviewed_rules_never_call_jev(self):
        calls = []

        def http(url, body=None, api_key=None):
            calls.append(url)
            return market()

        result = run_review({**case(), "rule_checks": []}, NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret")

        self.assertEqual("RULE_REVIEW_REQUIRED", result["status"])
        self.assertEqual(1, len(calls))
        self.assertNotIn("jev", result)
        self.assertNotIn("jev_evidence", result)

    def test_verified_rules_call_jev_then_quote_only_decisive_side(self):
        calls = []

        def http(url, body=None, api_key=None):
            calls.append(url)
            if "/markets/slug/" in url:
                return market()
            if "systemone" in url:
                self.assertEqual("secret", api_key)
                self.assertIn("Committee decided", body["state"]["evidence"][0]["text"])
                self.assertEqual(NOW.isoformat(), body["state"]["evidence"][0]["observed_at"])
                return {"model": "jev-1.13.0", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            return {"market": "0xabc", "asset_id": "yes-token", "timestamp": str(int(NOW.timestamp() * 1000)), "min_order_size": "5", "asks": [{"price": "0.60", "size": "20"}]}

        result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret", quote_now_fn=lambda: NOW)

        self.assertEqual("REVIEW_CANDIDATE", result["status"])
        self.assertEqual("Yes", result["candidate_outcome"])
        self.assertEqual("CONFIRMED", result["rule_checks"][0]["status"])
        self.assertEqual(result["source"]["content_sha256"], result["rule_review"]["source_content_sha256"])
        self.assertEqual({"source_url": SOURCE_URL, "source_title": "Federal Reserve issues FOMC statement",
                          "published_at": "2026-09-16T18:00:00+00:00", "time_basis": "feed_publication",
                          "observed_at": NOW.isoformat(),
                          "text": "The Committee decided to maintain the target range"}, result["jev_evidence"][0])
        self.assertEqual(Decimal("0.40"), result["quote"]["gap_per_share"])
        self.assertEqual(4, len(calls))
        self.assertTrue(result["paper_only"])
        self.assertNotIn("secret", json.dumps(result, default=str))

    def test_market_closed_after_jev_never_reaches_book(self):
        market_fetches = 0

        def http(url, body=None, api_key=None):
            nonlocal market_fetches
            if "/markets/slug/" in url:
                market_fetches += 1
                return market() if market_fetches == 1 else {**market(), "closed": True, "acceptingOrders": False}
            if "systemone" in url:
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            self.fail(f"book fetched after market closed: {url}")

        result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret")

        self.assertEqual(2, market_fetches)
        self.assertEqual("MARKET_UNAVAILABLE", result["status"])
        self.assertIs(result["market_closed"], True)
        self.assertIs(result["market_accepting_orders"], False)
        self.assertIsNone(result["candidate_outcome"])
        self.assertNotIn("quote", result)

    def test_crypto_tag_added_after_jev_never_reaches_book(self):
        tag_fetches = 0

        def http(url, body=None, api_key=None):
            nonlocal tag_fetches
            if "/markets/slug/" in url:
                return market()
            if url.endswith("/markets/4620900/tags"):
                tag_fetches += 1
                return [{"slug": "economy"}] if tag_fetches == 1 else [{"slug": "economy"}, {"slug": "crypto"}]
            if "systemone" in url:
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            self.fail(f"book fetched after crypto tag appeared: {url}")

        result = actual_run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE,
                                   http, "secret", quote_now_fn=lambda: NOW)

        self.assertEqual(2, tag_fetches)
        self.assertEqual("OUT_OF_SCOPE", result["status"])
        self.assertEqual(["economy", "crypto"], result["market_tags"])
        self.assertNotIn("quote", result)

    def test_official_article_changed_after_jev_never_reaches_book(self):
        article_fetches = 0
        changed_article = ARTICLE.replace("</main>", " A correction was added.</main>")

        def fetch(url):
            nonlocal article_fetches
            if url.endswith(".xml"):
                return FEED
            article_fetches += 1
            return ARTICLE if article_fetches == 1 else changed_article

        def http(url, body=None, api_key=None):
            if "/markets/slug/" in url:
                return market()
            if "systemone" in url:
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            self.fail(f"book fetched after official article changed: {url}")

        result = run_review(case(), NOW, fetch, http, "secret", quote_now_fn=lambda: NOW)

        self.assertEqual(2, article_fetches)
        self.assertEqual("RULE_REVIEW_REQUIRED", result["status"])
        self.assertIn("official source", result["reason"])
        self.assertIn("source_rechecked_at", result)
        self.assertNotEqual(result["source"]["content_sha256"], result["source_recheck_content_sha256"])
        self.assertNotIn("quote", result)

    def test_official_source_unavailable_after_jev_never_reaches_book(self):
        feed_fetches = 0

        def fetch(url):
            nonlocal feed_fetches
            if url.endswith(".xml"):
                feed_fetches += 1
                if feed_fetches == 2:
                    raise OSError("official feed timeout")
                return FEED
            return ARTICLE

        def http(url, body=None, api_key=None):
            if "/markets/slug/" in url:
                return market()
            if "systemone" in url:
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            self.fail(f"book fetched after official source failed: {url}")

        result = run_review(case(), NOW, fetch, http, "secret", quote_now_fn=lambda: NOW)

        self.assertEqual(2, feed_fetches)
        self.assertEqual("SOURCE_UNAVAILABLE", result["status"])
        self.assertIn("official feed timeout", result["reason"])
        self.assertIn("source_rechecked_at", result)
        self.assertNotIn("quote", result)

    def test_official_article_navigation_change_after_jev_does_not_invalidate_review(self):
        article_fetches = 0

        def fetch(url):
            nonlocal article_fetches
            if url.endswith(".xml"):
                return FEED
            article_fetches += 1
            return ARTICLE if article_fetches == 1 else "<nav>Changed navigation</nav>" + ARTICLE

        def http(url, body=None, api_key=None):
            if "/markets/slug/" in url:
                return market()
            if "systemone" in url:
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            return {"market": "0xabc", "asset_id": "yes-token",
                    "timestamp": str(int(NOW.timestamp() * 1000)), "min_order_size": "5",
                    "asks": [{"price": "0.60", "size": "20"}]}

        result = run_review(case(), NOW, fetch, http, "secret", quote_now_fn=lambda: NOW)

        self.assertEqual(2, article_fetches)
        self.assertEqual("REVIEW_CANDIDATE", result["status"])
        self.assertEqual(result["source"]["content_sha256"], result["source_recheck_content_sha256"])

    def test_rule_change_after_jev_requires_new_review_without_book(self):
        market_fetches = 0
        changed_rules = market()["description"] + " A later amendment applies."

        def http(url, body=None, api_key=None):
            nonlocal market_fetches
            if "/markets/slug/" in url:
                market_fetches += 1
                return market() if market_fetches == 1 else {**market(), "description": changed_rules}
            if "systemone" in url:
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            self.fail(f"book fetched after rules changed: {url}")

        result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret")

        self.assertEqual(2, market_fetches)
        self.assertEqual("RULE_REVIEW_REQUIRED", result["status"])
        self.assertEqual(changed_rules, result["resolution_rules"])
        self.assertNotIn("quote", result)

    def test_outcome_tokens_changed_after_jev_never_reaches_book(self):
        market_fetches = 0

        def http(url, body=None, api_key=None):
            nonlocal market_fetches
            if "/markets/slug/" in url:
                market_fetches += 1
                return market() if market_fetches == 1 else {**market(), "clobTokenIds": '["new-yes-token", "no-token"]'}
            if "systemone" in url:
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            self.fail(f"book fetched after token changed: {url}")

        result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret")

        self.assertEqual(2, market_fetches)
        self.assertEqual("MARKET_UNAVAILABLE", result["status"])
        self.assertIn("tokens changed", result["reason"])
        self.assertNotIn("quote", result)

    def test_quote_uses_refreshed_fee_schedule_after_jev(self):
        market_fetches = 0

        def http(url, body=None, api_key=None):
            nonlocal market_fetches
            if "/markets/slug/" in url:
                market_fetches += 1
                return market() if market_fetches == 1 else {
                    **market(), "feesEnabled": True,
                    "feeSchedule": {"rate": 0.04, "exponent": 1, "takerOnly": True},
                }
            if "systemone" in url:
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            return {"market": "0xabc", "asset_id": "yes-token",
                    "timestamp": str(int(NOW.timestamp() * 1000)), "min_order_size": "5",
                    "asks": [{"price": "0.60", "size": "20"}]}

        result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret", quote_now_fn=lambda: NOW)

        self.assertEqual(2, market_fetches)
        self.assertEqual(Decimal("0.04"), result["fee_rate"])
        self.assertEqual(Decimal("0.192"), result["quote"]["fee"])
        self.assertEqual(Decimal("0.3904"), result["quote"]["gap_per_share"])

    def test_unknown_refreshed_fee_stops_as_quote_unavailable(self):
        market_fetches = 0

        def http(url, body=None, api_key=None):
            nonlocal market_fetches
            if "/markets/slug/" in url:
                market_fetches += 1
                return market() if market_fetches == 1 else {**market(), "feesEnabled": None}
            if "systemone" in url:
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            self.fail(f"book fetched with unknown fees: {url}")

        result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret")

        self.assertEqual(2, market_fetches)
        self.assertEqual("QUOTE_UNAVAILABLE", result["status"])
        self.assertIsNone(result["fee_rate"])
        self.assertNotIn("quote", result)

    def test_failed_market_recheck_does_not_show_initial_open_state_as_current(self):
        market_fetches = 0

        def http(url, body=None, api_key=None):
            nonlocal market_fetches
            if "/markets/slug/" in url:
                market_fetches += 1
                if market_fetches == 1:
                    return market()
                raise OSError("Gamma timeout")
            if "systemone" in url:
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            self.fail(f"book fetched after Gamma timeout: {url}")

        result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret")

        self.assertEqual("MARKET_UNAVAILABLE", result["status"])
        self.assertIsNone(result["market_accepting_orders"])
        self.assertIsNone(result["fee_rate"])
        self.assertIn("market_rechecked_at", result)
        self.assertNotIn("quote", result)

    def test_crypto_market_is_rejected_before_source_or_jev(self):
        calls = []

        def http(url, body=None, api_key=None):
            calls.append(url)
            return market("Will the Fed approve a Bitcoin ETF?")

        result = actual_run_review(case(), NOW, lambda url: self.fail(f"source fetched: {url}"), http, "secret")

        self.assertEqual("OUT_OF_SCOPE", result["status"])
        self.assertEqual(1, len(calls))

    def test_crypto_only_in_resolution_rules_is_rejected(self):
        def http(url, body=None, api_key=None):
            return {**market(), "description": "Resolves Yes if the Federal Reserve approves a Bitcoin ETF."}

        result = actual_run_review(case(), NOW, lambda url: self.fail(f"source fetched: {url}"), http, "secret")

        self.assertEqual("OUT_OF_SCOPE", result["status"])

    def test_declared_category_must_match_gamma_tags(self):
        supplied = case()
        supplied["category"] = "politics"

        def http(url):
            return [{"slug": "economy"}] if url.endswith("/markets/4620900/tags") else market()

        result = actual_run_review(supplied, NOW, lambda url: self.fail(f"source fetched: {url}"), http, "secret")

        self.assertEqual("OUT_OF_SCOPE", result["status"])

    def test_white_house_source_can_support_finance_tagged_market(self):
        url = "https://www.whitehouse.gov/presidential-actions/2026/09/example-economic-order/"
        feed = f"<rss><channel><item><title>Example economic order</title><link>{url}</link><pubDate>Fri, 18 Sep 2026 22:02:43 +0000</pubDate></item></channel></rss>"
        supplied = {"market_slug": "fed-september-rates", "category": "finance",
                    "source_kind": "white_house_presidential", "source_url": url}

        def http(target):
            if target.endswith("/markets/4620900/tags"):
                return [{"slug": "economy"}]
            if "/markets/slug/" in target:
                return {**market("Will an economic order be issued?"),
                        "description": "Resolves Yes if a qualifying economic order is issued."}
            self.fail(f"Jev or CLOB called: {target}")

        result = actual_run_review(supplied, NOW,
                                   lambda target: feed if target.endswith("/feed/") else "<main>Official economic order text</main>",
                                   http, "secret")

        self.assertEqual("RULE_REVIEW_REQUIRED", result["status"])
        self.assertEqual("white_house_presidential", result["source"]["publisher"])
        self.assertEqual(["economy"], result["market_tags"])
        self.assertNotIn("jev", result)

    def test_reviewed_white_house_finance_case_reaches_only_no_side_book(self):
        url = "https://www.whitehouse.gov/presidential-actions/2026/09/example-bill-signing/"
        feed = f"<rss><channel><item><title>Example bill signing</title><link>{url}</link><pubDate>Fri, 18 Sep 2026 22:02:43 +0000</pubDate></item></channel></rss>"
        article = "<main>President signed H.R. 5334 into law.</main>"
        source = collect_source("white_house_presidential", url, NOW,
                                lambda target: feed if target.endswith("/feed/") else article)
        rules = "If the President signs H.R. 5334 into law, this market will immediately resolve No."
        example_market = {**market("Will the President veto H.R. 5334?"),
                          "slug": "veto-bill-example", "description": rules}
        supplied = {
            "market_slug": "veto-bill-example", "category": "finance",
            "source_kind": "white_house_presidential", "source_url": url,
            "rule_review": {
                "resolution_rules_sha256": hashlib.sha256(rules.encode()).hexdigest(),
                "source_content_sha256": source["content_sha256"], "complete": True,
                "reviewed_by": "test researcher", "reviewed_at": "2026-09-25T17:00:00+00:00",
                "evidence_verdict": "QUALIFIES", "evidence_reason": "Synthetic fixture: signing establishes No.",
            },
            "rule_checks": [{
                "criterion": "Signed bill resolves No", "rule_quote": "signs H.R. 5334 into law",
                "evidence_quote": "signed H.R. 5334 into law", "status": "CONFIRMED",
                "reviewed_by": "test researcher", "reviewed_at": "2026-09-25T17:00:00+00:00",
            }],
        }
        calls = []

        def http(target, body=None, api_key=None):
            calls.append(target)
            if "/markets/slug/" in target:
                return example_market
            if target.endswith("/markets/4620900/tags"):
                return [{"slug": "economy"}]
            if "systemone" in target:
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.01},
                    "no": {"type": "noul", "noul": 0.98},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            if "/book?" in target:
                return {"market": "0xabc", "asset_id": "no-token",
                        "timestamp": str(int(NOW.timestamp() * 1000)), "min_order_size": "5",
                        "asks": [{"price": "0.60", "size": "20"}]}
            self.fail(f"unexpected request: {target}")

        result = actual_run_review(supplied, NOW,
                                   lambda target: feed if target.endswith("/feed/") else article,
                                   http, "test-key", quote_now_fn=lambda: NOW)

        self.assertEqual("REVIEW_CANDIDATE", result["status"])
        self.assertEqual("No", result["candidate_outcome"])
        self.assertTrue(calls[-1].endswith("token_id=no-token"))
        self.assertEqual(2, calls.count("https://gamma-api.polymarket.com/markets/4620900/tags"))
        self.assertEqual(6, len(calls))
        self.assertNotIn("test-key", json.dumps(result, default=str))

    def test_malformed_source_kind_is_rejected_before_network(self):
        supplied = {**case(), "source_kind": []}

        with self.assertRaisesRegex(ValueError, "source_kind"):
            actual_run_review(supplied, NOW, lambda url: self.fail(f"source fetched: {url}"),
                              lambda url: self.fail(f"market fetched: {url}"))

    def test_gamma_market_tags_must_confirm_the_declared_scope_before_source_or_jev(self):
        calls = []

        def http(url, body=None, api_key=None):
            calls.append(url)
            if "/markets/4620900/tags" in url:
                return [{"slug": "sports", "label": "Sports"}]
            return market()

        result = actual_run_review(case(), NOW, lambda url: self.fail(f"source fetched: {url}"), http, "secret")

        self.assertEqual("OUT_OF_SCOPE", result["status"])
        self.assertEqual(["sports"], result["market_tags"])
        self.assertEqual(2, len(calls))

    def test_finance_tag_allows_market_without_title_keyword(self):
        plain_market = {**market("Will the target be 3.75%?"), "slug": "target-range-375"}
        supplied = {**case(), "market_slug": "target-range-375", "rule_checks": []}
        fetched = []

        def http(url):
            if url.endswith("/markets/4620900/tags"):
                return [{"slug": "economy"}]
            return plain_market

        def fetch(url):
            fetched.append(url)
            return FEED if url.endswith(".xml") else ARTICLE

        result = actual_run_review(supplied, NOW, fetch, http, "secret")

        self.assertEqual("RULE_REVIEW_REQUIRED", result["status"])
        self.assertEqual(["economy"], result["market_tags"])
        self.assertEqual(2, len(fetched))
        self.assertNotIn("jev", result)

    def test_crypto_tag_blocks_even_when_market_text_has_no_crypto_term(self):
        def http(url, body=None, api_key=None):
            if "/markets/4620900/tags" in url:
                return [{"slug": "economy"}, {"slug": "crypto"}]
            return market()

        result = actual_run_review(case(), NOW, lambda url: self.fail(f"source fetched: {url}"), http, "secret")

        self.assertEqual("OUT_OF_SCOPE", result["status"])
        self.assertEqual(["economy", "crypto"], result["market_tags"])

    def test_unavailable_market_tags_stop_before_source_or_jev(self):
        def http(url, body=None, api_key=None):
            if "/markets/4620900/tags" in url:
                raise OSError("Gamma tags unavailable")
            return market()

        result = actual_run_review(case(), NOW, lambda url: self.fail(f"source fetched: {url}"), http, "secret")

        self.assertEqual("SCOPE_UNVERIFIED", result["status"])
        self.assertNotIn("jev", result)

    def test_malformed_gamma_response_is_audited_as_market_unavailable(self):
        for payload in ([], {**market(), "description": ["not rules text"]}):
            with self.subTest(payload=payload):
                result = actual_run_review(case(), NOW, lambda url: self.fail(f"source fetched: {url}"), lambda url: payload)

                self.assertEqual("MARKET_UNAVAILABLE", result["status"])
                self.assertNotIn("jev", result)

    def test_gamma_market_slug_must_match_requested_market(self):
        supplied = case()

        def http(url):
            return [{"slug": "economy"}] if url.endswith("/markets/4620900/tags") else {**market(), "slug": "different-market"}

        result = actual_run_review(supplied, NOW, lambda url: self.fail(f"source fetched: {url}"),
                                   http, "secret")

        self.assertEqual("MARKET_UNAVAILABLE", result["status"])
        self.assertIn("slug", result["reason"])
        self.assertNotIn("jev", result)

    def test_market_slug_changed_after_jev_never_reaches_book(self):
        market_fetches = 0

        def http(url, body=None, api_key=None):
            nonlocal market_fetches
            if "/markets/slug/" in url:
                market_fetches += 1
                return market() if market_fetches == 1 else {**market(), "slug": "different-market"}
            if "systemone" in url:
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            self.fail(f"book fetched after market slug changed: {url}")

        result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret")

        self.assertEqual(2, market_fetches)
        self.assertEqual("MARKET_UNAVAILABLE", result["status"])
        self.assertNotIn("quote", result)

    def test_malformed_jev_response_is_audited_as_jev_unavailable(self):
        for payload in ([], {"answers": []}, {"answers": {"yes": [], "no": {}, "ambiguous": {}}}):
            with self.subTest(payload=payload):
                def http(url, body=None, api_key=None):
                    return market() if "/markets/slug/" in url else payload

                result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret")

                self.assertEqual("JEV_UNAVAILABLE", result["status"])
                self.assertNotIn("quote", result)

    def test_malformed_book_response_is_audited_as_quote_unavailable(self):
        def http(url, body=None, api_key=None):
            if "/markets/slug/" in url:
                return market()
            if "systemone" in url:
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            return []

        result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret")

        self.assertEqual("QUOTE_UNAVAILABLE", result["status"])
        self.assertNotIn("quote", result)

    def test_quote_not_in_official_article_blocks_jev(self):
        calls = []

        def http(url, body=None, api_key=None):
            calls.append(url)
            return market()

        altered = case()
        altered["rule_checks"][0]["evidence_quote"] = "The Fed raised rates by 50 bps"
        result = run_review(altered, NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret")

        self.assertEqual("RULE_REVIEW_REQUIRED", result["status"])
        self.assertEqual(1, len(calls))

    def test_rule_quote_must_exist_in_current_resolution_text(self):
        supplied = case()
        supplied["rule_checks"][0]["rule_quote"] = "A rule that does not exist"

        result = run_review(supplied, NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, lambda url: market(), "secret")

        self.assertEqual("RULE_REVIEW_REQUIRED", result["status"])
        self.assertNotIn("jev", result)

    def test_excluded_official_fact_is_recorded_without_calling_jev(self):
        excluded_rules = (
            "Yes if a rate hike is announced after September 17, 2026. "
            "The September 15 to 16 FOMC meeting will not count."
        )
        excluded_article = "<main>The Committee decided to raise the target range.</main>"
        supplied = case()
        supplied["rule_review"].update(
            resolution_rules_sha256=hashlib.sha256(excluded_rules.encode()).hexdigest(),
            source_content_sha256=hashlib.sha256(b"The Committee decided to raise the target range.").hexdigest(),
            complete=False,
            evidence_verdict="DOES_NOT_QUALIFY",
            evidence_reason="The September 16 hike is expressly excluded by the market rule.",
        )
        supplied["rule_checks"] = [{
            "criterion": "September 16 FOMC hike is outside the qualifying window",
            "rule_quote": "The September 15 to 16 FOMC meeting will not count.",
            "evidence_quote": "The Committee decided to raise the target range.",
            "status": "EXCLUDED", "reviewed_by": "researcher", "reviewed_at": "2026-09-25T17:00:00+00:00",
        }]
        calls = []

        def http(url, body=None, api_key=None):
            calls.append(url)
            return {**market(), "description": excluded_rules}

        result = run_review(supplied, NOW, lambda url: FEED if url.endswith(".xml") else excluded_article, http, "secret")

        self.assertEqual("EVIDENCE_NOT_QUALIFYING", result["status"])
        self.assertEqual("2026-09-10T16:18:52Z", result["market_created_at"])
        self.assertEqual(1, len(calls))
        self.assertNotIn("jev", result)

    def test_written_official_source_cannot_prove_recorded_verbal_mention(self):
        slug = "will-trump-say-pelosi-in-september-20260930"
        source_url = "https://www.whitehouse.gov/presidential-actions/2026/09/example-action/"
        article_text = "Official written action mentions Pelosi."
        feed = (f"<rss><channel><item><title>Official action</title><link>{source_url}</link>"
                "<pubDate>Fri, 18 Sep 2026 22:02:43 +0000</pubDate></item></channel></rss>")
        rules = ('This market will resolve to "Yes" if Donald Trump mentions Pelosi between September 1 and September 30, 2026. '
                 "A 'mention' will include any verbal mention which is recorded (audio or video) and publicly accessible.")
        supplied = {
            "market_slug": slug, "category": "politics", "source_kind": "white_house_presidential",
            "source_url": source_url,
            "rule_review": {
                "resolution_rules_sha256": hashlib.sha256(rules.encode()).hexdigest(),
                "source_content_sha256": hashlib.sha256(article_text.encode()).hexdigest(),
                "complete": True, "reviewed_by": "test researcher", "reviewed_at": "2026-09-25T17:00:00+00:00",
                "evidence_verdict": "QUALIFIES", "evidence_reason": "Synthetic review deliberately misclassifies written evidence.",
            },
            "rule_checks": [{
                "criterion": "Recorded verbal mention of Pelosi",
                "rule_quote": "verbal mention which is recorded (audio or video)",
                "evidence_quote": "Pelosi", "status": "CONFIRMED",
                "reviewed_by": "test researcher", "reviewed_at": "2026-09-25T17:00:00+00:00",
            }],
        }

        def http(url, body=None, api_key=None):
            if "/markets/slug/" in url:
                return {**market("Will Trump say Pelosi in September?"), "slug": slug, "description": rules}
            if "/markets/4620900/tags" in url:
                return [{"slug": "politics"}]
            self.fail(f"written-only evidence reached Jev or the book: {url}")

        result = actual_run_review(supplied, NOW,
                                   lambda url: feed if url.endswith("/feed/") else f"<main>{article_text}</main>",
                                   http, "test-key")

        self.assertEqual("SOURCE_TYPE_UNSUPPORTED", result["status"])
        self.assertIn("recorded verbal mention", result["reason"])
        self.assertEqual(article_text, result["source"]["text"])
        self.assertNotIn("jev", result)
        self.assertNotIn("jev_evidence", result)

    def test_full_resolution_rules_must_be_acknowledged(self):
        calls = []

        def http(url, body=None, api_key=None):
            calls.append(url)
            return market()

        altered = case()
        altered["rule_review"]["complete"] = False
        result = run_review(altered, NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret")

        self.assertEqual("RULE_REVIEW_REQUIRED", result["status"])
        self.assertEqual(1, len(calls))

    def test_external_full_rule_document_stops_before_jev_even_if_review_is_marked_complete(self):
        url = "https://polymarket-upload.s3.us-east-2.amazonaws.com/market_products/extra.pdf"
        rules = market()["description"] + f" For full rules, see: {url}"
        supplied = case()
        supplied["rule_review"]["resolution_rules_sha256"] = hashlib.sha256(rules.encode()).hexdigest()
        document_text = "Additional rule: the decision must be publicly announced."
        document = {"url": url, "raw_sha256": "a" * 64,
                    "text_sha256": hashlib.sha256(document_text.encode()).hexdigest(),
                    "page_count": 1, "text": document_text}

        def http(url, body=None, api_key=None):
            if "/markets/slug/" in url:
                return {**market(), "description": rules}
            self.fail(f"External full rules were not checked, but Jev or book was called: {url}")

        result = run_review(supplied, NOW,
                            lambda url: FEED if url.endswith(".xml") else ARTICLE,
                            http, "secret", rule_document_fn=lambda target: document)

        self.assertEqual("RULE_REVIEW_REQUIRED", result["status"])
        self.assertIn("external full rules", result["reason"])
        self.assertNotIn("jev", result)

    def test_bound_external_rule_document_is_sent_to_jev_and_rechecked_before_quote(self):
        url = "https://polymarket-upload.s3.us-east-2.amazonaws.com/market_products/rules.pdf"
        rules = market()["description"] + f" For full rules, see: {url}"
        document_text = "Additional rule: the decision must be publicly announced."
        document = {"url": url, "raw_sha256": "a" * 64,
                    "text_sha256": hashlib.sha256(document_text.encode()).hexdigest(),
                    "page_count": 1, "text": document_text}
        supplied = case()
        supplied["rule_review"]["resolution_rules_sha256"] = hashlib.sha256(
            (rules + "\n\n" + document["text"]).encode()).hexdigest()
        supplied["rule_review"]["rule_document_sha256"] = document["raw_sha256"]
        supplied["rule_checks"].append({
            "criterion": "Public announcement requirement in the full rules",
            "rule_quote": "the decision must be publicly announced",
            "evidence_quote": "The Committee decided to maintain the target range",
            "status": "CONFIRMED", "reviewed_by": "researcher",
            "reviewed_at": "2026-09-25T17:00:00+00:00",
        })
        calls = []

        def rule_pdf(target):
            self.assertEqual(url, target)
            calls.append("pdf")
            return document

        def http(target, body=None, api_key=None):
            if "/markets/slug/" in target:
                return {**market(), "description": rules}
            if "systemone" in target:
                self.assertIn(document["text"], body["state"]["resolution_rules"])
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            if "/book?" in target:
                return {"market": "0xabc", "asset_id": "yes-token",
                        "timestamp": str(int(NOW.timestamp() * 1000)), "min_order_size": "5",
                        "asks": [{"price": "0.60", "size": "20"}]}
            self.fail(target)

        result = run_review(supplied, NOW, lambda target: FEED if target.endswith(".xml") else ARTICLE,
                            http, "secret", quote_now_fn=lambda: NOW, rule_document_fn=rule_pdf)

        self.assertEqual("REVIEW_CANDIDATE", result["status"])
        self.assertEqual(["pdf", "pdf"], calls)
        self.assertEqual(document["raw_sha256"], result["rule_review"]["rule_document_sha256"])
        self.assertEqual(document["text"], result["rule_document"]["text"])
        self.assertIn("quote", result)

    def test_changed_external_rule_document_after_jev_blocks_quote(self):
        url = "https://polymarket-upload.s3.us-east-2.amazonaws.com/market_products/rules.pdf"
        rules = market()["description"] + f" For full rules, see: {url}"
        document_text = "Additional rule: the decision must be publicly announced."
        document = {"url": url, "raw_sha256": "a" * 64,
                    "text_sha256": hashlib.sha256(document_text.encode()).hexdigest(),
                    "page_count": 1, "text": document_text}
        supplied = case()
        supplied["rule_review"]["resolution_rules_sha256"] = hashlib.sha256(
            (rules + "\n\n" + document["text"]).encode()).hexdigest()
        supplied["rule_review"]["rule_document_sha256"] = document["raw_sha256"]
        fetch_count = 0

        def rule_pdf(target):
            nonlocal fetch_count
            fetch_count += 1
            return document if fetch_count == 1 else {**document, "raw_sha256": "c" * 64}

        def http(target, body=None, api_key=None):
            if "/markets/slug/" in target:
                return {**market(), "description": rules}
            if "systemone" in target:
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            self.fail(f"book fetched after external rules changed: {target}")

        result = run_review(supplied, NOW, lambda target: FEED if target.endswith(".xml") else ARTICLE,
                            http, "secret", rule_document_fn=rule_pdf)

        self.assertEqual(2, fetch_count)
        self.assertEqual("RULE_REVIEW_REQUIRED", result["status"])
        self.assertNotIn("quote", result)

    def test_changed_resolution_text_invalidates_prior_review(self):
        def http(url, body=None, api_key=None):
            return {**market(), "description": market()["description"] + " A later amendment applies."}

        result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret")

        self.assertEqual("RULE_REVIEW_REQUIRED", result["status"])
        self.assertNotIn("jev", result)

    def test_changed_official_article_invalidates_prior_review_even_when_quote_remains(self):
        edited_article = ARTICLE.replace("</main>", " A later qualification was added.</main>")

        def http(url, body=None, api_key=None):
            if "/markets/slug/" in url:
                return market()
            self.fail(f"Jev or book called after official article changed: {url}")

        result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else edited_article, http, "secret")

        self.assertEqual("RULE_REVIEW_REQUIRED", result["status"])
        self.assertNotIn("jev", result)

    def test_missing_official_article_hash_never_reaches_jev(self):
        supplied = case()
        supplied["rule_review"].pop("source_content_sha256")

        def http(url, body=None, api_key=None):
            if "/markets/slug/" in url:
                return market()
            self.fail(f"Jev or book called without official article hash: {url}")

        result = run_review(supplied, NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret")

        self.assertEqual("RULE_REVIEW_REQUIRED", result["status"])
        self.assertNotIn("jev", result)

    def test_missing_official_feed_item_blocks_jev(self):
        calls = []

        def http(url, body=None, api_key=None):
            calls.append(url)
            return market()

        result = run_review(case(), NOW, lambda url: "<rss><channel/></rss>", http, "secret")

        self.assertEqual("SOURCE_UNAVAILABLE", result["status"])
        self.assertEqual(1, len(calls))

    def test_inconclusive_jev_does_not_request_a_book(self):
        calls = []

        def http(url, body=None, api_key=None):
            calls.append(url)
            if "/markets/slug/" in url:
                return market()
            return {"model": "jev-1.13.0", "answers": {
                "yes": {"type": "noul", "noul": 0.2},
                "no": {"type": "noul", "noul": 0.1},
                "ambiguous": {"type": "noul", "noul": 0.9},
            }}

        result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret")

        self.assertEqual("JEV_INCONCLUSIVE", result["status"])
        self.assertEqual(2, len(calls))
        self.assertNotIn("quote", result)

    def test_stale_single_side_book_is_reported_not_a_candidate(self):
        def http(url, body=None, api_key=None):
            if "/markets/slug/" in url:
                return market()
            if "systemone" in url:
                return {"model": "jev-1.13.0", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            return {"market": "0xabc", "asset_id": "yes-token", "timestamp": str(int(NOW.timestamp() * 1000) - 60000), "min_order_size": "5", "asks": [{"price": "0.60", "size": "20"}]}

        result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret", quote_now_fn=lambda: NOW)

        self.assertEqual("QUOTE_UNAVAILABLE", result["status"])
        self.assertIn("stale", result["reason"])
        self.assertNotIn("quote", result)

    def test_disabled_order_book_market_never_fetches_a_book(self):
        calls = []

        def http(url, body=None, api_key=None):
            calls.append(url)
            if "/markets/slug/" in url:
                return {**market(), "enableOrderBook": False}
            if "systemone" in url:
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            self.fail(f"book fetched: {url}")

        result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret")

        self.assertEqual("QUOTE_UNAVAILABLE", result["status"])
        self.assertEqual(3, len(calls))
        self.assertIsNone(result["candidate_outcome"])

    def test_restricted_market_records_book_but_never_becomes_candidate(self):
        calls = []

        def http(url, body=None, api_key=None):
            calls.append(url)
            if "/markets/slug/" in url:
                return {**market(), "restricted": True}
            if "systemone" in url:
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            return {"market": "0xabc", "asset_id": "yes-token",
                    "timestamp": str(int(NOW.timestamp() * 1000)), "min_order_size": "5",
                    "asks": [{"price": "0.60", "size": "20"}]}

        result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret", quote_now_fn=lambda: NOW)

        self.assertEqual("RESTRICTION_UNVERIFIED", result["status"])
        self.assertEqual(4, len(calls))
        self.assertIn("quote", result)
        self.assertIs(result["market_restricted"], True)
        self.assertIsNone(result["candidate_outcome"])

    def test_book_must_match_selected_token_and_condition(self):
        for wrong_field in ({"asset_id": "other-token"}, {"market": "other-condition"}):
            with self.subTest(wrong_field=wrong_field):
                def http(url, body=None, api_key=None):
                    if "/markets/slug/" in url:
                        return market()
                    if "systemone" in url:
                        return {"model": "jev-test", "answers": {
                            "yes": {"type": "noul", "noul": 0.98},
                            "no": {"type": "noul", "noul": 0.01},
                            "ambiguous": {"type": "noul", "noul": 0.01},
                        }}
                    return {"market": "0xabc", "asset_id": "yes-token", **wrong_field,
                            "timestamp": str(int(NOW.timestamp() * 1000)), "min_order_size": "5",
                            "asks": [{"price": "0.60", "size": "20"}]}

                result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret", quote_now_fn=lambda: NOW)

                self.assertEqual("QUOTE_UNAVAILABLE", result["status"])
                self.assertNotIn("quote", result)

    def test_unsupported_fee_payer_never_becomes_candidate(self):
        calls = []

        def http(url, body=None, api_key=None):
            calls.append(url)
            if "/markets/slug/" in url:
                return {**market(), "feesEnabled": True,
                        "feeSchedule": {"rate": 0.04, "exponent": 1, "takerOnly": False}}
            if "systemone" in url:
                return {"model": "jev-test", "answers": {
                    "yes": {"type": "noul", "noul": 0.98},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            self.fail(f"book fetched: {url}")

        result = run_review(case(), NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http, "secret")

        self.assertEqual("QUOTE_UNAVAILABLE", result["status"])
        self.assertEqual(3, len(calls))

    def test_political_no_result_quotes_only_no_token(self):
        url = "https://www.whitehouse.gov/presidential-actions/2026/09/example-action/"
        feed = f"<rss><channel><item><title>Example action</title><link>{url}</link><pubDate>Fri, 18 Sep 2026 22:02:43 +0000</pubDate></item></channel></rss>"
        article = "<main>The proposed order was withdrawn.</main>"
        political_market = market("Will the president sign the proposed order?")
        political_market["description"] = "Resolves Yes if the president signs the proposed order."
        supplied = case()
        supplied.update(category="politics", source_kind="white_house_presidential", source_url=url)
        supplied["rule_review"]["resolution_rules_sha256"] = hashlib.sha256(political_market["description"].encode()).hexdigest()
        supplied["rule_review"]["source_content_sha256"] = hashlib.sha256(b"The proposed order was withdrawn.").hexdigest()
        supplied["rule_checks"][0]["rule_quote"] = "Resolves Yes if the president signs the proposed order."
        supplied["rule_checks"][0]["evidence_quote"] = "The proposed order was withdrawn."
        calls = []

        def http(target, body=None, api_key=None):
            calls.append(target)
            if "/markets/slug/" in target:
                return political_market
            if "systemone" in target:
                return {"model": "jev-1.13.0", "answers": {
                    "yes": {"type": "noul", "noul": 0.01},
                    "no": {"type": "noul", "noul": 0.98},
                    "ambiguous": {"type": "noul", "noul": 0.01},
                }}
            return {"market": "0xabc", "asset_id": "no-token", "timestamp": str(int(NOW.timestamp() * 1000)), "min_order_size": "5", "asks": [{"price": "0.60", "size": "20"}]}

        result = run_review(supplied, NOW, lambda target: feed if target.endswith("/feed/") else article, http, "secret", quote_now_fn=lambda: NOW)

        self.assertEqual("No", result["candidate_outcome"])
        self.assertTrue(calls[-1].endswith("token_id=no-token"))
        self.assertEqual(4, len(calls))

    def test_unlisted_source_url_is_not_fetched(self):
        with self.assertRaisesRegex(ValueError, "official feed"):
            collect_source("federal_reserve_monetary", "https://example.com/claim", NOW, lambda url: self.fail(url))

    def test_unexpected_case_fields_never_enter_the_snapshot(self):
        supplied = case()
        supplied["rule_review"]["api_key"] = "do-not-save-me"
        supplied["rule_checks"][0]["api_key"] = "do-not-save-me"

        def http(url, body=None, api_key=None):
            return market()

        result = run_review(supplied, NOW, lambda url: FEED if url.endswith(".xml") else ARTICLE, http)

        self.assertNotIn("do-not-save-me", json.dumps(result, default=str))

    def test_cli_audits_invalid_cases_and_returns_failure_when_all_skipped(self):
        with TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.json"
            output_path = Path(directory) / "snapshots.jsonl"
            input_path.write_text(json.dumps([
                {"market_slug": "invalid slug", "category": "finance"},
                "not an object",
            ]), encoding="utf-8")
            argv = ["jev_fact_chain.py", "--input", str(input_path), "--output", str(output_path)]
            with patch.object(sys, "argv", argv), patch("jev_fact_chain.load_api_key", return_value=None), redirect_stdout(StringIO()):
                exit_code = fact_chain_main()
            saved = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(1, exit_code)
        self.assertEqual(["SKIPPED", "SKIPPED"], [record["status"] for record in saved])
        self.assertEqual("finance", saved[0]["category"])


if __name__ == "__main__":
    unittest.main()
