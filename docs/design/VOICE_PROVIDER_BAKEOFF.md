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

A later explicit phase may add opt-in real-provider evaluation using:

- prerecorded/local audio fixtures;
- file-output TTS results;
- credentials loaded through an approved secret boundary;
- skipped-by-default integration tests;
- manual human rating.

Phase 2B must still avoid live microphone/speaker integration unless separately
authorized.

## Non-Claims

Voice Phase 2A does not prove:

- real STT quality;
- real TTS quality;
- real latency;
- real naturalness;
- real privacy behavior of any vendor;
- provider compatibility;
- production readiness.
