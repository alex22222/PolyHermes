package com.wrbug.polymarketbot.dto

data class UpdateVersionDto(
    val version: String
)

data class UpdateCheckDto(
    val hasUpdate: Boolean,
    val currentVersion: String,
    val latestVersion: String,
    val latestTag: String,
    val releaseNotes: String,
    val publishedAt: String,
    val prerelease: Boolean
)

data class UpdateStatusDto(
    val updating: Boolean,
    val progress: Int,
    val message: String,
    val error: String?
)
