"""Kubernetes best-practice and reliability rules."""

from pathlib import Path
from typing import Any

import yaml

from devworkbench.models import (
    Diagnostic,
    DiagnosticCategory,
    DiagnosticSeverity,
    FileDetection,
    Technology,
)
from devworkbench.rules.base import BaseRule, RuleMetadata


class K8sResourceLimitsRule(BaseRule):
    """K8S001: Warns if containers have no resources (requests/limits) configured."""

    @property
    def metadata(self) -> RuleMetadata:
        return RuleMetadata(
            rule_id="K8S001",
            technology=Technology.KUBERNETES,
            severity=DiagnosticSeverity.WARNING,
            category=DiagnosticCategory.BEST_PRACTICE,
            description="Container has no resource requests or limits defined.",
            rationale="Without resource limits, a malfunctioning pod can starve neighboring workloads of CPU/memory (noisy neighbor problem).",
            provider="devworkbench",
            provider_priority=3,
            rule_origin="DevWorkBench rule engine",
            documentation_url="https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/",
            help_url="https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/",
            autofix_supported=False,
            false_positive_notes="Ensure resource quotas and LimitRanges are evaluated before overriding.",
        )

    def evaluate(
        self,
        file_path: Path,
        content: str,
        detection: FileDetection,
        parsed_data: Any | None = None,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        try:
            docs = list(yaml.safe_load_all(content)) if parsed_data is None else [parsed_data]
            for doc in docs:
                if not isinstance(doc, dict):
                    continue
                kind = doc.get("kind", "")
                if kind in ["Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod"]:
                    spec = doc.get("spec", {})
                    if kind == "CronJob":
                        spec = spec.get("jobTemplate", {}).get("spec", {})
                    if kind in ["Deployment", "StatefulSet", "DaemonSet", "Job"]:
                        spec = spec.get("template", {}).get("spec", {})

                    containers = spec.get("containers", [])
                    for c in containers:
                        if isinstance(c, dict) and "resources" not in c:
                            diagnostics.append(
                                Diagnostic(
                                    path=detection.relative_path,
                                    severity=self.metadata.severity,
                                    rule=self.metadata.rule_id,
                                    message=f"Container '{c.get('name', 'unnamed')}' in {kind} has no resource requests or limits configured.",
                                    source="k8s-rules",
                                    category=self.metadata.category,
                                    provider=self.metadata.provider,
                                    provider_priority=self.metadata.provider_priority,
                                    provider_type="devworkbench",
                                    rule_origin=self.metadata.rule_origin,
                                    documentation_url=self.metadata.documentation_url,
                                )
                            )
        except Exception:
            pass
        return diagnostics


class K8sPrivilegedContainerRule(BaseRule):
    """K8S002: Flags containers running in privileged mode."""

    @property
    def metadata(self) -> RuleMetadata:
        return RuleMetadata(
            rule_id="K8S002",
            technology=Technology.KUBERNETES,
            severity=DiagnosticSeverity.ERROR,
            category=DiagnosticCategory.SECURITY,
            description="Container runs in privileged mode (securityContext.privileged: true).",
            rationale="Privileged containers inherit full root host access, allowing container escapes and host compromise.",
            provider="devworkbench",
            provider_priority=3,
            rule_origin="DevWorkBench rule engine",
            documentation_url="https://kubernetes.io/docs/concepts/security/pod-security-standards/",
            help_url="https://kubernetes.io/docs/concepts/security/pod-security-standards/",
            autofix_supported=False,
            false_positive_notes="Legitimate infrastructure agents (e.g. CNI plugins) may require privileged access.",
        )

    def evaluate(
        self,
        file_path: Path,
        content: str,
        detection: FileDetection,
        parsed_data: Any | None = None,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        try:
            docs = list(yaml.safe_load_all(content)) if parsed_data is None else [parsed_data]
            for doc in docs:
                if not isinstance(doc, dict):
                    continue
                kind = doc.get("kind", "")
                if kind in ["Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod"]:
                    spec = doc.get("spec", {})
                    if kind in ["Deployment", "StatefulSet", "DaemonSet", "Job"]:
                        spec = spec.get("template", {}).get("spec", {})

                    containers = spec.get("containers", [])
                    for c in containers:
                        if isinstance(c, dict):
                            sec_ctx = c.get("securityContext", {})
                            if sec_ctx.get("privileged") is True:
                                diagnostics.append(
                                    Diagnostic(
                                        path=detection.relative_path,
                                        severity=self.metadata.severity,
                                        rule=self.metadata.rule_id,
                                        message=f"Container '{c.get('name', 'unnamed')}' in {kind} is running in privileged mode.",
                                        source="k8s-rules",
                                        category=self.metadata.category,
                                        provider=self.metadata.provider,
                                        provider_priority=self.metadata.provider_priority,
                                        provider_type="devworkbench",
                                        rule_origin=self.metadata.rule_origin,
                                        documentation_url=self.metadata.documentation_url,
                                    )
                                )
        except Exception:
            pass
        return diagnostics


class K8sLatestImageTagRule(BaseRule):
    """K8S003: Detects container images using ':latest' or missing explicit tag."""

    @property
    def metadata(self) -> RuleMetadata:
        return RuleMetadata(
            rule_id="K8S003",
            technology=Technology.KUBERNETES,
            severity=DiagnosticSeverity.WARNING,
            category=DiagnosticCategory.BEST_PRACTICE,
            description="Container uses ':latest' or unpinned image tag.",
            rationale="Using unpinned tags or :latest causes non-deterministic deployments and unpredictable cluster rolling updates.",
            provider="devworkbench",
            provider_priority=3,
            rule_origin="DevWorkBench rule engine",
            documentation_url="https://kubernetes.io/docs/concepts/containers/images/#image-names",
            help_url="https://kubernetes.io/docs/concepts/containers/images/#image-names",
            autofix_supported=False,
            false_positive_notes="Test fixtures or local dev environments may deliberately test :latest.",
        )

    def evaluate(
        self,
        file_path: Path,
        content: str,
        detection: FileDetection,
        parsed_data: Any | None = None,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        try:
            docs = list(yaml.safe_load_all(content)) if parsed_data is None else [parsed_data]
            for doc in docs:
                if not isinstance(doc, dict):
                    continue
                kind = doc.get("kind", "")
                if kind in ["Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod"]:
                    spec = doc.get("spec", {})
                    if kind in ["Deployment", "StatefulSet", "DaemonSet", "Job"]:
                        spec = spec.get("template", {}).get("spec", {})

                    containers = spec.get("containers", [])
                    for c in containers:
                        if isinstance(c, dict):
                            img = str(c.get("image", ""))
                            if img.endswith(":latest") or (":" not in img and "@" not in img and img):
                                diagnostics.append(
                                    Diagnostic(
                                        path=detection.relative_path,
                                        severity=self.metadata.severity,
                                        rule=self.metadata.rule_id,
                                        message=f"Container '{c.get('name', 'unnamed')}' uses unpinned image tag '{img}'. Pin image to specific tag or digest.",
                                        source="k8s-rules",
                                        category=self.metadata.category,
                                        provider=self.metadata.provider,
                                        provider_priority=self.metadata.provider_priority,
                                        provider_type="devworkbench",
                                        rule_origin=self.metadata.rule_origin,
                                        documentation_url=self.metadata.documentation_url,
                                    )
                                )
        except Exception:
            pass
        return diagnostics


class K8sMissingProbesRule(BaseRule):
    """K8S004: Flags Deployment or StatefulSet containers lacking liveness or readiness probes."""

    @property
    def metadata(self) -> RuleMetadata:
        return RuleMetadata(
            rule_id="K8S004",
            technology=Technology.KUBERNETES,
            severity=DiagnosticSeverity.INFO,
            category=DiagnosticCategory.BEST_PRACTICE,
            description="Container missing liveness or readiness probes in long-running workload.",
            rationale="Without probes, Kubernetes cannot detect deadlocks or route traffic safely away from unready instances.",
            provider="devworkbench",
            provider_priority=3,
            rule_origin="DevWorkBench rule engine",
            documentation_url="https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/",
            help_url="https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/",
            autofix_supported=False,
            false_positive_notes="One-off migration jobs or utility pods do not require health probes.",
        )

    def evaluate(
        self,
        file_path: Path,
        content: str,
        detection: FileDetection,
        parsed_data: Any | None = None,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        try:
            docs = list(yaml.safe_load_all(content)) if parsed_data is None else [parsed_data]
            for doc in docs:
                if not isinstance(doc, dict):
                    continue
                kind = doc.get("kind", "")
                if kind in ["Deployment", "StatefulSet"]:
                    spec = doc.get("spec", {}).get("template", {}).get("spec", {})
                    containers = spec.get("containers", [])
                    for c in containers:
                        if isinstance(c, dict):
                            if "readinessProbe" not in c and "livenessProbe" not in c:
                                diagnostics.append(
                                    Diagnostic(
                                        path=detection.relative_path,
                                        severity=self.metadata.severity,
                                        rule=self.metadata.rule_id,
                                        message=f"Container '{c.get('name', 'unnamed')}' in {kind} is missing liveness/readiness probes.",
                                        source="k8s-rules",
                                        category=self.metadata.category,
                                        provider=self.metadata.provider,
                                        provider_priority=self.metadata.provider_priority,
                                        provider_type="devworkbench",
                                        rule_origin=self.metadata.rule_origin,
                                        documentation_url=self.metadata.documentation_url,
                                    )
                                )
        except Exception:
            pass
        return diagnostics
