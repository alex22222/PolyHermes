#!/usr/bin/env python3
"""Unit tests for portfolio position parsing and null-field filtering."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from polymtrade_executor import (  # noqa: E402
    apply_portfolio_position_line_fallback,
    apply_redeemable_quantity_derivation,
    map_data_api_position,
    parse_data_api_positions,
    validate_portfolio_position,
)


def test_valid_position_passes():
    pos = {
        "marketTitle": "Will France win?",
        "side": "Yes",
        "quantity": 12.5,
        "currentValue": 10.0,
        "pnl": 1.2,
        "percentPnl": 12.0,
    }
    assert validate_portfolio_position(pos) is True


def test_missing_market_title_dropped():
    pos = {"marketTitle": None, "side": "Yes", "quantity": 12.5}
    assert validate_portfolio_position(pos) is False


def test_blank_market_title_dropped():
    pos = {"marketTitle": "   ", "side": "Yes", "quantity": 12.5}
    assert validate_portfolio_position(pos) is False


def test_missing_side_dropped():
    pos = {"marketTitle": "Will France win?", "side": "", "quantity": 12.5}
    assert validate_portfolio_position(pos) is False


def test_null_quantity_dropped():
    pos = {"marketTitle": "Will France win?", "side": "Yes", "quantity": None}
    assert validate_portfolio_position(pos) is False


def test_zero_quantity_dropped():
    pos = {"marketTitle": "Will France win?", "side": "Yes", "quantity": 0}
    assert validate_portfolio_position(pos) is False


def test_negative_quantity_dropped():
    pos = {"marketTitle": "Will France win?", "side": "Yes", "quantity": -1}
    assert validate_portfolio_position(pos) is False


def test_string_quantity_dropped():
    pos = {"marketTitle": "Will France win?", "side": "Yes", "quantity": "12.5"}
    assert validate_portfolio_position(pos) is False


def test_null_optional_fields_still_valid():
    """currentValue/pnl/percentPnl may be null; the position is still usable."""
    pos = {
        "marketTitle": "Will France win?",
        "side": "Yes",
        "quantity": 12.5,
        "currentValue": None,
        "pnl": None,
        "percentPnl": None,
    }
    assert validate_portfolio_position(pos) is True


def test_split_side_quantity_lines_are_recovered():
    position = {
        "marketTitle": "Will France win?",
        "side": "",
        "quantity": None,
        "currentValue": None,
        "pnl": -1.48,
        "percentPnl": 8.2,
        "_rawLines": [
            "Will France win?",
            "No",
            "•",
            "71.5 shares",
            "$16.5",
            "-$1.48",
            "(8.2%)",
        ],
    }

    apply_portfolio_position_line_fallback(position)

    assert position["side"] == "No"
    assert position["quantity"] == 71.5
    assert position["currentValue"] == 16.5
    assert position["percentPnl"] == -8.2
    assert "_rawLines" not in position


def test_combined_side_quantity_line_remains_supported():
    position = {
        "marketTitle": "Will France win?",
        "side": "Yes",
        "quantity": 12.5,
        "currentValue": 10.0,
        "pnl": 1.2,
        "percentPnl": 12.0,
        "_rawLines": ["Will France win?", "$10", "Yes • 12.5 shares", "+$1.2", "12%"],
    }

    apply_portfolio_position_line_fallback(position)

    assert position["side"] == "Yes"
    assert position["quantity"] == 12.5
    assert position["currentValue"] == 10.0
    assert position["percentPnl"] == 12.0


def test_redeemable_row_derives_quantity_from_value():
    """Settled rows show no share count; winning shares redeem at $1 each."""
    position = {
        "marketTitle": "Will the Democratic Party candidate win by 20%-25%?",
        "side": "No",
        "quantity": None,
        "currentValue": 0.75,
        "redeemable": True,
    }

    apply_redeemable_quantity_derivation(position)

    assert position["quantity"] == 0.75
    assert validate_portfolio_position(position) is True


def test_live_row_without_quantity_still_fails_closed():
    """The derivation must never rescue a live (non-redeemable) position."""
    position = {
        "marketTitle": "Will France win?",
        "side": "Yes",
        "quantity": None,
        "currentValue": 10.0,
        "redeemable": False,
    }

    apply_redeemable_quantity_derivation(position)

    assert position["quantity"] is None
    assert validate_portfolio_position(position) is False


def test_redeemable_row_without_value_stays_dropped():
    position = {
        "marketTitle": "Will France win?",
        "side": "Yes",
        "quantity": None,
        "currentValue": None,
        "redeemable": True,
    }

    apply_redeemable_quantity_derivation(position)

    assert position["quantity"] is None
    assert validate_portfolio_position(position) is False


def test_redeemable_row_with_real_quantity_untouched():
    position = {
        "marketTitle": "Will France win?",
        "side": "Yes",
        "quantity": 12.5,
        "currentValue": 9.9,
        "redeemable": True,
    }

    apply_redeemable_quantity_derivation(position)

    assert position["quantity"] == 12.5


def api_row(**overrides):
    row = {
        "title": "Will the U.S. invade Iran before 2027?",
        "outcome": "No",
        "current_size": 17.368,
        "current_value": 16.2391,
        "unrealized_pnl": 1.131,
        "percent_pnl": 7.5,
        "icon": "https://example.com/icon.jpg",
        "redeemable": False,
        "condition_id": "0x5db999",
        "slug": "will-the-us-invade-iran-before-2027",
        "event_slug": "us-iran-2027",
    }
    row.update(overrides)
    return row


def test_data_api_position_maps_to_scraper_shape():
    mapped = map_data_api_position(api_row())
    assert mapped == {
        "marketTitle": "Will the U.S. invade Iran before 2027?",
        "side": "No",
        "quantity": 17.368,
        "currentValue": 16.2391,
        "pnl": 1.131,
        "percentPnl": 7.5,
        "marketIcon": "https://example.com/icon.jpg",
        "href": None,
        "redeemable": False,
        "conditionId": "0x5db999",
        "marketSlug": "will-the-us-invade-iran-before-2027",
        "eventSlug": "us-iran-2027",
    }
    assert validate_portfolio_position(mapped) is True


def test_data_api_position_rejects_missing_critical_fields():
    assert map_data_api_position(api_row(title="")) is None
    assert map_data_api_position(api_row(outcome=None)) is None
    assert map_data_api_position(api_row(current_size="17.4")) is None
    assert map_data_api_position(api_row(current_size=0)) is None


def test_data_api_envelope_skips_dust_and_maps_the_rest():
    payload = {"data": [api_row(), api_row(title="Dust market", current_size=0),
                        api_row(title="Settled win", current_size=0.75, redeemable=True)]}
    positions = parse_data_api_positions(payload)
    assert [p["marketTitle"] for p in positions] == [
        "Will the U.S. invade Iran before 2027?", "Settled win"]
    assert positions[1]["redeemable"] is True
    assert positions[1]["quantity"] == 0.75


def test_data_api_fallback_is_voided_by_any_bad_row():
    assert parse_data_api_positions({"data": [api_row(), api_row(title=None)]}) is None
    assert parse_data_api_positions({"data": "not-a-list"}) is None
    assert parse_data_api_positions(["not-a-dict"]) is None
    assert parse_data_api_positions({"data": ["not-a-dict"]}) is None
