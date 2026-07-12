#!/usr/bin/env python3

import unittest
from unittest.mock import patch

import httpx

from portfolio_risk_client import PortfolioRiskClient


class TestPortfolioRiskClient(unittest.IsolatedAsyncioTestCase):
    async def test_shadow_would_block_still_allows_execution(self):
        async def handler(request: httpx.Request):
            self.assertEqual(request.headers["X-Bridge-Risk-Secret"], "secret")
            return httpx.Response(200, json={
                "code": 0,
                "data": {
                    "decisionId": "d1",
                    "mode": "SHADOW",
                    "outcome": "WOULD_BLOCK",
                    "executionAllowed": True,
                },
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await PortfolioRiskClient(secret="secret", client=client).evaluate_buy({"side": "BUY"})

        self.assertTrue(result.available)
        self.assertTrue(result.execution_allowed)
        self.assertEqual(result.decision_id, "d1")
        self.assertEqual(result.outcome, "WOULD_BLOCK")

    async def test_enforced_denial_is_returned_to_execution_layer(self):
        async def handler(_request: httpx.Request):
            return httpx.Response(200, json={
                "code": 0,
                "data": {"decisionId": "d2", "mode": "ENFORCED", "outcome": "BLOCK", "executionAllowed": False},
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await PortfolioRiskClient(secret="secret", client=client).evaluate_buy({"side": "BUY"})

        self.assertTrue(result.available)
        self.assertFalse(result.execution_allowed)

    async def test_service_failure_is_explicit_but_does_not_block_during_shadow_integration(self):
        async def handler(_request: httpx.Request):
            raise httpx.ConnectError("offline")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await PortfolioRiskClient(secret="secret", client=client).evaluate_buy({"side": "BUY"})

        self.assertFalse(result.available)
        self.assertTrue(result.execution_allowed)
        self.assertIn("ConnectError", result.error)

    async def test_service_failure_is_fail_closed_when_bridge_enforcement_is_enabled(self):
        async def handler(_request: httpx.Request):
            raise httpx.ConnectError("offline")

        with patch.dict("os.environ", {"PORTFOLIO_RISK_ENFORCEMENT_MODE": "ENFORCED"}):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                result = await PortfolioRiskClient(secret="secret", client=client).evaluate_buy({"side": "BUY"})

        self.assertFalse(result.available)
        self.assertFalse(result.execution_allowed)

    async def test_completion_calls_terminal_endpoint(self):
        async def handler(request: httpx.Request):
            self.assertTrue(str(request.url).endswith("/complete"))
            return httpx.Response(200, json={"code": 0, "data": {"correlationId": "c1", "status": "SUCCESS"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await PortfolioRiskClient(secret="secret", client=client).complete("c1", "SUCCESS")

        self.assertTrue(result.available)
        self.assertEqual(result.status, "SUCCESS")


if __name__ == "__main__":
    unittest.main()
