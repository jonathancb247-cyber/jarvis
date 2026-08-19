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
- normalized failures;
- privacy notes;
- cost/quota notes;
- human-rating summary;
- known limitations;
- recommendation: continue, promising, poor fit or defer.

Reports may contain synthetic test values. Synthetic values are not real provider
performance.

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

The initial TTS candidate is a Piper-style local/offline TTS executable.

Piper evaluation is file-output only:

```text
approved phrase fixture
-> Piper executable
-> local WAV file
-> WAV validity check
-> provider-neutral result
```

No speaker playback is performed by JarvisOS. Piper executable, voice/model path
and output directory are local evaluation inputs. Large voice/model artifacts are
not committed by default, and voice licensing must be reviewed before any
redistribution.

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
python tools/voice_provider_bakeoff.py groq-stt --audio voice-fixtures.local/sample.wav --expected "Jarvis, enciende la lampara de la sala."
python tools/voice_provider_bakeoff.py groq-stt-compare --audio voice-fixtures.local/sample.wav --expected "Jarvis, enciende la lampara de la sala."
python tools/voice_provider_bakeoff.py piper-tts --text "Listo." --piper <local-piper-path> --voice <local-voice-model-path>
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
- production readiness.

Voice Phase 2B still does not prove live voice readiness. It does not include
microphones, speakers, wake word, VAD, AEC, audio ducking, realtime
speech-to-speech, Runtime execution, Dashboard integration, hardware validation,
permanent provider selection or production readiness.
