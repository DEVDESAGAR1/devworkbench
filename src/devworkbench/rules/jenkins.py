"""Jenkins DevOps best-practice and security rules."""

import re
from pathlib import Path
from typing import Any

from devworkbench.models import (
    Diagnostic,
    DiagnosticCategory,
    DiagnosticSeverity,
    FileDetection,
    Technology,
)
from devworkbench.rules.base import BaseRule, RuleMetadata


class JenkinsCredentialRule(BaseRule):
    """JENKINS001: Detects hard-coded secrets or credentials in Jenkinsfiles."""

    RE_SECRET_PATTERN = re.compile(
        r"""(?i)(?:password|passwd|api_key|apikey|secret_key|secretkey|auth_token|bearer_token|private_key|aws_secret_access_key)\s*[:=]\s*['"]([^'"\n\r\t\s]{5,})['"]"""
    )

    @property
    def metadata(self) -> RuleMetadata:
        return RuleMetadata(
            rule_id="JENKINS001",
            technology=Technology.JENKINS,
            severity=DiagnosticSeverity.WARNING,
            category=DiagnosticCategory.SECURITY,
            description="Possible hard-coded credential detected. Do not store credentials directly in pipeline source.",
            rationale="Plaintext secrets in source code expose systems to credential theft and compliance violations.",
            provider="devworkbench",
            provider_priority=3,
            rule_origin="DevWorkBench rule engine",
            documentation_url="https://www.jenkins.io/doc/book/pipeline/jenkinsfile/#handling-credentials",
            help_url="https://www.jenkins.io/doc/book/pipeline/jenkinsfile/#handling-credentials",
            autofix_supported=False,
            false_positive_notes="Ensure detected variable names are not dummy placeholder names in documentation.",
        )

    def evaluate(
        self,
        file_path: Path,
        content: str,
        detection: FileDetection,
        parsed_data: Any | None = None,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for line_num, line in enumerate(content.splitlines(), start=1):
            if self.RE_SECRET_PATTERN.search(line):
                diagnostics.append(
                    Diagnostic(
                        path=detection.relative_path,
                        line=line_num,
                        severity=self.metadata.severity,
                        rule=self.metadata.rule_id,
                        message="Possible hard-coded credential detected. Use Jenkins credentials store and withCredentials instead.",
                        source="jenkins-rules",
                        category=self.metadata.category,
                        provider=self.metadata.provider,
                        provider_priority=self.metadata.provider_priority,
                        provider_type="devworkbench",
                        rule_origin=self.metadata.rule_origin,
                        documentation_url=self.metadata.documentation_url,
                    )
                )
        return diagnostics


class JenkinsUnsafeShellInterpolationRule(BaseRule):
    """JENKINS002: Detects potentially unsafe string interpolation in sh steps."""

    RE_UNSAFE_SH = re.compile(
        r"""sh\s*\(?\s*(?:""" r'"""|")' r"""[^"']*?\$\{(?:params|env)\.[a-zA-Z0-9_]+\}"""
    )

    @property
    def metadata(self) -> RuleMetadata:
        return RuleMetadata(
            rule_id="JENKINS002",
            technology=Technology.JENKINS,
            severity=DiagnosticSeverity.WARNING,
            category=DiagnosticCategory.SECURITY,
            description="Potentially unsafe shell parameter interpolation inside double-quoted sh step.",
            rationale="Interpolating Groovy variables inside double-quoted shell commands allows arbitrary command injection.",
            provider="devworkbench",
            provider_priority=3,
            rule_origin="DevWorkBench rule engine",
            documentation_url="https://www.jenkins.io/doc/book/pipeline/jenkinsfile/#string-interpolation",
            help_url="https://www.jenkins.io/doc/book/pipeline/jenkinsfile/#string-interpolation",
            autofix_supported=False,
        )

    def evaluate(
        self,
        file_path: Path,
        content: str,
        detection: FileDetection,
        parsed_data: Any | None = None,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for line_num, line in enumerate(content.splitlines(), start=1):
            if self.RE_UNSAFE_SH.search(line):
                diagnostics.append(
                    Diagnostic(
                        path=detection.relative_path,
                        line=line_num,
                        severity=self.metadata.severity,
                        rule=self.metadata.rule_id,
                        message="Unsafe variable interpolation in shell step. Prefer single quotes or environment variables to prevent injection.",
                        source="jenkins-rules",
                        category=self.metadata.category,
                        provider=self.metadata.provider,
                        provider_priority=self.metadata.provider_priority,
                        provider_type="devworkbench",
                        rule_origin=self.metadata.rule_origin,
                        documentation_url=self.metadata.documentation_url,
                    )
                )
        return diagnostics


class JenkinsMissingTimeoutRule(BaseRule):
    """JENKINS003: Warns on long pipeline without obvious timeout protection."""

    @property
    def metadata(self) -> RuleMetadata:
        return RuleMetadata(
            rule_id="JENKINS003",
            technology=Technology.JENKINS,
            severity=DiagnosticSeverity.INFO,
            category=DiagnosticCategory.BEST_PRACTICE,
            description="Pipeline has multiple stages but lacks an explicit timeout option.",
            rationale="Unbounded pipeline runs can consume agent executors indefinitely if a step deadlocks or hangs.",
            provider="devworkbench",
            provider_priority=3,
            rule_origin="DevWorkBench rule engine",
            documentation_url="https://www.jenkins.io/doc/book/pipeline/syntax/#options",
            help_url="https://www.jenkins.io/doc/book/pipeline/syntax/#options",
            autofix_supported=False,
        )

    def evaluate(
        self,
        file_path: Path,
        content: str,
        detection: FileDetection,
        parsed_data: Any | None = None,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        stage_count = len(re.findall(r"\bstage\s*\(", content))
        if stage_count >= 3 and "timeout" not in content:
            diagnostics.append(
                Diagnostic(
                    path=detection.relative_path,
                    severity=self.metadata.severity,
                    rule=self.metadata.rule_id,
                    message=f"Pipeline defines {stage_count} stages without explicit timeout protection. Consider setting an options {{ timeout(...) }} constraint.",
                    source="jenkins-rules",
                    category=self.metadata.category,
                    provider=self.metadata.provider,
                    provider_priority=self.metadata.provider_priority,
                    provider_type="devworkbench",
                    rule_origin=self.metadata.rule_origin,
                    documentation_url=self.metadata.documentation_url,
                )
            )
        return diagnostics


class JenkinsShellErrorSuppressionRule(BaseRule):
    """JENKINS004: Detects shell steps that suppress errors using '|| true'."""

    RE_SUPPRESSED_SH = re.compile(r"""sh\s*\(?.*?\|\|\s*true""", re.IGNORECASE)

    @property
    def metadata(self) -> RuleMetadata:
        return RuleMetadata(
            rule_id="JENKINS004",
            technology=Technology.JENKINS,
            severity=DiagnosticSeverity.WARNING,
            category=DiagnosticCategory.BEST_PRACTICE,
            description="Shell step uses '|| true' which may silently ignore critical build failures.",
            rationale="Suppressing shell return codes prevents CI from halting on compilation, test, or security failures.",
            provider="devworkbench",
            provider_priority=3,
            rule_origin="DevWorkBench rule engine",
            documentation_url="https://www.jenkins.io/doc/book/pipeline/jenkinsfile/#handling-failures",
            help_url="https://www.jenkins.io/doc/book/pipeline/jenkinsfile/#handling-failures",
            autofix_supported=False,
        )

    def evaluate(
        self,
        file_path: Path,
        content: str,
        detection: FileDetection,
        parsed_data: Any | None = None,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for line_num, line in enumerate(content.splitlines(), start=1):
            if self.RE_SUPPRESSED_SH.search(line):
                diagnostics.append(
                    Diagnostic(
                        path=detection.relative_path,
                        line=line_num,
                        severity=self.metadata.severity,
                        rule=self.metadata.rule_id,
                        message="Shell command ignores errors via '|| true'. Use try/catch or warnError instead to preserve build diagnostics.",
                        source="jenkins-rules",
                        category=self.metadata.category,
                        provider=self.metadata.provider,
                        provider_priority=self.metadata.provider_priority,
                        provider_type="devworkbench",
                        rule_origin=self.metadata.rule_origin,
                        documentation_url=self.metadata.documentation_url,
                    )
                )
        return diagnostics
