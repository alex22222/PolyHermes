import sys
import unittest
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from jev_fact_chain_discover import bill_ids, discover_records


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
    def test_senate_resolution_identifier_generates_exact_unverified_search(self):
        vote_url = "https://www.senate.gov/legislative/LIS/roll_call_votes/vote1192/vote_119_2_00244.xml"
        menu = ("<vote_summary><congress>119</congress><session>2</session><congress_year>2026</congress_year><votes>"
                "<vote><vote_number>00244</vote_number><vote_date>24-Sep</vote_date><result>Rejected</result></vote>"
                "</votes></vote_summary>")
        vote = ("<roll_call_vote><congress>119</congress><session>2</session><congress_year>2026</congress_year>"
                "<vote_number>244</vote_number><vote_date>September 24, 2026, 02:16 PM</vote_date>"
                "<modify_date>September 24, 2026, 03:46 PM</modify_date>"
                "<vote_question_text>On the Motion to Discharge H.Con.Res.89</vote_question_text>"
                "<vote_document_text>H.Con.Res.89 regarding war powers</vote_document_text>"
                "<vote_result>Rejected</vote_result><vote_title>H.Con.Res.89</vote_title></roll_call_vote>")
        candidate = market("will-h-con-res-89-pass", question="Will H. Con. Res. 89 pass the Senate?")
        candidate["description"] = "Resolves Yes if H.Con.Res.89 passes the Senate."
        calls = []

        def fetch(url):
            return menu if url.endswith("vote_menu_119_2.xml") else vote if url == vote_url else self.fail(url)

        def http(url):
            calls.append(url)
            if "/public-search?" in url:
                self.assertEqual("H.Con.Res. 89", urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"][0])
                return {"events": [{"markets": [candidate]}]}
            if "/markets/slug/" in url:
                return candidate
            if "/markets/2657589/tags" in url:
                return [{"slug": "politics"}]
            self.fail(f"Jev or CLOB was called: {url}")

        rows = discover_records("senate_roll_call", vote_url, None, NOW, fetch, http)

        self.assertEqual(["H.Con.Res. 89"], [row["discovery_query"] for row in rows])
        self.assertEqual(["will-h-con-res-89-pass"], [row["market_slug"] for row in rows])
        self.assertTrue(all(row["discovery_basis"] == "UNVERIFIED_KEYWORD_SEARCH" for row in rows))
        self.assertTrue(all("jev" not in row and "quote" not in row for row in rows))
        self.assertEqual(3, len(calls))

    def test_bill_identifier_normalizes_resolution_variants_without_confusing_simple_bills(self):
        self.assertEqual(
            ["H.Con.Res. 89", "S.J.Res. 12", "H.J.Res. 8", "S.Con.Res. 2", "H.R. 3657", "S. 790"],
            bill_ids("H.Con.Res.89; S. J. Res. 12; H.J.Res.8; S.Con.Res.2; H.R.3657; S. 790; H Con Res 89"),
        )

    def test_bill_search_uses_card_identifier_only_when_detail_has_no_identifier(self):
        source_url = "https://www.whitehouse.gov/briefings-statements/2026/09/example-bill/"
        feed = (f"<rss><channel><item><title>H.R. 3657 signed</title><link>{source_url}</link>"
                "<pubDate>Fri, 25 Sep 2026 19:48:25 +0000</pubDate></item></channel></rss>")
        card = market("will-this-bill-pass", question="Will H.R. 3657 pass?")
        generic_detail = market(card["slug"], question="Will this bill pass?")
        conflicting_detail = market(card["slug"], question="Will H.R. 7250 pass?")
        generic_detail["description"] = "Resolves when the relevant bill becomes law."
        conflicting_detail["description"] = generic_detail["description"]

        def discover(detail):
            def http(url):
                if "/public-search?" in url:
                    return {"events": [{"markets": [card]}]}
                if "/markets/slug/" in url:
                    return detail
                if "/markets/2657589/tags" in url:
                    return [{"slug": "politics"}]
                self.fail(f"Jev or CLOB was called: {url}")
            return discover_records("white_house_briefings", source_url, None, NOW,
                                    lambda url: feed if url.endswith("/feed/") else "<main>H.R. 3657 signed.</main>", http)

        self.assertEqual([card["slug"]], [row["market_slug"] for row in discover(generic_detail)])
        self.assertEqual([], discover(conflicting_detail))

    def test_official_bill_ids_generate_bounded_unverified_searches(self):
        source_url = "https://www.whitehouse.gov/briefings-statements/2026/09/six-bills-signed/"
        feed = (f"<rss><channel><item><title>President signs bills</title><link>{source_url}</link>"
                "<pubDate>Fri, 25 Sep 2026 19:48:25 +0000</pubDate></item></channel></rss>")
        article = "<main>The President signed H.R. 3657 and S. 790 into law.</main>"
        hr_market = market("will-hr-3657-become-law", question="Will H.R. 3657 become law?")
        senate_market = market("will-s-790-become-law", question="Will S. 790 become law?")
        unrelated = market("will-hr-7250-become-law", question="Will H.R. 7250 become law?")
        calls = []

        def http(url):
            calls.append(url)
            if "/public-search?" in url:
                query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"][0]
                matches = [unrelated, senate_market, hr_market] if query == "H.R. 3657" else [unrelated, senate_market]
                return {"events": [{"markets": matches}]}
            if "/markets/slug/" in url:
                slug = url.rsplit("/", 1)[-1]
                return {item["slug"]: item for item in (unrelated, hr_market, senate_market)}[slug]
            if "/markets/2657589/tags" in url:
                return [{"slug": "politics"}]
            self.fail(f"Jev or CLOB was called: {url}")

        rows = discover_records("white_house_briefings", source_url, None, NOW,
                                lambda url: feed if url.endswith("/feed/") else article, http)

        self.assertEqual(["H.R. 3657", "S. 790"], [row["discovery_query"] for row in rows])
        self.assertEqual(["will-hr-3657-become-law", "will-s-790-become-law"],
                         [row["market_slug"] for row in rows])
        self.assertTrue(all(row["status"] == "RULE_REVIEW_REQUIRED" for row in rows))
        self.assertTrue(all(row["discovery_basis"] == "UNVERIFIED_KEYWORD_SEARCH" for row in rows))
        self.assertTrue(all("jev" not in row and "quote" not in row for row in rows))
        self.assertEqual(2, sum("/public-search?" in url for url in calls))

    def test_no_bill_identifier_requires_manual_query_before_gamma_search(self):
        with self.assertRaisesRegex(ValueError, "bill identifier"):
            discover_records("federal_reserve_monetary", SOURCE_URL, None, NOW,
                             lambda url: FEED if url.endswith(".xml") else ARTICLE,
                             lambda url: self.fail(f"Gamma called: {url}"))

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

    def test_sparse_search_card_is_checked_against_full_market_detail(self):
        full_market = market("will-1-fed-rate-hike-happen-in-2026")
        search_card = {"slug": full_market["slug"], "question": full_market["question"],
                       "active": True, "closed": False, "acceptingOrders": True}
        calls = []

        def http(url):
            calls.append(url)
            if "/public-search?" in url:
                return {"events": [{"markets": [search_card]}]}
            if "/markets/slug/" in url:
                return full_market
            if "/markets/2657589/tags" in url:
                return [{"slug": "fed"}]
            self.fail(f"Jev or CLOB was called: {url}")

        rows = discover_records("federal_reserve_monetary", SOURCE_URL, "Federal Reserve", NOW,
                                lambda url: FEED if url.endswith(".xml") else ARTICLE, http)

        self.assertEqual(1, len(rows))
        self.assertEqual("RULE_REVIEW_REQUIRED", rows[0]["status"])
        self.assertEqual("UNVERIFIED_KEYWORD_SEARCH", rows[0]["discovery_basis"])
        self.assertNotIn("jev", rows[0])
        self.assertNotIn("quote", rows[0])
        self.assertTrue(any("/markets/slug/" in url for url in calls))

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
