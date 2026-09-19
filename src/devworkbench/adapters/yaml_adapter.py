"""YAML adapter utilizing PyYAML (syntax/parsing) and Yamllint (style/linting)."""

import functools
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

from devworkbench.adapters.base import BaseAdapter
from devworkbench.execution import CommandRunner
from devworkbench.models import (
    CommandExecution,
    Diagnostic,
    DiagnosticCategory,
    DiagnosticSeverity,
    FileDetection,
    Technology,
    ToolWarning,
)


class YamlAdapter(BaseAdapter):
    """Adapter for YAML, Kubernetes, OpenShift, Ansible, Docker Compose, and CI/CD YAML files."""

    SUPPORTED_TECHS = {
        Technology.YAML,
        Technology.KUBERNETES,
        Technology.OPENSHIFT,
        Technology.ANSIBLE,
        Technology.GITHUB_ACTIONS,
        Technology.GITLAB_CI,
        Technology.DOCKER_COMPOSE,
        Technology.AWS,
    }

    @property
    def technology(self) -> Technology:
        return Technology.YAML

    @property
    def name(self) -> str:
        return "PyYAML / Yamllint"

    def can_handle(self, detection: FileDetection) -> bool:
        # Never parse Helm chart templates as raw YAML (they contain Go template tags {{ ... }})
        if detection.technology == Technology.HELM:
            return False
        if "template" in (detection.details or "").lower():
            return False
        return detection.technology in self.SUPPORTED_TECHS

    @functools.lru_cache(maxsize=1)
    def _get_yamllint_cmd(self) -> Optional[Tuple[str, ...]]:
        """Find yamllint executable if available."""
        if shutil.which("yamllint"):
            return ("yamllint",)
        try:
            res = subprocess.run(
                [sys.executable, "-m", "yamllint", "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3,
            )
            if res.returncode == 0:
                return (sys.executable, "-m", "yamllint")
        except Exception:
            pass
        return None

    def is_available(self) -> Tuple[bool, Optional[ToolWarning]]:
        # PyYAML is bundled, so basic YAML syntax parsing is always available
        return True, None

    def analyze_file(self, file_path: Path, detection: FileDetection) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        rel_path = detection.relative_path

        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = file_path.read_text(encoding="latin-1")
            except Exception as e:
                diagnostics.append(
                    Diagnostic(
                        path=rel_path,
                        message=f"Could not read YAML file: {e}",
                        source="yaml",
                        severity=DiagnosticSeverity.ERROR,
                        category=DiagnosticCategory.SYNTAX,
                    )
                )
                return diagnostics

        # 1. Syntax / Parsing Validation via PyYAML
        try:
            # Load all documents in multi-doc YAML files (e.g. Kubernetes manifests)
            list(yaml.safe_load_all(content))
            self.record_execution(
                CommandExecution(
                    technology="YAML",
                    capability="yaml_parsing",
                    provider_type="opensource",
                    provider_name="pyyaml",
                    executable="yaml.safe_load_all",
                    args=[str(file_path)],
                    command=f"yaml.safe_load_all({rel_path})",
                    cwd=str(file_path.parent),
                    exit_code=0,
                    status="PASS",
                )
            )
        except yaml.MarkedYAMLError as e:
            self.record_execution(
                CommandExecution(
                    technology="YAML",
                    capability="yaml_parsing",
                    provider_type="opensource",
                    provider_name="pyyaml",
                    executable="yaml.safe_load_all",
                    args=[str(file_path)],
                    command=f"yaml.safe_load_all({rel_path})",
                    cwd=str(file_path.parent),
                    exit_code=1,
                    status="FAIL",
                    error_message=str(e),
                )
            )
            line = None
            col = None
            if e.problem_mark:
                line = e.problem_mark.line + 1
                col = e.problem_mark.column + 1
            elif e.context_mark:
                line = e.context_mark.line + 1
                col = e.context_mark.column + 1

            msg = e.problem or str(e)
            if e.context:
                msg = f"{e.context}: {msg}"

            diagnostics.append(
                Diagnostic(
                    path=rel_path,
                    line=line,
                    column=col,
                    severity=DiagnosticSeverity.ERROR,
                    rule="yaml-syntax-error",
                    message=msg,
                    source="pyyaml",
                    category=DiagnosticCategory.SYNTAX,
                    details=str(e),
                    provider="pyyaml",
                    provider_priority=2,
                    provider_type="opensource",
                    rule_origin="External engine",
                    documentation_url="https://pyyaml.org",
                )
            )
            return diagnostics
        except yaml.YAMLError as e:
            self.record_execution(
                CommandExecution(
                    technology="YAML",
                    capability="yaml_parsing",
                    provider_type="opensource",
                    provider_name="pyyaml",
                    executable="yaml.safe_load_all",
                    args=[str(file_path)],
                    command=f"yaml.safe_load_all({rel_path})",
                    cwd=str(file_path.parent),
                    exit_code=1,
                    status="FAIL",
                    error_message=str(e),
                )
            )
            diagnostics.append(
                Diagnostic(
                    path=rel_path,
                    severity=DiagnosticSeverity.ERROR,
                    rule="yaml-parse-error",
                    message=str(e),
                    source="pyyaml",
                    category=DiagnosticCategory.SYNTAX,
                    provider="pyyaml",
                    provider_priority=2,
                    provider_type="opensource",
                    rule_origin="External engine",
                    documentation_url="https://pyyaml.org",
                )
            )
            return diagnostics

        # 2. Linting via Yamllint if available
        yamllint_cmd = self._get_yamllint_cmd()
        if yamllint_cmd:
            cmd_list = list(yamllint_cmd)
            exec_res = CommandRunner.run_command(
                executable=cmd_list[0],
                args=cmd_list[1:] + ["-f", "parsable", str(file_path)],
                technology="YAML",
                capability="yaml_lint",
                provider_type="opensource",
                provider_name="yamllint",
                cwd=file_path.parent,
                timeout_seconds=10.0,
            )
            self.record_execution(exec_res)

            # Parsable output: filename:line:col: [level] message (rule)
            for line_str in exec_res.stdout.splitlines():
                line_str = line_str.strip()
                if not line_str or ":" not in line_str:
                    continue
                parts = line_str.split(":", 3)
                if len(parts) >= 4:
                    try:
                        l_num = int(parts[1])
                        c_num = int(parts[2])
                    except ValueError:
                        l_num, c_num = None, None

                    rest = parts[3].strip()
                    severity = DiagnosticSeverity.WARNING
                    if rest.startswith("[error]"):
                        severity = DiagnosticSeverity.ERROR
                        rest = rest.replace("[error]", "").strip()
                    elif rest.startswith("[warning]"):
                        rest = rest.replace("[warning]", "").strip()

                    # Extract rule name in parens if present: "message (rule-name)"
                    rule_name = None
                    if rest.endswith(")") and "(" in rest:
                        msg_part, rule_part = rest.rsplit("(", 1)
                        rest = msg_part.strip()
                        rule_name = rule_part[:-1].strip()

                    diagnostics.append(
                        Diagnostic(
                            path=rel_path,
                            line=l_num,
                            column=c_num,
                            severity=severity,
                            rule=rule_name,
                            message=rest,
                            source="yamllint",
                            category=DiagnosticCategory.LINT,
                            provider="yamllint",
                            provider_priority=2,
                            provider_type="opensource",
                            rule_origin="External engine",
                            documentation_url=f"https://yamllint.readthedocs.io/en/stable/rules.html#{rule_name}" if rule_name else "https://yamllint.readthedocs.io",
                        )
                    )

        return diagnostics
