package com.jarvisos.companion

import android.content.Intent
import android.util.Log
import java.io.File

/**
 * Debug-only, opt-in bridge model override for lab evaluation.
 *
 * The production bridge always serves the default `gemma3-1b-it-int4.litertlm`
 * under app-private files. A debuggable build may point the bridge at a
 * different app-private `.litertlm` file for a single process lifetime by
 * supplying explicit extras on the [LocalAIHostService] start request:
 *
 *     com.jarvisos.companion.extra.DEBUG_MODEL_FILENAME
 *     com.jarvisos.companion.extra.DEBUG_MODEL_FAMILY
 *
 * or, alternatively, an absolute app-private path:
 *
 *     com.jarvisos.companion.extra.DEBUG_MODEL_PATH
 *
 * Safety rules (fail closed):
 * - a non-debuggable build never accepts an override (release behavior is
 *   default-path-only, even if the extras were sent);
 * - a model already loaded in the process can never be silently swapped;
 * - the target must resolve inside the app-private files directory (traversal
 *   is rejected before any file access);
 * - the target must exist when the bridge starts (a missing target rejects the
 *   start; it never falls back to a different model behind the caller's back);
 * - an unknown family value is rejected (never guessed);
 * - with no extras the result is [Result.Ignored] and the default path is used
 *   unchanged.
 *
 * This is intentionally NOT a model selector: there is no scanning, no
 * enumeration, no UI, and no persistence. Every start re-evaluates the extras
 * from scratch; a restart without extras (or in a non-debug build) returns to
 * the unaffected default path.
 */
object DebugModelOverride {

    const val EXTRA_MODEL_FILENAME = "com.jarvisos.companion.extra.DEBUG_MODEL_FILENAME"
    const val EXTRA_MODEL_PATH = "com.jarvisos.companion.extra.DEBUG_MODEL_PATH"
    const val EXTRA_MODEL_FAMILY = "com.jarvisos.companion.extra.DEBUG_MODEL_FAMILY"

    const val MODEL_FAMILY_GEMMA = "gemma"
    const val MODEL_FAMILY_FUNCTION_GEMMA = "functiongemma"
    const val MODEL_FAMILY_QWEN = "qwen"

    const val TAG = "JarvisOSGemma"

    sealed interface Result {
        /** No override requested; keep the default path and family untouched. */
        data object Ignored : Result

        /** Override accepted for this process lifetime. */
        data class Applied(val target: String, val family: ModelPromptFamily) : Result

        /** Override rejected; the caller must not start the bridge. */
        data class Rejected(val message: String) : Result
    }

    /**
     * Resolve a service start [intent] against the debug-only override contract.
     * The Intent overload delegates to the pure [resolve] so host tests can
     * exercise every pass/fail branch without Android stubs (host unit tests
     * return null/defaults for `Intent.get*Extra`).
     */
    fun resolve(
        intent: Intent?,
        appDebuggable: Boolean,
        filesDirAbsolutePath: String,
        modelAlreadyLoaded: Boolean,
    ): Result = resolve(
        requestedFilename = intent?.getStringExtra(EXTRA_MODEL_FILENAME),
        requestedPath = intent?.getStringExtra(EXTRA_MODEL_PATH),
        requestedFamily = intent?.getStringExtra(EXTRA_MODEL_FAMILY),
        appDebuggable = appDebuggable,
        filesDirAbsolutePath = filesDirAbsolutePath,
        modelAlreadyLoaded = modelAlreadyLoaded,
    )

    /**
     * Pure resolution of an explicit model override.
     *
     * @param requestedFilename app-private filename (takes precedence over
     *   [requestedPath]); blank counts as absent.
     * @param requestedPath absolute app-private `.litertlm` path; blank counts
     *   as absent.
     * @param requestedFamily family value ([MODEL_FAMILY_GEMMA] or
     *   [MODEL_FAMILY_FUNCTION_GEMMA]); blank defaults to [MODEL_FAMILY_GEMMA].
     * @param appDebuggable whether the running build is debuggable.
     * @param filesDirAbsolutePath the app-private files directory.
     * @param modelAlreadyLoaded whether the process already holds a loaded model.
     */
    fun resolve(
        requestedFilename: String?,
        requestedPath: String?,
        requestedFamily: String?,
        appDebuggable: Boolean,
        filesDirAbsolutePath: String,
        modelAlreadyLoaded: Boolean,
    ): Result {
        val filename = requestedFilename?.trim().orEmpty()
        val path = requestedPath?.trim().orEmpty()
        val hasFilename = filename.isNotEmpty()
        val hasPath = path.isNotEmpty()
        if (!hasFilename && !hasPath) {
            return Result.Ignored
        }
        if (hasFilename && hasPath) {
            return Result.Rejected("Provide either DEBUG_MODEL_FILENAME or DEBUG_MODEL_PATH, not both.")
        }
        if (!appDebuggable) {
            return Result.Rejected("Model override requires a debuggable build.")
        }
        if (modelAlreadyLoaded) {
            return Result.Rejected("Model is already loaded; it cannot be swapped safely.")
        }
        if (filesDirAbsolutePath.isBlank()) {
            return Result.Rejected("App files directory is not configured.")
        }

        val family = ModelPromptFamily.fromValue(requestedFamily)
            ?: if (requestedFamily.isNullOrBlank()) {
                ModelPromptFamily.GEMMA
            } else {
                return Result.Rejected("Unknown model family '${requestedFamily.trim()}'.")
            }

        val canonicalDir = canonicalOrNull(File(filesDirAbsolutePath))
            ?: return Result.Rejected("App files directory is not resolvable.")
        if (!canonicalDir.isDirectory) {
            return Result.Rejected("App files directory does not exist.")
        }

        val candidate = if (hasFilename) {
            if (filename.contains('/') || filename.contains('\\')) {
                return Result.Rejected("DEBUG_MODEL_FILENAME must be a bare filename.")
            }
            File(canonicalDir, filename)
        } else {
            File(path)
        }

        val canonicalTarget = canonicalOrNull(candidate)
            ?: return Result.Rejected("Model override path is not resolvable: $candidate")
        val dirPrefix = canonicalDir.path + File.separator
        if (canonicalTarget.path != canonicalDir.path && !canonicalTarget.path.startsWith(dirPrefix)) {
            return Result.Rejected("Model override must live inside the app-private files directory.")
        }
        if (!canonicalTarget.isFile) {
            return Result.Rejected("Model override file does not exist: ${canonicalTarget.path}")
        }

        return Result.Applied(canonicalTarget.path, family)
    }

    private fun canonicalOrNull(file: File): File? = try {
        file.canonicalFile
    } catch (error: Exception) {
        Log.w(TAG, "Failed to canonicalize model override path: $file", error)
        null
    }
}