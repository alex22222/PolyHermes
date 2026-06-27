package com.wrbug.polymarketbot.config

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.scheduling.annotation.EnableAsync
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor
import java.util.concurrent.Executor
import java.util.concurrent.ThreadPoolExecutor

/**
 * Spring 异步任务配置
 */
@Configuration
@EnableAsync
class AsyncConfig {

    /**
     * Leader 扫描专用线程池。
     * scan 任务会发起大量 Data API 调用，属于 IO 密集型长任务，必须和 HTTP 线程隔离，
     * 避免阻塞 Tomcat 导致服务假死或 OOM。
     */
    @Bean("leaderScanExecutor")
    fun leaderScanExecutor(): Executor {
        return ThreadPoolTaskExecutor().apply {
            corePoolSize = 2
            maxPoolSize = 3
            queueCapacity = 10
            setThreadNamePrefix("leader-scan-")
            setRejectedExecutionHandler(ThreadPoolExecutor.CallerRunsPolicy())
            setWaitForTasksToCompleteOnShutdown(true)
            setAwaitTerminationSeconds(60)
            initialize()
        }
    }
}
