import asyncio
import argparse
import json
import logging
import os
import re
import sys
import time
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field, ConfigDict

from polymtrade_executor import PolymtradeExecutor
from copy_trading_config import CopyTradingRuleEngine
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

BTC_UPDOWN_STALE_BUFFER_SECONDS = int(os.getenv("BTC_UPDOWN_STALE_BUFFER_SECONDS", "90"))
BTC_UPDOWN_5M_SECONDS = 300
BTC_UPDOWN_5M_MIN_BUY_PRICE = Decimal(os.getenv("BTC_UPDOWN_5M_MIN_BUY_PRICE", "0.20"))
BTC_UPDOWN_5M_MAX_BUY_PRICE = Decimal(os.getenv("BTC_UPDOWN_5M_MAX_BUY_PRICE", "0.65"))
BTC_UPDOWN_5M_DAILY_MAX_SUCCESS_BUYS = int(os.getenv("BTC_UPDOWN_5M_DAILY_MAX_SUCCESS_BUYS", "50"))

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
    event: str = "leader_trade"
    timestamp: int
    leader_id: Optional[int] = Field(None, alias="leaderId")
    leader_address: str = Field(..., alias="leaderAddress")
    leader_name: Optional[str] = Field(None, alias="leaderName")
    transaction_hash: str = Field(..., alias="transactionHash")
    condition_id: str = Field(..., alias="conditionId")
    market_slug: Optional[str] = Field(None, alias="marketSlug")
    title: Optional[str] = None
    side: str
    outcome: Optional[str] = None
    outcome_index: Optional[int] = Field(None, alias="outcomeIndex")
    price: float
    size: float
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


class AuditReconciliationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    market_id: str = Field(..., alias="marketId")
    market_title: Optional[str] = Field(None, alias="marketTitle")
    outcome: str
    outcome_index: Optional[int] = Field(None, alias="outcomeIndex")
    status: str = "externally_closed"
    note: Optional[str] = None
    actor: str = "operator"


# Global executor instance
executor: Optional[PolymtradeExecutor] = None
rule_engine: Optional[CopyTradingRuleEngine] = None
recorder: Optional[BridgeTradeRecorder] = None
position_ledger: Optional[PositionLedger] = None
_trade_lock = asyncio.Lock()
_portfolio_lock = asyncio.Lock()


def bridge_runtime_status() -> dict[str, Any]:
    return {
        "ready": executor.is_ready() if executor else False,
        "logged_in": executor.is_logged_in() if executor else False,
        "last_error": executor.last_error if executor else "executor not initialized",
        "copy_trading_account_id": rule_engine.active_account_id if rule_engine else None,
        "copy_trading_config_count": rule_engine.config_count if rule_engine else 0,
    }


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
    return {
        "status": "ok",
        "executor_ready": executor.is_ready() if executor else False,
    }


@app.get("/status")
async def status():
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
    """
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    if not executor.is_logged_in():
        raise HTTPException(status_code=401, detail="Not logged in")

    try:
        # Navigate to the portfolio page where the referral link contains the full wallet address.
        info = await executor.navigate_to("https://polym.trade/portfolio")
        text = info.get("text_sample", "") + " " + info.get("title", "")

        # The referral link is the most reliable full-address source.
        ref_match = re.search(r'[?&]ref=(0x[a-fA-F0-9]{40})', text)
        if ref_match:
            address = ref_match.group(1)
        else:
            # Fallback: any full Ethereum address visible on the page.
            addresses = re.findall(r'0x[a-fA-F0-9]{40}', text)
            if not addresses:
                raise HTTPException(status_code=404, detail="Wallet address not found in page")
            address = addresses[0]

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


@app.get("/portfolio")
async def portfolio_positions():
    """Return the current open positions scraped from Polymtrade portfolio page.

    Used by PolyHermes backend to keep Bridge read-only account positions in sync
    with the actual Polymtrade holdings.
    """
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    if not executor.is_logged_in():
        raise HTTPException(status_code=401, detail="Not logged in")

    metrics.portfolio_requests += 1
    # Serialize with trades as well as other portfolio scrapes. The executor has
    # one active page pointer; navigating it during post-submit confirmation can
    # destroy the trade page context and create false FAILED records.
    async with _trade_lock:
        async with _portfolio_lock:
            result = await executor.fetch_portfolio_positions()
    if "error" in result:
        metrics.portfolio_errors += 1
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@app.get("/balance")
async def account_balance():
    """Return the current pUSD/USDC balance scraped from the logged-in page."""
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")
    if not executor.is_logged_in():
        raise HTTPException(status_code=401, detail="Not logged in")

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
    return str(value or "").strip().lower()


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
    if not executor or not executor.is_ready() or not executor.is_logged_in():
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
        if target_market_id and (
            pos_market_id == target_market_id
            or target_market_id in pos_market_slug
            or target_market_id in pos_event_slug
            or pos_market_id in target_market_id
            or pos_market_slug in target_market_id
        ):
            market_matches = True
        if not market_matches and target_title and (
            pos_title == target_title
            or target_title in pos_title
            or pos_title in target_title
        ):
            market_matches = True

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
    if not executor.is_logged_in():
        raise HTTPException(status_code=401, detail="Not logged in")

    side_upper = request.side.upper()
    if side_upper not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="side must be BUY or SELL")

    external_trade_id = f"manual-{uuid.uuid4()}"

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
        amount=Decimal("0"),
        raw_payload=request.model_dump(by_alias=True),
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
    try:
        side_upper = request.side.upper()
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
    except Exception as e:
        logger.error(f"Manual trade failed: {external_trade_id}, error={e}", exc_info=True)
        recorder.update_status(record_id, "FAILED", error_message=str(e))


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

        matching = rule_engine.get_matching_configs(
            trader_address=signal.leader_address,
            side=signal.side,
            title=signal.title or "",
            price=Decimal(str(signal.price)),
            signal_timestamp_ms=signal.timestamp,
        )

        if not matching:
            logger.info(f"No copy-trading config matches leader {signal.leader_address}, skipping")
            return

        side_upper = signal.side.upper()

        for cfg, reason in matching:
            if reason:
                metrics.signals_filtered += 1
                logger.info(f"Config {cfg.id} filtered for {signal.transaction_hash}: {reason}")
                continue

            metrics.signals_executed += 1
            if side_upper == "BUY":
                metrics.trades_buy_total += 1
            else:
                metrics.trades_sell_total += 1

            await rule_engine.sleep_delay(cfg)

            price_dec = Decimal(str(signal.price))
            quantity: Optional[Decimal] = None
            amount: Optional[Decimal] = None

            if side_upper == "BUY":
                amount = rule_engine.compute_buy_quantity(
                    cfg, price_dec, Decimal(str(signal.size))
                )
                if amount is None:
                    logger.info(f"Config {cfg.id}: BUY quantity filtered")
                    continue
                quantity = amount / price_dec
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
                                raw_payload=signal.model_dump(by_alias=True),
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
                                raw_payload=signal.model_dump(by_alias=True),
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
                                raw_payload=signal.model_dump(by_alias=True),
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
                                raw_payload=signal.model_dump(by_alias=True),
                            )
                            recorder.update_status(skip_id, "FAILED", duplicate_reason)
                        except Exception as rec_err:
                            logger.warning(f"Failed to record duplicate BUY skip: {rec_err}")
                    continue
            else:
                quantity = rule_engine.compute_sell_shares(
                    cfg, price_dec, Decimal(str(signal.size))
                )
                if quantity is None:
                    logger.info(f"Config {cfg.id}: SELL quantity filtered")
                    continue
                amount = quantity * price_dec

                # SELL pre-check: ensure we have a corresponding position
                if position_ledger and not position_ledger.has_sufficient_position(
                    market_id=signal.condition_id or signal.market_slug or "",
                    outcome=signal.outcome,
                    outcome_index=signal.outcome_index,
                    sell_quantity=quantity,
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
                                raw_payload=signal.model_dump(by_alias=True),
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
                                raw_payload=signal.model_dump(by_alias=True),
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
                        raw_payload=signal.model_dump(by_alias=True),
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
                        continue
                    if side_upper == "BUY":
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
                else:
                    metrics.trades_sell_success += 1
            except Exception as exec_err:
                logger.exception(f"Trade execution failed for config {cfg.id}: {exec_err}")
                metrics.signals_failed += 1
                err_msg = str(exec_err).lower()
                if side_upper == "BUY":
                    metrics.trades_buy_failed += 1
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
    match = re.search(r"btc-updown-5m-(\d{10})", market_slug)
    if not match:
        return None

    started_at = int(match.group(1))
    market_close_at = started_at + BTC_UPDOWN_5M_SECONDS
    now = now_seconds if now_seconds is not None else time.time()
    cutoff = market_close_at - BTC_UPDOWN_STALE_BUFFER_SECONDS
    if now >= cutoff:
        seconds_to_close = market_close_at - now
        return (
            "Short-cycle market stale or closing soon, skipped "
            f"(seconds_to_close={seconds_to_close:.1f}, buffer={BTC_UPDOWN_STALE_BUFFER_SECONDS}s)"
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
