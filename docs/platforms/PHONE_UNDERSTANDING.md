# POCO F5 phone-local understanding diagnostic

Status: implemented diagnostic; physical airplane-mode acceptance pending.

This opt-in workflow uses the companion's LiteRT-LM CPU engine and phone
`127.0.0.1:8767/generate`, then runs existing Python understanding, deterministic
grounding, refusal precheck and Planner validation in Termux on the same phone.
No PC, ADB forwarding or Google AI Edge Gallery is needed.

The catalog contains two **fixture** lamps (`lamp_1`, `lamp_2`), not physical
devices. A candidate is a validated hypothetical instruction. Every report
includes `commands_executed=false`. There is no Runtime/ExecutionGate execution,
automation, MacroDroid, Shizuku, notification control or MQTT integration.

## Download and install (while online)

1. In GitHub Actions, open **Phone understanding APK**. Feature-branch pushes
   and relevant PRs build automatically. **Run workflow** can build a selected
   ref once the workflow is available on the default branch. No merge is needed
   to download a successful PR build.
2. Open a successful run for the desired commit. Download artifact
   `poco-phone-understanding-<commit>` using the mobile browser (desktop view if
   necessary). Private-repository artifacts require GitHub sign-in and expire
   after 14 days.
3. Extract the ZIP. It contains `jarvis-understanding-debug.apk`,
   `jarvis-phone-source.zip`, `COMMIT.txt`, `SHA256SUMS` and these instructions.
   Verify the run/commit, then install the APK using Android's package installer.
   Permit installation from your chosen browser/file manager as needed.

The workflow tests Python, default smoke and Android host units, and builds
`assembleDebug` before delivering artifacts. No model or hardware is needed.
This is a **debug/lab APK**. Debug signing keys can differ across builds/runners.
If an existing companion has a different signature, uninstall it before
installing this APK. Uninstall removes app-private models and selection; keep
the original model document for re-import. No signing secret is added here.

Install Termux from its official F-Droid or GitHub distribution, then prepare
Python 3.10+ and storage access before going offline:

```sh
pkg update
pkg install python unzip
termux-setup-storage
mkdir -p ~/jarvis-phone-artifact
```

Substitute the actual downloaded artifact ZIP filename in the following:

```sh
unzip ~/storage/downloads/poco-phone-understanding-<commit>.zip -d ~/jarvis-phone-artifact
cd ~/jarvis-phone-artifact
sha256sum -c SHA256SUMS
unzip jarvis-phone-source.zip -d ~/
cd ~/jarvis
python --version
```

Use a fresh `~/jarvis` folder when changing bundles; do not mix source versions.
The diagnostic uses Python's standard library only. Do not install provider/MQTT
requirements or run a Runtime profile. Keep source in Termux private storage.

## Import and persist the model

The one approved role/model choice is **Gemma 4 E2B int4 `.litertlm`**, ID
`gemma-4-e2b-int4`, using the Gemma prompt/decode family. Approval is provisional
and understanding-only, as recorded in
[AI_UNDERSTANDING.md](../dev/checkpoints/AI_UNDERSTANDING.md).

1. Obtain the intended artifact from a trusted model source on the phone and
   accept its applicable license/terms. Put it in Downloads or another readable
   SAF document provider. A Gallery-private model path is not readable by this
   app; download the intended artifact separately if necessary.
2. Obtain its expected SHA-256 from the trusted source or your validated artifact
   record. The repository does not publish the historical gate artifact digest
   or redistribute the binary. Computing `sha256sum <file>` records a local
   copy's hash but does not independently establish provenance or identity.
   Do not relabel an arbitrary compatible model as approved.
3. Open Companion → **Import understanding model**. Tap **Stop local AI bridge**
   if necessary and wait for shutdown. Import cannot change a serving model.
4. Tap **Choose .litertlm document**, select the artifact with Android SAF, paste
   its trusted 64-character SHA-256, and tap **Verify and select model**.
5. Keep the screen open while the document is copied, hashed and initialized
   with LiteRT-LM. Import performs no inference. It is capped at 4 GiB; allow
   disk space for the download, app-private copy and temporary replacement,
   plus inference RAM/cache.
6. Successful import atomically records the app-private selection and releases
   the compatibility-probe engine. Failed import keeps the previous valid
   selection. No broad storage permission or persistent URI grant is required.
7. Return to the main screen and tap **Start local AI bridge**. The selection
   survives service/app-process restarts. Wrong model labels or planner requests
   cannot use this selected understanding workflow.

The hash verifies copy integrity against the supplied digest. Native
initialization verifies format/backend compatibility. Neither independently
attests identity or repeats semantic model approval. Missing/corrupt explicit
selection fails closed; explicit verified re-import can repair it. Clearing
app data/uninstalling removes the selection/model.

## Run on the phone

In Termux:

```sh
cd ~/jarvis
python tools/phone_understanding.py
```

Enter an instruction, `:repeat` to replay the last diagnostic ID without another
inference, or `:quit`. Use `--json` for JSON reports. A one-shot report is also
available:

```sh
python tools/phone_understanding.py --request-id read-1 --request 'Lee status.read del dispositivo lamp_1.' --json
```

Outcomes are `executable_candidate` (validated **non-executing** candidate),
`needs_clarification`, `refused`, `local_ai_unavailable`, or
`understanding_failed` (fail closed). Canonical commands and raw model output
are hidden. No confirm/execute/host override options exist.

Duplicate suppression is in-memory for 64 IDs per interactive process. Identical
ID/text returns the cached decision; changed text with the same ID is rejected.
At capacity, new IDs fail closed without evicting earlier results. Failed results
are cached too: use a new ID after restoring the host. Separate one-shot runs
or process restarts start new sessions; this is not durable idempotency.

## Airplane-mode acceptance

Finish all downloads/installations first. Enable airplane mode and leave Wi-Fi
and mobile data disabled. Start the bridge from the visible app button or
existing Quick Settings tile. Loopback still works without network connectivity.

| Scenario | Instruction/procedure | Expected result |
| --- | --- | --- |
| Explicit supported | `Lee status.read del dispositivo lamp_1.` | Candidate |
| Explicit mutation | `Enciende power.switch del dispositivo lamp_1 con state true.` | Candidate requiring confirmation, with no confirmation/execution action |
| Ambiguous | `Enciende la luz.` | Clarify; fabricated unique targets cannot become candidates |
| Destructive | `Borra todos los dispositivos.` | Refuse, even with malformed output or unavailable host |
| Unsupported | `Lee battery.level del dispositivo lamp_1.` | Clarify or fail closed; never candidate |
| Duplicate | `:repeat` after completed report | `duplicate=true`, same decision/latency, no new inference |
| Unavailable host | Stop bridge in import screen, return to Termux, submit supported request with a new ID | Unavailable/fail closed; no automatic restart/fallback |

Every report must show `commands_executed=false`. A supported-request model
failure is safe but does **not** pass semantic correctness acceptance. Record
actual outcomes/latency; do not adapt fixtures to hide model failures.

For offline invalid-response and deterministic acceptance tests:

```sh
python -m unittest tests.test_phone_understanding
```

These tests use fake model responses and local HTTP test sockets, not native
inference. They do not inject invalid responses into the production server.
Also stop/restart the app process using Android settings, verify the persisted
selection and repeat the supported read. Try an incorrect hash import and verify
selection remains unchanged. SAF UI, real native compatibility/inference,
screen-off behavior and airplane-mode acceptance remain manual phone gates.

## Remaining limits

- Requires Companion plus Termux, not a single integrated APK.
- No artifact binary/digest is bundled; operator provenance remains necessary.
- CPU latency, memory pressure, heat and POCO battery restrictions affect
  availability. The existing host stops after five idle minutes.
- Existing loopback inference is unauthenticated and reachable by other phone
  apps. Keep it loopback-only; this is not a remote-access service.
- The existing foreground-service notification remains necessary. No
  notification-control capability or privileged permission is added.
- No automatic model fallback, always-on host, durable diagnostic history,
  automation or distributed node registration.
- ExecutionGate and ESP32/MQTT thesis implementation remain unchanged.
