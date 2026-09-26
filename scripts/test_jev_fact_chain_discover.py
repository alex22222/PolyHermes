import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from jev_fact_chain_discover import discover_records


NOW = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)
SOURCE_URL = "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm"
FEED = f"<rss><channel><item><title>Federal Reserve issues FOMC statement</title><link>{SOURCE_URL}</link><pubDate>Wed, 16 Sep 2026 18:00:00 GMT</pubDate></item></channel></rss>"
ARTICLE = "<main>The Committee decided to raise the target range by 1/4 percentage point.</main>"


def market(slug, closed=False, question="Will 1 Fed rate hike happen in 2026?"):
    return {
        "id": "2657589", "slug": slug, "question": question,
        "description": "Resolves according to the exact number of Fed hikes in 2026, including December.",
        "conditionId": "0xabc", "createdAt": "2026-06-23T19:37:37Z",
        "active": True, "closed": closed, "acceptingOrders": not closed,
        "enableOrderBook": True, "restricted": True,
        "outcomes": '["Yes", "No"]', "clobTokenIds": '["yes-token", "no-token"]',
        "feesEnabled": False,
    }


class JevFactChainDiscoveryTest(unittest.TestCase):
    def test_open_keyword_pair_is_only_an_unreviewed_suggestion(self):
        closed = market("will-no-fed-rate-hikes-happen-in-2026", closed=True)
        open_market = market("will-1-fed-rate-hike-happen-in-2026")
        calls = []
        fetched = []

        def fetch(url):
            fetched.append(url)
            return FEED if url.endswith(".xml") else ARTICLE

        def http(url, body=None, api_key=None):
            calls.append(url)
            if "/public-search?" in url:
                return {"events": [{"markets": [closed, open_market]}], "pagination": {"hasMore": False}}
            if "/markets/slug/" in url:
                return open_market
            if "/markets/2657589/tags" in url:
                return [{"slug": "fed"}, {"slug": "economy"}]
            self.fail(f"Jev or CLOB was called: {url}")

        rows = discover_records("federal_reserve_monetary", SOURCE_URL, "Federal Reserve", NOW, fetch, http)

        self.assertEqual(1, len(rows))
        self.assertEqual("RULE_REVIEW_REQUIRED", rows[0]["status"])
        self.assertEqual("keyword association and full settlement rules have not been reviewed", rows[0]["reason"])
        self.assertEqual("UNVERIFIED_KEYWORD_SEARCH", rows[0]["discovery_basis"])
        self.assertEqual("Federal Reserve", rows[0]["discovery_query"])
        self.assertIsNone(rows[0]["candidate_outcome"])
        self.assertNotIn("jev", rows[0])
        self.assertNotIn("quote", rows[0])
        self.assertEqual(2, len(fetched))
        self.assertEqual(3, len(calls))

    def test_tagged_finance_market_without_title_keyword_is_a_suggestion(self):
        plain_market = market("target-range-375", question="Will the target be 3.75%?")

        def http(url):
            if "/public-search?" in url:
                return {"events": [{"markets": [plain_market]}]}
            if "/markets/slug/" in url:
                return plain_market
            if "/markets/2657589/tags" in url:
                return [{"slug": "economy"}]
            self.fail(f"Jev or CLOB was called: {url}")

        rows = discover_records("federal_reserve_monetary", SOURCE_URL, "Federal Reserve", NOW,
                                lambda url: FEED if url.endswith(".xml") else ARTICLE, http)

        self.assertEqual(1, len(rows))
        self.assertEqual("target-range-375", rows[0]["market_slug"])
        self.assertEqual("RULE_REVIEW_REQUIRED", rows[0]["status"])
        self.assertNotIn("jev", rows[0])

    def test_white_house_source_can_discover_finance_tagged_market(self):
        source_url = "https://www.whitehouse.gov/presidential-actions/2026/09/example-economic-order/"
        feed = f"<rss><channel><item><title>Example order</title><link>{source_url}</link><pubDate>Fri, 18 Sep 2026 22:02:43 +0000</pubDate></item></channel></rss>"
        candidate = market("economic-order", question="Will an economic order be issued?")

        def http(url):
            if "/public-search?" in url:
                return {"events": [{"markets": [candidate]}]}
            if "/markets/slug/" in url:
                return candidate
            if "/markets/2657589/tags" in url:
                return [{"slug": "economy"}]
            self.fail(f"Jev or CLOB was called: {url}")

        rows = discover_records("white_house_presidential", source_url, "economic order", NOW,
                                lambda url: feed if url.endswith("/feed/") else "<main>Official economic order</main>",
                                http, category="finance")

        self.assertEqual(1, len(rows))
        self.assertEqual("finance", rows[0]["category"])
        self.assertEqual("RULE_REVIEW_REQUIRED", rows[0]["status"])
        self.assertNotIn("jev", rows[0])

    def test_market_phrase_filters_broad_gamma_bill_results(self):
        source_url = "https://www.whitehouse.gov/briefings-statements/2026/09/example-hydropower-bill/"
        feed = f"<rss><channel><item><title>Hydropower bill signed</title><link>{source_url}</link><pubDate>Fri, 25 Sep 2026 19:48:25 +0000</pubDate></item></channel></rss>"
        unrelated = market("unrelated-bill", question="Will an unrelated bill become law?")
        relevant = market("hydropower-bill", question="Will the Hydropower Licensing bill become law?")

        def http(url):
            if "/public-search?" in url:
                return {"events": [{"markets": [unrelated, relevant]}]}
            if "/markets/slug/" in url:
                return relevant
            if "/markets/2657589/tags" in url:
                return [{"slug": "politics"}]
            self.fail(f"Jev or CLOB was called: {url}")

        rows = discover_records("white_house_briefings", source_url, "Hydropower Licensing", NOW,
                                lambda url: feed if url.endswith("/feed/") else "<main>Hydropower Licensing bill signed.</main>",
                                http, market_phrase="Hydropower Licensing")

        self.assertEqual(["hydropower-bill"], [row["market_slug"] for row in rows])
        self.assertEqual("RULE_REVIEW_REQUIRED", rows[0]["status"])
        self.assertNotIn("jev", rows[0])

    def test_unverified_official_source_stops_before_gamma_search(self):
        with self.assertRaisesRegex(ValueError, "official feed"):
            discover_records("federal_reserve_monetary", SOURCE_URL, "Fed", NOW,
                             lambda url: "<rss><channel></channel></rss>" if url.endswith(".xml") else ARTICLE,
                             lambda url: self.fail(f"Gamma called: {url}"))

    def test_crypto_and_closed_search_results_are_not_suggestions(self):
        crypto = market("bitcoin-fed-hike", question="Will Bitcoin rise after the Fed hike?")
        closed = market("will-no-fed-rate-hikes-happen-in-2026", closed=True)
        rows = discover_records("federal_reserve_monetary", SOURCE_URL, "Fed", NOW,
                                lambda url: FEED if url.endswith(".xml") else ARTICLE,
                                lambda url: {"events": [{"markets": [crypto, closed]}]} if "/public-search?" in url else self.fail(url))

        self.assertEqual([], rows)

    def test_invalid_search_payload_is_not_misreported_as_no_edge(self):
        with self.assertRaisesRegex(ValueError, "Gamma search"):
            discover_records("federal_reserve_monetary", SOURCE_URL, "Fed", NOW,
                             lambda url: FEED if url.endswith(".xml") else ARTICLE,
                             lambda url: {"events": None})

    def test_malformed_market_in_search_is_a_source_error(self):
        with self.assertRaisesRegex(ValueError, "Gamma search market"):
            discover_records("federal_reserve_monetary", SOURCE_URL, "Fed", NOW,
                             lambda url: FEED if url.endswith(".xml") else ARTICLE,
                             lambda url: {"events": [{"markets": [None]}]})

    def test_tag_lookup_failure_is_kept_as_data_gap(self):
        open_market = market("will-1-fed-rate-hike-happen-in-2026")

        def http(url):
            if "/public-search?" in url:
                return {"events": [{"markets": [open_market]}]}
            if "/markets/slug/" in url:
                return open_market
            raise OSError("Gamma tags unavailable")

        rows = discover_records("federal_reserve_monetary", SOURCE_URL, "Fed", NOW,
                                lambda url: FEED if url.endswith(".xml") else ARTICLE, http)

        self.assertEqual("SCOPE_UNVERIFIED", rows[0]["status"])
        self.assertIn("Gamma tags unavailable", rows[0]["reason"])
        self.assertNotIn("jev", rows[0])


if __name__ == "__main__":
    unittest.main()
