#!/usr/bin/env python3
"""Unit tests for portfolio position parsing and null-field filtering."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from polymtrade_executor import validate_portfolio_position  # noqa: E402


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
