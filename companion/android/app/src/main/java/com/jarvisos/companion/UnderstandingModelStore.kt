package com.jarvisos.companion

import java.io.File
import java.io.InputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.util.Properties

/** App-private SAF copy + atomic selection. No URI, model output or request history is persisted. */
class UnderstandingModelStore(
    private val directory: File,
    private val maximumBytes: Long = 4L * 1024 * 1024 * 1024,
) {
    data class Selection(val modelId: String, val sha256: String, val bytes: Long, val file: File)

    companion object {
        // Provisional understanding-only approval; not a universal planner/model approval.
        const val MODEL_ID = "gemma-4-e2b-int4"
        const val MODEL_LABEL = "Gemma 4 E2B int4 — provisional understanding only"
        private val DIGEST = Regex("[a-f0-9]{64}")
    }

    private val selectionFile get() = File(directory, "selection.properties")

    @Synchronized
    fun selected(): Selection? {
        if (!selectionFile.exists()) return null
        val properties = Properties().apply { selectionFile.inputStream().use { load(it) } }
        require(properties.stringPropertyNames() == setOf("model_id", "sha256", "bytes"))
        require(properties.getProperty("model_id") == MODEL_ID)
        val digest = properties.getProperty("sha256")
        require(DIGEST.matches(digest))
        val bytes = properties.getProperty("bytes").toLong()
        require(bytes in 1..maximumBytes)
        val file = modelFile(digest)
        require(file.isFile && file.length() == bytes) { "Selected model is missing or changed." }
        return Selection(MODEL_ID, digest, bytes, file)
    }

    /** Caller supplies a trusted expected hash; native initialization proves format compatibility.
     * A hash match does not independently attest model identity or repeat semantic approval.
     * validate runs off the UI thread and must release all native resources before returning.
     */
    @Synchronized
    fun importModel(source: InputStream, expectedSha256: String, validate: (File) -> Boolean): Selection {
        val expected = expectedSha256.trim().lowercase()
        require(DIGEST.matches(expected)) { "Enter the trusted artifact's 64-character SHA-256." }
        require(directory.isDirectory || directory.mkdirs())
        // An explicit verified re-import can repair corrupt metadata. Serving still fails closed.
        val previous = try { selected() } catch (_: Exception) { null }
        // Only this store's temporary files: reclaim copies abandoned by process death.
        directory.listFiles()?.filter {
            (it.name.startsWith("import-") && it.name.endsWith(".litertlm")) ||
                (it.name.startsWith("selection-") && it.name.endsWith(".tmp"))
        }?.forEach { it.delete() }
        val temporary = File.createTempFile("import-", ".litertlm", directory)
        var created: File? = null
        var metadataTemporary: File? = null
        try {
            val digest = MessageDigest.getInstance("SHA-256")
            var bytes = 0L
            source.use { input ->
                temporary.outputStream().use { output ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        if (count == 0) continue
                        bytes += count
                        require(bytes <= maximumBytes) { "Model exceeds the 4 GiB import limit." }
                        digest.update(buffer, 0, count)
                        output.write(buffer, 0, count)
                    }
                }
            }
            require(bytes > 0) { "Model is empty." }
            val actual = digest.digest().joinToString("") { "%02x".format(it) }
            require(actual == expected) { "SHA-256 mismatch; selection unchanged." }
            require(validate(temporary)) { "LiteRT-LM could not initialize this artifact; selection unchanged." }
            val target = modelFile(actual)
            val alreadyExists = target.exists()
            // Replace even an existing same-hash name with the freshly checked copy.
            Files.move(temporary.toPath(), target.toPath(),
                StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
            if (!alreadyExists) created = target
            val properties = Properties().apply {
                setProperty("model_id", MODEL_ID)
                setProperty("sha256", actual)
                setProperty("bytes", bytes.toString())
            }
            val metadata = File.createTempFile("selection-", ".tmp", directory)
            metadataTemporary = metadata
            metadata.outputStream().use { properties.store(it, "Understanding-only selection v1") }
            Files.move(metadata.toPath(), selectionFile.toPath(),
                StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
            created = null // Committed selection owns the model now.
            if (previous != null && previous.file != target) previous.file.delete()
            return Selection(MODEL_ID, actual, bytes, target)
        } finally {
            temporary.delete()
            metadataTemporary?.delete()
            created?.delete()
        }
    }

    private fun modelFile(digest: String) = File(directory, "understanding-$digest.litertlm")
}
