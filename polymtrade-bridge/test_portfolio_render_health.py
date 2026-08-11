from types import SimpleNamespace

from polymtrade_executor import PolymtradeExecutor


def _live_executor() -> PolymtradeExecutor:
    executor = PolymtradeExecutor()
    executor._ready = True
    executor.page = SimpleNamespace(is_closed=lambda: False)
    executor.context = SimpleNamespace(pages=[executor.page])
    return executor


def test_repeated_portfolio_shell_render_marks_executor_unhealthy():
    executor = _live_executor()

    executor._record_portfolio_render_result(False)
    assert executor.is_ready() is True
    executor._record_portfolio_render_result(False)
    assert executor.is_ready() is False


def test_successful_portfolio_render_resets_failure_count():
    executor = _live_executor()

    executor._record_portfolio_render_result(False)
    executor._record_portfolio_render_result(True)

    assert executor.is_ready() is True
