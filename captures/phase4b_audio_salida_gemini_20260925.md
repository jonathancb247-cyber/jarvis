# Phase 4B — audio de salida de Gemini hacia XK One (implementación local, sin hardware)

Fecha: 2026-09-25
Alcance: código + tests deterministas. **Sin instalación de APK, sin TWS/TuneBuds, sin cambio de perfil Bluetooth, sin prueba física.**

## HECHO

Problema real de Phase 3: `GeminiLiveClient.onMessage()` solo consumía `part.text`.
El setup ya pedía `responseModalities = ["AUDIO"]`, así que el audio de respuesta
llegaba y se descartaba. La entrada (B2 → Opus → PCM 16 kHz → `pushPcm`) no tenía
ninguna relación con esa ausencia: entrada y salida nunca estuvieron conectadas.

Archivos nuevos:

- `app/src/main/java/com/xkone/bridge/audio/GeminiAudioSink.kt` — interfaz de salida + `GeminiAudioFormat`.
- `app/src/main/java/com/xkone/bridge/audio/PcmTrack.kt` — abstracción de `AudioTrack` y `SystemPcmTrackFactory` (`USAGE_MEDIA`, `CONTENT_TYPE_SPEECH`, streaming).
- `app/src/main/java/com/xkone/bridge/audio/AndroidAudioTrackSink.kt` — buffer acotado, hilo escritor, underrun, `stop()` idempotente.
- `app/src/main/java/com/xkone/bridge/ai/GeminiResponseAudio.kt` — parseo de `inlineData` (base64 + `mimeType`).

Archivos modificados:

- `ai/GeminiLiveClient.kt` — entrega de `inlineData` al sumidero, telemetría de audio de salida, `setSpeakResponses()`, `flushPending()` en `interrupted`, `stop()` del sumidero en `stop/onFailure/onClosed`.
- `BridgeSession.kt` — solo añade el parámetro `responseSink` inyectado.
- `ui/MainActivity.kt` — crea el sumidero en el composition root, tarjeta de telemetría, `--es xkone_speak 0|1`.

Sin cambios en: `protocol/*` (B0/B1/B2, parser, engine), `ConcentusOpusDecoder`,
`BluetoothClassicTransport`, `PcmTestRecorder`, `GeminiLiveProtocol`, `AndroidManifest.xml`.

## EVIDENCIA (local, determinista)

`.\gradlew.bat testDebugUnitTest assembleDebug --rerun-tasks` → BUILD SUCCESSFUL, 43 tasks.

```
tests=66 failures=0 errors=0
GeminiResponseAudioDeliveryTest: 12
GeminiResponseAudioTest:         9
AndroidAudioTrackSinkTest:       9
(suite Phase 3 sin cambios)     36
```

Cobertura de las 10 áreas exigidas:

| Área | Test |
|---|---|
| parsing de audio Gemini | `GeminiResponseAudioTest` (rate/channels declarados, fallback, MIME no soportado, base64 inválido, impar, cota) |
| chunks fragmentados | `los chunks fragmentados y consecutivos conservan el orden`, `reproduce los chunks fragmentados en orden y sin perdida` |
| chunks consecutivos | `acepta chunks consecutivos del mismo turno y los concatena` |
| orden de reproducción | `los chunks fragmentados y consecutivos conservan el orden` |
| stop durante reproducción | `stop durante la reproduccion libera el track y es idempotente` |
| desconexión Gemini | `el cierre del WebSocket detiene el sumidero`, `un fallo de conexion detiene el sumidero` |
| buffer acotado | `el buffer acotado descarta lo antiguo y respeta la cota`, `un chunk mayor que la cota se descarta` |
| sin `AudioRecord`/micrófono | `el sink no abre ninguna ruta de microfono ni cambia perfiles bluetooth` + manifest sin `RECORD_AUDIO` |
| Phase 3 intacta | suite previa 36/36; `la entrada B2 sigue siendo la unica fuente de audio enviado` |
| B2/Opus no se mezcla con salida | `el audio de salida no se realimenta a la entrada ni al socket` |

## INFERENCIA

- Android enruta `AudioTrack` con `USAGE_MEDIA` al dispositivo **A2DP** activo; no
  hace falta invocar ninguna API de perfil, ni SCO, ni `MODIFY_AUDIO_SETTINGS`.
- Las auditorías previas muestran A2DP `NOT_PLAYING->PLAYING` para
  `FA:00:11:19:2D:5C` y `mActiveDevice` en las gafas, y A2DP suspendido durante
  HFP/SCO: consistente con un dispositivo capaz de reproducir media, no probado
  como retorno de Gemini.

## HIPÓTESIS (pendiente del gate físico)

- Gemini devuelve `audio/pcm;rate=24000` mono. El parser acepta cualquier
  `audio/pcm` y usa 24000 mono solo si el MIME no declara `rate=`. El valor real
  queda registrado en el log.
- Los chunks de salida llegan fragmentados y consecutivos. El sumidero tolera
  ambos; el tamaño real se verá en el log.
- A2DP es viable para este caso. Si no lo es, el siguiente paso sería HFP/SCO
  (más latencia y peor calidad), y solo con evidencia.

## Procedimiento para el gate físico (NO ejecutado)

```powershell
adb install -r app\build\outputs\apk\debug\app-debug.apk
adb shell am force-stop com.xkone.bridge
adb shell am start -n com.xkone.bridge/.ui.MainActivity `
  --es xkone_mac "FA:00:11:19:2D:5C" `
  --es xkone_gemini_key "<KEY>" `
  --es xkone_gemini "1" `
  --es xkone_speak "1"
adb logcat -c
# hablar al micrófono de las gafas
adb logcat -s XK_Gemini XK_GeminiOut
```

A confirmar antes de dar la fase por buena:

1. A2DP conectado a las gafas antes de empezar, sin SCO activo.
2. MIME/rate/channels reales en el log `XK_Gemini`.
3. `bytesWritten > 0` y `bytesDropped = 0` en `XK_GeminiOut`.
4. Audio audible en las gafas.
5. `A2DP` en `dumpsys bluetooth_manager` y ausencia de SCO residual.
6. Estado del proceso y cierre limpio al terminar.

## Gate

Phase 4B queda **implementada y verificada localmente**. El cierre de Phase 4
requiere la prueba física anterior, que sigue sin autorización.
