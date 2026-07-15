import asyncio
import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field, ConfigDict

from polymtrade_executor import PolymtradeExecutor
from copy_trading_config import COPY_MODE_PROPORTIONAL_RISK, CopyTradingRuleEngine, infer_market_category
from bridge_recorder import BridgeTradeRecorder
from position_ledger import PositionLedger
from bridge_reliability_audit import (
    audit as run_bridge_reliability_audit,
    load_reconciliations,
    reconciliation_file_path,
    reconciliation_key,
    save_reconciliations,
)
from bridge_metrics import metrics
from portfolio_risk_client import PortfolioRiskCheck, PortfolioRiskClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

BTC_UPDOWN_STALE_BUFFER_SECONDS = int(os.getenv("BTC_UPDOWN_STALE_BUFFER_SECONDS", "90"))
CRYPTO_UPDOWN_STALE_BUFFER_SECONDS = int(os.getenv("CRYPTO_UPDOWN_STALE_BUFFER_SECONDS", "60"))
BTC_UPDOWN_5M_SECONDS = 300
BTC_UPDOWN_5M_MIN_BUY_PRICE = Decimal(os.getenv("BTC_UPDOWN_5M_MIN_BUY_PRICE", "0.20"))
BTC_UPDOWN_5M_MAX_BUY_PRICE = Decimal(os.getenv("BTC_UPDOWN_5M_MAX_BUY_PRICE", "0.65"))
BTC_UPDOWN_5M_DAILY_MAX_SUCCESS_BUYS = int(os.getenv("BTC_UPDOWN_5M_DAILY_MAX_SUCCESS_BUYS", "50"))
TAIL_RISK_MIN_BUY_PRICE = Decimal(os.getenv("TAIL_RISK_MIN_BUY_PRICE", "0.10"))
HIGH_CONFIDENCE_MAX_BUY_PRICE = Decimal(os.getenv("HIGH_CONFIDENCE_MAX_BUY_PRICE", "0.55"))
LEADER_EVENT_ACTIVITY_WINDOW_SECONDS = int(
    os.getenv("LEADER_EVENT_ACTIVITY_WINDOW_SECONDS", "1800")
)
LEADER_EVENT_ACTIVITY_MAX_RECORDS = int(os.getenv("LEADER_EVENT_ACTIVITY_MAX_RECORDS", "5"))
LEADER_EVENT_COMBO_MIN_MARKETS = int(os.getenv("LEADER_EVENT_COMBO_MIN_MARKETS", "2"))
GENERIC_REPEAT_BUY_WINDOW_SECONDS = int(os.getenv("GENERIC_REPEAT_BUY_WINDOW_SECONDS", "1800"))
NEAR_EXPIRY_NEWS_BUY_MAX_HOURS = Decimal(os.getenv("NEAR_EXPIRY_NEWS_BUY_MAX_HOURS", "72"))
NEAR_EXPIRY_NEWS_BUY_MAX_LEADER_VALUE = Decimal(
    os.getenv("NEAR_EXPIRY_NEWS_BUY_MAX_LEADER_VALUE", "25")
)
PROPORTIONAL_RISK_BUYBACK_WINDOW_SECONDS = int(
    os.getenv("PROPORTIONAL_RISK_BUYBACK_WINDOW_SECONDS", "600")
)
PROPORTIONAL_RISK_SMALL_BUYBACK_RATIO = Decimal(
    os.getenv("PROPORTIONAL_RISK_SMALL_BUYBACK_RATIO", "0.25")
)
CRYPTO_EXIT_RULE_MODE = os.getenv("CRYPTO_EXIT_RULE_MODE", "SHADOW").upper()
CRYPTO_EXIT_TAKE_PROFIT_PCT = Decimal(os.getenv("CRYPTO_EXIT_TAKE_PROFIT_PCT", "0.60"))
CRYPTO_EXIT_STOP_LOSS_PCT = Decimal(os.getenv("CRYPTO_EXIT_STOP_LOSS_PCT", "0.50"))
CRYPTO_EXIT_MIN_HOLD_SECONDS = int(os.getenv("CRYPTO_EXIT_MIN_HOLD_SECONDS", "20"))
CRYPTO_EXIT_NO_EXIT_LAST_SECONDS = int(os.getenv("CRYPTO_EXIT_NO_EXIT_LAST_SECONDS", "35"))

# Singleton PID lock to prevent multiple bridge instances from competing for the
# same browser profile and opening multiple Chrome windows.
PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".polymtrade-bridge.pid")


def _is_process_alive(pid: int) -> bool:
    """Return True if a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def acquire_singleton_lock() -> bool:
    """Check/create PID file. Return True if this instance may start."""
    current_pid = os.getpid()
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                existing_pid = int(f.read().strip())
            if existing_pid != current_pid and _is_process_alive(existing_pid):
                logger.error(
                    f"Another Polymtrade Bridge instance is already running (PID {existing_pid}). "
                    f"Refusing to start a second instance to avoid multiple Chrome windows."
                )
                return False
        except (ValueError, OSError) as e:
            logger.warning(f"Could not read PID file {PID_FILE}: {e}")
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(current_pid))
        return True
    except OSError as e:
        logger.error(f"Could not write PID file {PID_FILE}: {e}")
        return False


def release_singleton_lock():
    """Remove PID file on shutdown."""
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except OSError as e:
        logger.warning(f"Could not remove PID file {PID_FILE}: {e}")


class LeaderTradeSignal(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    event: str = "leader_trade"
    timestamp: int
    leader_id: Optional[int] = Field(None, alias="leaderId")
    leader_address: str = Field(..., alias="leaderAddress")
    leader_name: Optional[str] = Field(None, alias="leaderName")
    transaction_hash: str = Field(..., alias="transactionHash")
    model_candidate_id: Optional[str] = Field(None, alias="modelCandidateId")
    condition_id: str = Field(..., alias="conditionId")
    market_slug: Optional[str] = Field(None, alias="marketSlug")
    title: Optional[str] = None
    side: str
    outcome: Optional[str] = None
    outcome_index: Optional[int] = Field(None, alias="outcomeIndex")
    price: float
    size: float
    market_end_date: Optional[int] = Field(None, alias="marketEndDate")
    copy_trading_id: Optional[int] = Field(None, alias="copyTradingId")
    source: Optional[str] = None


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    market_slug: str
    side: str = "BUY"
    outcome: str
    amount_usdc: float = 1.0
    condition_id: Optional[str] = Field(None, alias="conditionId")
    size_shares: Optional[float] = Field(None, alias="sizeShares")
    outcome_index: Optional[int] = Field(None, alias="outcomeIndex")
    market_title: Optional[str] = Field(None, alias="marketTitle")
    external_trade_id: Optional[str] = Field(None, alias="externalTradeId")


class AuditReconciliationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    market_id: str = Field(..., alias="marketId")
    market_title: Optional[str] = Field(None, alias="marketTitle")
    outcome: str
    outcome_index: Optional[int] = Field(None, alias="outcomeIndex")
    status: str = "externally_closed"
    note: Optional[str] = None
    actor: str = "operator"


class AccountSelectRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    account_id: int = Field(..., alias="account_id")
    expected_wallet_address: str = Field(..., alias="expected_wallet_address")


# Global executor instance
executor: Optional[PolymtradeExecutor] = None
rule_engine: Optional[CopyTradingRuleEngine] = None
recorder: Optional[BridgeTradeRecorder] = None
position_ledger: Optional[PositionLedger] = None
portfolio_risk_client = PortfolioRiskClient()
_trade_lock = asyncio.Lock()
_portfolio_lock = asyncio.Lock()


def bridge_runtime_status() -> dict[str, Any]:
    return {
        "ready": executor.is_ready() if executor else False,
        "logged_in": executor.is_logged_in() if executor else False,
        "last_error": executor.last_error if executor else "executor not initialized",
        "copy_trading_account_id": rule_engine.active_account_id if rule_engine else None,
        "copy_trading_config_count": rule_engine.config_count if rule_engine else 0,
        "synced_at": executor.last_portfolio_synced_at if executor else None,
        "portfolio_risk_configured": bool(portfolio_risk_client.secret),
        "portfolio_risk_mode": portfolio_risk_client.enforcement_mode,
    }


async def ensure_login_state() -> bool:
    """Refresh stale login state when the browser page already has a session."""
    if not executor or not executor.is_ready():
        return False
    if executor.is_logged_in():
        return True
    try:
        return await executor.refresh_login_state()
    except Exception as e:
        logger.warning(f"Login state refresh failed: {e}")
        return False


async def require_logged_in():
    if not await ensure_login_state():
        raise HTTPException(status_code=401, detail="Not logged in")


def runtime_block_reasons(runtime_status: dict[str, Any]) -> list[str]:
    reasons = []
    if not runtime_status.get("ready"):
        reasons.append("executor_not_ready")
    if not runtime_status.get("logged_in"):
        reasons.append("not_logged_in")
    if runtime_status.get("copy_trading_account_id") in (None, "", 0):
        reasons.append("copy_trading_account_missing")
    if int(runtime_status.get("copy_trading_config_count") or 0) <= 0:
        reasons.append("copy_trading_config_empty")
    if runtime_status.get("last_error"):
        reasons.append("last_error_present")
    return reasons


def apply_runtime_status_to_audit_result(
    audit_result: dict[str, Any],
    runtime_status: dict[str, Any],
) -> dict[str, Any]:
    audit_result["runtime_status"] = runtime_status
    reasons = runtime_block_reasons(runtime_status)
    if not reasons:
        return audit_result

    previous_status = audit_result.get("monitor_status") or {}
    audit_result["monitor_status"] = {
        **previous_status,
        "status": "runtime_blocked",
        "message": f"Bridge runtime is not ready for copy trading: {', '.join(reasons)}.",
        "runtime_block_reasons": reasons,
    }
    return audit_result


@asynccontextmanager
async def lifespan(app: FastAPI):
    global executor, rule_engine, recorder, position_ledger

    if not acquire_singleton_lock():
        logger.error("Singleton lock not acquired, shutting down.")
        sys.exit(1)

    try:
        logger.info("Initializing Polymtrade executor...")
        executor = PolymtradeExecutor()
        await executor.start()
        logger.info("Polymtrade executor initialized")

        logger.info("Initializing copy-trading rule engine...")
        rule_engine = CopyTradingRuleEngine()
        try:
            if executor and executor.is_logged_in():
                wallet = await executor.get_wallet_address()
                if wallet:
                    detected_account = rule_engine.resolve_account_id_by_wallet(wallet)
                    env_account = CopyTradingRuleEngine.normalize_account_id(
                        os.getenv("COPY_TRADING_ACCOUNT_ID")
                    )
                    if detected_account:
                        if env_account is not None and detected_account != env_account:
                            logger.warning(
                                f"COPY_TRADING_ACCOUNT_ID mismatch: env={env_account}, "
                                f"detected={detected_account} for wallet {wallet}. "
                                f"Using detected account id."
                            )
                        elif env_account is None:
                            logger.info(
                                f"Using detected copy-trading account id {detected_account} "
                                f"for wallet {wallet}."
                            )
                        rule_engine.set_account_id(detected_account)
                    elif env_account:
                        logger.warning(
                            f"Could not resolve account id for wallet {wallet}; "
                            f"falling back to COPY_TRADING_ACCOUNT_ID={env_account}."
                        )
            rule_engine.refresh_if_needed()
        except Exception as e:
            logger.warning(f"Rule engine not available (DB may be unreachable): {e}")
        logger.info("Copy-trading rule engine initialized")

        logger.info("Initializing bridge trade recorder...")
        recorder = BridgeTradeRecorder()
        logger.info("Bridge trade recorder initialized")

        logger.info("Initializing position ledger...")
        position_ledger = PositionLedger()
        logger.info("Position ledger initialized")

        yield

    finally:
        logger.info("Shutting down Polymtrade executor...")
        if executor:
            async with _trade_lock:
                await executor.stop()
        logger.info("Polymtrade executor stopped")
        release_singleton_lock()


app = FastAPI(title="PolyHermes → Polymtrade Bridge", lifespan=lifespan)


@app.get("/health")
async def health():
    executor_ready = executor.is_ready() if executor else False
    if not executor_ready:
        raise HTTPException(
            status_code=503,
            detail={"status": "degraded", "executor_ready": False},
        )
    return {"status": "ok", "executor_ready": True}


@app.get("/status")
async def status():
    await ensure_login_state()
    return bridge_runtime_status()


@app.get("/metrics")
async def bridge_metrics():
    """Return in-memory bridge counters for observability."""
    return {
        "status": "ok",
        "metrics": metrics.to_dict(),
    }


@app.get("/debug/page")
async def debug_page():
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    return await executor.debug_info()


@app.get("/debug/screenshot")
async def debug_screenshot():
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    info = await executor.debug_info()
    if "error" in info:
        raise HTTPException(status_code=500, detail=info["error"])
    return {
        "url": info["url"],
        "title": info["title"],
        "screenshot_png_base64": info["screenshot_png_base64"],
    }


@app.post("/debug/refresh-login")
async def refresh_login():
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    logged_in = await executor.refresh_login_state()
    return {"logged_in": logged_in}


@app.get("/debug/search")
async def debug_search(q: str):
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    return await executor.search_markets(q)


@app.get("/debug/html")
async def debug_html():
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    return await executor.debug_html()


@app.get("/debug/inputs")
async def debug_inputs():
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    return await executor.debug_inputs()


@app.post("/debug/click")
async def debug_click(text: str):
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    return await executor.click_by_text(text)


@app.post("/debug/click-selector")
async def debug_click_selector(selector: str):
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    return await executor.click_selector(selector)


@app.get("/debug/navigate")
async def debug_navigate(url: str):
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    return await executor.navigate_to(url)


@app.post("/debug/eval")
async def debug_eval(request: dict):
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    expr = request.get("expression", "")
    if not expr:
        raise HTTPException(status_code=400, detail="expression required")
    return await executor.eval_js(expr)


@app.get("/account")
async def account_info():
    """Expose the currently logged-in Polymtrade account address.

    Used by PolyHermes backend to link this Bridge account as a read-only
    position-management account.

    This endpoint is called very frequently (account list, positions list,
    balance queries). To avoid blocking behind /portfolio scrapes, it first
    returns a cached wallet address if available; only if missing/stale does it
    navigate to /portfolio to refresh.
    """
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    await require_logged_in()

    try:
        # Fast path: return cached address without touching the page.
        cached = executor.cached_wallet_address
        if cached:
            return {
                "wallet_address": cached,
                "wallet_type": "magic",  # cached path cannot reliably infer wallet type
                "source": "cache",
            }

        active_account_id = rule_engine.active_account_id if rule_engine else None
        if active_account_id and rule_engine:
            db_wallet = await asyncio.to_thread(
                rule_engine.resolve_wallet_address_by_account_id,
                active_account_id,
            )
            if db_wallet:
                return {
                    "wallet_address": db_wallet,
                    "wallet_type": "magic",
                    "source": "account_db",
                }

        # Slow path: navigate to portfolio and refresh cache.
        async with _trade_lock:
            async with _portfolio_lock:
                address = await executor.get_wallet_address()
                text = ""
                if executor.page:
                    try:
                        text = await executor.page.inner_text("body", timeout=5000)
                    except Exception:
                        text = ""

                if not address:
                    # Fallback for older page states where get_wallet_address cannot
                    # parse the body after navigation but debug text still has a ref.
                    info = await executor.navigate_to("https://polym.trade/portfolio")
                    text = (info.get("text_sample", "") + " " + info.get("title", "")).strip()
                    ref_match = re.search(r'[?&]ref=(0x[a-fA-F0-9]{40})', text)
                    if ref_match:
                        address = ref_match.group(1).lower()
                    else:
                        addresses = re.findall(r'0x[a-fA-F0-9]{40}', text)
                        address = addresses[0].lower() if addresses else None

        if not address:
            raise HTTPException(status_code=404, detail="Wallet address not found in page")

        # If an email is visible on the page, assume Magic (Privy embedded wallet);
        # otherwise treat as a Safe/Web3 wallet.
        has_email = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}', text) is not None
        wallet_type = "magic" if has_email else "safe"

        return {
            "wallet_address": address.lower(),
            "wallet_type": wallet_type,
            "source": "page_text",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to extract account info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to extract account info: {e}")


@app.post("/account/select")
async def select_account(request: AccountSelectRequest):
    """Bind the current browser session to a PolyHermes account id.

    The Bridge has one persistent browser session. This endpoint intentionally
    does not log into another Magic wallet silently; it verifies the currently
    visible wallet first, then switches copy-trading config filtering.
    """
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    await require_logged_in()
    if not rule_engine:
        raise HTTPException(status_code=503, detail="Rule engine not initialized")
    if request.account_id <= 0:
        raise HTTPException(status_code=400, detail="account_id must be positive")

    account = await account_info()
    current_wallet = (account.get("wallet_address") or "").lower()
    expected_wallet = request.expected_wallet_address.lower()
    if current_wallet != expected_wallet:
        raise HTTPException(
            status_code=409,
            detail=(
                "Current Bridge wallet does not match selected account. "
                f"current={current_wallet}, expected={expected_wallet}"
            ),
        )

    rule_engine.set_account_id(request.account_id)
    rule_engine.refresh_if_needed()

    return {
        "success": True,
        "message": "Bridge current account selected",
        "account_id": request.account_id,
        "wallet_address": current_wallet,
        "copy_trading_account_id": rule_engine.active_account_id,
        "copy_trading_config_count": rule_engine.config_count,
    }


@app.get("/portfolio")
async def portfolio_positions():
    """Return the current open positions scraped from Polymtrade portfolio page.

    Used by PolyHermes backend to keep Bridge read-only account positions in sync
    with the actual Polymtrade holdings.
    """
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    await require_logged_in()

    metrics.portfolio_requests += 1
    wallet_address = None
    active_account_id = rule_engine.active_account_id if rule_engine else None
    if active_account_id and rule_engine:
        wallet_address = await asyncio.to_thread(
            rule_engine.resolve_wallet_address_by_account_id,
            active_account_id,
        )
    # Serialize with trades as well as other portfolio scrapes. The executor has
    # one active page pointer; navigating it during post-submit confirmation can
    # destroy the trade page context and create false FAILED records.
    async with _trade_lock:
        async with _portfolio_lock:
            result = await executor.fetch_portfolio_positions()
            available_balance = None
            for balance_attempt in range(3):
                available_balance = await executor._get_usdc_balance()
                if available_balance is not None:
                    break
                if balance_attempt < 2:
                    await asyncio.sleep(0.5)
    if "error" in result:
        metrics.portfolio_errors += 1
        raise HTTPException(status_code=500, detail=result["error"])
    result["crypto_exit_rule"] = _annotate_crypto_exit_shadow(result.get("positions") or [])
    result["wallet_address"] = wallet_address.lower() if wallet_address else None
    result["available_balance"] = available_balance
    return result


@app.get("/balance")
async def account_balance():
    """Return the current pUSD/USDC balance scraped from the logged-in page."""
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    await require_logged_in()

    async with _trade_lock:
        async with _portfolio_lock:
            balance = await executor._get_usdc_balance()
    return {"available_balance": balance, "synced_at": int(time.time() * 1000)}


@app.get("/audit")
async def reliability_audit(
    limit: int = Query(100, ge=1, le=500),
    since_ms: Optional[int] = Query(
        None,
        ge=0,
        description="Only include recent PENDING/FAILED rows created or updated at/after this timestamp.",
    ),
    ledger_limit: int = Query(1000, ge=1, le=5000),
    failure_limit: int = Query(20, ge=0, le=100),
    pending_timeout_ms: int = Query(120000, ge=1000),
    stale_mismatch_ms: int = Query(1800000, ge=1000),
    min_quantity_ratio: float = Query(0.5, ge=0.0, le=1.0),
    quantity_tolerance: float = Query(0.05, ge=0.0),
    portfolio_timeout: float = Query(90.0, ge=1.0, le=180.0),
):
    """Return read-only Bridge reliability audit metrics.

    This exposes the same checks as bridge_reliability_audit.py: PENDING
    timeouts, SUCCESS ledger vs live portfolio mismatches, unexpected live
    portfolio positions, FAILED error buckets, and next action candidates.
    SUCCESS mismatches older than stale_mismatch_ms are marked as
    historical/stale. It never places trades.
    """
    args = argparse.Namespace(
        limit=limit,
        since_ms=since_ms,
        ledger_limit=ledger_limit,
        failure_limit=failure_limit,
        pending_timeout_ms=pending_timeout_ms,
        stale_mismatch_ms=stale_mismatch_ms,
        reconciliation_file=str(reconciliation_file_path()),
        reconciliation_suggestion_limit=20,
        portfolio_url=os.getenv("BRIDGE_PORTFOLIO_URL", "http://127.0.0.1:8080/portfolio"),
        portfolio_timeout=portfolio_timeout,
        min_quantity_ratio=Decimal(str(min_quantity_ratio)),
        quantity_tolerance=Decimal(str(quantity_tolerance)),
        strict=False,
    )
    try:
        result = await asyncio.to_thread(run_bridge_reliability_audit, args)
        return apply_runtime_status_to_audit_result(result, bridge_runtime_status())
    except Exception as e:
        logger.error(f"Bridge reliability audit failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Bridge reliability audit failed: {e}")


@app.get("/audit/reconciliations")
async def audit_reconciliations():
    """Return local operator annotations used by /audit."""
    annotations = await asyncio.to_thread(load_reconciliations)
    return {
        "file": str(reconciliation_file_path()),
        "count": len(annotations),
        "annotations": annotations,
    }


@app.post("/audit/reconciliations")
async def upsert_audit_reconciliation(request: AuditReconciliationRequest):
    """Persist an operator reconciliation annotation for stale audit drift.

    This marks an audit key as accepted/external/manual-close evidence. It does
    not place trades or modify bridge_trade_record rows.
    """
    allowed_statuses = {"externally_closed", "manual_closed", "accepted_stale", "wrong_market_known"}
    status_value = request.status.strip().lower()
    if status_value not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {sorted(allowed_statuses)}",
        )

    key = reconciliation_key(
        bridge_id=os.getenv("BRIDGE_ID", "polymtrade-bridge"),
        market_id=request.market_id,
        market_title=request.market_title,
        outcome=request.outcome,
        outcome_index=request.outcome_index,
    )
    now_ms = int(time.time() * 1000)
    annotations = await asyncio.to_thread(load_reconciliations)
    annotations[key] = {
        "status": status_value,
        "note": request.note,
        "actor": request.actor,
        "market_id": request.market_id,
        "market_title": request.market_title,
        "outcome": request.outcome,
        "outcome_index": request.outcome_index,
        "reconciled_at": now_ms,
        "updated_at": now_ms,
    }
    file_path = await asyncio.to_thread(save_reconciliations, annotations)
    return {
        "status": "saved",
        "key": key,
        "file": str(file_path),
        "annotation": annotations[key],
    }


def _normalize_market_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_market_title(value: Any) -> str:
    text = str(value or "").strip().lower().replace("&", " and ")
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_condition_id(value: str) -> bool:
    return bool(re.fullmatch(r"0x[0-9a-f]{16,}|[0-9a-f]{32,}", value or ""))


def _normalize_outcome(value: Any) -> str:
    text = str(value or "").strip().lower()
    mapping = {
        "yes": "yes",
        "y": "yes",
        "是": "yes",
        "no": "no",
        "n": "no",
        "否": "no",
    }
    return mapping.get(text, text)


def _decimal_from_any(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0")


async def _get_live_position_quantity(
    *,
    market_id: str,
    market_title: Optional[str],
    outcome: Optional[str],
) -> Decimal:
    """Return current live portfolio quantity for a market/outcome."""
    if not executor or not executor.is_ready() or not await ensure_login_state():
        logger.warning("Live portfolio check skipped because executor is not ready/logged in")
        return Decimal("0")

    async with _portfolio_lock:
        portfolio = await executor.fetch_portfolio_positions()
    if "error" in portfolio:
        logger.warning(f"Live portfolio check failed: {portfolio.get('error')}")
        return Decimal("0")

    target_market_id = _normalize_market_id(market_id)
    target_title = _normalize_market_title(market_title)
    target_outcome = _normalize_outcome(outcome)
    total = Decimal("0")
    for pos in portfolio.get("positions") or []:
        pos_market_id = _normalize_market_id(pos.get("conditionId") or pos.get("marketId"))
        pos_title = _normalize_market_title(pos.get("marketTitle"))
        pos_market_slug = _normalize_market_id(pos.get("marketSlug"))
        pos_event_slug = _normalize_market_id(pos.get("eventSlug"))
        pos_outcome = _normalize_outcome(pos.get("side"))

        market_matches = False
        allow_title_fallback = True
        if target_market_id and _is_condition_id(target_market_id):
            allow_title_fallback = not pos_market_id
            if pos_market_id:
                market_matches = pos_market_id == target_market_id
            elif target_title and pos_title:
                market_matches = pos_title == target_title
        elif target_market_id:
            market_matches = (
                pos_market_id == target_market_id
                or pos_market_slug == target_market_id
                or pos_event_slug == target_market_id
            )
        if not market_matches and allow_title_fallback and target_title and pos_title:
            market_matches = pos_title == target_title

        if market_matches and pos_outcome == target_outcome:
            total += _decimal_from_any(pos.get("quantity"))
    return total


async def _wait_for_live_position_decrease(
    *,
    market_id: str,
    market_title: Optional[str],
    outcome: Optional[str],
    before_quantity: Decimal,
    poll_attempts: int = 8,
    poll_delay_seconds: float = 2.5,
) -> Decimal:
    """Wait until live portfolio quantity is lower after a SELL."""
    tolerance = Decimal("0.01")
    last_quantity = before_quantity
    for attempt in range(poll_attempts):
        if attempt > 0:
            await asyncio.sleep(poll_delay_seconds)
        last_quantity = await _get_live_position_quantity(
            market_id=market_id,
            market_title=market_title,
            outcome=outcome,
        )
        logger.info(
            "SELL post-submit portfolio check: "
            f"before={before_quantity}, after={last_quantity}, attempt={attempt + 1}/{poll_attempts}"
        )
        if last_quantity <= before_quantity - tolerance:
            return last_quantity

    raise RuntimeError(
        "SELL post-submit verification failed: live portfolio quantity did not decrease "
        f"(before={before_quantity}, after={last_quantity})"
    )


@app.post("/signal")
async def receive_signal(signal: LeaderTradeSignal, background_tasks: BackgroundTasks):
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")

    metrics.signals_received += 1
    logger.info(f"Received leader trade signal: {signal.side} {signal.outcome} @ {signal.market_slug}")

    # Execute asynchronously to avoid blocking the response
    background_tasks.add_task(handle_signal, signal)

    return {"status": "accepted", "signal": signal.model_dump(by_alias=True)}


@app.post("/execute")
async def execute_trade(request: ExecuteRequest, background_tasks: BackgroundTasks):
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    await require_logged_in()

    side_upper = request.side.upper()
    if side_upper not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="side must be BUY or SELL")

    external_trade_id = request.external_trade_id or f"manual-{uuid.uuid4()}"
    if len(external_trade_id) > 100 or not re.fullmatch(r"[A-Za-z0-9:_-]+", external_trade_id):
        raise HTTPException(status_code=400, detail="invalid external_trade_id")
    if recorder.exists(external_trade_id):
        return {
            "status": "duplicate",
            "record_id": None,
            "external_trade_id": external_trade_id,
            "request": request.model_dump(by_alias=True),
        }
    manual_payload = request.model_dump(by_alias=True)
    manual_payload["copyTradingAccountId"] = rule_engine.active_account_id if rule_engine else None
    manual_payload["copyTradingId"] = None
    manual_payload["portfolioRiskCorrelationId"] = f"bridge:{external_trade_id}:manual"

    # 记录 PENDING，后续由后台任务更新为 SUCCESS/FAILED
    record_id = recorder.record_pending(
        external_trade_id=external_trade_id,
        market_id=request.condition_id or request.market_slug,
        market_title=request.market_title or request.market_slug,
        side=side_upper,
        outcome=request.outcome,
        outcome_index=request.outcome_index,
        quantity=Decimal(str(request.size_shares)) if request.size_shares is not None else Decimal("0"),
        price=Decimal("0"),
        amount=Decimal(str(request.amount_usdc)) if side_upper == "BUY" else Decimal("0"),
        raw_payload=manual_payload,
    )

    background_tasks.add_task(
        _execute_and_record,
        record_id=record_id,
        request=request,
        external_trade_id=external_trade_id,
    )

    return {
        "status": "accepted",
        "record_id": record_id,
        "external_trade_id": external_trade_id,
        "request": request.model_dump(by_alias=True),
    }


async def _execute_and_record(record_id: int, request: ExecuteRequest, external_trade_id: str):
    """执行交易并更新 bridge_trade_record 状态。"""
    manual_risk_correlation = f"bridge:{external_trade_id}:manual"
    try:
        side_upper = request.side.upper()
        if side_upper == "BUY":
            precheck = await _evaluate_manual_buy_risk(request, external_trade_id, "precheck")
            if not precheck.execution_allowed:
                reason = f"Portfolio risk blocked manual BUY: {precheck.outcome or precheck.error}"
                recorder.update_status(record_id, "FAILED", error_message=reason)
                await _complete_manual_buy_risk(manual_risk_correlation, "FAILED")
                return
        before_quantity: Optional[Decimal] = None
        can_verify_live_sell = side_upper == "SELL" and bool(
            request.condition_id or request.market_title
        )

        async with _trade_lock:
            if can_verify_live_sell:
                before_quantity = await _get_live_position_quantity(
                    market_id=request.condition_id or "",
                    market_title=request.market_title,
                    outcome=request.outcome,
                )
                requested_quantity = (
                    Decimal(str(request.size_shares))
                    if request.size_shares is not None and request.size_shares > 0
                    else None
                )
                if requested_quantity is not None and before_quantity < requested_quantity:
                    raise RuntimeError(
                        "Live portfolio insufficient position, skipped "
                        f"(available={before_quantity}, required={requested_quantity})"
                    )
                if requested_quantity is None and before_quantity <= Decimal("0"):
                    raise RuntimeError(
                        "Live portfolio insufficient position, skipped "
                        f"(available={before_quantity}, required=full position)"
                    )
            elif side_upper == "SELL":
                logger.warning(
                    "Manual SELL live portfolio verification skipped because "
                    "condition_id and market_title are missing"
                )

            if side_upper == "BUY":
                final_risk = await _evaluate_manual_buy_risk(request, external_trade_id, "final")
                if not final_risk.execution_allowed:
                    raise RuntimeError(f"Portfolio risk blocked manual BUY: {final_risk.outcome or final_risk.error}")

            result = await executor.execute_trade(
                market_slug=request.market_slug,
                side=side_upper,
                outcome=request.outcome,
                amount_usdc=request.amount_usdc,
                condition_id=request.condition_id,
                size_shares=request.size_shares,
                market_title=request.market_title,
            )

            if can_verify_live_sell and before_quantity is not None:
                after_quantity = await _wait_for_live_position_decrease(
                    market_id=request.condition_id or "",
                    market_title=request.market_title,
                    outcome=request.outcome,
                    before_quantity=before_quantity,
                )
                logger.info(
                    f"Manual SELL verified by live portfolio decrease: "
                    f"before={before_quantity}, after={after_quantity}"
                )

        logger.info(f"Manual trade executed: {external_trade_id}, result={result}")
        recorder.update_status(record_id, "SUCCESS")
        if side_upper == "BUY":
            await _complete_manual_buy_risk(manual_risk_correlation, "SUCCESS")
    except Exception as e:
        logger.error(f"Manual trade failed: {external_trade_id}, error={e}", exc_info=True)
        recorder.update_status(record_id, "FAILED", error_message=str(e))
        if request.side.upper() == "BUY":
            await _complete_manual_buy_risk(manual_risk_correlation, "FAILED")


async def _evaluate_manual_buy_risk(
    request: ExecuteRequest,
    external_trade_id: str,
    stage: str,
) -> PortfolioRiskCheck:
    account_id = rule_engine.active_account_id if rule_engine else None
    if not account_id:
        return PortfolioRiskCheck(
            available=False,
            execution_allowed=portfolio_risk_client.enforcement_mode != "ENFORCED",
            error="manual BUY has no active account id",
        )
    correlation_id = f"bridge:{external_trade_id}:manual"
    return await portfolio_risk_client.evaluate_buy({
        "accountId": account_id,
        "side": "BUY",
        "amount": str(request.amount_usdc),
        "marketId": request.condition_id or request.market_slug,
        "marketTitle": request.market_title,
        "category": infer_market_category(request.market_title),
        "requestId": f"{correlation_id}:{stage}",
        "correlationId": correlation_id,
        "stage": stage.upper(),
    })


async def _complete_manual_buy_risk(correlation_id: str, status: str):
    result = await portfolio_risk_client.complete(correlation_id, status)
    if not result.available:
        logger.warning("Manual portfolio risk completion failed: correlation_id=%s error=%s", correlation_id, result.error)
    return result


def _record_failed_signal(
    signal: LeaderTradeSignal,
    cfg,
    side: str,
    quantity: Optional[Decimal],
    price: Decimal,
    amount: Optional[Decimal],
    reason: str,
):
    """Persist a skipped/filtered signal so the UI can explain why it did not trade."""
    if not recorder:
        return
    try:
        skip_id = recorder.record_pending(
            external_trade_id=signal.transaction_hash,
            market_id=signal.condition_id or signal.market_slug or "",
            market_title=signal.title,
            side=side,
            outcome=signal.outcome,
            outcome_index=signal.outcome_index,
            quantity=quantity or Decimal("0"),
            price=price,
            amount=amount or Decimal("0"),
            raw_payload=_execution_raw_payload(signal, cfg),
        )
        recorder.update_status(skip_id, "FAILED", reason)
    except Exception as rec_err:
        logger.warning(f"Failed to record skipped signal: {rec_err}")


async def _evaluate_portfolio_buy_risk(
    cfg,
    signal: LeaderTradeSignal,
    amount: Decimal,
    stage: str,
) -> PortfolioRiskCheck:
    correlation_id = f"bridge:{signal.transaction_hash}:{cfg.id}"
    request_id = f"{correlation_id}:{stage}"
    result = await portfolio_risk_client.evaluate_buy({
        "accountId": cfg.account_id,
        "modelCandidateId": signal.model_candidate_id,
        "side": "BUY",
        "amount": str(amount),
        "marketId": signal.condition_id or signal.market_slug,
        "marketTitle": signal.title,
        "leaderAddress": signal.leader_address,
        "category": infer_market_category(signal.title),
        "requestId": request_id,
        "correlationId": correlation_id,
        "stage": stage.upper(),
    })
    metrics.portfolio_risk_checks += 1
    if result.available:
        if result.outcome == "WOULD_BLOCK":
            metrics.portfolio_risk_would_block += 1
        if not result.execution_allowed:
            metrics.portfolio_risk_denied += 1
        logger.info(
            "Portfolio risk %s: config=%s request_id=%s decision_id=%s mode=%s "
            "outcome=%s execution_allowed=%s",
            stage,
            cfg.id,
            request_id,
            result.decision_id,
            result.mode,
            result.outcome,
            result.execution_allowed,
        )
    else:
        metrics.portfolio_risk_unavailable += 1
        logger.warning(
            "Portfolio risk %s unavailable: config=%s request_id=%s error=%s "
            "execution_allowed=%s",
            stage,
            cfg.id,
            request_id,
            result.error,
            result.execution_allowed,
        )
    return result


async def _complete_portfolio_buy_risk(cfg, signal: LeaderTradeSignal, status: str):
    correlation_id = f"bridge:{signal.transaction_hash}:{cfg.id}"
    result = await portfolio_risk_client.complete(correlation_id, status)
    if result.available:
        logger.info("Portfolio risk reservation completed: correlation_id=%s status=%s", correlation_id, result.status)
    else:
        logger.warning("Portfolio risk reservation completion failed: correlation_id=%s error=%s", correlation_id, result.error)
    return result


def _execution_raw_payload(signal: LeaderTradeSignal, cfg=None) -> dict[str, Any]:
    payload = signal.model_dump(by_alias=True)
    payload["copyTradingAccountId"] = getattr(cfg, "account_id", None) or (rule_engine.active_account_id if rule_engine else None)
    payload["copyTradingId"] = getattr(cfg, "id", None) or signal.copy_trading_id
    config_id = payload["copyTradingId"]
    payload["portfolioRiskCorrelationId"] = f"bridge:{signal.transaction_hash}:{config_id}" if config_id is not None else None
    return payload


def _proportional_risk_small_buyback_reason(
    cfg,
    signal: LeaderTradeSignal,
    side: str,
    leader_size: Decimal,
    now_ms: Optional[int] = None,
) -> Optional[str]:
    """Skip tiny same-outcome BUY backs shortly after a leader-side SELL."""
    if cfg.copy_mode != COPY_MODE_PROPORTIONAL_RISK or side.upper() != "BUY" or not recorder:
        return None
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    since_ms = now - PROPORTIONAL_RISK_BUYBACK_WINDOW_SECONDS * 1000
    recent_sell_size = recorder.recent_leader_sell_size(
        market_id=signal.condition_id or signal.market_slug or "",
        market_slug=signal.market_slug,
        outcome=signal.outcome,
        outcome_index=signal.outcome_index,
        leader_address=signal.leader_address,
        since_ms=since_ms,
    )
    if recent_sell_size <= 0:
        recent_sell_size = recorder.recent_success_sell_size(
            market_id=signal.condition_id or signal.market_slug or "",
            market_slug=signal.market_slug,
            outcome=signal.outcome,
            outcome_index=signal.outcome_index,
            leader_address=signal.leader_address,
            since_ms=since_ms,
        )
    if recent_sell_size <= 0:
        return None
    buyback_ratio = leader_size / recent_sell_size
    if buyback_ratio < PROPORTIONAL_RISK_SMALL_BUYBACK_RATIO:
        return (
            "Small buyback after recent SELL, skipped "
            f"(buy_size={leader_size}, recent_sell_size={recent_sell_size}, "
            f"ratio={buyback_ratio:.4f}, threshold={PROPORTIONAL_RISK_SMALL_BUYBACK_RATIO})"
        )
    return None


async def handle_signal(signal: LeaderTradeSignal):
    try:
        if not signal.market_slug:
            logger.warning(f"Signal missing market_slug, cannot execute: {signal.transaction_hash}")
            return

        # Idempotency: skip if this external trade has already been processed
        if recorder and recorder.exists(signal.transaction_hash):
            logger.debug(f"Signal {signal.transaction_hash} already processed, skipping")
            return

        if not rule_engine:
            logger.warning("Copy-trading rule engine not initialized, skipping signal")
            return

        from decimal import Decimal

        price_dec = Decimal(str(signal.price))
        matching = rule_engine.get_matching_configs(
            trader_address=signal.leader_address,
            side=signal.side,
            title=signal.title or "",
            price=price_dec,
            signal_timestamp_ms=signal.timestamp,
        )

        if not matching:
            logger.info(f"No copy-trading config matches leader {signal.leader_address}, skipping")
            return

        side_upper = signal.side.upper()
        has_executable_config = any(reason is None for _, reason in matching)
        filtered_signal_recorded = False

        for cfg, reason in matching:
            if reason:
                metrics.signals_filtered += 1
                logger.info(f"Config {cfg.id} filtered for {signal.transaction_hash}: {reason}")
                if not has_executable_config and not filtered_signal_recorded:
                    _record_failed_signal(
                        signal=signal,
                        cfg=cfg,
                        side=side_upper,
                        quantity=Decimal("0"),
                        price=price_dec,
                        amount=Decimal("0"),
                        reason=reason,
                    )
                    filtered_signal_recorded = True
                continue

            metrics.signals_executed += 1
            if side_upper == "BUY":
                metrics.trades_buy_total += 1
            else:
                metrics.trades_sell_total += 1

            await rule_engine.sleep_delay(cfg)

            leader_size_dec = Decimal(str(signal.size))
            quantity: Optional[Decimal] = None
            amount: Optional[Decimal] = None

            if side_upper == "BUY":
                amount = rule_engine.compute_buy_quantity(
                    cfg, price_dec, leader_size_dec
                )
                if amount is None:
                    reason = rule_engine.buy_skip_reason(cfg, price_dec, leader_size_dec) or "BUY quantity filtered"
                    logger.info(f"Config {cfg.id}: {reason}")
                    _record_failed_signal(
                        signal=signal,
                        cfg=cfg,
                        side=side_upper,
                        quantity=Decimal("0"),
                        price=price_dec,
                        amount=Decimal("0"),
                        reason=reason,
                    )
                    continue
                quantity = amount / price_dec
                tail_risk_reason = _tail_risk_low_price_buy_reason(side_upper, price_dec)
                if tail_risk_reason:
                    logger.info(
                        f"Config {cfg.id}: BUY skipped for {signal.transaction_hash}: "
                        f"{tail_risk_reason}"
                    )
                    _record_failed_signal(
                        signal=signal,
                        cfg=cfg,
                        side=side_upper,
                        quantity=quantity,
                        price=price_dec,
                        amount=amount,
                        reason=tail_risk_reason,
                    )
                    continue
                high_confidence_reason = _high_confidence_buy_reason(
                    side=side_upper,
                    price=price_dec,
                    title=signal.title,
                    market_slug=signal.market_slug,
                )
                if high_confidence_reason:
                    logger.info(
                        f"Config {cfg.id}: BUY skipped for {signal.transaction_hash}: "
                        f"{high_confidence_reason}"
                    )
                    _record_failed_signal(
                        signal=signal,
                        cfg=cfg,
                        side=side_upper,
                        quantity=quantity,
                        price=price_dec,
                        amount=amount,
                        reason=high_confidence_reason,
                    )
                    continue
                repeat_buy_reason = _generic_repeat_buy_reason(
                    signal=signal,
                    side=side_upper,
                )
                if repeat_buy_reason:
                    logger.info(
                        f"Config {cfg.id}: BUY skipped for {signal.transaction_hash}: "
                        f"{repeat_buy_reason}"
                    )
                    _record_failed_signal(
                        signal=signal,
                        cfg=cfg,
                        side=side_upper,
                        quantity=quantity,
                        price=price_dec,
                        amount=amount,
                        reason=repeat_buy_reason,
                    )
                    continue
                near_expiry_reason = _near_expiry_news_buy_reason(
                    signal=signal,
                    side=side_upper,
                    price=price_dec,
                    leader_size=leader_size_dec,
                )
                if near_expiry_reason:
                    logger.info(
                        f"Config {cfg.id}: BUY skipped for {signal.transaction_hash}: "
                        f"{near_expiry_reason}"
                    )
                    _record_failed_signal(
                        signal=signal,
                        cfg=cfg,
                        side=side_upper,
                        quantity=quantity,
                        price=price_dec,
                        amount=amount,
                        reason=near_expiry_reason,
                    )
                    continue
                event_activity_reason = _leader_event_activity_buy_reason(
                    signal=signal,
                    side=side_upper,
                )
                if event_activity_reason:
                    logger.info(
                        f"Config {cfg.id}: BUY skipped for {signal.transaction_hash}: "
                        f"{event_activity_reason}"
                    )
                    _record_failed_signal(
                        signal=signal,
                        cfg=cfg,
                        side=side_upper,
                        quantity=quantity,
                        price=price_dec,
                        amount=amount,
                        reason=event_activity_reason,
                    )
                    continue
                price_band_reason = _short_cycle_price_band_buy_reason(
                    market_slug=signal.market_slug,
                    side=side_upper,
                    price=price_dec,
                )
                if price_band_reason:
                    logger.info(
                        f"Config {cfg.id}: BUY skipped for {signal.transaction_hash}: "
                        f"{price_band_reason}"
                    )
                    if recorder:
                        try:
                            skip_id = recorder.record_pending(
                                external_trade_id=signal.transaction_hash,
                                market_id=signal.condition_id or signal.market_slug or "",
                                market_title=signal.title,
                                side=side_upper,
                                outcome=signal.outcome,
                                outcome_index=signal.outcome_index,
                                quantity=quantity,
                                price=price_dec,
                                amount=amount,
                                raw_payload=_execution_raw_payload(signal, cfg),
                            )
                            recorder.update_status(skip_id, "FAILED", price_band_reason)
                        except Exception as rec_err:
                            logger.warning(f"Failed to record BTC 5M price-band BUY skip: {rec_err}")
                    continue
                global_duplicate_reason = _short_cycle_global_buy_reason(
                    market_slug=signal.market_slug,
                    market_id=signal.condition_id or signal.market_slug or "",
                )
                if global_duplicate_reason:
                    logger.info(
                        f"Config {cfg.id}: BUY skipped for {signal.transaction_hash}: "
                        f"{global_duplicate_reason}"
                    )
                    if recorder:
                        try:
                            skip_id = recorder.record_pending(
                                external_trade_id=signal.transaction_hash,
                                market_id=signal.condition_id or signal.market_slug or "",
                                market_title=signal.title,
                                side=side_upper,
                                outcome=signal.outcome,
                                outcome_index=signal.outcome_index,
                                quantity=quantity,
                                price=price_dec,
                                amount=amount,
                                raw_payload=_execution_raw_payload(signal, cfg),
                            )
                            recorder.update_status(skip_id, "FAILED", global_duplicate_reason)
                        except Exception as rec_err:
                            logger.warning(f"Failed to record global BTC 5M BUY skip: {rec_err}")
                    continue
                daily_limit_reason = _short_cycle_daily_limit_buy_reason(
                    market_slug=signal.market_slug,
                    side=side_upper,
                    amount=amount,
                )
                if daily_limit_reason:
                    logger.info(
                        f"Config {cfg.id}: BUY skipped for {signal.transaction_hash}: "
                        f"{daily_limit_reason}"
                    )
                    if recorder:
                        try:
                            skip_id = recorder.record_pending(
                                external_trade_id=signal.transaction_hash,
                                market_id=signal.condition_id or signal.market_slug or "",
                                market_title=signal.title,
                                side=side_upper,
                                outcome=signal.outcome,
                                outcome_index=signal.outcome_index,
                                quantity=quantity,
                                price=price_dec,
                                amount=amount,
                                raw_payload=_execution_raw_payload(signal, cfg),
                            )
                            recorder.update_status(skip_id, "FAILED", daily_limit_reason)
                        except Exception as rec_err:
                            logger.warning(f"Failed to record BTC 5M daily-limit BUY skip: {rec_err}")
                    continue
                duplicate_reason = _short_cycle_duplicate_buy_reason(
                    market_slug=signal.market_slug,
                    market_id=signal.condition_id or signal.market_slug or "",
                    leader_address=signal.leader_address,
                )
                if duplicate_reason:
                    logger.info(
                        f"Config {cfg.id}: BUY skipped for {signal.transaction_hash}: "
                        f"{duplicate_reason}"
                    )
                    if recorder:
                        try:
                            skip_id = recorder.record_pending(
                                external_trade_id=signal.transaction_hash,
                                market_id=signal.condition_id or signal.market_slug or "",
                                market_title=signal.title,
                                side=side_upper,
                                outcome=signal.outcome,
                                outcome_index=signal.outcome_index,
                                quantity=quantity,
                                price=price_dec,
                                amount=amount,
                                raw_payload=_execution_raw_payload(signal, cfg),
                            )
                            recorder.update_status(skip_id, "FAILED", duplicate_reason)
                        except Exception as rec_err:
                            logger.warning(f"Failed to record duplicate BUY skip: {rec_err}")
                    continue
                buyback_reason = _proportional_risk_small_buyback_reason(
                    cfg=cfg,
                    signal=signal,
                    side=side_upper,
                    leader_size=leader_size_dec,
                )
                if buyback_reason:
                    logger.info(
                        f"Config {cfg.id}: BUY skipped for {signal.transaction_hash}: "
                        f"{buyback_reason}"
                    )
                    _record_failed_signal(
                        signal=signal,
                        cfg=cfg,
                        side=side_upper,
                        quantity=quantity,
                        price=price_dec,
                        amount=amount,
                        reason=buyback_reason,
                    )
                    continue
            else:
                quantity = rule_engine.compute_sell_shares(
                    cfg, price_dec, leader_size_dec
                )
                if quantity is None:
                    reason = rule_engine.sell_skip_reason(cfg, price_dec, leader_size_dec) or "SELL quantity filtered"
                    logger.info(f"Config {cfg.id}: {reason}")
                    _record_failed_signal(
                        signal=signal,
                        cfg=cfg,
                        side=side_upper,
                        quantity=Decimal("0"),
                        price=price_dec,
                        amount=Decimal("0"),
                        reason=reason,
                    )
                    continue
                amount = quantity * price_dec
                is_proportional_risk = cfg.copy_mode == COPY_MODE_PROPORTIONAL_RISK
                ledger_miss_live_fallback = False

                if is_proportional_risk and position_ledger:
                    local_quantity = position_ledger.get_net_quantity(
                        market_id=signal.condition_id or signal.market_slug or "",
                        outcome=signal.outcome,
                        outcome_index=signal.outcome_index,
                    )
                    if local_quantity <= 0:
                        ledger_miss_live_fallback = True
                        logger.warning(
                            f"Config {cfg.id}: local ledger has no proportional-risk SELL position "
                            f"for {signal.transaction_hash}; checking live portfolio before skipping"
                        )
                    elif local_quantity < quantity:
                        logger.info(
                            f"Config {cfg.id}: capping proportional-risk SELL to local ledger "
                            f"position, desired={quantity}, available={local_quantity}"
                        )
                        quantity = local_quantity
                        amount = quantity * price_dec

                # SELL pre-check: ensure we have a corresponding position
                if (
                    not is_proportional_risk
                    and position_ledger
                    and not position_ledger.has_sufficient_position(
                        market_id=signal.condition_id or signal.market_slug or "",
                        outcome=signal.outcome,
                        outcome_index=signal.outcome_index,
                        sell_quantity=quantity,
                    )
                ):
                    logger.info(
                        f"Config {cfg.id}: SELL skipped for {signal.transaction_hash} "
                        f"due to insufficient position"
                    )
                    # Record the skip so it is visible in the UI
                    if recorder:
                        try:
                            skip_id = recorder.record_pending(
                                external_trade_id=signal.transaction_hash,
                                market_id=signal.condition_id or signal.market_slug or "",
                                market_title=signal.title,
                                side=side_upper,
                                outcome=signal.outcome,
                                outcome_index=signal.outcome_index,
                                quantity=quantity,
                                price=price_dec,
                                amount=amount,
                                raw_payload=_execution_raw_payload(signal, cfg),
                            )
                            recorder.update_status(
                                skip_id,
                                "FAILED",
                                "Insufficient position, skipped",
                            )
                        except Exception as rec_err:
                            logger.warning(f"Failed to record skipped SELL: {rec_err}")
                    continue

                # Live portfolio check: if our cached/ledger quantity overestimates
                # the actual holdings, sell what we actually have instead of skipping.
                live_quantity = await _get_live_position_quantity(
                    market_id=signal.condition_id or signal.market_slug or "",
                    market_title=signal.title,
                    outcome=signal.outcome,
                )
                if live_quantity <= 0:
                    logger.info(
                        f"Config {cfg.id}: SELL skipped for {signal.transaction_hash} "
                        f"because live portfolio has no matching position"
                    )
                    if recorder:
                        try:
                            skip_id = recorder.record_pending(
                                external_trade_id=signal.transaction_hash,
                                market_id=signal.condition_id or signal.market_slug or "",
                                market_title=signal.title,
                                side=side_upper,
                                outcome=signal.outcome,
                                outcome_index=signal.outcome_index,
                                quantity=quantity,
                                price=price_dec,
                                amount=amount,
                                raw_payload=_execution_raw_payload(signal, cfg),
                            )
                            recorder.update_status(
                                skip_id,
                                "FAILED",
                                "Live portfolio insufficient position, skipped "
                                f"(available={live_quantity}, required={quantity})",
                            )
                        except Exception as rec_err:
                            logger.warning(f"Failed to record live skipped SELL: {rec_err}")
                    continue
                if live_quantity < quantity:
                    logger.warning(
                        f"Config {cfg.id}: Adjusting SELL quantity from {quantity} to {live_quantity} "
                        f"due to live portfolio mismatch"
                    )
                    quantity = live_quantity
                    amount = quantity * price_dec
                elif ledger_miss_live_fallback:
                    logger.warning(
                        f"Config {cfg.id}: allowing proportional-risk SELL from live portfolio "
                        f"fallback despite missing local ledger, live_available={live_quantity}, "
                        f"sell_quantity={quantity}"
                    )

            if side_upper == "BUY":
                precheck_risk = await _evaluate_portfolio_buy_risk(
                    cfg=cfg,
                    signal=signal,
                    amount=amount,
                    stage="precheck",
                )
                if not precheck_risk.execution_allowed:
                    reason = f"Portfolio risk blocked BUY: {precheck_risk.outcome or precheck_risk.error}"
                    _record_failed_signal(signal, cfg, side_upper, quantity, price_dec, amount, reason)
                    await _complete_portfolio_buy_risk(cfg, signal, "FAILED")
                    continue

            record_id = None
            if recorder:
                try:
                    record_id = recorder.record_pending(
                        external_trade_id=signal.transaction_hash,
                        market_id=signal.condition_id or signal.market_slug or "",
                        market_title=signal.title,
                        side=side_upper,
                        outcome=signal.outcome,
                        outcome_index=signal.outcome_index,
                        quantity=quantity,
                        price=price_dec,
                        amount=amount,
                        raw_payload=_execution_raw_payload(signal, cfg),
                    )
                except Exception as rec_err:
                    logger.warning(f"Failed to record pending trade: {rec_err}")

            logger.info(
                f"Executing {side_upper} for config {cfg.id}: {signal.market_slug} "
                f"{signal.outcome} qty={quantity} amount=${amount}"
            )

            try:
                async with _trade_lock:
                    stale_reason = _short_cycle_market_stale_reason(signal.market_slug, side_upper)
                    if stale_reason:
                        logger.info(
                            f"Config {cfg.id}: skipping {signal.transaction_hash} before UI execution: "
                            f"{stale_reason}"
                        )
                        if record_id and recorder:
                            recorder.update_status(record_id, "FAILED", stale_reason)
                        if side_upper == "BUY":
                            await _complete_portfolio_buy_risk(cfg, signal, "FAILED")
                        continue
                    if side_upper == "BUY":
                        final_risk = await _evaluate_portfolio_buy_risk(
                            cfg=cfg,
                            signal=signal,
                            amount=amount,
                            stage="final",
                        )
                        if not final_risk.execution_allowed:
                            reason = f"Portfolio risk blocked BUY: {final_risk.outcome or final_risk.error}"
                            logger.warning("Config %s: %s", cfg.id, reason)
                            if record_id and recorder:
                                recorder.update_status(record_id, "FAILED", reason)
                            await _complete_portfolio_buy_risk(cfg, signal, "FAILED")
                            continue
                        await executor.execute_trade(
                            market_slug=signal.market_slug,
                            side="BUY",
                            outcome=signal.outcome or "Yes",
                            amount_usdc=float(amount),
                            condition_id=signal.condition_id,
                            market_title=signal.title,
                        )
                    else:
                        result = await executor.execute_trade(
                            market_slug=signal.market_slug,
                            side="SELL",
                            outcome=signal.outcome or "Yes",
                            amount_usdc=0.0,
                            condition_id=signal.condition_id,
                            size_shares=float(quantity),
                            market_title=signal.title,
                        )
                        # Best-effort live portfolio decrease check. We do not fail the
                        # trade here because Polymtrade can take a while to reflect the
                        # sell, and failing would create false-negative FAILED records.
                        try:
                            after_quantity = await _wait_for_live_position_decrease(
                                market_id=signal.condition_id or signal.market_slug or "",
                                market_title=signal.title,
                                outcome=signal.outcome,
                                before_quantity=live_quantity,
                            )
                            logger.info(
                                f"SELL verified by live portfolio decrease: "
                                f"before={live_quantity}, after={after_quantity}"
                            )
                        except RuntimeError as verify_err:
                            logger.warning(
                                f"SELL live portfolio verification did not confirm decrease, "
                                f"but trade was submitted. executor_verified={result.get('verified')} "
                                f"error={verify_err}"
                            )
                if record_id and recorder:
                    recorder.update_status(record_id, "SUCCESS")
                if side_upper == "BUY":
                    metrics.trades_buy_success += 1
                    await _complete_portfolio_buy_risk(cfg, signal, "SUCCESS")
                else:
                    metrics.trades_sell_success += 1
            except Exception as exec_err:
                logger.exception(f"Trade execution failed for config {cfg.id}: {exec_err}")
                metrics.signals_failed += 1
                err_msg = str(exec_err).lower()
                if side_upper == "BUY":
                    metrics.trades_buy_failed += 1
                    await _complete_portfolio_buy_risk(cfg, signal, "FAILED")
                    if "outcome" in err_msg:
                        metrics.outcome_selection_failures += 1
                    if "enter trade amount" in err_msg:
                        metrics.amount_input_failures += 1
                else:
                    metrics.trades_sell_failed += 1
                if record_id and recorder:
                    recorder.update_status(record_id, "FAILED", str(exec_err))
    except Exception as e:
        logger.exception(f"Failed to handle signal: {e}")


def _short_cycle_market_stale_reason(
    market_slug: Optional[str],
    side: str,
    now_seconds: Optional[float] = None,
) -> Optional[str]:
    """Return a skip reason when a short-cycle market is too close to close."""
    if side.upper() != "BUY" or not market_slug:
        return None
    match = re.search(r"(btc|eth|xrp|sol|doge|bnb)-updown-5m-(\d{10})", market_slug)
    if not match:
        return None

    asset = match.group(1)
    started_at = int(match.group(2))
    market_close_at = started_at + BTC_UPDOWN_5M_SECONDS
    now = now_seconds if now_seconds is not None else time.time()
    buffer_seconds = (
        BTC_UPDOWN_STALE_BUFFER_SECONDS
        if asset == "btc"
        else CRYPTO_UPDOWN_STALE_BUFFER_SECONDS
    )
    cutoff = market_close_at - buffer_seconds
    if now >= cutoff:
        seconds_to_close = market_close_at - now
        return (
            "Short-cycle market stale or closing soon, skipped "
            f"(seconds_to_close={seconds_to_close:.1f}, buffer={buffer_seconds}s)"
        )
    return None


def _tail_risk_low_price_buy_reason(side: str, price: Decimal) -> Optional[str]:
    """Return a skip reason for low-price tail-risk BUYs."""
    if side.upper() != "BUY":
        return None
    if price < TAIL_RISK_MIN_BUY_PRICE:
        return (
            "Low-price tail-risk BUY skipped: "
            f"price={price}, min={TAIL_RISK_MIN_BUY_PRICE}"
        )
    return None


def _is_crypto_market(title: Optional[str], market_slug: Optional[str] = None) -> bool:
    if infer_market_category(title) == "crypto":
        return True
    return bool(market_slug and re.search(r"(btc|eth|xrp|sol|doge|bnb)-updown-", market_slug, re.IGNORECASE))


def _is_crypto_5m_market(market_slug: Optional[str], market_title: Optional[str] = None) -> bool:
    raw = " ".join(part for part in [market_slug, market_title] if part).lower()
    return bool(re.search(r"(btc|eth|xrp|sol|doge|bnb)-updown-5m-\d{10}", raw))


def _crypto_5m_market_close_seconds(market_slug: Optional[str]) -> Optional[int]:
    if not market_slug:
        return None
    match = re.search(r"(btc|eth|xrp|sol|doge|bnb)-updown-5m-(\d{10})", market_slug.lower())
    if not match:
        return None
    return int(match.group(2)) + BTC_UPDOWN_5M_SECONDS


def _crypto_exit_shadow_decision(
    *,
    market_slug: Optional[str],
    market_title: Optional[str],
    entry_price: Decimal,
    current_price: Decimal,
    entry_created_at_ms: Optional[int],
    now_seconds: Optional[float] = None,
) -> Optional[dict]:
    """Return a shadow take-profit/stop-loss decision for crypto 5m positions."""
    if not _is_crypto_5m_market(market_slug, market_title):
        return None
    if entry_price <= 0 or current_price <= 0:
        return None

    now = now_seconds if now_seconds is not None else time.time()
    age_seconds = None
    if entry_created_at_ms:
        age_seconds = max(0, now - (int(entry_created_at_ms) / 1000))

    close_seconds = _crypto_5m_market_close_seconds(market_slug)
    seconds_to_close = None
    if close_seconds is not None:
        seconds_to_close = close_seconds - now

    take_profit_price = entry_price * (Decimal("1") + CRYPTO_EXIT_TAKE_PROFIT_PCT)
    stop_loss_price = entry_price * (Decimal("1") - CRYPTO_EXIT_STOP_LOSS_PCT)
    pnl_pct = (current_price - entry_price) / entry_price

    blocked_reason = None
    if age_seconds is not None and age_seconds < CRYPTO_EXIT_MIN_HOLD_SECONDS:
        blocked_reason = f"min_hold_seconds={CRYPTO_EXIT_MIN_HOLD_SECONDS}"
    elif seconds_to_close is not None and seconds_to_close <= CRYPTO_EXIT_NO_EXIT_LAST_SECONDS:
        blocked_reason = f"no_exit_last_seconds={CRYPTO_EXIT_NO_EXIT_LAST_SECONDS}"

    action = "HOLD"
    trigger = None
    if blocked_reason is None:
        if current_price >= take_profit_price:
            action = "TAKE_PROFIT"
            trigger = "take_profit"
        elif current_price <= stop_loss_price:
            action = "STOP_LOSS"
            trigger = "stop_loss"

    return {
        "mode": CRYPTO_EXIT_RULE_MODE,
        "action": action,
        "trigger": trigger,
        "entry_price": str(entry_price),
        "current_price": str(current_price),
        "pnl_pct": str(pnl_pct),
        "take_profit_price": str(take_profit_price),
        "stop_loss_price": str(stop_loss_price),
        "take_profit_pct": str(CRYPTO_EXIT_TAKE_PROFIT_PCT),
        "stop_loss_pct": str(CRYPTO_EXIT_STOP_LOSS_PCT),
        "age_seconds": float(age_seconds) if age_seconds is not None else None,
        "seconds_to_close": float(seconds_to_close) if seconds_to_close is not None else None,
        "blocked_reason": blocked_reason,
    }


def _annotate_crypto_exit_shadow(positions: list[dict]) -> dict:
    """Annotate live portfolio positions with crypto 5m TP/SL shadow decisions."""
    summary = {
        "mode": CRYPTO_EXIT_RULE_MODE,
        "take_profit_pct": str(CRYPTO_EXIT_TAKE_PROFIT_PCT),
        "stop_loss_pct": str(CRYPTO_EXIT_STOP_LOSS_PCT),
        "evaluated": 0,
        "take_profit": 0,
        "stop_loss": 0,
    }
    if not position_ledger:
        return summary

    for pos in positions:
        market_slug = pos.get("marketSlug")
        market_title = pos.get("marketTitle")
        if not _is_crypto_5m_market(market_slug, market_title):
            continue
        try:
            quantity = Decimal(str(pos.get("quantity") or "0"))
            current_value = Decimal(str(pos.get("currentValue") or "0"))
        except Exception:
            continue
        if quantity <= 0 or current_value <= 0:
            continue

        current_price = current_value / quantity
        outcome = pos.get("side")
        entry = position_ledger.latest_success_buy_entry(
            market_id=pos.get("conditionId") or market_slug,
            market_slug=market_slug,
            market_title=market_title,
            outcome=outcome,
        )
        if not entry:
            continue

        entry_price = Decimal(str(entry.get("price") or "0"))
        decision = _crypto_exit_shadow_decision(
            market_slug=market_slug,
            market_title=market_title,
            entry_price=entry_price,
            current_price=current_price,
            entry_created_at_ms=entry.get("created_at"),
        )
        if not decision:
            continue

        decision["entry_record_id"] = entry.get("id")
        pos["cryptoExitShadow"] = decision
        summary["evaluated"] += 1
        if decision["action"] == "TAKE_PROFIT":
            summary["take_profit"] += 1
        elif decision["action"] == "STOP_LOSS":
            summary["stop_loss"] += 1
        if decision["action"] != "HOLD":
            logger.info(
                "Crypto exit shadow %s: title=%s side=%s entry=%s current=%s pnl_pct=%s mode=%s",
                decision["action"],
                market_title,
                outcome,
                decision["entry_price"],
                decision["current_price"],
                decision["pnl_pct"],
                decision["mode"],
            )

    return summary


def _high_confidence_buy_reason(
    side: str,
    price: Decimal,
    title: Optional[str] = None,
    market_slug: Optional[str] = None,
) -> Optional[str]:
    """Return a skip reason for high-price crypto BUYs with poor copy-trading payoff."""
    if side.upper() != "BUY":
        return None
    if not _is_crypto_market(title, market_slug):
        return None
    if price > HIGH_CONFIDENCE_MAX_BUY_PRICE:
        max_upside = Decimal("1") - price
        return (
            "High-price low-upside BUY skipped: "
            f"price={price}, max={HIGH_CONFIDENCE_MAX_BUY_PRICE}, "
            f"max_upside={max_upside}"
        )
    return None


def _same_market_record_matches_signal(record: dict, signal: LeaderTradeSignal) -> bool:
    raw = {}
    raw_payload = record.get("raw_payload")
    if raw_payload:
        try:
            raw = json.loads(raw_payload)
        except Exception:
            raw = {}
    record_market_id = record.get("market_id")
    record_slug = raw.get("marketSlug") or raw.get("market_slug")
    signal_market_id = signal.condition_id or signal.market_slug or ""
    if record_market_id and signal_market_id and record_market_id == signal_market_id:
        return True
    if record_slug and signal.market_slug and record_slug == signal.market_slug:
        return True
    return False


def _generic_repeat_buy_reason(
    signal: LeaderTradeSignal,
    side: str,
    now_ms: Optional[int] = None,
) -> Optional[str]:
    """Skip repeated BUYs for the same leader and market in a short window."""
    if side.upper() != "BUY" or not recorder:
        return None
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    since_ms = now - GENERIC_REPEAT_BUY_WINDOW_SECONDS * 1000
    records = recorder.recent_leader_records_since(
        leader_address=signal.leader_address,
        since_ms=since_ms,
    )
    for record in records:
        if str(record.get("side") or "").upper() != "BUY":
            continue
        if str(record.get("status") or "").upper() not in {"PENDING", "SUCCESS"}:
            continue
        if _same_market_record_matches_signal(record, signal):
            return (
                "Repeat same-market BUY skipped: "
                f"window={GENERIC_REPEAT_BUY_WINDOW_SECONDS}s"
            )
    return None


def _signal_market_end_date_ms(signal: LeaderTradeSignal) -> Optional[int]:
    if signal.market_end_date is not None:
        return int(signal.market_end_date)
    if recorder:
        return recorder.get_market_end_date(signal.condition_id)
    return None


def _near_expiry_news_buy_reason(
    signal: LeaderTradeSignal,
    side: str,
    price: Decimal,
    leader_size: Decimal,
    now_ms: Optional[int] = None,
) -> Optional[str]:
    """Skip small leader-notional news/event BUYs close to market end."""
    if side.upper() != "BUY":
        return None
    market_category = infer_market_category(signal.title)
    if market_category in {"sports", "crypto"}:
        return None

    end_date_ms = _signal_market_end_date_ms(signal)
    if end_date_ms is None:
        return None

    now = now_ms if now_ms is not None else int(time.time() * 1000)
    hours_to_end = Decimal(end_date_ms - now) / Decimal("3600000")
    if hours_to_end < 0 or hours_to_end > NEAR_EXPIRY_NEWS_BUY_MAX_HOURS:
        return None

    leader_value = price * leader_size
    if leader_value > NEAR_EXPIRY_NEWS_BUY_MAX_LEADER_VALUE:
        return None

    return (
        "Near-expiry small news-event BUY skipped: "
        f"hours_to_end={hours_to_end:.2f}, leader_value={leader_value}, "
        f"max_hours={NEAR_EXPIRY_NEWS_BUY_MAX_HOURS}, "
        f"max_leader_value={NEAR_EXPIRY_NEWS_BUY_MAX_LEADER_VALUE}"
    )


def _normalized_token_text(value: Optional[str]) -> str:
    text = str(value or "").strip().lower().replace("&", " and ")
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _leader_event_key(market_slug: Optional[str], market_title: Optional[str]) -> str:
    """Group related outcome markets into one event for copy-trading risk guards."""
    slug_text = _normalized_token_text(market_slug)
    title_text = _normalized_token_text(market_title)
    combined = f"{slug_text} {title_text}".strip()
    if "fed" in combined and "july 2026 meeting" in combined:
        return "fed-july-2026-meeting"

    fed_after_match = re.search(r"fed .* after the ([a-z]+ \d{4}) meeting", combined)
    if fed_after_match:
        return f"fed-{fed_after_match.group(1).replace(' ', '-')}-meeting"

    return slug_text or title_text


def _record_market_key(record: dict) -> str:
    raw_payload = record.get("raw_payload")
    raw = {}
    if raw_payload:
        try:
            raw = json.loads(raw_payload)
        except Exception:
            raw = {}
    slug = raw.get("marketSlug") or raw.get("market_slug")
    title = record.get("market_title") or raw.get("title")
    outcome = record.get("outcome") or raw.get("outcome")
    return "|".join(
        part
        for part in (
            _normalized_token_text(slug) or _normalized_token_text(title),
            _normalize_outcome(outcome),
        )
        if part
    )


def _leader_event_activity_buy_reason(
    signal: LeaderTradeSignal,
    side: str,
    now_ms: Optional[int] = None,
) -> Optional[str]:
    """Skip BUYs when a leader is rapidly trading multiple markets in one event."""
    if side.upper() != "BUY" or not recorder:
        return None
    event_key = _leader_event_key(signal.market_slug, signal.title)
    if not event_key:
        return None

    now = now_ms if now_ms is not None else int(time.time() * 1000)
    since_ms = now - LEADER_EVENT_ACTIVITY_WINDOW_SECONDS * 1000
    records = recorder.recent_leader_records_since(
        leader_address=signal.leader_address,
        since_ms=since_ms,
    )

    event_records = []
    market_keys = {
        "|".join(
            part
            for part in (
                _normalized_token_text(signal.market_slug) or _normalized_token_text(signal.title),
                _normalize_outcome(signal.outcome),
            )
            if part
        )
    }
    for record in records:
        if str(record.get("side") or "").upper() != "BUY":
            continue
        if str(record.get("status") or "").upper() not in {"PENDING", "SUCCESS"}:
            continue
        raw = {}
        raw_payload = record.get("raw_payload")
        if raw_payload:
            try:
                raw = json.loads(raw_payload)
            except Exception:
                raw = {}
        record_key = _leader_event_key(
            raw.get("marketSlug") or raw.get("market_slug"),
            record.get("market_title") or raw.get("title"),
        )
        if record_key != event_key:
            continue
        event_records.append(record)
        market_key = _record_market_key(record)
        if market_key:
            market_keys.add(market_key)

    if len(event_records) >= LEADER_EVENT_ACTIVITY_MAX_RECORDS:
        return (
            "High-frequency same-event leader activity skipped: "
            f"event={event_key}, records={len(event_records)}, "
            f"window={LEADER_EVENT_ACTIVITY_WINDOW_SECONDS}s, "
            f"max={LEADER_EVENT_ACTIVITY_MAX_RECORDS}"
        )
    if len(event_records) > 0 and len(market_keys) >= LEADER_EVENT_COMBO_MIN_MARKETS:
        return (
            "Multi-outcome same-event leader combo skipped: "
            f"event={event_key}, distinct_markets={len(market_keys)}, "
            f"window={LEADER_EVENT_ACTIVITY_WINDOW_SECONDS}s"
        )
    return None


def _short_cycle_price_band_buy_reason(
    market_slug: Optional[str],
    side: str,
    price: Decimal,
) -> Optional[str]:
    """Return a skip reason for BTC 5M BUYs outside the allowed price band."""
    if side.upper() != "BUY" or not market_slug:
        return None
    if not re.search(r"btc-updown-5m-\d{10}", market_slug):
        return None
    if price < BTC_UPDOWN_5M_MIN_BUY_PRICE:
        return (
            "BTC 5M low-price BUY skipped: "
            f"price={price}, min={BTC_UPDOWN_5M_MIN_BUY_PRICE}"
        )
    if price > BTC_UPDOWN_5M_MAX_BUY_PRICE:
        return (
            "BTC 5M high-price BUY skipped: "
            f"price={price}, max={BTC_UPDOWN_5M_MAX_BUY_PRICE}"
        )
    return None


def _short_cycle_global_buy_reason(
    market_slug: Optional[str],
    market_id: str,
) -> Optional[str]:
    """Return a skip reason if any BTC 5M BUY already exists for this market."""
    if not market_slug or not re.search(r"btc-updown-5m-\d{10}", market_slug):
        return None
    if not recorder:
        return None
    if recorder.has_any_prior_short_cycle_buy(market_id=market_id, market_slug=market_slug):
        return (
            "BTC 5M global market BUY skipped: "
            "a PENDING/SUCCESS BUY already exists for this BTC 5M market"
        )
    return None


def _start_of_local_day_ms(now_seconds: Optional[float] = None) -> int:
    now = now_seconds if now_seconds is not None else time.time()
    local = time.localtime(now)
    start = time.mktime(
        (
            local.tm_year,
            local.tm_mon,
            local.tm_mday,
            0,
            0,
            0,
            local.tm_wday,
            local.tm_yday,
            local.tm_isdst,
        )
    )
    return int(start * 1000)


def _short_cycle_daily_limit_buy_reason(
    market_slug: Optional[str],
    side: str,
    amount: Decimal,
    now_seconds: Optional[float] = None,
) -> Optional[str]:
    """Return a skip reason if daily BTC 5M successful BUY limits are exhausted."""
    if side.upper() != "BUY" or not market_slug:
        return None
    if not re.search(r"btc-updown-5m-\d{10}", market_slug):
        return None
    if not recorder:
        return None
    since_ms = _start_of_local_day_ms(now_seconds)
    count, _ = recorder.btc_5m_success_buy_usage_since(since_ms)
    if count >= BTC_UPDOWN_5M_DAILY_MAX_SUCCESS_BUYS:
        return (
            "BTC 5M daily BUY count limit skipped: "
            f"count={count}, max={BTC_UPDOWN_5M_DAILY_MAX_SUCCESS_BUYS}"
        )
    return None


def _short_cycle_duplicate_buy_reason(
    market_slug: Optional[str],
    market_id: str,
    leader_address: Optional[str],
) -> Optional[str]:
    """Return a skip reason for repeated BUYs on the same BTC 5M market."""
    if not market_slug or not re.search(r"btc-updown-5m-\d{10}", market_slug):
        return None
    if not recorder:
        return None
    if recorder.has_prior_short_cycle_buy(
        market_id=market_id,
        market_slug=market_slug,
        leader_address=leader_address,
    ):
        return (
            "Duplicate short-cycle market BUY skipped: "
            "same leader already has a PENDING/SUCCESS BUY for this BTC 5M market"
        )
    return None


def _get_pids_listening_on_port(port: int) -> list[int]:
    """Return PIDs that currently listen on the given TCP port."""
    try:
        output = subprocess.check_output(
            ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        pids = []
        suffix = f":{port}"
        for line in output.strip().split("\n")[1:]:
            parts = line.split()
            if len(parts) < 9:
                continue
            name = parts[8]
            if "->" in name or not name.endswith(suffix):
                continue
            pid = parts[1]
            if pid.isdigit():
                pids.append(int(pid))
        return sorted(set(pids))
    except Exception:
        return []


def _is_bridge_process(pid: int) -> bool:
    """Heuristic: is this PID a Bridge (or uvicorn serving main.py)?"""
    try:
        cmd = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "command="],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return any(keyword in cmd for keyword in ("polymtrade-bridge", "main.py", "uvicorn"))
    except Exception:
        return False


def enforce_unique_bridge_port() -> int:
    """
    Before binding, ensure the configured port is not stolen by a non-Bridge service.
    If a stale Bridge instance holds the port, kill it. If a foreign service holds it,
    fail loudly and refuse to start.
    """
    port = int(os.environ.get("BRIDGE_PORT", "8080"))
    my_pid = os.getpid()
    for pid in _get_pids_listening_on_port(port):
        if pid == my_pid:
            continue
        if _is_bridge_process(pid):
            logger.warning(
                "Port %s is held by a stale Bridge process (pid %s); killing it.",
                port,
                pid,
            )
            try:
                os.kill(pid, 9)
            except Exception as e:
                logger.error("Failed to kill stale Bridge pid %s: %s", pid, e)
        else:
            foreign_cmd = subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "command="],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            logger.error(
                "FATAL: Port %s is already used by a non-Bridge process (pid %s): %s",
                port,
                pid,
                foreign_cmd,
            )
            sys.exit(1)
    return port


if __name__ == "__main__":
    import uvicorn

    BRIDGE_PORT = enforce_unique_bridge_port()
    logger.info("Starting PolyHermes → Polymtrade Bridge on port %s", BRIDGE_PORT)
    uvicorn.run(app, host="0.0.0.0", port=BRIDGE_PORT)
