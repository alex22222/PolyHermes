import os
from dataclasses import dataclass
from typing import Any, Optional

import httpx


@dataclass(frozen=True)
class PortfolioRiskCheck:
    available: bool
    execution_allowed: bool
    decision_id: Optional[str] = None
    outcome: Optional[str] = None
    mode: Optional[str] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class PortfolioRiskCompletion:
    available: bool
    status: Optional[str] = None
    error: Optional[str] = None


class PortfolioRiskClient:
    """Call the PolyHermes portfolio-risk service with the actual proposed amount."""

    def __init__(
        self,
        url: Optional[str] = None,
        secret: Optional[str] = None,
        timeout_seconds: float = 2.0,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.url = url or os.getenv(
            "PORTFOLIO_RISK_URL",
            "http://127.0.0.1:8000/api/internal/risk/portfolio/evaluate",
        )
        self.secret = secret if secret is not None else (
            os.getenv("BRIDGE_RISK_SHARED_SECRET") or os.getenv("JWT_SECRET") or ""
        )
        self.timeout_seconds = timeout_seconds
        self._client = client
        self.enforcement_mode = os.getenv("PORTFOLIO_RISK_ENFORCEMENT_MODE", "SHADOW").strip().upper()

    async def evaluate_buy(self, payload: dict[str, Any]) -> PortfolioRiskCheck:
        if not self.secret:
            return self._unavailable("risk shared secret is not configured")
        try:
            if self._client is not None:
                response = await self._client.post(
                    self.url,
                    json=payload,
                    headers={"X-Bridge-Risk-Secret": self.secret},
                    timeout=self.timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False) as client:
                    response = await client.post(
                        self.url,
                        json=payload,
                        headers={"X-Bridge-Risk-Secret": self.secret},
                    )
            response.raise_for_status()
            body = response.json()
            data = body.get("data") if isinstance(body, dict) and body.get("code") == 0 else None
            if not isinstance(data, dict):
                return self._unavailable(f"invalid risk response: {body}")
            return PortfolioRiskCheck(
                available=True,
                execution_allowed=bool(data.get("executionAllowed", False)),
                decision_id=data.get("decisionId"),
                outcome=data.get("outcome"),
                mode=data.get("mode"),
            )
        except Exception as exc:
            return self._unavailable(f"{type(exc).__name__}: {exc}")

    async def complete(self, correlation_id: str, status: str) -> PortfolioRiskCompletion:
        if not self.secret:
            return PortfolioRiskCompletion(False, error="risk shared secret is not configured")
        url = self.url.rsplit("/", 1)[0] + "/complete"
        try:
            payload = {"correlationId": correlation_id, "status": status}
            if self._client is not None:
                response = await self._client.post(
                    url, json=payload, headers={"X-Bridge-Risk-Secret": self.secret}, timeout=self.timeout_seconds
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False) as client:
                    response = await client.post(url, json=payload, headers={"X-Bridge-Risk-Secret": self.secret})
            response.raise_for_status()
            body = response.json()
            data = body.get("data") if isinstance(body, dict) and body.get("code") == 0 else None
            if not isinstance(data, dict):
                return PortfolioRiskCompletion(False, error=f"invalid completion response: {body}")
            return PortfolioRiskCompletion(True, status=data.get("status"))
        except Exception as exc:
            return PortfolioRiskCompletion(False, error=f"{type(exc).__name__}: {exc}")

    def _unavailable(self, error: str) -> PortfolioRiskCheck:
        return PortfolioRiskCheck(
            available=False,
            execution_allowed=self.enforcement_mode != "ENFORCED",
            error=error,
        )
