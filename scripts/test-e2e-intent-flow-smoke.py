#!/usr/bin/env python3
from __future__ import annotations

import json
import re
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
        needs_approval = capability_id in {
            "system.file.bulk_delete",
            "compat.code.execute",
            "device.capture.screen.read",
        }
        decision = {
            "decision": "needs-approval" if needs_approval else "allowed",
            "capability_id": capability_id,
            "execution_location": execution_location,
            "reason": "approval-required" if needs_approval else "policy-allowed-default",
            "requires_approval": needs_approval,
            "taint_summary": "",
        }
        envelope = {
            "decision": decision,
            "approval_lane": "high-risk" if needs_approval else "standard",
            "taint_hint": "",
            "approval_ref": f"approval-{uuid.uuid4().hex[:12]}" if needs_approval else None,
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
        capabilities = self._infer_capabilities(intent)
        primary_capability = capabilities[0]
        plan = {
            "plan_id": f"plan-{uuid.uuid4().hex[:12]}",
            "session_id": session_id,
            "task_id": task_id,
            "intent": intent,
            "candidate_capabilities": capabilities,
            "next_action": self._next_action(primary_capability),
            "steps": [
                {
                    "step_id": f"step-{uuid.uuid4().hex[:8]}",
                    "capability_id": primary_capability,
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
        else:
            self.sessiond.update_task_state(task["task_id"], "waiting-approval", "policy-needs-approval")
            plan["steps"][0]["status"] = "waiting-approval"

        route = self.runtimed.resolve_route(preferred_backend="local-cpu")

        provider_resolution = {
            "selected": {
                "provider_id": self._provider_for_capability(primary_capability),
                "execution_location": self._execution_location_for_capability(primary_capability),
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

    def _infer_capabilities(self, intent: str) -> list[str]:
        lower = intent.lower()
        capabilities: list[str] = []

        mentions_web = self._contains_any(
            lower,
            ("browser", "https://", "http://", "www.", "网页", "网站", "浏览器", "网址", "链接"),
        )
        mentions_path = not mentions_web and self._contains_any(
            lower,
            ("/", "\\", "~/", "../", "./", ".txt", ".md", ".pdf", ".doc", ".docx", ".odt", ".json", ".yaml", ".yml", ".log", ".csv"),
        )
        mentions_file_target = mentions_path or self._contains_any(
            lower,
            ("file", "files", "folder", "directory", "path", "文件", "文件夹", "目录", "路径", "文档"),
        )

        if self._contains_any(lower, ("delete", "remove", "删除", "移除", "清空")):
            capabilities.append("system.file.bulk_delete")
        if mentions_web:
            capabilities.append("compat.browser.navigate")
            if self._contains_any(lower, ("extract", "scrape", "selector", "title", "提取", "抓取", "抽取", "标题")):
                capabilities.append("compat.browser.extract")
        if self._contains_any(lower, ("python", "script", "sandbox", "code", "代码", "脚本", "沙箱")) and self._contains_any(
            lower,
            ("run", "execute", "运行", "执行", "启动"),
        ):
            capabilities.append("compat.code.execute")
        if self._contains_any(lower, ("screen", "screenshot", "share", "capture", "屏幕", "截图", "共享屏幕")):
            capabilities.append("device.capture.screen.read")
        if mentions_file_target:
            capabilities.append("provider.fs.open")
        if self._contains_any(
            lower,
            (
                "summarize",
                "summary",
                "infer",
                "inference",
                "model",
                "generate",
                "draft",
                "plan",
                "analyze",
                "analyse",
                "explain",
                "translate",
                "review",
                "总结",
                "摘要",
                "生成",
                "计划",
                "概括",
                "分析",
                "解释",
                "翻译",
                "审阅",
            ),
        ):
            capabilities.append("runtime.infer.submit")

        if not capabilities:
            capabilities.append("system.intent.execute")

        ordered: list[str] = []
        for capability in capabilities:
            if capability not in ordered:
                ordered.append(capability)
        return sorted(ordered, key=self._capability_priority)

    def _contains_any(self, text: str, tokens: tuple[str, ...]) -> bool:
        for token in tokens:
            if token.startswith(".") or "/" in token or "\\" in token:
                if token in text:
                    return True
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", text):
                return True
        return False

    def _capability_priority(self, capability_id: str) -> int:
        return {
            "system.file.bulk_delete": 5,
            "compat.code.execute": 10,
            "device.capture.screen.read": 20,
            "compat.browser.navigate": 30,
            "compat.browser.extract": 35,
            "provider.fs.open": 50,
            "runtime.infer.submit": 60,
            "system.intent.execute": 100,
        }.get(capability_id, 110)

    def _next_action(self, capability_id: str) -> str:
        return {
            "system.file.bulk_delete": "request-destructive-approval",
            "compat.code.execute": "request-sandbox-approval",
            "device.capture.screen.read": "request-screen-capture-approval",
            "compat.browser.navigate": "open-browser-target",
            "compat.browser.extract": "extract-browser-content",
            "provider.fs.open": "inspect-bound-target",
            "runtime.infer.submit": "invoke-runtime-preview",
            "system.intent.execute": "review-local-control-plan",
        }.get(capability_id, "review-local-control-plan")

    def _provider_for_capability(self, capability_id: str) -> str:
        if capability_id in {"provider.fs.open", "system.file.bulk_delete"}:
            return "system.files.local"
        if capability_id in {"compat.browser.navigate", "compat.browser.extract"}:
            return "compat.browser.automation.local"
        if capability_id == "compat.code.execute":
            return "compat.code.sandbox.local"
        if capability_id == "device.capture.screen.read":
            return "shell.screen-capture.portal"
        if capability_id == "runtime.infer.submit":
            return "runtime.local.inference"
        return "system.intent.local"

    def _execution_location_for_capability(self, capability_id: str) -> str:
        if capability_id in {"compat.browser.navigate", "compat.browser.extract", "compat.code.execute"}:
            return "sandbox"
        return "local"


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
        result["plan"]["candidate_capabilities"] == ["runtime.infer.submit"],
        "plan capability mismatch",
    )
    require(
        result["plan"]["next_action"] == "invoke-runtime-preview",
        "plan next_action mismatch",
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
        "candidate_capabilities", "next_action", "steps", "created_at",
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
    require(plan["next_action"] == "invoke-runtime-preview", "plan next_action should target runtime preview")
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


def test_chinese_file_intent_prioritizes_filesystem_then_runtime() -> None:
    sessiond = MockSessiond()
    policyd = MockPolicyd()
    runtimed = MockRuntimed()
    agentd = MockAgentd(sessiond=sessiond, policyd=policyd, runtimed=runtimed)

    result = agentd.submit_intent(user_id="zh-user", intent="打开 /tmp/中文报告.md 并总结重点")
    plan = result["plan"]

    require(
        plan["candidate_capabilities"][0] == "provider.fs.open",
        "chinese file intent should prioritize provider.fs.open",
    )
    require(
        "runtime.infer.submit" in plan["candidate_capabilities"],
        "chinese file intent should retain runtime inference capability",
    )
    require(plan["next_action"] == "inspect-bound-target", "chinese file next_action mismatch")
    require(
        result["provider_resolution"]["selected"]["provider_id"] == "system.files.local",
        "chinese file intent provider mismatch",
    )


def test_chinese_browser_intent_prefers_browser_provider() -> None:
    sessiond = MockSessiond()
    policyd = MockPolicyd()
    runtimed = MockRuntimed()
    agentd = MockAgentd(sessiond=sessiond, policyd=policyd, runtimed=runtimed)

    result = agentd.submit_intent(user_id="zh-user", intent="用浏览器打开 https://example.com 并提取标题")
    plan = result["plan"]

    require(
        plan["candidate_capabilities"][0] == "compat.browser.navigate",
        "chinese browser intent should prioritize compat.browser.navigate",
    )
    require(
        "compat.browser.extract" in plan["candidate_capabilities"],
        "chinese browser intent should include extract capability",
    )
    require(plan["next_action"] == "open-browser-target", "chinese browser next_action mismatch")
    require(
        result["provider_resolution"]["selected"]["provider_id"] == "compat.browser.automation.local",
        "chinese browser provider mismatch",
    )
    require(
        result["provider_resolution"]["selected"]["execution_location"] == "sandbox",
        "chinese browser execution location mismatch",
    )


def test_chinese_delete_intent_requires_approval() -> None:
    sessiond = MockSessiond()
    policyd = MockPolicyd()
    runtimed = MockRuntimed()
    agentd = MockAgentd(sessiond=sessiond, policyd=policyd, runtimed=runtimed)

    result = agentd.submit_intent(user_id="zh-user", intent="删除 /tmp/危险报告.txt 并清空回收站")
    plan = result["plan"]
    policy = result["policy"]

    require(
        plan["candidate_capabilities"][0] == "system.file.bulk_delete",
        "chinese delete intent should prioritize destructive capability",
    )
    require(
        policy["decision"]["decision"] == "needs-approval",
        "chinese delete intent should require approval",
    )
    require(
        plan["next_action"] == "request-destructive-approval",
        "chinese delete next_action mismatch",
    )
    require(
        result["task"]["state"] == "waiting-approval",
        "chinese delete task should wait for approval",
    )
    require(result["execution_token"] is None, "approval-gated delete should not issue token")
    require(
        result["provider_resolution"]["selected"]["provider_id"] == "system.files.local",
        "chinese delete provider mismatch",
    )


ALL_TESTS = [
    ("intent creates session and task", test_intent_creates_session_and_task),
    ("policy evaluation produces token", test_policy_evaluation_produces_token),
    ("runtime routing selects backend", test_runtime_routing_selects_backend),
    ("response contract fields", test_response_contract_fields),
    ("session reuse across intents", test_session_reuse_across_intents),
    ("full flow end to end", test_full_flow_end_to_end),
    ("chinese file intent", test_chinese_file_intent_prioritizes_filesystem_then_runtime),
    ("chinese browser intent", test_chinese_browser_intent_prefers_browser_provider),
    ("chinese delete approval intent", test_chinese_delete_intent_requires_approval),
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
