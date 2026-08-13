# Legacy Jarvis Lessons

Status: Reference
Purpose: Preserve useful experimental knowledge from pre-JarvisOS assistants.

This document is historical evidence and design input.

Legacy behavior is not automatically approved JarvisOS architecture.

## 1. Historical Role

Previous Jarvis prototypes prioritized experience:

- natural voice interaction;
- responsiveness;
- assistant personality;
- remote interaction;
- multimedia behavior;
- experimentation with physical devices.

JarvisOS prioritizes stable architectural boundaries while preserving the best
experience lessons from those prototypes.

## 2. Voice Lessons

Legacy experiments included:

- wake-word detection;
- VAD;
- Whisper-based STT;
- Groq-backed speech/conversation experiments;
- Edge TTS;
- shorter conversational responses;
- increased speech rate;
- audio pause/resume behavior;
- browser/local audio interaction.

These are reference implementations and benchmark evidence.

They should not be ported blindly.

## 3. TTS Lesson

Previous TTS behavior was not sufficiently satisfactory as the long-term Jarvis
voice experience.

Therefore:

- legacy TTS is a baseline, not the target;
- voice quality must be evaluated experimentally;
- naturalness matters alongside raw latency;
- TTFA, interruption, pacing, prosody, and long-session fatigue matter;
- selecting a TTS engine does not complete Voice Architecture.

## 4. Conversation Lesson

Fast conversational response is valuable.

Groq and similar services may be useful as specialized conversation/STT
providers without becoming execution authorities.

Conversation and physical execution must remain separate concerns.

## 5. Audio Lesson

Legacy Jarvis experimented with pausing or reducing competing audio while Jarvis
spoke and restoring it afterward.

This concept should evolve into explicit audio/voice direction rather than
remaining ad-hoc media-control code.

## 6. Confirmation Lesson

Spoken confirmation produced useful UX.

JarvisOS should preserve conversational confirmation while leaving authorization
and mutation policy in deterministic project boundaries.

Voice is an interface to policy, not the owner of policy.

## 7. Remote Connectivity Lessons

Legacy development experimented with remote-access mechanisms such as tunneling.

Remote-access experiments prove UX possibilities but do not define production
security architecture.

Temporary tunnels may remain useful for controlled development/lab validation.

Permanent remote JarvisOS access requires explicit authentication,
authorization, network, and secret boundaries.

## 8. Architecture That Must Not Be Ported

Do not restore legacy patterns such as:

- monolithic assistant ownership of all concerns;
- LLM output directly triggering physical actions;
- extracting arbitrary free-form JSON and executing it;
- secrets embedded in normal source/configuration;
- public exposure of Runtime for convenience;
- mixing conversation, device transport, state, and execution in one component.

## 9. Reuse Classification

Legacy discoveries should be classified as:

- REUSE: concept remains directly valuable;
- REDESIGN: useful behavior, incompatible architecture;
- REFERENCE: experimental evidence only;
- MERGE: concept now belongs to a newer JarvisOS subsystem;
- RESEARCH: requires new investigation;
- DROP: obsolete or unsafe direction.

## 10. Guiding Principle

Legacy Jarvis tells us how the assistant should feel.

Modern JarvisOS determines how that experience can be implemented safely,
modularly, and maintainably.