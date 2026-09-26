#!/usr/bin/env python3
"""Run an evidence-gated, read-only Jev and single-side quote review."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from jev_shadow_monitor import CRYPTO_TERMS
from jev_shadow_probe import (
    CLOB_BASE, GAMMA_BASE, MAX_OPPOSITE_SCORE, MIN_DECISIVE_SCORE, USER_AGENT,
    evaluate_jev, http_json, load_api_key, parse_binary_market, simulate_buy,
)


OFFICIAL_FEEDS = {
    "federal_reserve_monetary": (
        "https://www.federalreserve.gov/feeds/press_monetary.xml", "www.federalreserve.gov",
    ),
    "white_house_presidential": (
        "https://www.whitehouse.gov/presidential-actions/feed/", "www.whitehouse.gov",
    ),
    "white_house_briefings": (
        "https://www.whitehouse.gov/briefings-statements/feed/", "www.whitehouse.gov",
    ),
}
SOURCE_CATEGORIES = {
    "federal_reserve_monetary": "finance",
    "white_house_presidential": "politics",
    "white_house_briefings": "politics",
    "senate_roll_call": "politics",
}
SCOPE_TAGS = {
    "finance": {"economy", "economic-policy", "finance", "fed", "fed-rates", "fomc"},
    "politics": {"politics", "geopolitics", "election", "elections", "us-politics", "white-house"},
}
RULE_DOCUMENT_HOST = "polymarket-upload.s3.us-east-2.amazonaws.com"
FULL_RULES_LINK = re.compile(
    r"\b(?:full|additional|complete)\s+(?:market\s+)?rules\b.{0,120}?(https?://[^\s)]+)",
    re.IGNORECASE | re.DOTALL,
)


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.found = False
        self.depth = 0
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.depth:
            attributes = dict(attrs)
            if not self.found and (tag == "main" or attributes.get("id") == "content" and attributes.get("role") == "main"):
                self.found = True
                self.depth = 1
            return
        if tag not in ("area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"):
            self.depth += 1
        if tag in ("script", "style", "noscript"):
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if not self.depth or tag in ("area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"):
            return
        if tag in ("script", "style", "noscript") and self.hidden:
            self.hidden -= 1
        self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.depth and not self.hidden:
            self.parts.append(data)


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html, application/rss+xml, text/xml"})
    try:
        import certifi
    except ImportError:
        context = ssl.create_default_context()
    else:
        context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, timeout=15, context=context) as response:
        final_url = urllib.parse.urlparse(response.geturl())
        if final_url.scheme != "https" or final_url.hostname != urllib.parse.urlparse(url).hostname:
            raise ValueError("official source redirected to another host")
        body = response.read(2_000_001)
    if len(body) > 2_000_000:
        raise ValueError("official source is too large")
    return body.decode("utf-8-sig")


def full_rules_url(rules: str) -> str | None:
    matches = list(FULL_RULES_LINK.finditer(rules))
    if not matches:
        return None
    nearby = rules[matches[0].start():matches[0].end() + 120]
    if len(matches) > 1 or len(re.findall(r"https?://[^\s)]+", nearby)) > 1:
        raise ValueError("multiple external full rules documents are unsupported")
    return matches[0].group(1).rstrip(".,;")


def collect_rule_document(url: str) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    if (parsed.scheme != "https" or parsed.netloc != RULE_DOCUMENT_HOST
            or not parsed.path.startswith("/market_products/") or not parsed.path.lower().endswith(".pdf")
            or parsed.query or parsed.fragment):
        raise ValueError("external full rules URL is not an approved Polymarket PDF")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf"})
    try:
        import certifi
    except ImportError:
        context = ssl.create_default_context()
    else:
        context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, timeout=15, context=context) as response:
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme != "https" or final.netloc != RULE_DOCUMENT_HOST:
            raise ValueError("external full rules PDF redirected outside the approved host")
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000 or not raw.startswith(b"%PDF-"):
        raise ValueError("external full rules PDF is oversized or invalid")
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError("pypdf is required to verify external full rules") from None
    try:
        reader = PdfReader(BytesIO(raw))
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 20:
            raise ValueError("external full rules PDF is encrypted or has an unsupported page count")
        pages = [" ".join((page.extract_text() or "").split()) for page in reader.pages]
    except ValueError:
        raise
    except Exception:
        raise ValueError("external full rules PDF text could not be extracted") from None
    if any(not text for text in pages):
        raise ValueError("external full rules PDF has a page without extractable text")
    text = "\n\n".join(f"[Page {number}] {page}" for number, page in enumerate(pages, 1))
    if len(text) > 50_000:
        raise ValueError("external full rules PDF extracted text is too large")
    return {"url": url, "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "page_count": len(pages), "text": text}


def collect_source(
    source_kind: str, source_url: str, now: datetime,
    fetch_fn: Callable[[str], str] = fetch_text,
) -> dict[str, str]:
    if source_kind == "senate_roll_call":
        return collect_senate_vote(source_url, now, fetch_fn)
    if source_kind not in OFFICIAL_FEEDS:
        raise ValueError("unknown official feed")
    feed_url, host = OFFICIAL_FEEDS[source_kind]
    if not isinstance(source_url, str):
        raise ValueError("source URL is outside the official feed host")
    parsed_url = urllib.parse.urlparse(source_url)
    if parsed_url.scheme != "https" or parsed_url.hostname != host:
        raise ValueError("source URL is outside the official feed host")
    feed = ET.fromstring(fetch_fn(feed_url))
    item = next((item for item in feed.findall("./channel/item") if item.findtext("link") == source_url), None)
    if item is None:
        raise ValueError("source URL is not in the official feed")
    published_raw = item.findtext("pubDate")
    if not published_raw:
        raise ValueError("official feed item has no publication date")
    try:
        published = parsedate_to_datetime(published_raw)
    except (TypeError, ValueError):
        raise ValueError("official feed publication date is invalid") from None
    if published.tzinfo is None or published.utcoffset() is None:
        raise ValueError("official feed publication date has no time zone")
    published = published.astimezone(timezone.utc)
    if published > now:
        raise ValueError("official source publication date is in the future")
    raw_html = fetch_fn(source_url)
    parser = _VisibleText()
    parser.feed(raw_html)
    article_text = " ".join(" ".join(parser.parts).split())
    if not parser.found or not article_text:
        raise ValueError("official article main content is missing")
    return {
        "publisher": source_kind,
        "feed_url": feed_url,
        "source_url": source_url,
        "title": item.findtext("title") or "",
        "published_at": published.isoformat(),
        "retrieved_at": now.isoformat(),
        "content_sha256": hashlib.sha256(article_text.encode("utf-8")).hexdigest(),
        "raw_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "text": article_text,
    }


def collect_senate_vote(
    source_url: str, now: datetime, fetch_fn: Callable[[str], str],
) -> dict[str, str]:
    if not isinstance(source_url, str):
        raise ValueError("Senate vote URL must be an official XML vote record")
    parsed_url = urllib.parse.urlparse(source_url)
    match = re.fullmatch(
        r"/legislative/LIS/roll_call_votes/vote(\d{3})([12])/vote_(\d{3})_([12])_(\d{5})\.xml",
        parsed_url.path,
    )
    if (parsed_url.scheme != "https" or parsed_url.netloc != "www.senate.gov"
            or parsed_url.query or parsed_url.fragment or not match
            or match.group(1, 2) != match.group(3, 4)):
        raise ValueError("Senate vote URL must be a canonical official XML vote record")
    congress, session, _, _, vote_number = match.groups()
    menu_url = f"https://www.senate.gov/legislative/LIS/roll_call_lists/vote_menu_{congress}_{session}.xml"
    menu = ET.fromstring(fetch_fn(menu_url))
    if menu.findtext("congress") != congress or menu.findtext("session") != session:
        raise ValueError("Senate official vote menu identity is invalid")
    item = next((vote for vote in menu.findall("./votes/vote")
                 if vote.findtext("vote_number") == vote_number), None)
    if item is None:
        raise ValueError("Senate vote is not in the official vote menu")
    raw_xml = fetch_fn(source_url)
    vote = ET.fromstring(raw_xml)
    if (vote.tag != "roll_call_vote" or vote.findtext("congress") != congress
            or vote.findtext("session") != session
            or vote.findtext("vote_number") != str(int(vote_number))
            or vote.findtext("congress_year") != menu.findtext("congress_year")):
        raise ValueError("Senate vote identity does not match the official menu")
    raw_date = " ".join((vote.findtext("vote_date") or "").split())
    try:
        local_vote_time = datetime.strptime(raw_date, "%B %d, %Y, %I:%M %p")
    except ValueError:
        raise ValueError("Senate vote date is invalid") from None
    if (local_vote_time.strftime("%d-%b") != item.findtext("vote_date")
            or str(local_vote_time.year) != menu.findtext("congress_year")):
        raise ValueError("Senate vote date does not match the official menu")
    published = local_vote_time.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
    if published > now:
        raise ValueError("Senate vote date is in the future")
    modified_raw = " ".join((vote.findtext("modify_date") or "").split())
    try:
        modified = datetime.strptime(modified_raw, "%B %d, %Y, %I:%M %p")
    except ValueError:
        raise ValueError("Senate vote modification time is missing or invalid") from None
    modified = modified.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
    if not published <= modified <= now:
        raise ValueError("Senate vote modification time is outside the observation window")
    result = " ".join((vote.findtext("vote_result") or "").split())
    menu_result = " ".join((item.findtext("result") or "").split())
    if not menu_result or result.casefold() not in (menu_result.casefold(), f"nomination {menu_result}".casefold()):
        raise ValueError("Senate vote result does not match the official menu")
    question = " ".join((vote.findtext("vote_question_text") or "").split())
    document = " ".join((vote.findtext("vote_document_text") or "").split())
    title = " ".join((vote.findtext("vote_title") or "").split())
    if not all((question, document, title)):
        raise ValueError("Senate vote details are incomplete")
    source_text = f"Vote date: {raw_date}. Question: {question}. Document: {document}. Result: {result}."
    return {
        "publisher": "senate_roll_call", "feed_url": menu_url, "source_url": source_url,
        "title": title, "published_at": published.isoformat(), "time_basis": "vote_date",
        "source_modified_at": modified.isoformat(),
        "retrieved_at": now.isoformat(),
        "content_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "raw_xml_sha256": hashlib.sha256(raw_xml.encode("utf-8")).hexdigest(),
        "menu_item_sha256": hashlib.sha256(ET.tostring(item)).hexdigest(),
        "text": source_text,
    }


def check_rules(checks: Any, rules: str, source: dict[str, str], now: datetime) -> bool:
    if not isinstance(checks, list) or not checks:
        return False
    published = datetime.fromisoformat(source["published_at"])
    criteria = set()
    for check in checks:
        if not isinstance(check, dict):
            return False
        criterion = str(check.get("criterion") or "").strip()
        rule_quote = str(check.get("rule_quote") or "").strip()
        quote = str(check.get("evidence_quote") or "").strip()
        if (not criterion or criterion in criteria or check.get("status") not in ("CONFIRMED", "EXCLUDED")
                or not str(check.get("reviewed_by") or "").strip()
                or not rule_quote or rule_quote.casefold() not in rules.casefold()
                or not quote or quote.casefold() not in source["text"].casefold()):
            return False
        try:
            reviewed = datetime.fromisoformat(check["reviewed_at"].replace("Z", "+00:00"))
        except (KeyError, AttributeError, ValueError, TypeError):
            return False
        if reviewed.tzinfo is None or not published <= reviewed <= now:
            return False
        criteria.add(criterion)
    return True


def check_rule_review(review: Any, rules: str, source: dict[str, str], now: datetime,
                      rule_document: dict[str, Any] | None = None) -> bool:
    if not isinstance(review, dict) or not isinstance(review.get("complete"), bool):
        return False
    if review.get("resolution_rules_sha256") != hashlib.sha256(rules.encode("utf-8")).hexdigest():
        return False
    if review.get("source_content_sha256") != source["content_sha256"]:
        return False
    if rule_document and review.get("rule_document_sha256") != rule_document["raw_sha256"]:
        return False
    if not str(review.get("reviewed_by") or "").strip():
        return False
    if review.get("evidence_verdict") not in ("QUALIFIES", "DOES_NOT_QUALIFY") or not str(review.get("evidence_reason") or "").strip():
        return False
    if review["evidence_verdict"] == "QUALIFIES" and review["complete"] is not True:
        return False
    try:
        reviewed = datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
    except (KeyError, AttributeError, ValueError, TypeError):
        return False
    return reviewed.tzinfo is not None and datetime.fromisoformat(source["published_at"]) <= reviewed <= now


def decisive_side(scores: dict[str, float]) -> str | None:
    if scores["ambiguous"] > MAX_OPPOSITE_SCORE:
        return None
    if scores["yes"] >= MIN_DECISIVE_SCORE and scores["no"] <= MAX_OPPOSITE_SCORE:
        return "Yes"
    if scores["no"] >= MIN_DECISIVE_SCORE and scores["yes"] <= MAX_OPPOSITE_SCORE:
        return "No"
    return None


def run_review(
    case: dict[str, Any], now: datetime,
    fetch_fn: Callable[[str], str] = fetch_text,
    http_fn: Callable[..., Any] = http_json,
    api_key: str | None = None,
    shares: Decimal = Decimal("20"),
    min_gap: Decimal = Decimal("0.15"),
    quote_now_fn: Callable[[], datetime] | None = None,
    rule_document_fn: Callable[[str], dict[str, Any]] = collect_rule_document,
) -> dict[str, Any]:
    slug = case.get("market_slug")
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        raise ValueError("market_slug must be a market slug")
    if not isinstance(case.get("source_kind"), str):
        raise ValueError("source_kind must name an official feed")
    checks = case.get("rule_checks")
    review = case.get("rule_review")
    result: dict[str, Any] = {
        "schema_version": 1, "observed_at": now.isoformat(), "market_slug": slug,
        "category": case.get("category") if case.get("category") in ("politics", "finance") else None,
        "rule_checks": [{key: check.get(key) for key in ("criterion", "rule_quote", "evidence_quote", "status", "reviewed_by", "reviewed_at")}
                        for check in checks if isinstance(check, dict)] if isinstance(checks, list) else None,
        "rule_review": {key: review.get(key) for key in ("resolution_rules_sha256", "source_content_sha256", "rule_document_sha256", "complete", "reviewed_by", "reviewed_at", "evidence_verdict", "evidence_reason")}
                       if isinstance(review, dict) else None,
        "status": "MARKET_UNAVAILABLE", "candidate_outcome": None, "paper_only": True,
    }
    market_url = f"{GAMMA_BASE}/markets/slug/{urllib.parse.quote(slug, safe='')}"
    try:
        market = http_fn(market_url)
        if not isinstance(market, dict) or any(
            not isinstance(market.get(field), str) or not market[field].strip()
            for field in ("question", "description", "conditionId")
        ):
            raise ValueError("Gamma market details are invalid")
        if market.get("slug") != slug:
            raise ValueError("Gamma market slug does not match request")
        market_text = " ".join(str(market.get(field) or "") for field in ("question", "slug", "description"))
        if case.get("category") not in ("politics", "finance") or CRYPTO_TERMS.search(market_text):
            result.update(status="OUT_OF_SCOPE", reason="category is not politics/finance or market contains crypto")
            return result
        parsed = parse_binary_market(market)
    except (ValueError, RuntimeError, OSError) as error:
        result["reason"] = str(error)
        return result
    result.update(
        question=market["question"], resolution_rules=market["description"], condition_id=market["conditionId"],
        market_created_at=market.get("createdAt"),
        market_closed=market.get("closed"), market_accepting_orders=market.get("acceptingOrders"),
        market_restricted=market.get("restricted"), orderbook_enabled=market.get("enableOrderBook"),
        fees_enabled=market.get("feesEnabled"), fee_rate=parsed["fee_rate"],
    )
    market_id = str(market.get("id") or "")
    if not market_id.isdecimal():
        result.update(status="SCOPE_UNVERIFIED", reason="Gamma market ID unavailable for tag verification")
        return result
    try:
        tags = http_fn(f"{GAMMA_BASE}/markets/{market_id}/tags")
    except (ValueError, RuntimeError, OSError) as error:
        result.update(status="SCOPE_UNVERIFIED", reason=f"Gamma market tags unavailable: {error}")
        return result
    if not isinstance(tags, list) or not all(isinstance(tag, dict) for tag in tags):
        result.update(status="SCOPE_UNVERIFIED", reason="Gamma market tags are invalid")
        return result
    tag_slugs = [str(tag.get("slug") or "").casefold() for tag in tags if tag.get("slug")]
    result["market_tags"] = tag_slugs
    if not tag_slugs:
        result.update(status="SCOPE_UNVERIFIED", reason="Gamma market has no topic tags")
        return result
    if (any(CRYPTO_TERMS.search(f"{tag.get('slug') or ''} {tag.get('label') or ''}") for tag in tags)
            or not SCOPE_TAGS[case["category"]].intersection(tag_slugs)):
        result.update(status="OUT_OF_SCOPE", reason="Gamma market tags do not confirm the declared politics/finance category or include crypto")
        return result

    try:
        source = collect_source(case.get("source_kind"), case.get("source_url", ""), now, fetch_fn)
    except (ValueError, RuntimeError, OSError, ET.ParseError) as error:
        result.update(status="SOURCE_UNAVAILABLE", reason=str(error))
        return result
    result["source"] = source
    rules_text = market["description"].casefold()
    if all(phrase in rules_text for phrase in ("verbal mention", "audio or video")):
        result.update(status="SOURCE_TYPE_UNSUPPORTED",
                      reason="market requires a recorded verbal mention; approved sources provide written text only")
        return result
    rule_document = None
    try:
        rule_url = full_rules_url(market["description"])
    except ValueError as error:
        result.update(status="RULE_REVIEW_REQUIRED", reason=str(error))
        return result
    if rule_url:
        result["rule_document_url"] = rule_url
        try:
            rule_document = rule_document_fn(rule_url)
            if (rule_document.get("url") != rule_url
                    or not re.fullmatch(r"[0-9a-f]{64}", str(rule_document.get("raw_sha256", "")))
                    or rule_document.get("text_sha256") != hashlib.sha256(
                        str(rule_document.get("text", "")).encode("utf-8")).hexdigest()
                    or not isinstance(rule_document.get("page_count"), int)
                    or rule_document["page_count"] < 1 or not rule_document.get("text")):
                raise ValueError("external full rules document metadata is invalid")
        except (ValueError, RuntimeError, OSError, AttributeError) as error:
            result.update(status="RULE_REVIEW_REQUIRED", reason=f"external full rules document unavailable: {error}")
            return result
        result["rule_document"] = {**rule_document, "retrieved_at": now.isoformat()}
        result["gamma_resolution_rules"] = market["description"]
    full_rules = market["description"] + ("\n\n" + rule_document["text"] if rule_document else "")
    result["resolution_rules"] = full_rules
    if CRYPTO_TERMS.search(full_rules):
        result.update(status="OUT_OF_SCOPE", reason="full market rules contain crypto")
        return result
    if rule_document and (not isinstance(review, dict)
                          or review.get("rule_document_sha256") != rule_document["raw_sha256"]):
        result.update(status="RULE_REVIEW_REQUIRED",
                      reason="external full rules SHA-256 is missing or changed since human review")
        return result
    if not isinstance(review, dict) or review.get("source_content_sha256") != source["content_sha256"]:
        result.update(status="RULE_REVIEW_REQUIRED", reason="official source SHA-256 is missing or changed since human review")
        return result
    if (not check_rule_review(review, full_rules, source, now, rule_document)
            or not check_rules(checks, full_rules, source, now)):
        result.update(status="RULE_REVIEW_REQUIRED", reason="review the full current resolution text and each criterion against a dated quote in the official source")
        return result
    statuses = [check["status"] for check in checks]
    if review["evidence_verdict"] == "DOES_NOT_QUALIFY" and "EXCLUDED" in statuses:
        result.update(status="EVIDENCE_NOT_QUALIFYING", reason=review["evidence_reason"])
        return result
    if review["evidence_verdict"] != "QUALIFIES" or any(status != "CONFIRMED" for status in statuses):
        result.update(status="RULE_REVIEW_REQUIRED", reason="rule check statuses contradict the evidence verdict")
        return result
    if not api_key:
        result.update(status="JEV_UNAVAILABLE", reason="Jev key unavailable")
        return result

    evidence = [{"source_url": source["source_url"], "source_title": source["title"],
                 "published_at": source["published_at"],
                 "time_basis": source.get("time_basis", "feed_publication"),
                 "observed_at": source["retrieved_at"],
                 "text": source["text"] if source["publisher"] == "senate_roll_call"
                 else " ".join(check["evidence_quote"] for check in case["rule_checks"])}]
    if source.get("source_modified_at"):
        evidence[0]["source_modified_at"] = source["source_modified_at"]
    result["jev_evidence"] = evidence
    try:
        jev = evaluate_jev(market["question"], full_rules, evidence, api_key, http_fn)
    except (ValueError, RuntimeError, OSError) as error:
        result.update(status="JEV_UNAVAILABLE", reason=str(error))
        return result
    result["jev"] = jev
    side = decisive_side(jev["scores"])
    if side is None:
        result["status"] = "JEV_INCONCLUSIVE"
        return result
    result["evaluated_outcome"] = side
    try:
        refreshed_market = http_fn(market_url)
        result["market_rechecked_at"] = datetime.now(timezone.utc).isoformat()
        if not isinstance(refreshed_market, dict) or any(
            not isinstance(refreshed_market.get(field), str) or not refreshed_market[field].strip()
            for field in ("question", "description", "conditionId")
        ):
            raise ValueError("Gamma market recheck details are invalid")
    except (ValueError, RuntimeError, OSError) as error:
        result.update(status="MARKET_UNAVAILABLE", reason=f"Gamma market recheck before quote failed: {error}",
                      market_rechecked_at=result.get("market_rechecked_at") or datetime.now(timezone.utc).isoformat(),
                      market_closed=None, market_accepting_orders=None, market_restricted=None,
                      orderbook_enabled=None, fees_enabled=None, fee_rate=None)
        return result
    result.update(market_closed=refreshed_market.get("closed"),
                  market_accepting_orders=refreshed_market.get("acceptingOrders"),
                  market_restricted=refreshed_market.get("restricted"),
                  orderbook_enabled=refreshed_market.get("enableOrderBook"),
                  fees_enabled=refreshed_market.get("feesEnabled"), fee_rate=None)
    try:
        refreshed_parsed = parse_binary_market(refreshed_market)
    except ValueError as error:
        status = "QUOTE_UNAVAILABLE" if str(error).startswith("market fee") else "MARKET_UNAVAILABLE"
        result.update(status=status, reason=f"Gamma market recheck before quote failed: {error}")
        return result
    if (refreshed_market["question"] != market["question"]
            or refreshed_market["description"] != market["description"]):
        result.update(status="RULE_REVIEW_REQUIRED", reason="Gamma question or resolution rules changed after Jev; review and rerun",
                      question=refreshed_market["question"], resolution_rules=refreshed_market["description"])
        return result
    if rule_document:
        result["rule_document_rechecked_at"] = datetime.now(timezone.utc).isoformat()
        try:
            refreshed_document = rule_document_fn(rule_url)
            if (refreshed_document.get("url") != rule_url
                    or refreshed_document.get("raw_sha256") != rule_document["raw_sha256"]
                    or refreshed_document.get("text_sha256") != hashlib.sha256(
                        str(refreshed_document.get("text", "")).encode("utf-8")).hexdigest()
                    or refreshed_document.get("text_sha256") != rule_document["text_sha256"]):
                raise ValueError("external full rules document changed after Jev")
        except (ValueError, RuntimeError, OSError, AttributeError) as error:
            result.update(status="RULE_REVIEW_REQUIRED", reason=f"external full rules recheck failed: {error}")
            return result
    if (refreshed_market.get("slug") != slug
            or refreshed_market.get("id") != market.get("id")
            or refreshed_market["conditionId"] != market["conditionId"]
            or refreshed_parsed["tokens"] != parsed["tokens"]):
        result.update(status="MARKET_UNAVAILABLE", reason="Gamma market slug, identity, or outcome tokens changed after Jev")
        return result
    result["market_tags_rechecked_at"] = datetime.now(timezone.utc).isoformat()
    try:
        refreshed_tags = http_fn(f"{GAMMA_BASE}/markets/{market_id}/tags")
    except (ValueError, RuntimeError, OSError) as error:
        result.update(status="SCOPE_UNVERIFIED", reason=f"Gamma market tags unavailable after Jev: {error}")
        return result
    if not isinstance(refreshed_tags, list) or not refreshed_tags or not all(isinstance(tag, dict) for tag in refreshed_tags):
        result.update(status="SCOPE_UNVERIFIED", reason="Gamma market tags are invalid after Jev")
        return result
    tag_slugs = [str(tag.get("slug") or "").casefold() for tag in refreshed_tags if tag.get("slug")]
    result["market_tags"] = tag_slugs
    if not tag_slugs:
        result.update(status="SCOPE_UNVERIFIED", reason="Gamma market has no topic tags after Jev")
        return result
    if (any(CRYPTO_TERMS.search(f"{tag.get('slug') or ''} {tag.get('label') or ''}") for tag in refreshed_tags)
            or not SCOPE_TAGS[case["category"]].intersection(tag_slugs)):
        result.update(status="OUT_OF_SCOPE", reason="Gamma market tags changed or include crypto after Jev")
        return result
    source_rechecked_at = datetime.now(timezone.utc)
    result["source_rechecked_at"] = source_rechecked_at.isoformat()
    try:
        refreshed_source = collect_source(case["source_kind"], case["source_url"], source_rechecked_at, fetch_fn)
    except (ValueError, RuntimeError, OSError, ET.ParseError) as error:
        result.update(status="SOURCE_UNAVAILABLE", reason=f"official source recheck after Jev failed: {error}")
        return result
    result["source_recheck_content_sha256"] = refreshed_source["content_sha256"]
    identity_fields = ("publisher", "feed_url", "source_url", "title", "published_at", "time_basis",
                       "source_modified_at", "content_sha256")
    if source["publisher"] == "senate_roll_call":
        identity_fields += ("raw_xml_sha256", "menu_item_sha256")
    if any(refreshed_source.get(field) != source.get(field) for field in identity_fields):
        result.update(status="RULE_REVIEW_REQUIRED", reason="official source changed after Jev; review and rerun")
        return result
    market, parsed = refreshed_market, refreshed_parsed
    result.update(market_restricted=market.get("restricted"), orderbook_enabled=market.get("enableOrderBook"),
                  fees_enabled=market.get("feesEnabled"), fee_rate=parsed["fee_rate"])
    if market.get("enableOrderBook") is not True:
        result.update(status="QUOTE_UNAVAILABLE", reason="order book availability is unconfirmed")
        return result
    if market.get("feesEnabled") is True and market.get("feeSchedule", {}).get("takerOnly") is not True:
        result.update(status="QUOTE_UNAVAILABLE", reason="taker fee payer is unconfirmed")
        return result
    if quote_now_fn is None:
        quote_now_fn = lambda: datetime.now(timezone.utc)
    try:
        token = parsed["tokens"][side]
        book = http_fn(f"{CLOB_BASE}/book?{urllib.parse.urlencode({'token_id': token})}")
        if not isinstance(book, dict) or book.get("asset_id") != token or book.get("market") != market["conditionId"]:
            raise ValueError("order book does not match the selected market and outcome")
        quote = simulate_buy(book, shares, parsed["fee_rate"], quote_now_fn())
    except (ValueError, RuntimeError, OSError) as error:
        result.update(status="QUOTE_UNAVAILABLE", reason=str(error))
        return result
    result.update(quote=quote, requested_shares=shares, fee_rate=parsed["fee_rate"], min_gap=min_gap)
    if market.get("restricted") is not False:
        result.update(status="RESTRICTION_UNVERIFIED", reason="market has geographic restrictions or restriction status is unknown")
        return result
    if quote["gap_per_share"] >= min_gap:
        result.update(status="REVIEW_CANDIDATE", candidate_outcome=side)
    else:
        result["status"] = "BELOW_GAP"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/jev-fact-chain.jsonl"))
    args = parser.parse_args()
    with args.input.open(encoding="utf-8") as input_file:
        cases = json.load(input_file)
    if not isinstance(cases, list) or not cases:
        parser.error("input must be a non-empty JSON list")
    api_key = load_api_key()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed = 0
    with args.output.open("a", encoding="utf-8") as output_file:
        for case in cases:
            now = datetime.now(timezone.utc)
            try:
                if not isinstance(case, dict):
                    raise ValueError("each case must be an object")
                result = run_review(case, now, api_key=api_key)
            except (ValueError, RuntimeError, OSError) as error:
                result = {"schema_version": 1, "observed_at": now.isoformat(), "market_slug": case.get("market_slug") if isinstance(case, dict) else None,
                          "category": case.get("category") if isinstance(case, dict) and case.get("category") in ("politics", "finance") else None,
                          "status": "SKIPPED", "reason": str(error), "paper_only": True}
            if result["status"] != "SKIPPED":
                completed += 1
            output_file.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
            print(f"{result['market_slug']}: {result['status']}")
    return 0 if completed else 1


if __name__ == "__main__":
    sys.exit(main())
