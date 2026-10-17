import asyncio
import ast
import inspect
import json
import logging
import math
import shutil
import subprocess
import textwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import main
from polymtrade_executor import PolymtradeExecutor, validate_portfolio_position


def configure(monkeypatch, positions=None, balance=40.0, explicit_error=False):
    snapshot = {"error": "synthetic scrape failure"} if explicit_error else {
        "positions": positions or [], "portfolio_complete": True,
        "pending_redeem_value": 0.0,
    }
    executor = SimpleNamespace(
        is_ready=lambda: True,
        fetch_portfolio_positions=AsyncMock(return_value=snapshot),
        get_portfolio_balance=AsyncMock(return_value=balance),
    )
    monkeypatch.setattr(main, "executor", executor)
    monkeypatch.setattr(main, "rule_engine", None)
    monkeypatch.setattr(main, "require_logged_in", AsyncMock())
    monkeypatch.setattr(main, "_annotate_crypto_exit_shadow", lambda _: {})
    monkeypatch.setattr(main, "_portfolio_lock", asyncio.Lock())
    monkeypatch.setattr(main.metrics, "portfolio_requests", 0)
    monkeypatch.setattr(main.metrics, "portfolio_errors", 0)
    return snapshot


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_balance_still_fails_but_counts_once(monkeypatch, caplog, value):
    snapshot = configure(monkeypatch, balance=value)
    with caplog.at_level(logging.WARNING, logger="main"):
        response = TestClient(main.app, raise_server_exceptions=False).get("/portfolio")
    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert main.metrics.portfolio_requests == 1
    assert main.metrics.portfolio_errors == 1
    assert not math.isfinite(snapshot["available_balance"])
    assert snapshot["portfolio_complete"] is True
    assert "available_balance" in caplog.text


def test_nested_bad_values_log_only_safe_paths_and_do_not_modify_payload(monkeypatch, caplog):
    secret_marker = "SYNTHETIC_PRIVATE_TITLE_NEVER_LOG"
    position = {"marketTitle": secret_marker, "side": "Yes", "quantity": float("nan"),
                "currentValue": float("inf"), secret_marker: float("-inf")}
    snapshot = configure(monkeypatch, positions=[position])
    with caplog.at_level(logging.WARNING, logger="main"):
        response = TestClient(main.app, raise_server_exceptions=False).get("/portfolio")
    assert response.status_code == 500
    assert main.metrics.portfolio_errors == 1
    assert "positions[0].quantity" in caplog.text
    assert "positions[0].currentValue" in caplog.text
    assert secret_marker not in caplog.text
    assert snapshot["positions"][0] is position
    assert math.isnan(position["quantity"])
    assert snapshot["portfolio_complete"] is True


@pytest.mark.parametrize("balance", [None, 0.0, 40.0])
def test_finite_or_unknown_optional_balance_preserves_success(monkeypatch, balance):
    configure(monkeypatch, positions=[{"marketTitle": "Synthetic", "side": "Yes",
              "quantity": 2.0, "currentValue": None, "pnl": -1.0, "percentPnl": None}], balance=balance)
    response = TestClient(main.app, raise_server_exceptions=False).get("/portfolio")
    assert response.status_code == 200
    assert response.json()["available_balance"] == balance
    assert main.metrics.portfolio_errors == 0


def test_explicit_scrape_error_is_counted_once(monkeypatch):
    configure(monkeypatch, explicit_error=True)
    response = TestClient(main.app, raise_server_exceptions=False).get("/portfolio")
    assert response.status_code == 500
    assert main.metrics.portfolio_errors == 1


def test_nonfinite_balance_is_unknown_without_changing_position_validation():
    assert validate_portfolio_position({"marketTitle": "Synthetic", "side": "Yes",
                                        "quantity": float("nan")}) is True
    executor = PolymtradeExecutor()
    executor.page = SimpleNamespace(evaluate=AsyncMock(return_value={"value": float("nan"), "text": "synthetic"}))
    assert asyncio.run(executor._get_usdc_balance()) is None


def test_actual_balance_javascript_rejects_comma_only_nan():
    node = shutil.which("node")
    assert node, "Node is required to reproduce the actual DOM parser locally"
    function = ast.parse(textwrap.dedent(inspect.getsource(PolymtradeExecutor._get_usdc_balance)))
    assignment = next(x for x in function.body[0].body if isinstance(x, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "js" for t in x.targets))
    source = ast.literal_eval(assignment.value)
    runner = '''const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const results = input.texts.map(text => {
  const document = {querySelectorAll: () => [{innerText: text, textContent: text, getClientRects: () => [{}]}]};
  const result = new Function("document", "return (" + input.source + ")()") (document);
  return result === null ? "unknown" : Number.isNaN(result.value) ? "nan" :
    Number.isFinite(result.value) ? "finite" : "infinite";
});
process.stdout.write(JSON.stringify(results));'''
    output = subprocess.run([node, "-e", runner], input=json.dumps({"source": source,
        "texts": ["Balance, pUSD", "Balance ,,, pUSD", "40 pUSD", "Balance 40", "Balance —"]}),
        text=True, capture_output=True, check=True, timeout=10)
    assert json.loads(output.stdout) == ["unknown", "unknown", "finite", "finite", "unknown"]


def test_diagnostic_paths_are_bounded_and_unknown_keys_are_redacted():
    paths = main._nonfinite_portfolio_field_paths({"positions": [
        {"private-wallet-key": float("nan")} for _ in range(100)]})
    assert len(paths) == 32
    assert all("private-wallet-key" not in path for path in paths)
