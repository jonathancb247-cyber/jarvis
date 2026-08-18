# Voice Experience Benchmark

Status: Current / Design and Test Harness Guide

The Voice Experience Benchmark is a deterministic harness for validating future
JarvisOS voice control flow before any real microphone, speaker, STT provider,
TTS provider, cloud service or hardware is introduced.

This document describes the Phase 1 fake-only benchmark. It does not claim real
voice capability, real provider compatibility, real-world latency or audio UX
quality.

## Purpose

The benchmark protects the Voice Architecture boundary:

```text
scripted speech events
-> fake VAD / endpointing
-> fake STT
-> minimal Turn Manager
-> bounded Conversation Session
-> fake intent / confirmation outcome
-> fake TTS lifecycle
-> benchmark report
```

Voice remains an interface to JarvisOS. The benchmark must not create a second
Runtime path.

## Fake-Only Scope

Phase 1 may use:

- scripted speech events;
- fake STT partial, final, error, timeout and cancellation events;
- fake TTS start, first-audio, completion, interruption, cancellation, timeout
  and error events;
- minimal Turn Manager behavior;
- bounded in-memory Conversation Session behavior;
- fake deterministic intent and confirmation outcomes;
- deterministic simulated metrics.

Phase 1 must not use:

- microphones;
- speakers;
- wake-word engines;
- real VAD engines;
- Whisper, Groq, Gemini, Piper, Edge TTS or other real providers;
- provider credentials;
- network or cloud calls;
- hardware;
- real Drivers;
- physical mutation;
- persistent conversation memory;
- Dashboard changes.

## Scenario Families

The initial harness covers:

- normal command;
- follow-up without repeated wake word;
- partial STT followed by final STT;
- partial STT safety;
- cancellation;
- pending confirmation rejection;
- unrelated confirmation speech;
- barge-in / TTS interruption;
- ambiguous reference requiring clarification;
- ambiguous addressing with no execution;
- STT failure;
- TTS failure;
- provider timeout/unavailable behavior;
- no automatic transcript persistence;
- session expiry/reset;
- human-facing device names;
- no real physical mutation.

## Simulated Metrics

Phase 1 metrics are deterministic and simulated:

- scenario pass/fail;
- task success rate;
- scripted intent accuracy;
- clarification success;
- confirmation rejection success;
- partial-transcript safety;
- simulated endpoint-to-final latency;
- simulated response-to-first-audio latency;
- simulated barge-in latency;
- session continuity;
- safety invariant violations.

All latency values are simulated benchmark timings. They are not measurements of
real microphones, providers, audio output devices or user-perceived latency.

## Safety Invariants

The harness must assert:

- no real Driver is reached;
- no physical mutation is attempted;
- partial transcripts never execute;
- confirmation is never bypassed;
- unrelated "sí" does not confirm an action;
- raw provider exceptions do not leak;
- transcripts are not persisted;
- sessions are not restored from persistent memory;
- STT/TTS failures do not mutate DeviceState;
- Runtime remains provider-neutral and untouched;
- normal spoken output uses human-facing names, not internal device IDs.

## Reports

Benchmark reports are compact deterministic data:

- benchmark version;
- scenario ID and name;
- pass/fail;
- simulated metrics;
- safety violations;
- expected and actual state transitions where useful;
- notes.

Reports are comparison aids for future providers and versions. They are not
proof of real voice quality.

## Future Provider And Hardware Relationship

Future provider bake-offs may run the same scenario families through local STT,
cloud STT, local TTS, cloud TTS, modular voice pipelines or realtime
speech-to-speech providers.

Future hardware/audio validation may add real microphones, speakers, echo
cancellation, audio ducking and physical-device gates.

Those future phases must remain explicit. They must not be inferred from the
fake-only benchmark.
