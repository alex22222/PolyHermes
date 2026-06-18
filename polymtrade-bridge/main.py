import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from polymtrade_executor import PolymtradeExecutor
from copy_trading_config import CopyTradingRuleEngine
from bridge_recorder import BridgeTradeRecorder
from position_ledger import PositionLedger

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


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
    market_slug: str
    side: str = "BUY"
    outcome: str
    amount_usdc: float = 1.0
    condition_id: Optional[str] = Field(None, alias="conditionId")


# Global executor instance
executor: Optional[PolymtradeExecutor] = None
rule_engine: Optional[CopyTradingRuleEngine] = None
recorder: Optional[BridgeTradeRecorder] = None
position_ledger: Optional[PositionLedger] = None
_trade_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global executor, rule_engine, recorder, position_ledger
    logger.info("Initializing Polymtrade executor...")
    executor = PolymtradeExecutor()
    await executor.start()
    logger.info("Polymtrade executor initialized")

    logger.info("Initializing copy-trading rule engine...")
    rule_engine = CopyTradingRuleEngine()
    try:
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

    logger.info("Shutting down Polymtrade executor...")
    if executor:
        await executor.stop()
    logger.info("Polymtrade executor stopped")


app = FastAPI(title="PolyHermes → Polymtrade Bridge", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "executor_ready": executor.is_ready() if executor else False,
    }


@app.get("/status")
async def status():
    if not executor:
        return {"error": "executor not initialized"}
    return {
        "ready": executor.is_ready(),
        "logged_in": executor.is_logged_in(),
        "last_error": executor.last_error,
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


@app.post("/signal")
async def receive_signal(signal: LeaderTradeSignal, background_tasks: BackgroundTasks):
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")

    logger.info(f"Received leader trade signal: {signal.side} {signal.outcome} @ {signal.market_slug}")

    # Execute asynchronously to avoid blocking the response
    background_tasks.add_task(handle_signal, signal)

    return {"status": "accepted", "signal": signal.model_dump(by_alias=True)}


@app.post("/execute")
async def execute_trade(request: ExecuteRequest, background_tasks: BackgroundTasks):
    if not executor or not executor.is_ready():
        raise HTTPException(status_code=503, detail="Executor not ready")

    background_tasks.add_task(
        executor.execute_trade,
        market_slug=request.market_slug,
        side=request.side,
        outcome=request.outcome,
        amount_usdc=request.amount_usdc,
        condition_id=request.condition_id,
    )

    return {"status": "accepted", "request": request.model_dump()}


async def handle_signal(signal: LeaderTradeSignal):
    try:
        if not signal.market_slug:
            logger.warning(f"Signal missing market_slug, cannot execute: {signal.transaction_hash}")
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
        )

        if not matching:
            logger.info(f"No copy-trading config matches leader {signal.leader_address}, skipping")
            return

        for cfg, reason in matching:
            if reason:
                logger.info(f"Config {cfg.id} filtered for {signal.transaction_hash}: {reason}")
                continue

            await rule_engine.sleep_delay(cfg)

            price_dec = Decimal(str(signal.price))
            side_upper = signal.side.upper()
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
                    if side_upper == "BUY":
                        await executor.execute_trade(
                            market_slug=signal.market_slug,
                            side="BUY",
                            outcome=signal.outcome or "Yes",
                            amount_usdc=float(amount),
                            condition_id=signal.condition_id,
                        )
                    else:
                        await executor.execute_trade(
                            market_slug=signal.market_slug,
                            side="SELL",
                            outcome=signal.outcome or "Yes",
                            amount_usdc=0.0,
                            condition_id=signal.condition_id,
                            size_shares=float(quantity),
                        )
                if record_id and recorder:
                    recorder.update_status(record_id, "SUCCESS")
            except Exception as exec_err:
                logger.exception(f"Trade execution failed for config {cfg.id}: {exec_err}")
                if record_id and recorder:
                    recorder.update_status(record_id, "FAILED", str(exec_err))
    except Exception as e:
        logger.exception(f"Failed to handle signal: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
