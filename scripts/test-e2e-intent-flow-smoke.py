#!/usr/bin/env python3
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def require_fields(label: str, payload: dict[str, Any], fields: list[str]) -> None:
    missing = [f for f in fields if f not in payload]
    if missing:
        raise RuntimeError(f"{label} missing fields: {missing}")


@dataclass
class MockSessiond:
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    tasks: dict[str, dict[str, Any]] = field(default_factory=dict)

    def create_session(self, user_id: str) -> dict[str, Any]:
        session_id = f"session-{uuid.uuid4().hex[:12]}"
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": utc_now(),
            "status": "active",
        }
        self.sessions[session_id] = session
        return session

    def create_task(self, session_id: str, intent: str) -> dict[str, Any]:
        task_id = f"task-{uuid.uuid4().hex[:12]}"
        task = {
            "task_id": task_id,
            "session_id": session_id,
            "intent": intent,
            "state": "planned",
            "created_at": utc_now(),
        }
        self.tasks[task_id] = task
        return task

    def update_task_state(self, task_id: str, new_state: str, reason: str | None = None) -> dict[str, Any]:
        task = self.tasks[task_id]
        task["state"] = new_state
        if reason:
            task["state_reason"] = reason
        task["updated_at"] = utc_now()
        return task


@dataclass
class MockPolicyd:
    evaluations: list[dict[str, Any]] = field(default_factory=list)
    tokens: dict[str, dict[str, Any]] = field(default_factory=dict)

    def evaluate(
        self,
        user_id: str,
        session_id: str,
        task_id: str,
        capability_id: str,
        execution_location: str = "local",
    ) -> dict[str, Any]:
        decision = {
            "decision": "allowed",
            "capability_id": capability_id,
            "execution_location": execution_location,
            "reason": "policy-allowed-default",
            "requires_approval": False,
            "taint_summary": "",
        }
        envelope = {
            "decision": decision,
            "approval_lane": "standard",
            "taint_hint": "",
            "approval_ref": None,
        }
        self.evaluations.append({
            "user_id": user_id,
            "session_id": session_id,
            "task_id": task_id,
            "capability_id": capability_id,
            "envelope": envelope,
            "evaluated_at": utc_now(),
        })
        return envelope

    def issue_token(
        self,
        user_id: str,
        session_id: str,
        task_id: str,
        capability_id: str,
        execution_location: str = "local",
    ) -> dict[str, Any]:
        token_id = f"tok-{uuid.uuid4().hex[:16]}"
        token = {
            "token": token_id,
            "user_id": user_id,
            "session_id": session_id,
            "task_id": task_id,
            "capability_id": capability_id,
            "execution_location": execution_location,
            "issued_at": utc_now(),
            "valid": True,
            "taint_summary": "",
        }
        self.tokens[token_id] = token
        return token

    def verify_token(self, token_id: str) -> dict[str, Any]:
        token = self.tokens.get(token_id)
        if token is None:
            return {"valid": False, "reason": "token-not-found"}
        return {"valid": True, "token": token}


@dataclass
class MockRuntimed:
    routes: list[dict[str, Any]] = field(default_factory=list)

    def resolve_route(self, preferred_backend: str | None = None) -> dict[str, Any]:
        selected = preferred_backend or "local-cpu"
        route = {
            "selected_backend": selected,
            "allow_remote": False,
            "route_state": f"{selected}-routed",
            "resolved_at": utc_now(),
        }
        self.routes.append(route)
        return route


@dataclass
class MockAgentd:
    sessiond: MockSessiond
    policyd: MockPolicyd
    runtimed: MockRuntimed
    plans: dict[str, dict[str, Any]] = field(default_factory=dict)

    def plan_for_task(self, session_id: str, task_id: str, intent: str) -> dict[str, Any]:
        capability = self._infer_capability(intent)
        plan = {
            "plan_id": f"plan-{uuid.uuid4().hex[:12]}",
            "session_id": session_id,
            "task_id": task_id,
            "intent": intent,
            "candidate_capabilities": [capability],
            "steps": [
                {
                    "step_id": f"step-{uuid.uuid4().hex[:8]}",
                    "capability_id": capability,
                    "status": "planned",
                    "execution_path": "local",
                }
            ],
            "created_at": utc_now(),
        }
        self.plans[task_id] = plan
        return plan

    def submit_intent(self, user_id: str, intent: str, session_id: str | None = None) -> dict[str, Any]:
        if session_id and session_id in self.sessiond.sessions:
            session = self.sessiond.sessions[session_id]
        else:
            session = self.sessiond.create_session(user_id)

        task = self.sessiond.create_task(session["session_id"], intent)
        plan = self.plan_for_task(session["session_id"], task["task_id"], intent)
        primary_capability = plan["candidate_capabilities"][0]

        policy = self.policyd.evaluate(
            user_id=user_id,
            session_id=session["session_id"],
            task_id=task["task_id"],
            capability_id=primary_capability,
        )

        execution_token = None
        if policy["decision"]["decision"] == "allowed":
            self.sessiond.update_task_state(task["task_id"], "approved", "policy-allowed-provider-resolved")
            plan["steps"][0]["status"] = "approved"
            execution_token = self.policyd.issue_token(
                user_id=user_id,
                session_id=session["session_id"],
                task_id=task["task_id"],
                capability_id=primary_capability,
            )

        route = self.runtimed.resolve_route(preferred_backend="local-cpu")

        provider_resolution = {
            "selected": {
                "provider_id": f"system.intent.local",
                "execution_location": "local",
                "capability_id": primary_capability,
            },
            "candidates": 1,
        }

        return {
            "session": session,
            "task": self.sessiond.tasks[task["task_id"]],
            "plan": plan,
            "policy": policy,
            "route": route,
            "provider_resolution": provider_resolution,
            "execution_token": execution_token,
        }

    def _infer_capability(self, intent: str) -> str:
        lower = intent.lower()
        if any(k in lower for k in ("file", "open", "read", "write")):
            return "provider.fs.open"
        if any(k in lower for k in ("screen", "share", "capture")):
            return "device.capture.request"
        if any(k in lower for k in ("infer", "model", "generate")):
            return "runtime.infer.submit"
        return "system.intent.execute"


def test_intent_creates_session_and_task() -> None:
    sessiond = MockSessiond()
    policyd = MockPolicyd()
    runtimed = MockRuntimed()
    agentd = MockAgentd(sessiond=sessiond, policyd=policyd, runtimed=runtimed)

    result = agentd.submit_intent(user_id="test-user", intent="Summarize the current plan")
    require_fields("intent submission", result, [
        "session", "task", "plan", "policy", "route", "provider_resolution",
    ])
    session = result["session"]
    task = result["task"]
    require(session["session_id"] in sessiond.sessions, "session not persisted")
    require(task["task_id"] in sessiond.tasks, "task not persisted")
    require(session["user_id"] == "test-user", "session user_id mismatch")
    require(task["session_id"] == session["session_id"], "task session_id mismatch")
    require(task["intent"] == "Summarize the current plan", "task intent mismatch")
    require(task["state"] == "approved", "task should be approved after allowed policy")
    require(
        result["plan"]["candidate_capabilities"] == ["system.intent.execute"],
        "plan capability mismatch",
    )
    require(
        result["plan"]["steps"][0]["status"] == "approved",
        "plan step should be approved",
    )


def test_policy_evaluation_produces_token() -> None:
    sessiond = MockSessiond()
    policyd = MockPolicyd()
    runtimed = MockRuntimed()
    agentd = MockAgentd(sessiond=sessiond, policyd=policyd, runtimed=runtimed)

    result = agentd.submit_intent(user_id="test-user", intent="Open the project file")
    policy = result["policy"]
    require(policy["decision"]["decision"] == "allowed", "policy should allow the intent")
    require(policy["decision"]["capability_id"] == "provider.fs.open", "policy capability_id mismatch")

    execution_token = result["execution_token"]
    require(execution_token is not None, "execution token should be issued for allowed policy")
    require(execution_token["valid"] is True, "execution token should be valid")
    require(execution_token["capability_id"] == "provider.fs.open", "token capability_id mismatch")
    require(execution_token["user_id"] == "test-user", "token user_id mismatch")

    verification = policyd.verify_token(execution_token["token"])
    require(verification["valid"] is True, "token verification should pass")

    require(len(policyd.evaluations) == 1, "exactly one evaluation expected")
    require(
        policyd.evaluations[0]["capability_id"] == "provider.fs.open",
        "evaluation should record the capability",
    )


def test_runtime_routing_selects_backend() -> None:
    sessiond = MockSessiond()
    policyd = MockPolicyd()
    runtimed = MockRuntimed()
    agentd = MockAgentd(sessiond=sessiond, policyd=policyd, runtimed=runtimed)

    result = agentd.submit_intent(user_id="test-user", intent="Run inference on this text")
    route = result["route"]
    require(route["selected_backend"] == "local-cpu", "route should select local-cpu")
    require("route_state" in route, "route should include route_state")
    require(route["allow_remote"] is False, "route should not allow remote by default")
    require(len(runtimed.routes) == 1, "exactly one route resolution expected")


def test_response_contract_fields() -> None:
    sessiond = MockSessiond()
    policyd = MockPolicyd()
    runtimed = MockRuntimed()
    agentd = MockAgentd(sessiond=sessiond, policyd=policyd, runtimed=runtimed)

    result = agentd.submit_intent(user_id="test-user", intent="Capture the screen")

    require_fields("session", result["session"], [
        "session_id", "user_id", "created_at", "status",
    ])
    require_fields("task", result["task"], [
        "task_id", "session_id", "intent", "state", "created_at",
    ])
    require_fields("plan", result["plan"], [
        "plan_id", "session_id", "task_id", "intent",
        "candidate_capabilities", "steps", "created_at",
    ])
    for step in result["plan"]["steps"]:
        require_fields("plan step", step, [
            "step_id", "capability_id", "status", "execution_path",
        ])
    require_fields("policy decision", result["policy"]["decision"], [
        "decision", "capability_id", "execution_location", "reason",
    ])
    require_fields("route", result["route"], [
        "selected_backend", "allow_remote", "route_state", "resolved_at",
    ])
    require_fields("provider_resolution", result["provider_resolution"], [
        "selected", "candidates",
    ])
    require_fields("provider_resolution.selected", result["provider_resolution"]["selected"], [
        "provider_id", "execution_location", "capability_id",
    ])
    if result["execution_token"] is not None:
        require_fields("execution_token", result["execution_token"], [
            "token", "user_id", "session_id", "task_id",
            "capability_id", "execution_location", "issued_at", "valid",
        ])

    serialized = json.dumps(result, default=str)
    deserialized = json.loads(serialized)
    require(
        deserialized["session"]["session_id"] == result["session"]["session_id"],
        "response should be JSON-serializable without data loss",
    )


def test_session_reuse_across_intents() -> None:
    sessiond = MockSessiond()
    policyd = MockPolicyd()
    runtimed = MockRuntimed()
    agentd = MockAgentd(sessiond=sessiond, policyd=policyd, runtimed=runtimed)

    first = agentd.submit_intent(user_id="test-user", intent="Open /tmp/test.txt")
    session_id = first["session"]["session_id"]

    second = agentd.submit_intent(
        user_id="test-user",
        intent="Run inference on the opened file",
        session_id=session_id,
    )

    require(
        second["session"]["session_id"] == session_id,
        "second intent should reuse the same session",
    )
    require(
        second["task"]["task_id"] != first["task"]["task_id"],
        "second intent should create a new task",
    )
    require(len(sessiond.sessions) == 1, "only one session should exist")
    require(len(sessiond.tasks) == 2, "two tasks should exist")
    require(len(policyd.evaluations) == 2, "two policy evaluations expected")
    require(len(runtimed.routes) == 2, "two route resolutions expected")


def test_full_flow_end_to_end() -> None:
    sessiond = MockSessiond()
    policyd = MockPolicyd()
    runtimed = MockRuntimed()
    agentd = MockAgentd(sessiond=sessiond, policyd=policyd, runtimed=runtimed)

    result = agentd.submit_intent(user_id="e2e-user", intent="Summarize the project README")

    session = result["session"]
    task = result["task"]
    plan = result["plan"]
    policy = result["policy"]
    route = result["route"]
    token = result["execution_token"]

    require(session["status"] == "active", "session should be active")
    require(task["state"] == "approved", "task should transition to approved")
    require(plan["task_id"] == task["task_id"], "plan should reference the task")
    require(policy["decision"]["decision"] == "allowed", "policy should allow")
    require(route["selected_backend"] == "local-cpu", "backend should be selected")
    require(token is not None, "token should be issued")

    require(
        task["task_id"] in agentd.plans,
        "plan should be stored in agentd",
    )
    require(
        token["session_id"] == session["session_id"],
        "token should reference the session",
    )
    require(
        token["task_id"] == task["task_id"],
        "token should reference the task",
    )
    require(
        token["capability_id"] == plan["candidate_capabilities"][0],
        "token capability should match plan capability",
    )

    verification = policyd.verify_token(token["token"])
    require(verification["valid"], "token should verify successfully")

    require(len(sessiond.sessions) == 1, "single session in flow")
    require(len(sessiond.tasks) == 1, "single task in flow")
    require(len(policyd.evaluations) == 1, "single evaluation in flow")
    require(len(policyd.tokens) == 1, "single token in flow")
    require(len(runtimed.routes) == 1, "single route in flow")


ALL_TESTS = [
    ("intent creates session and task", test_intent_creates_session_and_task),
    ("policy evaluation produces token", test_policy_evaluation_produces_token),
    ("runtime routing selects backend", test_runtime_routing_selects_backend),
    ("response contract fields", test_response_contract_fields),
    ("session reuse across intents", test_session_reuse_across_intents),
    ("full flow end to end", test_full_flow_end_to_end),
]


def main() -> int:
    passed = 0
    failed = 0
    errors: list[tuple[str, Exception]] = []

    for name, test_fn in ALL_TESTS:
        try:
            test_fn()
            passed += 1
            print(f"  PASS  {name}")
        except Exception as exc:
            failed += 1
            errors.append((name, exc))
            print(f"  FAIL  {name}: {exc}")

    print(f"\ne2e intent flow smoke: {passed} passed, {failed} failed")

    if errors:
        print("\nfailures:")
        for name, exc in errors:
            print(f"  - {name}: {exc}")
        return 1

    print("e2e intent flow smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
