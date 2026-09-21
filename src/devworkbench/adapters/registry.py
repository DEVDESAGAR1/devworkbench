"""Adapter registry managing technology adapters and dispatching."""


from devworkbench.adapters.actionlint_adapter import ActionlintAdapter
from devworkbench.adapters.ansible_adapter import AnsibleLintAdapter
from devworkbench.adapters.base import BaseAdapter
from devworkbench.adapters.checkov_adapter import CheckovAdapter
from devworkbench.adapters.docker_adapter import DockerAdapter
from devworkbench.adapters.helm_adapter import HelmAdapter
from devworkbench.adapters.helmify_adapter import HelmifyAdapter
from devworkbench.adapters.jenkins_adapter import JenkinsAdapter
from devworkbench.adapters.kubelinter_adapter import KubeLinterAdapter
from devworkbench.adapters.python_adapter import PythonAdapter
from devworkbench.adapters.shell_adapter import ShellAdapter
from devworkbench.adapters.terraform_adapter import TerraformAdapter
from devworkbench.adapters.tflint_adapter import TFLintAdapter
from devworkbench.adapters.yaml_adapter import YamlAdapter
from devworkbench.models import FileDetection, Technology, ToolWarning


class AdapterRegistry:
    """Central registry of all registered technology adapters."""

    def __init__(self) -> None:
        self.adapters: list[BaseAdapter] = [
            JenkinsAdapter(),
            PythonAdapter(),
            YamlAdapter(),
            KubeLinterAdapter(),
            TerraformAdapter(),
            TFLintAdapter(),
            CheckovAdapter(),
            ShellAdapter(),
            DockerAdapter(),
            ActionlintAdapter(),
            AnsibleLintAdapter(),
            HelmAdapter(),
            HelmifyAdapter(),
        ]

    def get_adapters_for_file(self, detection: FileDetection) -> list[BaseAdapter]:
        """Find all adapters capable of processing this file detection."""
        return [adapter for adapter in self.adapters if adapter.can_handle(detection)]

    def get_adapter_for_tech(self, tech: Technology) -> BaseAdapter | None:
        """Find an adapter handling the given technology."""
        for adapter in self.adapters:
            if adapter.technology == tech:
                return adapter
        return None

    def get_tool_warnings(self, active_technologies: set[Technology]) -> list[ToolWarning]:
        """Collect tool availability warnings only for technologies actually discovered in the workspace."""
        warnings: list[ToolWarning] = []
        seen_tools: set[str] = set()

        for tech in active_technologies:
            for adapter in self.adapters:
                if adapter.technology == tech:
                    is_avail, warning = adapter.is_available()
                    if not is_avail and warning and warning.tool_name not in seen_tools:
                        seen_tools.add(warning.tool_name)
                        warnings.append(warning)

        return warnings
