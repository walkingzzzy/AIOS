#!/usr/bin/env python3
"""Smoke tests for AIOS security hardening infrastructure.

Validates that SELinux policies, sandbox configurations, and mkosi security
packages are properly defined and structurally sound.
"""

from __future__ import annotations

import configparser
import re
import sys
from pathlib import Path
from typing import NamedTuple

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

REPO_ROOT = Path(__file__).resolve().parent.parent
IMAGE_DIR = REPO_ROOT / "aios" / "image"
SELINUX_DIR = IMAGE_DIR / "selinux"
SANDBOX_DIR = IMAGE_DIR / "sandbox"

EXPECTED_SERVICES = [
    "agentd",
    "sessiond",
    "policyd",
    "runtimed",
    "deviced",
    "updated",
]

EXPECTED_SECURITY_PACKAGES = [
    "selinux-policy-targeted",
    "policycoreutils",
    "policycoreutils-python-utils",
    "bubblewrap",
    "audit",
    "libseccomp",
]

EXPECTED_SANDBOX_PROFILES = [
    "runtime-worker",
    "compat-browser",
    "compat-code-sandbox",
]


class TestResult(NamedTuple):
    name: str
    passed: bool
    detail: str


def check_selinux_te_exists() -> TestResult:
    """SELinux .te policy file must exist."""
    te_path = SELINUX_DIR / "aios-services.te"
    if te_path.is_file():
        return TestResult("selinux_te_exists", True, str(te_path))
    return TestResult("selinux_te_exists", False, f"Missing: {te_path}")


def check_selinux_fc_exists() -> TestResult:
    """SELinux .fc file contexts file must exist."""
    fc_path = SELINUX_DIR / "aios-services.fc"
    if fc_path.is_file():
        return TestResult("selinux_fc_exists", True, str(fc_path))
    return TestResult("selinux_fc_exists", False, f"Missing: {fc_path}")


def check_selinux_te_structure() -> TestResult:
    """SELinux .te must contain policy_module declaration and section headers."""
    te_path = SELINUX_DIR / "aios-services.te"
    if not te_path.is_file():
        return TestResult("selinux_te_structure", False, "File not found")

    content = te_path.read_text(encoding="utf-8")

    if not re.search(r"^policy_module\(aios_services,\s*[\d.]+\)", content, re.MULTILINE):
        return TestResult(
            "selinux_te_structure", False, "Missing policy_module declaration"
        )

    required_sections = [
        "AIOS Service Types",
        "Service Domain Transitions",
        "Common Service Permissions",
        "Service-Specific Permissions",
    ]
    missing = [s for s in required_sections if s not in content]
    if missing:
        return TestResult(
            "selinux_te_structure", False, f"Missing sections: {missing}"
        )

    return TestResult("selinux_te_structure", True, "All sections present")


def check_selinux_service_types() -> TestResult:
    """All 6 services must have domain and exec types declared."""
    te_path = SELINUX_DIR / "aios-services.te"
    if not te_path.is_file():
        return TestResult("selinux_service_types", False, "File not found")

    content = te_path.read_text(encoding="utf-8")
    missing: list[str] = []

    for svc in EXPECTED_SERVICES:
        domain_type = f"aios_{svc}_t"
        exec_type = f"aios_{svc}_exec_t"
        if f"type {domain_type};" not in content:
            missing.append(domain_type)
        if f"type {exec_type};" not in content:
            missing.append(exec_type)

    if missing:
        return TestResult(
            "selinux_service_types", False, f"Missing types: {missing}"
        )
    return TestResult(
        "selinux_service_types", True, f"All {len(EXPECTED_SERVICES)} service types defined"
    )


def check_selinux_domain_transitions() -> TestResult:
    """All services must have init_daemon_domain transitions."""
    te_path = SELINUX_DIR / "aios-services.te"
    if not te_path.is_file():
        return TestResult("selinux_domain_transitions", False, "File not found")

    content = te_path.read_text(encoding="utf-8")
    missing: list[str] = []

    for svc in EXPECTED_SERVICES:
        pattern = f"init_daemon_domain(aios_{svc}_t, aios_{svc}_exec_t)"
        if pattern not in content:
            missing.append(svc)

    if missing:
        return TestResult(
            "selinux_domain_transitions",
            False,
            f"Missing domain transitions for: {missing}",
        )
    return TestResult(
        "selinux_domain_transitions",
        True,
        f"All {len(EXPECTED_SERVICES)} domain transitions defined",
    )


def check_selinux_file_contexts() -> TestResult:
    """File contexts must cover all service executable paths."""
    fc_path = SELINUX_DIR / "aios-services.fc"
    if not fc_path.is_file():
        return TestResult("selinux_file_contexts", False, "File not found")

    content = fc_path.read_text(encoding="utf-8")
    missing_exec: list[str] = []

    for svc in EXPECTED_SERVICES:
        if f"/usr/lib/aios/{svc}" not in content:
            missing_exec.append(svc)

    required_paths = ["/var/lib/aios", "/run/aios", "/var/log/aios"]
    missing_paths = [p for p in required_paths if p not in content]

    issues: list[str] = []
    if missing_exec:
        issues.append(f"Missing exec contexts: {missing_exec}")
    if missing_paths:
        issues.append(f"Missing path contexts: {missing_paths}")

    if issues:
        return TestResult("selinux_file_contexts", False, "; ".join(issues))
    return TestResult(
        "selinux_file_contexts",
        True,
        "All service and directory contexts present",
    )


def check_sandbox_policy_exists() -> TestResult:
    """Sandbox policy YAML must exist."""
    policy_path = SANDBOX_DIR / "aios-sandbox-policy.yaml"
    if policy_path.is_file():
        return TestResult("sandbox_policy_exists", True, str(policy_path))
    return TestResult("sandbox_policy_exists", False, f"Missing: {policy_path}")


def _parse_yaml_fallback(content: str) -> dict | None:
    """Minimal YAML-like parser for when PyYAML is unavailable.

    Only validates that the file is non-empty and contains expected
    top-level keys via regex. Returns a pseudo-dict with profile names.
    """
    result: dict = {}
    if "profiles:" in content:
        result["profiles"] = {}
        for match in re.finditer(r"^  ([\w-]+):\s*$", content, re.MULTILINE):
            result["profiles"][match.group(1)] = {"_parsed": False}
    if "schema_version:" in content:
        m = re.search(r'schema_version:\s*"?([^"\n]+)"?', content)
        if m:
            result["schema_version"] = m.group(1).strip()
    return result if result else None


def check_sandbox_policy_valid() -> TestResult:
    """Sandbox policy must be valid YAML with required structure."""
    policy_path = SANDBOX_DIR / "aios-sandbox-policy.yaml"
    if not policy_path.is_file():
        return TestResult("sandbox_policy_valid", False, "File not found")

    content = policy_path.read_text(encoding="utf-8")

    if HAS_YAML:
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            return TestResult("sandbox_policy_valid", False, f"YAML parse error: {exc}")
    else:
        data = _parse_yaml_fallback(content)
        if data is None:
            return TestResult(
                "sandbox_policy_valid",
                False,
                "Failed to parse (PyYAML not installed; fallback parser failed)",
            )

    if not isinstance(data, dict):
        return TestResult("sandbox_policy_valid", False, "Root is not a mapping")

    if "profiles" not in data:
        return TestResult("sandbox_policy_valid", False, "Missing 'profiles' key")

    if "schema_version" not in data:
        return TestResult("sandbox_policy_valid", False, "Missing 'schema_version' key")

    return TestResult("sandbox_policy_valid", True, "Valid YAML with required keys")


def check_sandbox_profiles() -> TestResult:
    """All expected sandbox profiles must be present."""
    policy_path = SANDBOX_DIR / "aios-sandbox-policy.yaml"
    if not policy_path.is_file():
        return TestResult("sandbox_profiles", False, "File not found")

    content = policy_path.read_text(encoding="utf-8")

    if HAS_YAML:
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            return TestResult("sandbox_profiles", False, "YAML parse error")
    else:
        data = _parse_yaml_fallback(content)

    if not data or "profiles" not in data:
        return TestResult("sandbox_profiles", False, "No profiles section found")

    profiles = data["profiles"]
    missing = [p for p in EXPECTED_SANDBOX_PROFILES if p not in profiles]

    if missing:
        return TestResult("sandbox_profiles", False, f"Missing profiles: {missing}")
    return TestResult(
        "sandbox_profiles",
        True,
        f"All {len(EXPECTED_SANDBOX_PROFILES)} profiles present",
    )


def check_mkosi_security_packages() -> TestResult:
    """mkosi.conf must include all required security packages."""
    mkosi_path = IMAGE_DIR / "mkosi.conf"
    if not mkosi_path.is_file():
        return TestResult("mkosi_security_packages", False, "mkosi.conf not found")

    content = mkosi_path.read_text(encoding="utf-8")
    missing = [pkg for pkg in EXPECTED_SECURITY_PACKAGES if pkg not in content]

    if missing:
        return TestResult(
            "mkosi_security_packages", False, f"Missing packages: {missing}"
        )
    return TestResult(
        "mkosi_security_packages",
        True,
        f"All {len(EXPECTED_SECURITY_PACKAGES)} security packages present",
    )


def check_mkosi_selinux_kernel_params() -> TestResult:
    """mkosi.conf KernelCommandLine must enable SELinux."""
    mkosi_path = IMAGE_DIR / "mkosi.conf"
    if not mkosi_path.is_file():
        return TestResult("mkosi_selinux_kernel", False, "mkosi.conf not found")

    content = mkosi_path.read_text(encoding="utf-8")
    missing: list[str] = []

    if "security=selinux" not in content:
        missing.append("security=selinux")
    if "selinux=1" not in content:
        missing.append("selinux=1")

    if missing:
        return TestResult(
            "mkosi_selinux_kernel", False, f"Missing kernel params: {missing}"
        )
    return TestResult("mkosi_selinux_kernel", True, "SELinux kernel params present")


ALL_CHECKS = [
    check_selinux_te_exists,
    check_selinux_fc_exists,
    check_selinux_te_structure,
    check_selinux_service_types,
    check_selinux_domain_transitions,
    check_selinux_file_contexts,
    check_sandbox_policy_exists,
    check_sandbox_policy_valid,
    check_sandbox_profiles,
    check_mkosi_security_packages,
    check_mkosi_selinux_kernel_params,
]


def main() -> int:
    print("=" * 60)
    print("AIOS Security Hardening — Smoke Tests")
    print("=" * 60)

    results: list[TestResult] = []
    for check_fn in ALL_CHECKS:
        result = check_fn()
        results.append(result)
        status = "PASS" if result.passed else "FAIL"
        print(f"  [{status}] {result.name}: {result.detail}")

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)

    print()
    print("-" * 60)
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print("-" * 60)

    if failed:
        print("\nSecurity hardening validation FAILED.")
        return 1

    print("\nAll security hardening checks PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
