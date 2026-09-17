"""Standalone concurrency stress reproducer for the ExecutionGate.

Each iteration races two confirm() calls on the same token and asserts:
- exactly one Runtime.execute() per token (never more)
- exactly one executed/execution_failed plus one rejected
- token consumed afterward (pending is None)

Run: python tools/_stress_execution_gate_claim.py [iterations]
"""

from __future__ import annotations

import sys
import threading
from types import SimpleNamespace

sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[1].as_posix())

from jarvis_core.ai.contracts import (
    ACTION_KIND_MUTATE,
    PLAN_KIND_EXECUTE,
    PLAN_SCHEMA_VERSION,
    AIActionPlan,
    AIActionStep,
)
from jarvis_core.ai.execution_gate import (
    GATE_STATUS_EXECUTED,
    GATE_STATUS_EXECUTION_FAILED,
    GATE_STATUS_REJECTED,
    ExecutionGate,
)
from jarvis_core.ai.understanding_decision import (
    EXECUTABLE_CANDIDATE,
    LocalUnderstandingDecision,
)
from jarvis_core.devices import Device, DeviceCapability, DeviceRegistry
from jarvis_core.domain import CapabilityResult
from jarvis_core.planner import DEVICE_EXECUTE_COMMAND


def lamp():
    return Device(
        id="lamp_1",
        name="Lamp",
        type="light",
        capabilities=[
            DeviceCapability("power.switch", "action", {}),
            DeviceCapability("status.read", "reading", {}),
        ],
        metadata={"room": "cuarto"},
    )


def build_decision():
    plan = AIActionPlan(
        schema_version=PLAN_SCHEMA_VERSION,
        kind=PLAN_KIND_EXECUTE,
        steps=(
            AIActionStep(
                index=0,
                canonical_command_text="device apply lamp_1 power.switch state=true",
                safe_description="Prepared power.switch on lamp_1.",
                target_device_id="lamp_1",
                capability_name="power.switch",
                action_kind=ACTION_KIND_MUTATE,
            ),
        ),
        safe_summary="Prepared a deterministic device plan.",
    )
    return LocalUnderstandingDecision(
        provider_id="p",
        model_id="m",
        status=EXECUTABLE_CANDIDATE,
        proposal_valid=True,
        resolver_kind=PLAN_KIND_EXECUTE,
        planner_kind=DEVICE_EXECUTE_COMMAND,
        plan=plan,
        commands_executed=False,
    )


class RecordingRuntime:
    def __init__(self):
        registry = DeviceRegistry()
        registry.register(lamp())
        self.context = SimpleNamespace(device_registry=registry)
        self.executions = []

    def execute(self, command, correlation_id=None):
        self.executions.append(command)
        return CapabilityResult(
            success=True,
            message="ok",
            data={
                "device_id": "lamp_1",
                "capability": "power.switch",
                "operation": "apply",
            },
        )


def race_once(decision):
    runtime = RecordingRuntime()
    gate = ExecutionGate(runtime)
    prepared = gate.prepare(decision)
    results = []
    barrier = threading.Barrier(2)

    def worker():
        barrier.wait()
        results.append(gate.confirm(prepared.confirmation_id, prepared.plan_digest))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    executed = sum(1 for r in results if r.status == GATE_STATUS_EXECUTED)
    execution_failed = sum(1 for r in results if r.status == GATE_STATUS_EXECUTION_FAILED)
    rejected = sum(1 for r in results if r.status == GATE_STATUS_REJECTED)
    runtime_calls = len(runtime.executions)
    return executed, execution_failed, rejected, runtime_calls, gate.confirmation_store.pending


def main(argv=None):
    iterations = int(argv[1]) if argv and len(argv) > 1 else 100
    decision = build_decision()
    violations = []
    for index in range(iterations):
        executed, execution_failed, rejected, runtime_calls, pending = race_once(decision)
        winners = executed + execution_failed
        if winners != 1 or rejected != 1 or runtime_calls != 1 or pending is not None:
            violations.append(
                {
                    "iteration": index,
                    "executed": executed,
                    "execution_failed": execution_failed,
                    "rejected": rejected,
                    "runtime_calls": runtime_calls,
                    "pending": pending,
                }
            )
    if violations:
        print(f"VIOLATIONS: {len(violations)}")
        for violation in violations[:10]:
            print(violation)
        return 1
    print(
        f"OK: {iterations} iterations, "
        "max Runtime calls per token == 1, winners == 1, rejected == 1, pending cleared"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))