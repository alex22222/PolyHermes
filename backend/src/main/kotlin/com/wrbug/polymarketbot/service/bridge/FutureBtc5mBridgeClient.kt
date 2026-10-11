package com.wrbug.polymarketbot.service.bridge

import com.google.gson.Gson
import com.google.gson.JsonArray
import com.google.gson.JsonElement
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import com.wrbug.polymarketbot.dto.FutureBtc5mBridgeStatus
import com.wrbug.polymarketbot.dto.FutureBtc5mOrder
import com.wrbug.polymarketbot.dto.FutureBtc5mOrderListRequest
import com.wrbug.polymarketbot.dto.FutureBtc5mOrderListResponse
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Component
import java.net.URI
import java.net.URLEncoder
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.charset.StandardCharsets
import java.time.Duration

/** Connect only to the configured Future bridge; never forward browser tokens or caller URLs. */
@Component
class FutureBtc5mBridgeClient(
    @Value("\${future.bridge.url:http://127.0.0.1:8766}") private val bridgeUrl: String
) {
    private val gson = Gson()
    private val httpClient = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .connectTimeout(Duration.ofSeconds(2))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build()

    fun status(): FutureBtc5mBridgeStatus = request("/bridge/status", FutureBtc5mBridgeStatus::class.java) {
        validateStatus(it)
    }

    fun control(enabled: Boolean): FutureBtc5mBridgeStatus = request(
        "/bridge/control", FutureBtc5mBridgeStatus::class.java, gson.toJson(mapOf("enabled" to enabled))
    ) {
        validateStatus(it)
        check(boolean(it, "requestedEnabled") == enabled) { "Future Bridge 未确认请求的开关状态" }
    }

    fun orders(request: FutureBtc5mOrderListRequest): FutureBtc5mOrderListResponse {
        require(request.page >= 1 && request.size in 1..100) { "page 必须大于0，size 必须在1-100之间" }
        require(request.status == null || request.status in ORDER_STATUSES) { "订单状态无效" }
        val filter = request.status?.let { "&status=${encode(it)}" } ?: ""
        return request("/bridge/orders?page=${request.page}&size=${request.size}$filter", FutureBtc5mOrderListResponse::class.java) {
            check(integer(it, "page") == request.page.toLong() && integer(it, "size") == request.size.toLong()) {
                "Future Bridge 返回的分页不匹配"
            }
            val total = integer(it, "total")
            check(total in 0..Int.MAX_VALUE.toLong()) { "Future Bridge 返回的订单总数无效" }
            val list = array(it, "list")
            val offset = (request.page.toLong() - 1) * request.size
            check(list.size() == (total - offset).coerceIn(0, request.size.toLong()).toInt()) {
                "Future Bridge 返回的订单数量不匹配"
            }
            val ids = mutableSetOf<String>()
            list.forEach { element ->
                val order = objectValue(element)
                validateOrder(order)
                check(ids.add(string(order, "id"))) { "Future Bridge 返回重复订单" }
                check(request.status == null || string(order, "status") == request.status) { "Future Bridge 返回的订单状态不匹配" }
            }
        }
    }

    fun detail(id: String): FutureBtc5mOrder {
        require(Regex("future-btc5m:[0-9]{1,15}").matches(id)) { "订单ID无效" }
        return request("/bridge/orders/${encode(id)}", FutureBtc5mOrder::class.java) {
            validateOrder(it)
            check(string(it, "id") == id) { "Future Bridge 返回的订单ID不匹配" }
        }
    }

    private fun <T> request(path: String, responseType: Class<T>, body: String? = null, validate: (JsonObject) -> Unit): T {
        val base = try {
            URI.create(bridgeUrl)
        } catch (error: IllegalArgumentException) {
            throw IllegalStateException("Future Bridge 地址配置无效", error)
        }
        check(base.scheme in setOf("http", "https") && !base.host.isNullOrBlank() &&
            base.userInfo == null && base.query == null && base.fragment == null &&
            base.path in listOf("", "/") && (base.port == -1 || base.port in 1..65535)) { "future.bridge.url 必须是独立桥的基础地址" }
        val builder = HttpRequest.newBuilder(URI.create(bridgeUrl.trimEnd('/') + path))
            .header("Accept", "application/json")
            .timeout(Duration.ofSeconds(4))
        if (body == null) builder.GET() else builder
            .header("Content-Type", "application/json")
            .header("X-PolyHermes-Future-Control", "1")
            .POST(HttpRequest.BodyPublishers.ofString(body))
        val response = try {
            httpClient.send(builder.build(), HttpResponse.BodyHandlers.ofString())
        } catch (error: InterruptedException) {
            Thread.currentThread().interrupt()
            throw IllegalStateException("Future Bridge 请求被中断，未确认操作成功", error)
        } catch (error: Exception) {
            throw IllegalStateException("Future Bridge 请求失败，未确认操作成功", error)
        }
        if (response.statusCode() == 404) throw NoSuchElementException("Future 订单不存在或控制接口尚未加载")
        check(response.statusCode() in 200..299) { "Future Bridge 返回 ${response.statusCode()}，未确认操作成功" }
        val payload = try {
            objectValue(JsonParser.parseString(response.body()))
        } catch (error: Exception) {
            throw IllegalStateException("Future Bridge 返回无效响应，未确认操作成功", error)
        }
        validate(payload)
        return try {
            gson.fromJson(payload, responseType)
                ?: throw IllegalStateException("Future Bridge 返回空响应，未确认操作成功")
        } catch (error: Exception) {
            throw IllegalStateException("Future Bridge 返回无效响应，未确认操作成功", error)
        }
    }

    private fun validateStatus(status: JsonObject) {
        check(string(status, "bridgeId") == "future-btc5m" && string(status, "series") == "5m" && integer(status, "amountUsd") == 1L) {
            "Future Bridge 身份或固定金额无效"
        }
        val requested = boolean(status, "requestedEnabled")
        check(boolean(status, "online") && !boolean(status, "effectiveEnabled") && !boolean(status, "executorReady")) {
            "当前 Future Bridge 没有交易执行器，不能返回交易就绪状态"
        }
        check(string(status, "mode") == if (requested) "BLOCKED" else "DISABLED") { "Future Bridge 开关和模式不一致" }
        val serverTime = number(status, "serverTime")
        check(serverTime >= 0) { "Future Bridge 服务器时间无效" }
        val period = field(status, "periodStart")
        val start = if (period.isJsonNull) null else integer(status, "periodStart")
        check(start == null || start >= 0 && start % 300 == 0L) { "Future Bridge 轮次无效" }
        string(status, "feedStatus")
        nullableString(status, "reason")
        val reasons = array(status, "blockReasons")
        reasons.forEach { check(it.isJsonPrimitive && it.asJsonPrimitive.isString && it.asString.isNotBlank()) { "Future Bridge 拦截原因无效" } }
        check(reasons.any { it.asString == "EXECUTOR_NOT_CONNECTED" }) { "Future Bridge 缺少执行器阻断事实" }
        val counts = objectValue(field(status, "orderCounts"))
        val values = listOf("total", "pending", "submitted", "filled", "failed", "skipped").associateWith { key ->
            integer(counts, key).also { check(it in 0..Int.MAX_VALUE.toLong()) { "Future Bridge 订单统计无效" } }
        }
        check(values["total"] == values["skipped"] && listOf("pending", "submitted", "filled", "failed").all { values[it] == 0L }) {
            "当前 Future Bridge 只能返回已跳过的订单事实"
        }
        val signalValue = field(status, "signal")
        if (!signalValue.isJsonNull) {
            val signal = objectValue(signalValue)
            val signalStart = integer(signal, "period_start")
            check(start == signalStart && string(signal, "slug") == "btc-updown-5m-$signalStart") { "Future Bridge 信号轮次不匹配" }
            val observed = number(signal, "price_observed_at")
            val opening = number(signal, "open_price")
            val current = number(signal, "current_price")
            check(observed >= 0 && observed <= serverTime && opening > 0 && current > 0) { "Future Bridge 信号价格或时间无效" }
            val side = nullableString(signal, "side")
            val expected = if (current > opening) "Up" else if (current < opening) "Down" else null
            check(side == expected) { "Future Bridge 信号方向和价格不一致" }
            if (signal.has("period_end")) check(integer(signal, "period_end") == signalStart + 300) { "Future Bridge 信号结束时间无效" }
            if (signal.has("price_source")) check(string(signal, "price_source") == "chainlink") { "Future Bridge 信号来源无效" }
            if (signal.has("open_price_source")) check(string(signal, "open_price_source") == OPEN_PRICE_SOURCE) { "Future Bridge 开盘价来源无效" }
            if (signal.has("twap_lookback_seconds")) check(integer(signal, "twap_lookback_seconds") == 60L) { "Future Bridge TWAP时长无效" }
        }
        if (status.has("preflight") && !status.get("preflight").isJsonNull) validatePreflight(objectValue(status.get("preflight")), status)
        validatePreparation(objectValue(field(status, "preparation")), status)
    }

    private fun validatePreparation(preparation: JsonObject, status: JsonObject) {
        validatePreparationScope(preparation)
        val enabled = boolean(preparation, "enabled")
        check(enabled == boolean(status, "requestedEnabled")) { "Future 票据准备开关未获确认" }
        val state = string(preparation, "state")
        check(state in PREPARATION_STATES && (enabled || state in setOf("DISABLED", "BLOCKED")) && (state != "DISABLED" || !enabled)) {
            "Future 票据准备状态和开关不一致"
        }
        array(preparation, "reasons").forEach {
            check(it.isJsonPrimitive && it.asJsonPrimitive.isString && it.asString in PREPARATION_REASONS) { "Future 票据准备原因无效" }
        }
        if (state in setOf("PENDING", "CLAIMED", "READY")) check(array(preparation, "reasons").isEmpty) {
            "Future 活动准备状态仍存在阻断原因"
        }
        val serverTime = number(status, "serverTime")
        val intentValue = field(preparation, "intent")
        val historyValue = field(preparation, "lastAttempt")
        val record = if (historyValue.isJsonNull) null else objectValue(historyValue).also { validatePreparationRecord(it, serverTime) }
        if (state in setOf("PENDING", "CLAIMED")) {
            val intent = objectValue(intentValue)
            validatePreparationIntent(intent, serverTime)
            check(intent.keySet() == PREPARATION_INTENT_FIELDS && record != null && string(record, "state") == state &&
                PREPARATION_INTENT_FIELDS.all { intent.get(it) == record.get(it) } &&
                integer(intent, "periodStart") == integer(status, "periodStart") && string(status, "feedStatus") == "CURRENT" &&
                serverTime < number(intent, "expiresAt") && serverTime - number(intent, "priceObservedAt") in 0.0..5.0) {
                "Future 当前准备意图缺少新鲜的本轮信号或对应记录"
            }
            validateCurrentPreparation(record, status)
        } else check(intentValue.isJsonNull) { "Future 当前状态不允许暴露可写票据意图" }
        when (state) {
            "READY" -> {
                check(record != null && string(record, "state") == "READY") { "Future 准备成功缺少对应操作报告" }
                validateCurrentPreparation(record, status)
            }
            "FAILED", "REVOKED" -> check(record != null && string(record, "state") == state) { "Future 准备结果缺少对应操作报告" }
            "EXPIRED" -> check(record != null && serverTime >= number(record, "expiresAt") &&
                string(record, "state") in setOf("PENDING", "READY", "EXPIRED") &&
                (string(record, "state") != "EXPIRED" || nullableString(record, "reason") == "INTENT_EXPIRED")) {
                "Future 过期视图缺少已到期的准备记录"
            }
            "RECEIPT_UNKNOWN" -> check(record != null && serverTime >= number(record, "expiresAt") &&
                (string(record, "state") == "CLAIMED" || string(record, "state") == "EXPIRED" &&
                    nullableString(record, "reason") == "PREPARATION_RECEIPT_UNKNOWN")) { "Future 未知结果缺少已到期的领取事实" }
        }
    }

    private fun validateCurrentPreparation(record: JsonObject, status: JsonObject) {
        val now = number(status, "serverTime")
        val start = integer(record, "periodStart")
        val signal = objectValue(field(status, "signal"))
        check(integer(status, "periodStart") == start && string(status, "feedStatus") == "CURRENT" &&
            now >= start + 60 && now < number(record, "expiresAt") && now - number(record, "priceObservedAt") in 0.0..5.0 &&
            integer(signal, "period_start") == start && integer(signal, "period_end") == start + 300 &&
            now - number(signal, "price_observed_at") in 0.0..5.0 && nullableString(signal, "side") == string(record, "side") &&
            string(signal, "price_source") == "chainlink" && string(signal, "open_price_source") == OPEN_PRICE_SOURCE &&
            integer(signal, "twap_lookback_seconds") == 60L) { "Future 当前准备状态与新鲜的原信号不一致" }
        val preflight = objectValue(field(status, "preflight"))
        check(boolean(preflight, "browserConnected") && string(preflight, "navigation") == "CURRENT" &&
            string(preflight, "ticketStatus") == "PASS" && integer(preflight, "pagePeriodStart") == start &&
            now - number(preflight, "receivedAt") in 0.0..5.0 && kotlin.math.abs(now - number(preflight, "checkedAt")) <= 5 &&
            array(preflight, "reasons").none { it.asString.startsWith("PREFLIGHT_LEDGER_") }) {
            "Future 当前准备状态缺少同轮新鲜的浏览器报告"
        }
        if (string(record, "state") == "READY") check(number(preflight, "amountUsd") == 1.0 &&
            nullableString(preflight, "selectedSide") == string(record, "side") && boolean(preflight, "buyButtonEnabled")) {
            "Future 当前票据已改变，不能声明准备就绪"
        }
    }

    private fun validatePreparationScope(value: JsonObject) {
        check(string(value, "mode") == "PREPARE_ONLY" && boolean(value, "noSubmission") &&
            boolean(value, "operatorAuthorized") && string(value, "authorizationSource") == "USER_REQUEST") {
            "Future 票据准备只能采用用户授权的准备模式，不能提交买入"
        }
    }

    private fun validatePreparationIntent(intent: JsonObject, serverTime: Double) {
        validatePreparationScope(intent)
        val start = integer(intent, "periodStart")
        check(integer(intent, "schemaVersion") == 1L && start >= 0 && start % 300 == 0L &&
            integer(intent, "periodEnd") == start + 300 && string(intent, "id") == "future-btc5m-prepare:$start" &&
            string(intent, "slug") == "btc-updown-5m-$start" && integer(intent, "amountUsd") == 1L) {
            "Future 准备意图的市场或固定金额无效"
        }
        val created = number(intent, "createdAt")
        val observed = number(intent, "priceObservedAt")
        check(created >= start + 60 && created < start + 80 && created <= serverTime &&
            number(intent, "expiresAt") == (start + 80).toDouble() && observed >= 0 && created - observed in 0.0..5.0) {
            "Future 准备意图的信号采样或入场窗口无效"
        }
        val opening = number(intent, "openPrice")
        val current = number(intent, "currentPrice")
        check(opening > 0 && current > 0 && current != opening &&
            string(intent, "side") == if (current > opening) "Up" else "Down") { "Future 准备方向和采样价格不一致" }
        check(string(intent, "priceSource") == "chainlink" && string(intent, "openPriceSource") == OPEN_PRICE_SOURCE &&
            integer(intent, "twapLookbackSeconds") == 60L) { "Future 准备意图的价格来源无效" }
        val token = nullableString(intent, "claimToken")
        check(token == null || Regex("[0-9a-f]{32}").matches(token)) { "Future 准备意图的领取凭证无效" }
    }

    private fun validatePreparationRecord(record: JsonObject, serverTime: Double) {
        validatePreparationIntent(record, serverTime)
        check(record.keySet() == PREPARATION_INTENT_FIELDS + setOf("state", "updatedAt", "claimedAt", "reason", "receipt")) {
            "Future 准备报告包含未知执行字段"
        }
        val state = string(record, "state")
        check(state in setOf("PENDING", "CLAIMED", "READY", "FAILED", "EXPIRED", "REVOKED")) { "Future 准备操作报告状态无效" }
        val created = number(record, "createdAt")
        val expires = number(record, "expiresAt")
        val updated = number(record, "updatedAt")
        val claimed = if (field(record, "claimedAt").isJsonNull) null else number(record, "claimedAt")
        val token = nullableString(record, "claimToken")
        val reason = nullableString(record, "reason")
        val receiptValue = field(record, "receipt")
        check(updated >= created && updated <= serverTime && (claimed == null) == (token == null) &&
            (claimed == null || claimed >= created && claimed < expires && updated >= claimed &&
                claimed - number(record, "priceObservedAt") in 0.0..5.0)) { "Future 准备报告时间或领取凭证不一致" }
        when (state) {
            "PENDING" -> check(claimed == null && receiptValue.isJsonNull && reason == null && updated == created)
            "CLAIMED" -> check(claimed != null && receiptValue.isJsonNull && reason == null && updated == claimed)
            "READY" -> check(claimed != null && !receiptValue.isJsonNull && reason == null && updated < expires &&
                updated - number(record, "priceObservedAt") in 0.0..5.0)
            "FAILED" -> check(claimed != null && !receiptValue.isJsonNull && reason in PREPARATION_FAILURE_REASONS)
            "EXPIRED" -> check(reason in setOf("INTENT_EXPIRED", "PREPARATION_RECEIPT_UNKNOWN") && updated >= expires &&
                (claimed != null || receiptValue.isJsonNull))
            "REVOKED" -> check(receiptValue.isJsonNull && reason in setOf("PREPARATION_REVOKED", "PROCESS_RESTARTED"))
        }
        if (!receiptValue.isJsonNull) {
            check(claimed != null) { "Future 准备报告缺少领取事实" }
            val receipt = objectValue(receiptValue)
            check(receipt.keySet() == setOf("checkedAt", "marketUrl", "amountUsd", "selectedSide")) { "Future 准备回执字段无效" }
            val checked = number(receipt, "checkedAt")
            check(checked >= 0 && kotlin.math.abs(checked - updated) <= 3 && checked >= claimed - 3 &&
                marketUrlStart(string(receipt, "marketUrl")) == integer(record, "periodStart")) { "Future 准备回执的市场或浏览器时间无效" }
            val amount = if (field(receipt, "amountUsd").isJsonNull) null else number(receipt, "amountUsd")
            val side = nullableString(receipt, "selectedSide")
            check((amount == null || amount >= 0) && side in setOf(null, "Up", "Down")) { "Future 准备回执金额或方向无效" }
            if (state == "READY") check(amount == 1.0 && side == string(record, "side") &&
                checked >= integer(record, "periodStart") + 60 && checked < expires) { "Future 票据准备成功缺少实际金额和方向核对" }
        }
    }

    private fun validatePreflight(preflight: JsonObject, status: JsonObject) {
        check(string(preflight, "mode") == "READ_ONLY" && boolean(preflight, "noSubmission")) { "Future 预检只能报告只读事实" }
        val serverTime = number(status, "serverTime")
        val connected = boolean(preflight, "browserConnected")
        val fresh = boolean(preflight, "signalFresh")
        val matching = boolean(preflight, "sideMatches")
        val enabled = boolean(preflight, "buyButtonEnabled")
        val checked = if (field(preflight, "checkedAt").isJsonNull) null else number(preflight, "checkedAt")
        val received = if (field(preflight, "receivedAt").isJsonNull) null else number(preflight, "receivedAt")
        val start = if (field(preflight, "pagePeriodStart").isJsonNull) null else integer(preflight, "pagePeriodStart")
        val url = nullableString(preflight, "marketUrl")
        val amount = if (field(preflight, "amountUsd").isJsonNull) null else number(preflight, "amountUsd")
        check(amount == null || amount >= 0) { "Future 预检金额无效" }
        val side = nullableString(preflight, "selectedSide")
        val signalSide = nullableString(preflight, "signalSide")
        check(side in setOf(null, "Up", "Down") && signalSide in setOf(null, "Up", "Down")) { "Future 预检方向无效" }
        val navigation = string(preflight, "navigation")
        val ticket = string(preflight, "ticketStatus")
        check(navigation in setOf("UNKNOWN", "CURRENT", "ENDED", "MISMATCH") && ticket in setOf("UNKNOWN", "PASS", "FAIL")) { "Future 预检页面状态无效" }
        if (start == null) {
            check(url == null && checked == null && received == null && !connected && navigation == "UNKNOWN" && ticket == "UNKNOWN") { "Future 预检浏览器事实缺失" }
        } else {
            check(url != null && marketUrlStart(url) == start && checked != null && received != null &&
                checked >= 0 && received >= 0 && received <= serverTime && kotlin.math.abs(checked - received) <= 3) { "Future 预检市场或时间无效" }
        }
        if (connected) check(checked != null && received != null && serverTime - received in 0.0..5.0 &&
            kotlin.math.abs(serverTime - checked) <= 5) { "Future 预检浏览器报告已过期" }
        check(!matching || connected && fresh && side != null && side == signalSide) { "Future 预检方向匹配事实无效" }
        val result = string(preflight, "result")
        check(result in setOf("WAITING_BROWSER", "BLOCKED", "READ_ONLY_READY")) { "Future 预检结果无效" }
        val reasons = array(preflight, "reasons")
        reasons.forEach { check(it.isJsonPrimitive && it.asJsonPrimitive.isString && it.asString.isNotBlank()) { "Future 预检原因无效" } }
        if (result == "WAITING_BROWSER") check(!connected) { "Future 预检等待浏览器状态无效" }
        if (result == "READ_ONLY_READY") {
            check(connected && fresh && matching && enabled && navigation == "CURRENT" && ticket == "PASS" && amount == 1.0 && reasons.isEmpty) { "Future 预检通过所需条件缺失" }
            val signal = objectValue(field(status, "signal"))
            val period = integer(signal, "period_start")
            check(start == period && integer(status, "periodStart") == period && string(status, "feedStatus") == "CURRENT" &&
                serverTime >= period + 60 && serverTime < period + 80 && checked != null && checked >= period + 60 && checked < period + 80 &&
                serverTime - number(signal, "price_observed_at") in 0.0..5.0 && nullableString(signal, "side") == signalSide &&
                integer(signal, "period_end") == period + 300 && string(signal, "price_source") == "chainlink" &&
                string(signal, "open_price_source") == OPEN_PRICE_SOURCE && integer(signal, "twap_lookback_seconds") == 60L) { "Future 预检通过与实时信号不一致" }
        } else check(reasons.size() > 0) { "Future 预检阻断原因缺失" }
        val history = field(preflight, "lastPassed")
        if (!history.isJsonNull) {
            val passed = objectValue(history)
            val period = integer(passed, "periodStart")
            val at = number(passed, "checkedAt")
            check(marketUrlStart(string(passed, "marketUrl")) == period && at >= period + 60 && at < period + 80 && at <= serverTime + 3 &&
                string(passed, "signalSide") in setOf("Up", "Down") && integer(passed, "amountUsd") == 1L && boolean(passed, "noSubmission")) { "Future 历史预检记录无效" }
        }
    }

    private fun marketUrlStart(url: String): Long? {
        val digits = Regex("https://future\\.news/(?:zh/)?event/btc-updown-5m-([0-9]{1,15})/?").matchEntire(url)?.groupValues?.get(1) ?: return null
        val start = digits.toLongOrNull() ?: return null
        return start.takeIf { it >= 0 && it % 300 == 0L && it.toString() == digits }
    }

    private fun validateOrder(order: JsonObject) {
        val start = integer(order, "periodStart")
        check(start >= 0 && start % 300 == 0L && integer(order, "periodEnd") == start + 300 &&
            string(order, "id") == "future-btc5m:$start" && string(order, "slug") == "btc-updown-5m-$start" &&
            string(order, "bridgeId") == "future-btc5m" && string(order, "side") in setOf("Up", "Down") && integer(order, "amountUsd") == 1L) {
            "Future Bridge 订单身份或金额无效"
        }
        check(string(order, "status") == "SKIPPED" && nullableString(order, "reason") == "EXECUTOR_NOT_CONNECTED") {
            "当前 Future Bridge 不能返回已执行或已成交订单"
        }
        val created = number(order, "createdAt")
        check(created >= start + 60 && created < start + 80 && number(order, "updatedAt") == created) { "Future Bridge 订单记录时间无效" }
        listOf("submittedAt", "filledAt", "platformOrderId", "filledQuantity", "avgFilledPrice", "feeUsd").forEach {
            check(field(order, it).isJsonNull) { "Future Bridge 缺少平台回执，执行和成交字段必须明确为空" }
        }
        val events = array(order, "events")
        check(events.size() == 2) { "Future Bridge 执行步骤缺失" }
        val accepted = objectValue(events[0])
        val blocked = objectValue(events[1])
        check(string(accepted, "stage") == "SIGNAL_ACCEPTED" && nullableString(accepted, "reason") == null &&
            string(blocked, "stage") == "EXECUTION_BLOCKED" && nullableString(blocked, "reason") == "EXECUTOR_NOT_CONNECTED" &&
            number(accepted, "at") == created && number(blocked, "at") == created) { "Future Bridge 执行步骤不匹配" }
    }

    private fun field(value: JsonObject, key: String): JsonElement = value.get(key)
        ?: throw IllegalStateException("Future Bridge 响应缺少 $key")

    private fun objectValue(value: JsonElement): JsonObject {
        check(value.isJsonObject) { "Future Bridge 响应必须是对象" }
        return value.asJsonObject
    }

    private fun array(value: JsonObject, key: String): JsonArray {
        val element = field(value, key)
        check(element.isJsonArray) { "Future Bridge 的 $key 必须是数组" }
        return element.asJsonArray
    }

    private fun string(value: JsonObject, key: String): String {
        val element = field(value, key)
        check(element.isJsonPrimitive && element.asJsonPrimitive.isString && element.asString.isNotBlank()) { "Future Bridge 的 $key 必须是非空字符串" }
        return element.asString
    }

    private fun nullableString(value: JsonObject, key: String): String? = if (field(value, key).isJsonNull) null else string(value, key)

    private fun boolean(value: JsonObject, key: String): Boolean {
        val element = field(value, key)
        check(element.isJsonPrimitive && element.asJsonPrimitive.isBoolean) { "Future Bridge 的 $key 必须是布尔值" }
        return element.asBoolean
    }

    private fun number(value: JsonObject, key: String): Double {
        val element = field(value, key)
        check(element.isJsonPrimitive && element.asJsonPrimitive.isNumber) { "Future Bridge 的 $key 必须是数字" }
        val number = element.asDouble
        check(number.isFinite()) { "Future Bridge 的 $key 必须是有限数字" }
        return number
    }

    private fun integer(value: JsonObject, key: String): Long {
        number(value, key)
        return try {
            field(value, key).asBigDecimal.longValueExact()
        } catch (error: Exception) {
            throw IllegalStateException("Future Bridge 的 $key 必须是有效整数", error)
        }
    }

    private fun encode(value: String): String = URLEncoder.encode(value, StandardCharsets.UTF_8)

    companion object {
        private const val OPEN_PRICE_SOURCE = "polymarket_crypto_price_fiveminute_twap60_openPrice"
        private val PREPARATION_INTENT_FIELDS = setOf("schemaVersion", "id", "slug", "periodStart", "periodEnd", "side", "amountUsd",
            "createdAt", "expiresAt", "priceObservedAt", "openPrice", "currentPrice", "priceSource", "openPriceSource", "twapLookbackSeconds",
            "mode", "noSubmission", "operatorAuthorized", "authorizationSource", "claimToken")
        private val PREPARATION_STATES = setOf("DISABLED", "WAITING_SIGNAL", "WAITING_BROWSER", "PENDING", "CLAIMED", "READY", "FAILED",
            "EXPIRED", "REVOKED", "RECEIPT_UNKNOWN", "BLOCKED")
        private val PREPARATION_FAILURE_REASONS = setOf("PREPARATION_FAILED", "MARKET_MISMATCH", "TICKET_CHANGED", "UNSAFE_DIRECTION_CONTROL",
            "AMOUNT_WRITE_FAILED", "DIRECTION_WRITE_FAILED", "POSTCHECK_FAILED", "PREPARATION_REVOKED")
        private val PREPARATION_REASONS = PREPARATION_FAILURE_REASONS + setOf("AUTO_PREPARATION_DISABLED", "WAITING_CURRENT_SIGNAL",
            "BROWSER_NOT_CONNECTED", "MARKET_NOT_CURRENT", "TICKET_CHECK_FAILED", "PREPARED_TICKET_CHANGED", "INTENT_EXPIRED",
            "PREPARATION_RECEIPT_UNKNOWN", "PREPARATION_REVOKED", "PROCESS_RESTARTED", "PREPARATION_LEDGER_INVALID",
            "PREPARATION_LEDGER_WRITE_FAILED", "ORDER_LEDGER_INVALID", "ORDER_LEDGER_WRITE_FAILED", "CONTROL_STATE_WRITE_FAILED",
            "SIGNAL_SOURCE_UNAVAILABLE", "SIGNAL_SOURCE_INVALID", "STOP_FILE_PRESENT", "PREFLIGHT_LEDGER_INVALID", "PREFLIGHT_LEDGER_WRITE_FAILED")
        val ORDER_STATUSES = setOf("PENDING", "SKIPPED", "FAILED", "SUBMITTED_UNVERIFIED", "FILLED")
    }
}
