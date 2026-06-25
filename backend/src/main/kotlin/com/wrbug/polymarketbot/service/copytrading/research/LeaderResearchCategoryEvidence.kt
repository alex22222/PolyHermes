package com.wrbug.polymarketbot.service.copytrading.research

data class LeaderResearchCategoryEvidence(
    val category: String,
    val counts: Map<String, Int>,
    val dominantRatio: Double,
    val mixed: Boolean
)

object LeaderResearchCategoryEvidenceClassifier {
    private val knownCategories = setOf("politics", "finance", "sports", "crypto")
    private val categoryRegex = Regex("category[:=]([a-z_-]+)")

    fun classify(sourceEvidence: String?, fallback: String? = null): LeaderResearchCategoryEvidence {
        val normalizedEvidence = sourceEvidence.orEmpty().lowercase()
        val counts = categoryRegex.findAll(normalizedEvidence)
            .mapNotNull { match -> normalize(match.groupValues.getOrNull(1)) }
            .groupingBy { it }
            .eachCount()
        val total = counts.values.sum()
        val dominant = counts.maxWithOrNull(compareBy<Map.Entry<String, Int>> { it.value }.thenBy { priority(it.key) })
        val fallbackCategory = normalize(fallback)
        val category = dominant?.key ?: fallbackCategory ?: "unknown"
        val dominantRatio = if (total > 0 && dominant != null) dominant.value.toDouble() / total.toDouble() else 1.0
        val mixed = total >= 2 && counts.size > 1 && dominantRatio < MIXED_DOMINANCE_THRESHOLD
        return LeaderResearchCategoryEvidence(
            category = category,
            counts = counts,
            dominantRatio = dominantRatio,
            mixed = mixed
        )
    }

    private fun normalize(value: String?): String? {
        val normalized = value?.trim()?.lowercase()?.replace("_", "-") ?: return null
        return when (normalized) {
            "politics", "political" -> "politics"
            "finance", "financial", "economics", "economic" -> "finance"
            "sports", "sport", "esports", "e-sports" -> "sports"
            "crypto", "cryptocurrency", "bitcoin", "btc" -> "crypto"
            else -> normalized.takeIf { it in knownCategories }
        }
    }

    private fun priority(category: String): Int {
        return when (category) {
            "politics" -> 4
            "finance" -> 3
            "sports" -> 2
            "crypto" -> 1
            else -> 0
        }
    }

    private const val MIXED_DOMINANCE_THRESHOLD = 0.70
}
