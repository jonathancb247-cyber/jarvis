# Android Integration

Status: Experimental inference companion; phone-local acceptance pending

`companion/android/` provides LiteRT-LM CPU inference and a loopback-only
`POST /generate` bridge. The opt-in phone-local understanding diagnostic adds
SAF model import and existing Python deterministic validation in Termux. Gradle
flavors preserve Companion (`com.jarvisos.companion`, port 8767) and provide
Understanding Lab (`com.jarvisos.companion.understandinglab`, port 8769) for
parallel installation without replacing the original app or touching its data.

See [POCO F5 phone-local instructions](PHONE_UNDERSTANDING.md) for cloud APK
artifacts, persistent model selection, installation and airplane-mode acceptance.
This diagnostic always reports `commands_executed=false`.

No Android automation adapter, MacroDroid/Shizuku integration, distributed node
registration or real Wear OS integration is implemented. Future Android
execution requires separate capability, permission, authentication and
verification design. The current inference listener must remain loopback-only.
