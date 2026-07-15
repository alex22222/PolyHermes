from types import SimpleNamespace

from polymtrade_executor import PolymtradeExecutor


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
