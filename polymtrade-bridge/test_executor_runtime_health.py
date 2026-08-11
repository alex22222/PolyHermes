from types import SimpleNamespace

import pytest

from polymtrade_executor import PolymtradeExecutor


@pytest.mark.parametrize("value", ["", "   "])
def test_executor_treats_blank_proxy_as_disabled(monkeypatch, value):
    monkeypatch.setenv("BROWSER_PROXY", value)

    assert PolymtradeExecutor().proxy is None


def test_executor_is_ready_rejects_closed_page():
    executor = PolymtradeExecutor()
    executor._ready = True
    executor.page = SimpleNamespace(is_closed=lambda: True)
    executor.context = SimpleNamespace(pages=[executor.page])

    assert executor.is_ready() is False


def test_executor_is_ready_accepts_live_page_and_context():
    executor = PolymtradeExecutor()
    executor._ready = True
    executor.page = SimpleNamespace(is_closed=lambda: False)
    executor.context = SimpleNamespace(pages=[executor.page])

    assert executor.is_ready() is True
