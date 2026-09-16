"""Jenkins / Groovy pipeline adapter for structural, security, and tool-interaction analysis."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from devworkbench.adapters.base import BaseAdapter
from devworkbench.models import (
    Diagnostic,
    DiagnosticCategory,
    DiagnosticSeverity,
    FileDetection,
    Technology,
    ToolWarning,
)
from devworkbench.rules.registry import RuleRegistry


class JenkinsAdapter(BaseAdapter):
    """Adapter for Jenkinsfiles and Groovy pipelines."""

    def __init__(self) -> None:
        self.rule_registry = RuleRegistry()

    @property
    def technology(self) -> Technology:
        return Technology.JENKINS

    @property
    def name(self) -> str:
        return "Jenkins Pipeline Analyzer"

    def is_available(self) -> Tuple[bool, Optional[ToolWarning]]:
        # Built-in deterministic parser is always available
        return True, None

    def _check_balanced_brackets(
        self, content: str, rel_path: str
    ) -> List[Diagnostic]:
        """Check for unmatched braces and parentheses with accurate line/column tracking."""
        diagnostics: List[Diagnostic] = []
        stack: List[Tuple[str, int, int]] = []  # (char, line, col)

        in_single_quote = False
        in_double_quote = False
        in_triple_quote = False
        in_line_comment = False
        in_block_comment = False

        lines = content.splitlines(keepends=True)
        for line_idx, line in enumerate(lines, start=1):
            col = 0
            while col < len(line):
                char = line[col]

                # Handle comments
                if not (in_single_quote or in_double_quote or in_triple_quote):
                    if not in_block_comment and line[col : col + 2] == "//":
                        break
                    if not in_block_comment and line[col : col + 2] == "/*":
                        in_block_comment = True
                        col += 2
                        continue
                    if in_block_comment and line[col : col + 2] == "*/":
                        in_block_comment = False
                        col += 2
                        continue
                    if in_block_comment:
                        col += 1
                        continue

                # Handle string literals
                if not in_block_comment:
                    if line[col : col + 3] in ['"""', "'''"]:
                        in_triple_quote = not in_triple_quote
                        col += 3
                        continue
                    if not in_triple_quote:
                        if char == "'" and not in_double_quote:
                            in_single_quote = not in_single_quote
                            col += 1
                            continue
                        if char == '"' and not in_single_quote:
                            in_double_quote = not in_double_quote
                            col += 1
                            continue

                # If outside strings and comments, check brackets
                if (
                    not in_single_quote
                    and not in_double_quote
                    and not in_triple_quote
                    and not in_block_comment
                ):
                    if char in "{(":
                        stack.append((char, line_idx, col + 1))
                    elif char in "})":
                        if not stack:
                            diagnostics.append(
                                Diagnostic(
                                    path=rel_path,
                                    line=line_idx,
                                    column=col + 1,
                                    severity=DiagnosticSeverity.ERROR,
                                    rule="JENKINS-SYNTAX-001",
                                    message=f"Unexpected closing '{char}' without matching opening bracket",
                                    source="jenkins",
                                    category=DiagnosticCategory.SYNTAX,
                                    provider="jenkins",
                                    provider_priority=3,
                                    provider_type="devworkbench",
                                    rule_origin="DevWorkBench: Groovy Syntax Parser",
                                    documentation_url="https://www.jenkins.io/doc/book/pipeline/syntax/",
                                )
                            )
                            return diagnostics
                        opening, open_line, open_col = stack.pop()
                        expected = "}" if opening == "{" else ")"
                        if char != expected:
                            diagnostics.append(
                                Diagnostic(
                                    path=rel_path,
                                    line=line_idx,
                                    column=col + 1,
                                    severity=DiagnosticSeverity.ERROR,
                                    rule="JENKINS-SYNTAX-002",
                                    message=f"Mismatched bracket: expected '{expected}' but found '{char}' (opened at line {open_line}:{open_col})",
                                    source="jenkins",
                                    category=DiagnosticCategory.SYNTAX,
                                    provider="jenkins",
                                    provider_priority=3,
                                    provider_type="devworkbench",
                                    rule_origin="DevWorkBench: Groovy Syntax Parser",
                                    documentation_url="https://www.jenkins.io/doc/book/pipeline/syntax/",
                                )
                            )
                            return diagnostics

                col += 1

        # Check for unclosed brackets
        if stack:
            unclosed, open_line, open_col = stack[-1]
            diagnostics.append(
                Diagnostic(
                    path=rel_path,
                    line=open_line,
                    column=open_col,
                    severity=DiagnosticSeverity.ERROR,
                    rule="JENKINS-SYNTAX-003",
                    message=f"Unclosed bracket '{unclosed}' (missing matching '{'}' if unclosed == '{' else ')'}')",
                    source="jenkins",
                    category=DiagnosticCategory.SYNTAX,
                    provider="jenkins",
                    provider_priority=3,
                    provider_type="devworkbench",
                    rule_origin="DevWorkBench: Groovy Syntax Parser",
                    documentation_url="https://www.jenkins.io/doc/book/pipeline/syntax/",
                )
            )

        return diagnostics

    def _check_pipeline_structure(
        self, content: str, rel_path: str
    ) -> List[Diagnostic]:
        """Validate Declarative Pipeline structure."""
        diagnostics: List[Diagnostic] = []

        if re.search(r"\bpipeline\s*\{", content):
            # Must contain 'agent' declaration: agent any, agent none, agent { ... } or agent 'label'
            if not re.search(r"\bagent\s+(?:any|none|\{|'|\")", content):
                diagnostics.append(
                    Diagnostic(
                        path=rel_path,
                        severity=DiagnosticSeverity.ERROR,
                        rule="JENKINS-DECL-001",
                        message="Declarative Pipeline is missing required 'agent' declaration",
                        source="jenkins",
                        category=DiagnosticCategory.SCHEMA,
                        provider="jenkins",
                        provider_priority=3,
                        provider_type="devworkbench",
                        rule_origin="DevWorkBench: Declarative Pipeline Parser",
                        documentation_url="https://www.jenkins.io/doc/book/pipeline/syntax/#agent",
                    )
                )

            # Must contain 'stages'
            if not re.search(r"\bstages\s*\{", content):
                diagnostics.append(
                    Diagnostic(
                        path=rel_path,
                        severity=DiagnosticSeverity.ERROR,
                        rule="JENKINS-DECL-002",
                        message="Declarative Pipeline is missing required 'stages { ... }' block",
                        source="jenkins",
                        category=DiagnosticCategory.SCHEMA,
                        provider="jenkins",
                        provider_priority=3,
                        provider_type="devworkbench",
                        rule_origin="DevWorkBench: Declarative Pipeline Parser",
                        documentation_url="https://www.jenkins.io/doc/book/pipeline/syntax/#stages",
                    )
                )
            else:
                # Check for empty stages block
                if re.search(r"\bstages\s*\{\s*\}", content):
                    diagnostics.append(
                        Diagnostic(
                            path=rel_path,
                            severity=DiagnosticSeverity.WARNING,
                            rule="JENKINS-DECL-003",
                            message="Pipeline defines an empty 'stages { }' block with no stages",
                            source="jenkins",
                            category=DiagnosticCategory.BEST_PRACTICE,
                            provider="jenkins",
                            provider_priority=3,
                            provider_type="devworkbench",
                            rule_origin="DevWorkBench: Declarative Pipeline Parser",
                            documentation_url="https://www.jenkins.io/doc/book/pipeline/syntax/#stages",
                        )
                    )

                # Check for stage without steps or parallel
                stage_matches = list(re.finditer(r"\bstage\s*\([^)]+\)\s*\{", content))
                if stage_matches and not re.search(
                    r"\b(steps|parallel|matrix|stages)\s*\{", content
                ):
                    diagnostics.append(
                        Diagnostic(
                            path=rel_path,
                            severity=DiagnosticSeverity.WARNING,
                            rule="JENKINS-DECL-004",
                            message="Stage block does not contain 'steps { }' or 'parallel { }'",
                            source="jenkins",
                            category=DiagnosticCategory.BEST_PRACTICE,
                            provider="jenkins",
                            provider_priority=3,
                            provider_type="devworkbench",
                            rule_origin="DevWorkBench: Declarative Pipeline Parser",
                            documentation_url="https://www.jenkins.io/doc/book/pipeline/syntax/#stage",
                        )
                    )

        return diagnostics

    def _extract_tool_invocations(
        self, content: str, detection: FileDetection
    ) -> List[str]:
        """Detect when Jenkins pipeline invokes external DevOps tools (oc, kubectl, helm, docker, etc.)."""
        invoked_tools: List[str] = []
        tool_patterns = {
            "oc": r"""\b(?:sh|bat|powershell)\s*\(?.*?['"]\s*oc\s+""",
            "kubectl": r"""\b(?:sh|bat|powershell)\s*\(?.*?['"]\s*kubectl\s+""",
            "helm": r"""\b(?:sh|bat|powershell)\s*\(?.*?['"]\s*helm\s+""",
            "docker": r"""\b(?:sh|bat|powershell|docker)\s*\(?.*?['"]\s*docker\s+""",
            "podman": r"""\b(?:sh|bat|powershell)\s*\(?.*?['"]\s*podman\s+""",
            "terraform": r"""\b(?:sh|bat|powershell)\s*\(?.*?['"]\s*terraform\s+""",
        }

        for tool_name, pattern in tool_patterns.items():
            if re.search(pattern, content, re.IGNORECASE):
                invoked_tools.append(tool_name)

        detection.metadata["invoked_tools"] = invoked_tools
        return invoked_tools

    def analyze_file(self, file_path: Path, detection: FileDetection) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        rel_path = detection.relative_path

        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = file_path.read_text(encoding="latin-1", errors="ignore")
            except Exception as e:
                diagnostics.append(
                    Diagnostic(
                        path=rel_path,
                        message=f"Could not read Jenkins file: {e}",
                        source="jenkins",
                        severity=DiagnosticSeverity.ERROR,
                        category=DiagnosticCategory.SYNTAX,
                    )
                )
                return diagnostics

        # 1. Check bracket balance (Syntax)
        bracket_diags = self._check_balanced_brackets(content, rel_path)
        diagnostics.extend(bracket_diags)
        if bracket_diags:
            # If critical syntax error, stop before false-positive structural checks
            return diagnostics

        # 2. Check pipeline structure (Declarative schema / structure)
        struct_diags = self._check_pipeline_structure(content, rel_path)
        diagnostics.extend(struct_diags)

        # 3. Best-Practice & Security rules evaluation
        rule_diags = self.rule_registry.evaluate_rules(
            file_path=file_path,
            detection=detection,
            content=content,
        )
        diagnostics.extend(rule_diags)

        # 4. Extract invoked DevOps tools for cross-tool correlation
        self._extract_tool_invocations(content, detection)

        return diagnostics
