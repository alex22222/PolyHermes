package com.wrbug.polymarketbot.controller.bridge

import com.wrbug.polymarketbot.dto.ApiResponse
import com.wrbug.polymarketbot.dto.BridgeLogContentRequest
import com.wrbug.polymarketbot.dto.BridgeLogContentResponse
import com.wrbug.polymarketbot.dto.BridgeLogInfo
import org.slf4j.LoggerFactory
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController
import java.io.BufferedReader
import java.io.File
import java.io.InputStreamReader

/**
 * 桥接日志接口
 * 供前端实时查看 Bridge 和 Leader Event Poller 的运行日志
 */
@RestController
@RequestMapping("/api/bridge/logs")
class BridgeLogController {

    private val logger = LoggerFactory.getLogger(BridgeLogController::class.java)

    companion object {
        private val LOG_FILES = mapOf(
            "bridge" to "/tmp/polymtrade-bridge.log",
            "poller" to "/tmp/polymtrade-event-poller.log"
        )

        private val LOG_DISPLAY_NAMES = mapOf(
            "bridge" to "Bridge 运行日志",
            "poller" to "Leader Event Poller 日志"
        )
    }

    /**
     * 获取可查看的日志列表
     */
    @PostMapping("/list")
    fun listLogs(): ApiResponse<List<BridgeLogInfo>> {
        val list = LOG_FILES.map { (name, path) ->
            BridgeLogInfo(
                name = name,
                displayName = LOG_DISPLAY_NAMES[name] ?: name,
                path = path
            )
        }
        return ApiResponse.success(list)
    }

    /**
     * 获取指定日志的最新 N 行内容
     */
    @PostMapping("/content")
    fun getLogContent(@RequestBody request: BridgeLogContentRequest): ApiResponse<BridgeLogContentResponse> {
        val name = request.name
        val path = LOG_FILES[name]
            ?: return ApiResponse.error(400, "未知日志名称: $name")

        val lines = (request.lines ?: 200).coerceIn(1, 2000)
        val content = readLastLines(path, lines)

        return ApiResponse.success(
            BridgeLogContentResponse(
                name = name,
                content = content,
                lines = content.lines().size
            )
        )
    }

    /**
     * 使用系统 tail 命令读取最后 N 行
     */
    private fun readLastLines(path: String, lines: Int): String {
        val file = File(path)
        if (!file.exists()) {
            return "[日志文件不存在: $path]"
        }

        return try {
            val process = ProcessBuilder("tail", "-n", lines.toString(), path)
                .redirectErrorStream(true)
                .start()

            process.inputStream.use { input ->
                BufferedReader(InputStreamReader(input)).use { reader ->
                    reader.readText()
                }
            }
        } catch (e: Exception) {
            logger.error("读取日志失败: $path", e)
            "[读取日志失败: ${e.message}]"
        }
    }
}
