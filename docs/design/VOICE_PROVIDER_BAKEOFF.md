# Voice Provider Bake-Off

Status: Current / Design and Test Harness Guide

Voice Phase 2A provides a provider-neutral foundation for future STT and TTS
provider bake-offs. It does not evaluate any real provider.

## Purpose

The bake-off foundation lets JarvisOS compare future STT and TTS providers
through safe contracts before live audio, credentials, cloud calls, hardware or
Runtime integration are introduced.

The foundation extends the fake Voice Experience Benchmark with:

- provider identity and local/cloud classification;
- compact provider capability metadata;
- deterministic STT and TTS fixture metadata;
- bilingual downstream semantic/tool fixture metadata;
- normalized provider failures;
- synthetic/test metric placeholders;
- human-rating placeholders;
- compact comparable reports.

## Phase 2A Foundation-Only Scope

Phase 2A may use only mock/fake providers and deterministic fixture metadata.

Phase 2A does not:

- evaluate a real STT provider;
- evaluate a real TTS provider;
- measure real provider latency;
- validate naturalness;
- validate provider compatibility;
- use microphones or speakers;
- use network or cloud services;
- use credentials;
- select a provider.

## Provider-Neutral Contracts

STT evaluation can represent:

- provider and mode identifier;
- local/cloud classification;
- fixture identifier;
- final transcript;
- partial transcript events;
- detected language;
- confidence;
- latency metadata;
- normalized failure;
- capability metadata.

TTS evaluation can represent:

- provider and mode identifier;
- local/cloud classification;
- phrase fixture identifier;
- synthesized-output reference concept;
- first-audio timing metadata;
- total synthesis timing metadata;
- normalized failure;
- capability metadata;
- human-rating placeholders.

Downstream semantic/tool evaluation can represent:

- provider and mode identifier;
- local/cloud classification through the enclosing provider report;
- paired English/Spanish scenario identifiers;
- STT transcript correctness;
- intent correctness;
- conceptual tool selection correctness;
- argument extraction correctness;
- relative date/time normalization correctness;
- clarification quality;
- end-to-end task success;
- simulated or externally supplied latency metadata.

These contracts are intentionally not SDK-specific.

## Fixture Taxonomy

STT fixtures may represent:

- Mexican Spanish;
- neutral Spanish;
- code switching;
- short commands;
- natural phrasing;
- technical vocabulary;
- device names;
- acronyms;
- hesitation;
- self-correction;
- ambiguity.

TTS phrase fixtures may represent:

- acknowledgement;
- confirmation;
- refusal;
- warning;
- long explanation;
- human-facing device names;
- numbers and dates;
- bilingual technical terms;
- urgent but calm responses;
- repeated long-session phrases.

Phase 2A uses textual fixture metadata only. It does not include private user
recordings, public datasets or synthesized audio files.

## Bilingual Semantic / Tool Robustness

Voice provider evaluation must distinguish transcription quality from downstream
semantic usefulness. A provider can produce a correct transcript while the
downstream intent/tool layer still fails, and that must be recorded as a
semantic/tool failure rather than an STT failure.

Phase 2A includes deterministic paired English/Spanish semantic scenarios:

| Scenario | English | Spanish | Conceptual tool | Expected arguments |
| --- | --- | --- | --- | --- |
| Flashlight power | `turn on the flashlight` | `enciende la linterna` | `device_power` | `target=flashlight`, `state=on` |
| Wi-Fi settings | `open Wi-Fi settings` | `abre los ajustes de Wi-Fi` | `open_settings` | `panel=wifi` |
| Map lookup | `show Mexico City on the map` | `muestrame Ciudad de Mexico en el mapa` | `show_map` | `place=Mexico City` / `place=Ciudad de Mexico` |
| Calendar event | `create a calendar event tomorrow at 5 PM` | `crea un evento manana a las 5` | `calendar_create_event` | English: `date=tomorrow`, `time=17:00`; Spanish: `date=tomorrow`, `time=ambiguous_5` with clarification required |

The conceptual tools are benchmark concepts only. They are not JarvisOS Runtime
capabilities, Planner commands, Android API calls, external app calls or driver
operations.

Semantic/tool metrics are scored independently:

- `stt_transcription_accuracy`;
- `intent_accuracy`;
- `tool_selection_accuracy`;
- `argument_extraction_accuracy`;
- `relative_datetime_normalization`;
- `clarification_quality`;
- `end_to_end_task_success`.

Required scoring separation:

- correct transcript plus wrong conceptual tool is semantic/tool failure, not
  STT failure;
- correct conceptual tool plus malformed arguments is argument extraction
  failure;
- relative date/time failures are separate from transcript and tool selection;
- requesting machine/API-formatted user input, such as ISO timestamps, is a
  clarification UX failure;
- clarification is valid only when human-level information is genuinely missing.

Outcome tags include:

- `english_pass_spanish_fail`;
- `spanish_transcript_pass_tool_fail`;
- `relative_datetime_not_normalized`;
- `machine_formatted_clarification_requested`;
- `clarification_needed`;
- `clarification_unnecessary`.

The benchmark does not require users to speak API-formatted values. For example,
`manana a las 5` may require a human-facing AM/PM clarification; it must not
require the user to provide an ISO timestamp.

## Failure Taxonomy

Provider failures are normalized to:

- unavailable;
- timeout;
- cancelled;
- unsupported language;
- invalid input;
- quota or capacity;
- malformed output;
- provider error.

Raw provider or mock exceptions must not cross the public report boundary.

## Report Format

Reports include:

- provider name and mode;
- version or model identifier when supplied;
- local/cloud classification;
- capability summary;
- fixture set;
- STT metrics;
- TTS metrics;
- bilingual semantic/tool metrics;
- normalized failures;
- privacy notes;
- cost/quota notes;
- human-rating summary;
- known limitations;
- recommendation: continue, promising, poor fit or defer.

Reports may contain synthetic test values. Synthetic values are not real provider
performance.

## Non-Execution Guarantee

The bilingual semantic layer evaluates conceptual expected tools and arguments
only. It must not call:

- Runtime;
- Planner;
- Runtime API;
- Dashboard;
- Drivers;
- Android APIs;
- external apps;
- provider SDKs;
- network services.

Future real STT providers may supply transcripts and latency metadata to the
same semantic evaluator, but the evaluator still produces only benchmark
results.

## Privacy Rules

Phase 2A must not include:

- credentials;
- secrets;
- raw Runtime internals;
- raw DeviceState internals;
- unrelated personal data;
- private audio fixtures;
- provider-specific raw exceptions.

Credential handling, if later needed for Phase 2B, must be explicit and outside
Runtime, DeviceState, Conversation Session and benchmark reports.

## Future Phase 2B Real-Provider Evaluation

Voice Phase 2B may add opt-in real-provider evaluation using:

- prerecorded/local audio fixtures;
- file-output TTS results;
- credentials loaded through an approved secret boundary;
- skipped-by-default integration tests;
- manual human rating.

Phase 2B must still avoid live microphone/speaker integration unless separately
authorized.

Phase 2B is a provider evaluation phase, not provider selection. Valid
recommendations remain: continue, promising, poor fit or defer.

## Voice Phase 2B - First Real STT Provider Validation

The first real STT validation path reuses the existing provider-neutral STT
contracts and the opt-in Groq STT adapter. It accepts prerecorded local audio
files only.

The approved Phase 2B STT flow is:

```text
local prerecorded audio fixture
-> STTFixture
-> GroqSTTProvider
-> STTEvaluationResult
-> ProviderBakeOffReport
```

It is not a live voice path and it must never call Runtime, Planner, Runtime
API, Dashboard, Drivers, Android APIs, applications or hardware.

Real Groq STT evaluation may be run manually with an explicitly supplied local
fixture and process-local `GROQ_API_KEY`:

```bash
python tools/voice_provider_bakeoff.py groq-stt --audio voice-fixtures.local/es_mx_flashlight.wav --expected "enciende la linterna" --fixture-id es_mx_flashlight --language es
python tools/voice_provider_bakeoff.py groq-stt --audio voice-fixtures.local/en_flashlight.wav --expected "turn on the flashlight" --fixture-id en_flashlight --language en
python tools/voice_provider_bakeoff.py groq-stt-compare --audio voice-fixtures.local/es_mx_technical.wav --expected "revisando el ESP32 y el estado de MQTT" --fixture-id es_mx_technical --language es
```

Supported first-pass language hints are `es` and `en`, mapped to benchmark
fixture hints `es-MX` and `en-US`.

Recommended local fixture corpus:

- Spanish (Mexico) command;
- English equivalent command;
- paired bilingual command cases;
- technical vocabulary: ESP32, STM32, MQTT, Wi-Fi and OBD-II;
- hesitation;
- self-correction;
- genuine ambiguity;
- code switching.

These local audio fixtures remain ignored/private by default. They must not be
committed unless a later policy explicitly approves deterministic non-private
audio artifacts.

Real STT measurements may include:

- final transcript;
- word error rate or equivalent transcript accuracy;
- technical-term accuracy;
- code-switch transcription behavior;
- provider/file-pipeline latency;
- normalized STT failure;
- provider/model identity.

Downstream semantic/tool metrics may consume the transcript later through the
existing non-executing semantic evaluator, but they are not evidence that any
tool, app, Runtime capability or Android action executed.

### STT Candidates

The initial STT candidates are Groq Speech-to-Text models:

- `whisper-large-v3-turbo`;
- `whisper-large-v3`.

Both models must use the same provider adapter and fixture path. JarvisOS must
collect its own transcript, latency and accuracy results; provider-published
quality numbers are not JarvisOS benchmark evidence.

Groq credentials must be read only from `GROQ_API_KEY` in the active process
environment. The key must never be committed, logged, printed, persisted, stored
in RuntimeProfile, included in State Store, sent to AI context or included in
reports.

### TTS Candidate

The initial TTS candidate is the maintained OHF Piper local/offline TTS
package, installed outside the repository with `pip install piper-tts`.

The archived standalone Windows Piper build is not the approved Phase 2B
evaluation path unless the maintained package is proven unusable in the target
environment.

Piper evaluation is file-output only:

```text
approved phrase fixture
-> local Python executable
-> python -m piper
-> local WAV file
-> WAV validity check
-> provider-neutral result
```

No speaker playback is performed by JarvisOS. Piper configuration is
evaluation-local:

- `PIPER_EXECUTABLE` points to the local virtual-environment Python executable
  used to run `python -m piper`;
- `PIPER_VOICE_MODEL` is the maintained Piper voice ID, such as
  `es_MX-ald-medium`;
- `PIPER_DATA_DIR` points to the local Piper voice data directory;
- `PIPER_OUTPUT_DIR` optionally points to the ignored local output directory.

The `es_MX-ald-medium` voice remains an evaluation candidate only, not a
selected production JarvisOS voice. Large voice/model artifacts are not
committed by default, no automatic model download occurs inside JarvisOS, and
voice licensing must be reviewed before any redistribution.

### Local Fixture Policy

Local audio fixtures should live in an ignored directory such as:

```text
voice-fixtures.local/
```

Generated TTS output should live in an ignored directory such as:

```text
voice-output.local/
```

Private/user recordings are not committed by default. Reports should identify
fixtures through stable fixture IDs rather than sensitive full paths. Fixtures
must not include incidental conversations, credentials or unrelated private
audio.

### Real Metrics

STT real-provider metrics may include:

- final transcript;
- word error rate or equivalent;
- technical-term accuracy;
- code-switch handling;
- provider/file-pipeline latency;
- normalized failure category;
- provider/model identity.

TTS real-provider metrics may include:

- synthesis invocation latency;
- total file-pipeline synthesis time;
- output file creation success;
- WAV validity;
- generated audio duration;
- normalized failure category;
- provider/voice identity.

These timings are provider/file-pipeline timings. They are not live
conversational latency, endpointing latency or user-perceived voice UX latency.

Human naturalness, fatigue, pronunciation and pacing/prosody ratings remain
manual fields. They must not be fabricated.

### Opt-In Execution

Real provider evaluation must not run during default `python -m unittest`.

Real evaluation is triggered only through an explicit manual workflow such as:

```bash
python tools/voice_provider_bakeoff.py groq-stt --audio voice-fixtures.local/sample.wav --expected "Jarvis, enciende la lampara de la sala." --language es
python tools/voice_provider_bakeoff.py groq-stt-compare --audio voice-fixtures.local/sample.wav --expected "Jarvis, enciende la lampara de la sala." --language es
python tools/voice_provider_bakeoff.py piper-tts --text "Listo." --piper <local-python-path> --voice es_MX-ald-medium --data-dir <local-piper-data-dir>
```

Without `GROQ_API_KEY`, local fixture audio or Piper installation, real
evaluation must fail safely or skip in integration workflows. Default unit tests
remain deterministic and offline-safe.

### Real Versus Synthetic Reports

Provider reports must identify whether they contain:

- `synthetic_mock`;
- `real_provider`.

Mock metrics must never be mistaken for provider measurements. Real
file-pipeline metrics must never be described as live voice UX latency.

## Non-Claims

Voice Phase 2A does not prove:

- real STT quality;
- real TTS quality;
- real latency;
- real naturalness;
- real privacy behavior of any vendor;
- provider compatibility;
- Android tool compatibility;
- downstream app/tool execution compatibility;
- production readiness.

Voice Phase 2B still does not prove live voice readiness. It does not include
microphones, speakers, wake word, VAD, AEC, audio ducking, realtime
speech-to-speech, Runtime execution, Dashboard integration, hardware validation,
permanent provider selection or production readiness.
