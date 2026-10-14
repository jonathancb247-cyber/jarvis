"""Guarded local validation harness for the JarvisOS ESP32 MQTT vertical.

This harness proves one explicit guarded vertical on real hardware:

    SafeContextBuilder
    -> decide_understanding
    -> DeterministicUnderstandingResolver
    -> LocalUnderstandingDecision
    -> ExecutionGate.prepare
    -> explicit human confirmation
    -> ExecutionGate.confirm
    -> Runtime
    -> DeviceRuntimeCapability
    -> DeviceCommandRouter
    -> MQTTDeviceDriver
    -> PahoMQTTClient
    -> NanoMQ
    -> ESP32 relay_1

Design boundaries (this file is additive and changes no core behavior):

- ``ExecutionGate``, the confirmation store, ``Runtime``,
  ``DeviceRuntimeCapability``, ``DeviceCommandRouter``, ``MQTTDeviceDriver``,
  the profile schema and the firmware are all used unmodified.
- The Runtime is composed once through the existing bootstrap. The MQTT client
  is resolved by the existing deployment layer from ``JARVIS_MQTT_HOST``,
  ``JARVIS_MQTT_PORT`` and ``JARVIS_MQTT_ALLOW_LAN``. This harness never
  constructs a second MQTT stack and never bypasses that resolution.
- ``ExecutionGate`` uses the default deterministic ``Planner``. No custom
  planner is injected.
- The only harness-local intelligence is a deterministic *hint* provider. It
  emits untrusted hints and never constructs a ``Command``, an
  ``AIActionPlan`` or a ``LocalUnderstandingDecision``. The real deterministic
  resolver produces the executable candidate.
- Every mutation requires explicit human confirmation typed in this same
  running process. There is no ``--confirm`` flag, no auto-confirmation and no
  timeout-based confirmation. The confirmation store is in-memory, so prepare
  and confirm must share one process.
- Evidence recording is passive and defensive. It never mutates device state,
  never retries, and never raises into the execution path.
- Safety scope is the existing onboard LED on GPIO2 only. No mains voltage, no
  physical relay, no GPIO reassignment. Human physical observation is
  recorded separately from semantic software state.

Usage:

    python tools/run_guarded_hardware_validation.py --case confirm-on
    python tools/run_guarded_hardware_validation.py --case prepare-only --case confirm-on

"""

from __future__ import annotations

import argparse
import sys

from dataclasses import replace
from pathlib import Path
from typing import NamedTuple, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from jarvis_core.ai.context import SafeContextBuilder  # noqa: E402
from jarvis_core.ai.execution_gate import (  # noqa: E402
    GATE_STATUS_CANCELLED,
    GATE_STATUS_CONFIRMATION_REQUIRED,
    GATE_STATUS_EXECUTED,
    GATE_STATUS_REJECTED,
    ExecutionGate,
)
from jarvis_core.ai.understanding_decision import (  # noqa: E402
    EXECUTABLE_CANDIDATE,
    decide_understanding,
)
from jarvis_core.ai.understanding_resolution import (  # noqa: E402
    DeterministicUnderstandingResolver,
)
from jarvis_core.bootstrap import (  # noqa: E402
    build_runtime_from_config,
    build_runtime_from_profile,
)
from jarvis_core.configuration import RuntimeConfigurationLoader  # noqa: E402
from jarvis_core.runtime import (  # noqa: E402
    CAPABILITY_EXECUTION_COMPLETED_EVENT,
    CAPABILITY_EXECUTION_FAILED_EVENT,
    COMMAND_EXECUTION_STARTED_EVENT,
)


DEFAULT_PROFILE = "profiles/mqtt-esp32.local.json"
DEFAULT_CONFIG_PATH = REPO_ROOT / DEFAULT_PROFILE

CONFIRM_TOKEN = "CONFIRM"

DEVICE_ID = "relay_1"
CAPABILITY = "power.switch"
OPERATION = "apply"
POWER_SWITCH_STATE_KEY = "state"

STATE_STORE_OPTION = "state_store_path"

PROVIDER_ID = "harness-relay-hint-provider"
MODEL_ID = "deterministic-relay-hints-v1"

STATE_TRUE = "true"
STATE_FALSE = "false"

REQUEST_ON = "turn on relay_1"
REQUEST_OFF = "turn off relay_1"

ACTION_NONE = "none"
ACTION_CONFIRM = "confirm"
ACTION_REPLAY = "confirm-replay"
ACTION_WRONG_ID = "confirm-wrong-id"
ACTION_WRONG_DIGEST = "confirm-wrong-digest"
ACTION_CANCEL = "cancel-then-confirm"

EXPECT_REJECT_CONFIRMATION = "confirmation_not_found"
EXPECT_REJECT_DIGEST = "confirmation_digest_mismatch"


class CaseSpec(NamedTuple):
    """One explicit validation case."""

    name: str
    request: str
    hint_state: str
    action: str
    prompt_human: bool
    expects_runtime_invocation: bool


CASES = {
    "prepare-only": CaseSpec(
        "prepare-only", REQUEST_ON, STATE_TRUE, ACTION_NONE, False, False
    ),
    "confirm-on": CaseSpec(
        "confirm-on", REQUEST_ON, STATE_TRUE, ACTION_CONFIRM, True, True
    ),
    "replay": CaseSpec(
        "replay", REQUEST_ON, STATE_TRUE, ACTION_REPLAY, True, True
    ),
    "confirm-off": CaseSpec(
        "confirm-off", REQUEST_OFF, STATE_FALSE, ACTION_CONFIRM, True, True
    ),
    "wrong-id": CaseSpec(
        "wrong-id", REQUEST_ON, STATE_TRUE, ACTION_WRONG_ID, True, False
    ),
    "wrong-digest": CaseSpec(
        "wrong-digest", REQUEST_ON, STATE_TRUE, ACTION_WRONG_DIGEST, True, False
    ),
    "cancel-confirm": CaseSpec(
        "cancel-confirm", REQUEST_ON, STATE_TRUE, ACTION_CANCEL, False, False
    ),
}

CASE_ORDER = tuple(CASES)


class RelayPowerHintProvider:
    """Harness-local deterministic *hint* provider.

    It emits only untrusted hints. It never builds a ``Command``, an
    ``AIActionPlan`` or a ``LocalUnderstandingDecision``. The deterministic
    resolver owns candidate grounding and plan construction.
    """

    def __init__(self, hint_state: str):
        self._hint_state = hint_state

    def extract_understanding(self, context):
        return {
            "intent": "mutate",
            "referenced_device_text": DEVICE_ID,
            "referenced_device_id": DEVICE_ID,
            "capability_hint": CAPABILITY,
            "operation_hint": OPERATION,
            "raw_arguments": [[POWER_SWITCH_STATE_KEY, self._hint_state]],
            "safe_explanation": "Harness hint for the guarded relay validation.",
        }


class Evidence:
    """Passive, defensive observation recorder.

    Every method swallows its own failures. Evidence collection must never
    break, delay or alter the execution path it observes.
    """

    def __init__(self):
        self.entries = []
        self.runtime_invocations = 0

    def record(self, kind: str, detail: Optional[dict] = None):
        try:
            entry = {"kind": str(kind)}
            if isinstance(detail, dict):
                entry.update(detail)
            self.entries.append(entry)
            return entry
        except Exception:
            return None

    def count_runtime_invocation(self):
        try:
            self.runtime_invocations += 1
        except Exception:
            return None

    def observe_runtime_event(self, event):
        """EventBus handler.

        ``EventBus.publish`` calls handlers directly without swallowing
        exceptions, so this handler must never raise.
        """
        try:
            event_type = getattr(event, "type", "")
            if event_type == COMMAND_EXECUTION_STARTED_EVENT:
                self.count_runtime_invocation()
            payload = getattr(event, "payload", {})
            safe_payload = {}
            if isinstance(payload, dict):
                for key in ("command", "capability", "success", "error"):
                    if key in payload:
                        safe_payload[key] = payload[key]
            self.record(
                "runtime_event",
                {
                    "type": event_type,
                    "correlation_id": getattr(event, "correlation_id", None),
                    "payload": safe_payload,
                },
            )
        except Exception:
            return None

    def failures(self):
        try:
            return [e for e in self.entries if e.get("kind", "").endswith("_failed")]
        except Exception:
            return []


class GuardedHardwareValidation:
    """Runs ordered validation cases against one Runtime and one gate."""

    def __init__(self, runtime, evidence: Evidence):
        self.runtime = runtime
        self.evidence = evidence
        # Default deterministic Planner. No custom planner is injected.
        self.gate = ExecutionGate(runtime)
        self._subscribe()

    def _subscribe(self):
        bus = getattr(self.runtime.context, "event_bus", None)
        if bus is None:
            self.evidence.record("subscribe_failed", {"reason": "no event bus"})
            return
        for event_type in (
            COMMAND_EXECUTION_STARTED_EVENT,
            CAPABILITY_EXECUTION_COMPLETED_EVENT,
            CAPABILITY_EXECUTION_FAILED_EVENT,
        ):
            try:
                bus.subscribe(event_type, self.evidence.observe_runtime_event)
            except Exception:
                self.evidence.record(
                    "subscribe_failed", {"event_type": str(event_type)}
                )

    # -- observation -----------------------------------------------------

    def state_projection(self):
        try:
            device = self.runtime.context.device_registry.get(DEVICE_ID)
        except Exception:
            self.evidence.record("state_read_failed", {"device_id": DEVICE_ID})
            return None
        state = getattr(device, "state", None)
        if state is None:
            return None
        try:
            return {
                "status": state.status,
                "properties": dict(state.properties),
            }
        except Exception:
            self.evidence.record("state_read_failed", {"device_id": DEVICE_ID})
            return None

    # -- understanding ---------------------------------------------------

    def resolve(self, request: str, hint_state: str):
        """Run the real understanding chain for one request."""
        registry = self.runtime.context.device_registry
        provider = RelayPowerHintProvider(hint_state)
        try:
            context = SafeContextBuilder().build(request, registry)
        except Exception:
            self.evidence.record("resolver_failed", {"request": request})
            return None
        try:
            decision = decide_understanding(
                provider,
                context,
                provider_id=PROVIDER_ID,
                model_id=MODEL_ID,
                resolver=DeterministicUnderstandingResolver(),
            )
        except Exception:
            self.evidence.record("resolver_failed", {"request": request})
            return None
        safe_summary = None
        if getattr(decision, "plan", None) is not None:
            safe_summary = getattr(decision.plan, "safe_summary", None)
        self.evidence.record(
            "decision",
            {
                "request": request,
                "hint_state": hint_state,
                "status": getattr(decision, "status", None),
                "safe_summary": safe_summary,
            },
        )
        return decision

    # -- display ---------------------------------------------------------

    def display(self, title: str, request: str, decision, prepared):
        print("")
        print("=" * 68)
        print(title)
        print("=" * 68)
        print("REQUEST           :", request)
        print(
            "DECISION STATUS   :",
            getattr(decision, "status", None) if decision is not None else None,
        )
        print("DEVICE            :", getattr(prepared, "device_id", None))
        print("CAPABILITY        :", getattr(prepared, "capability", None))
        print("ARGUMENTS         :", getattr(prepared, "arguments", None))
        summary = None
        if decision is not None and getattr(decision, "plan", None) is not None:
            summary = getattr(decision.plan, "safe_summary", None)
        print("SAFE SUMMARY      :", summary)
        print("CONFIRMATION ID   :", getattr(prepared, "confirmation_id", None))
        print("PLAN DIGEST       :", getattr(prepared, "plan_digest", None))

    def prompt(self) -> bool:
        print("")
        print("-" * 68)
        print("Type exactly:")
        print("    " + CONFIRM_TOKEN)
        print("to execute the displayed action.")
        print("Any other input will not execute.")
        try:
            answer = input("> ")
        except (EOFError, KeyboardInterrupt):
            print("")
            return False
        return answer.strip() == CONFIRM_TOKEN

    # -- gate actions ----------------------------------------------------

    @staticmethod
    def _corrupt(value: str) -> str:
        """Derive a deliberately wrong value from a real one."""
        if not value:
            return "invalid"
        return value[:-1] + ("0" if value[-1] != "0" else "1")

    def confirm(self, prepared):
        return self.gate.confirm(
            prepared.confirmation_id, prepared.plan_digest
        )

    def report_gate(self, label: str, result):
        self.evidence.record(
            "gate_result",
            {
                "label": label,
                "status": getattr(result, "status", None),
                "success": getattr(result, "success", None),
                "commands_executed": getattr(result, "commands_executed", None),
                "error": getattr(result, "error", None),
                "reason": getattr(result, "reason", None),
            },
        )
        print("")
        print("GATE RESULT       :", label)
        print("  status          :", getattr(result, "status", None))
        print("  success         :", getattr(result, "success", None))
        print("  commands_run    :", getattr(result, "commands_executed", None))
        print("  error           :", getattr(result, "error", None))
        print("  reason          :", getattr(result, "reason", None))
        print("  message         :", getattr(result, "message", None))
        runtime_result = getattr(result, "runtime_result", None)
        if runtime_result is not None:
            data = getattr(runtime_result, "data", None)
            state = data.get("state") if isinstance(data, dict) else None
            print("  capability      :", getattr(runtime_result, "message", None))
            print("  capability_err  :", getattr(runtime_result, "error", None))
            print("  device_state    :", state)
        return runtime_result

    # -- one case --------------------------------------------------------

    def run_case(self, case: CaseSpec) -> str:
        self.evidence.record("case_start", {"case": case.name})
        invocations_before = self.evidence.runtime_invocations
        state_before = self.state_projection()

        decision = self.resolve(case.request, case.hint_state)
        if decision is None or getattr(decision, "status", None) != EXECUTABLE_CANDIDATE:
            self.display(
                "CASE %s - NOT EXECUTABLE" % case.name,
                case.request,
                decision,
                _EMPTY_PREPARED,
            )
            print("")
            print("OUTCOME           : REFUSED BEFORE PREPARE (no mutation)")
            self.evidence.record(
                "case_result", {"case": case.name, "outcome": "refused"}
            )
            return "fail"

        prepared = self.gate.prepare(decision)
        self.display(
            "CASE %s - PREPARED (NOT EXECUTED)" % case.name,
            case.request,
            decision,
            prepared,
        )
        if getattr(prepared, "status", None) != GATE_STATUS_CONFIRMATION_REQUIRED:
            self.report_gate("prepare", prepared)
            self.evidence.record(
                "case_result",
                {"case": case.name, "outcome": "prepare_not_required"},
            )
            return "fail"

        action = case.action

        if action == ACTION_NONE:
            print("")
            print("OUTCOME           : PREPARED ONLY")
            print("No confirmation requested, therefore no Runtime call and")
            print("no physical mutation. The pending token remains in memory")
            print("until this process ends or the next prepare replaces it.")
            self.evidence.record(
                "case_result", {"case": case.name, "outcome": "prepared_only"}
            )
            return self._finish(
                case, invocations_before, state_before, "pass"
            )

        if action == ACTION_CANCEL:
            cancelled = self.gate.cancel(prepared.confirmation_id)
            self.report_gate("cancel", cancelled)
            after_cancel = self.confirm(prepared)
            self.report_gate("confirm-after-cancel", after_cancel)
            ok = (
                getattr(cancelled, "status", None) == GATE_STATUS_CANCELLED
                and getattr(after_cancel, "status", None) == GATE_STATUS_REJECTED
            )
            print("")
            print("OUTCOME           :", "PASS" if ok else "FAIL")
            print("A cancelled confirmation must never execute.")
            self.evidence.record(
                "case_result",
                {"case": case.name, "outcome": "pass" if ok else "fail"},
            )
            return self._finish(
                case, invocations_before, state_before, "pass" if ok else "fail"
            )

        # Every remaining action is a real mutation attempt and therefore
        # requires explicit human confirmation in this same process.
        if case.prompt_human:
            if not self.prompt():
                cancelled = self.gate.cancel(prepared.confirmation_id)
                self.report_gate("cancel-non-confirm", cancelled)
                print("")
                print("OUTCOME           : NOT CONFIRMED - no mutation")
                print(
                    "This is a safe outcome, not a harness defect. The"
                )
                print(
                    "confirmation was declined, so nothing executed."
                )
                self.evidence.record(
                    "case_result",
                    {"case": case.name, "outcome": "not_confirmed"},
                )
                return self._finish(
                    case, invocations_before, state_before, "skipped"
                )

        if action == ACTION_CONFIRM:
            result = self.confirm(prepared)
            self.report_gate("confirm", result)
            ok = getattr(result, "status", None) == GATE_STATUS_EXECUTED
            print("")
            print("OUTCOME           :", "EXECUTED" if ok else "NOT EXECUTED")
            print(
                "Transport success is reported above and is NOT asserted by"
            )
            print(
                "this harness. Physical LED state requires human observation."
            )
            self.evidence.record(
                "case_result",
                {"case": case.name, "outcome": "executed" if ok else "not_executed"},
            )
            return self._finish(
                case, invocations_before, state_before, "pass" if ok else "fail"
            )

        if action == ACTION_REPLAY:
            first = self.confirm(prepared)
            self.report_gate("confirm-first", first)
            replayed = self.confirm(prepared)
            self.report_gate("confirm-replay", replayed)
            ok = (
                getattr(first, "status", None) == GATE_STATUS_EXECUTED
                and getattr(replayed, "status", None) == GATE_STATUS_REJECTED
                and getattr(replayed, "reason", None) == EXPECT_REJECT_CONFIRMATION
            )
            print("")
            print("OUTCOME           :", "PASS" if ok else "FAIL")
            print(
                "A consumed confirmation must not execute a second time."
            )
            self.evidence.record(
                "case_result",
                {"case": case.name, "outcome": "pass" if ok else "fail"},
            )
            return self._finish(
                case, invocations_before, state_before, "pass" if ok else "fail"
            )

        if action == ACTION_WRONG_ID:
            result = self.gate.confirm(
                self._corrupt(prepared.confirmation_id), prepared.plan_digest
            )
            self.report_gate("confirm-wrong-id", result)
            ok = (
                getattr(result, "status", None) == GATE_STATUS_REJECTED
                and getattr(result, "reason", None) == EXPECT_REJECT_CONFIRMATION
            )
            print("")
            print("OUTCOME           :", "PASS" if ok else "FAIL")
            print("A wrong confirmation id must never execute.")
            self.evidence.record(
                "case_result",
                {"case": case.name, "outcome": "pass" if ok else "fail"},
            )
            return self._finish(
                case, invocations_before, state_before, "pass" if ok else "fail"
            )

        if action == ACTION_WRONG_DIGEST:
            result = self.gate.confirm(
                prepared.confirmation_id, self._corrupt(prepared.plan_digest)
            )
            self.report_gate("confirm-wrong-digest", result)
            ok = (
                getattr(result, "status", None) == GATE_STATUS_REJECTED
                and getattr(result, "reason", None) == EXPECT_REJECT_DIGEST
            )
            print("")
            print("OUTCOME           :", "PASS" if ok else "FAIL")
            print("A wrong plan digest must never execute.")
            self.evidence.record(
                "case_result",
                {"case": case.name, "outcome": "pass" if ok else "fail"},
            )
            return self._finish(
                case, invocations_before, state_before, "pass" if ok else "fail"
            )

        self.evidence.record(
            "case_failed", {"case": case.name, "reason": "unknown action"}
        )
        return "fail"

    def _finish(self, case, invocations_before, state_before, base_verdict) -> str:
        """Enforce the Runtime-invocation expectation and return a verdict."""
        used = self.evidence.runtime_invocations - invocations_before
        state_after = self.state_projection()
        print("")
        print("EVIDENCE")
        print("  runtime_invocations:", used)
        print("  expected           :", 1 if case.expects_runtime_invocation else 0)
        print("  state_before       :", state_before)
        print("  state_after        :", state_after)
        expectation_ok = used == (1 if case.expects_runtime_invocation else 0)
        print("  invocation_match   :", expectation_ok)
        if base_verdict == "skipped":
            verdict = "skipped"
        elif base_verdict == "pass" and expectation_ok:
            verdict = "pass"
        else:
            verdict = "fail"
        print("  verdict            :", verdict)
        self.evidence.record(
            "case_evidence",
            {
                "case": case.name,
                "runtime_invocations": used,
                "state_before": state_before,
                "state_after": state_after,
                "verdict": verdict,
            },
        )
        return verdict


class _EmptyPrepared:
    """Safe stand-in when prepare never ran."""

    device_id = None
    capability = None
    arguments = None
    confirmation_id = None
    plan_digest = None
    status = None
    success = False
    commands_executed = False
    error = None
    reason = None
    message = None
    runtime_result = None


_EMPTY_PREPARED = _EmptyPrepared()


def compose_runtime(config_path: Path, state_mode: str):
    """Compose one Runtime through the existing bootstrap.

    ``fresh`` (default) composes without restoring any persisted semantic
    state, using only public configuration APIs. ``profile`` uses
    ``build_runtime_from_config`` unchanged, which honors the profile's
    configured state store.
    """
    config_path = Path(config_path)
    if state_mode == "profile":
        runtime = build_runtime_from_config(str(config_path))
        return runtime, "profile state store honored (build_runtime_from_config)"
    profile = RuntimeConfigurationLoader().load(config_path)
    runtime_options = {
        key: value
        for key, value in (profile.runtime_options or {}).items()
        if key != STATE_STORE_OPTION
    }
    fresh_profile = replace(profile, runtime_options=runtime_options)
    runtime = build_runtime_from_profile(
        fresh_profile, base_directory=config_path.parent
    )
    return runtime, "no state store: persisted DeviceState is not restored"


def main(argv=None) -> int:
    args = _parse_args(argv)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (REPO_ROOT / config_path).resolve()

    print("=" * 68)
    print("GUARDED HARDWARE VALIDATION HARNESS")
    print("=" * 68)
    print("profile      :", config_path)
    print("device       :", DEVICE_ID, CAPABILITY, OPERATION)
    print("safety scope : onboard LED / GPIO2 only")
    print(
        "broker       : resolved by the existing deployment layer from"
    )
    print(
        "               JARVIS_MQTT_HOST / JARVIS_MQTT_PORT /"
    )
    print("               JARVIS_MQTT_ALLOW_LAN")

    try:
        runtime, state_note = compose_runtime(config_path, args.state)
    except Exception as error:
        print("error: could not compose runtime: %s" % type(error).__name__)
        return 2

    print("state store  :", state_note)
    print(
        "semantic note: this harness never fabricates device state from"
    )
    print(
        "               human visual observation. Physical confirmation is"
    )
    print("               recorded separately by the operator.")

    evidence = Evidence()
    harness = GuardedHardwareValidation(runtime, evidence)

    results = []
    try:
        for name in args.case:
            spec = CASES[name]
            try:
                results.append((name, harness.run_case(spec)))
            except KeyboardInterrupt:
                print("")
                print("interrupted; no further cases will run.")
                break
    finally:
        _summary(harness, evidence, results)
        try:
            runtime.shutdown()
        except Exception:
            pass
    if not results:
        return 1
    return 0 if all(verdict != "fail" for _, verdict in results) else 1


def _summary(harness, evidence, results):
    print("")
    print("=" * 68)
    print("HARNESS SUMMARY")
    print("=" * 68)
    for name, verdict in results:
        print("  %-16s %s" % (name, verdict.upper()))
    print("")
    print("total runtime invocations:", evidence.runtime_invocations)
    print("recorded evidence entries:", len(evidence.entries))
    failures = evidence.failures()
    if failures:
        print("evidence collection problems:", len(failures))
    print("final device state         :", harness.state_projection())


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python tools/run_guarded_hardware_validation.py",
        description=(
            "Guarded local validation of the JarvisOS ESP32 MQTT vertical: "
            "understanding -> ExecutionGate.prepare -> explicit human "
            "confirmation -> ExecutionGate.confirm -> Runtime -> real MQTT -> "
            "NanoMQ -> ESP32."
        ),
        epilog=(
            "There is no --confirm flag. Every mutation requires typing CONFIRM "
            "in this same running process, because the confirmation store is "
            "in-memory."
        ),
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=list(CASE_ORDER),
        required=True,
        help="Validation case to run. Repeat to run an ordered sequence.",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_PROFILE,
        help="Declarative MQTT profile used to compose the Runtime.",
    )
    parser.add_argument(
        "--state",
        choices=("fresh", "profile"),
        default="fresh",
        help=(
            "fresh (default) composes without restoring persisted DeviceState; "
            "profile uses build_runtime_from_config and honors the profile "
            "state store."
        ),
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())