package com.jarvisos.companion

/**
 * Prompt/decode family for the process-owned bridge model.
 *
 * Lab evaluation can point the bridge at a different app-private `.litertlm`
 * model (for example the FunctionGemma 270M candidate). Each family owns the
 * matching hint-only prompt adapter and the matching minimal output decoder.
 * The production default remains [GEMMA] (`gemma3-1b-it-int4`), whose prompt
 * builder and JSON extractor are untouched.
 */
enum class ModelPromptFamily {
    GEMMA,
    FUNCTION_GEMMA,
    ;

    companion object {
        /**
         * Case-insensitive value lookup used by the debug-only override
         * ([DebugModelOverride.EXTRA_MODEL_FAMILY]). Returns null for unknown
         * values so callers can fail closed instead of guessing.
         */
        fun fromValue(value: String?): ModelPromptFamily? = when (value?.trim()?.lowercase()) {
            DebugModelOverride.MODEL_FAMILY_GEMMA -> GEMMA
            DebugModelOverride.MODEL_FAMILY_FUNCTION_GEMMA -> FUNCTION_GEMMA
            else -> null
        }
    }
}