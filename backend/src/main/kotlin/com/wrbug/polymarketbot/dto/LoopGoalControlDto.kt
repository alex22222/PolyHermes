package com.wrbug.polymarketbot.dto

data class LoopGoalControlStatusDto(
    val activeGoalKey: String?,
    val goals: List<LoopGoalDto>,
    val updatedAt: Long
)

data class LoopGoalDto(
    val goalKey: String,
    val title: String,
    val status: String,
    val priority: Int,
    val summary: String,
    val canStart: Boolean,
    val canPause: Boolean,
    val retained: Boolean,
    val updatedAt: Long?
)

data class LoopGoalControlUpdateRequest(
    val goalKey: String,
    val action: String
)
