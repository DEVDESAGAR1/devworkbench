"""Capability Registry managing all tool providers across technologies."""

import importlib.util
import shutil
import subprocess

from devworkbench.capabilities.model import (
    CapabilityType,
    InstallMethod,
    ToolPriority,
    ToolProvider,
)
from devworkbench.models import Technology


def _is_binary_available(cmd: str) -> bool:
    """Check if an executable binary is in system PATH."""
    return shutil.which(cmd) is not None


def _is_module_available(module_name: str) -> bool:
    """Check if a Python module is importable in the current environment."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def _get_binary_version(cmd: str, args: list[str] = ["--version"]) -> str | None:
    """Retrieve version string from binary if available."""
    if not _is_binary_available(cmd):
        return None
    try:
        proc = subprocess.run(
            [cmd] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2.0,
            check=False,
        )
        out = (proc.stdout or proc.stderr or "").strip().splitlines()
        return out[0] if out else None
    except Exception:
        return None


class CapabilityRegistry:
    """Central registry of all capability providers."""

    def __init__(self) -> None:
        self.providers: list[ToolProvider] = []
        self._register_default_providers()

    def register(self, provider: ToolProvider) -> None:
        """Register a tool provider."""
        self.providers.append(provider)

    def get_providers_for_capability(self, capability: CapabilityType) -> list[ToolProvider]:
        """Get all providers registered for a specific capability, sorted by priority (1 to 4)."""
        matches = [p for p in self.providers if p.capability == capability]
        return sorted(matches, key=lambda p: int(p.priority))

    def get_providers_for_technology(self, tech: Technology) -> list[ToolProvider]:
        """Get all providers registered for a technology."""
        return [p for p in self.providers if p.technology == tech]

    def _register_default_providers(self) -> None:
        """Register the verified suite of Native, Open-Source, and DevWorkBench providers."""

        # ------------------ HELM ------------------
        self.register(ToolProvider(
            name="helm",
            technology=Technology.HELM,
            capability=CapabilityType.HELM_LINT,
            priority=ToolPriority.NATIVE,
            source="CLI binary",
            license="Apache-2.0",
            real_command="helm lint",
            install_method=InstallMethod.SYSTEM_PACKAGE,
            install_hint="Install Helm via 'brew install helm' or 'winget install Helm.Helm' or from https://helm.sh",
            documentation_url="https://helm.sh",
            is_available_fn=lambda: _is_binary_available("helm"),
            version_fn=lambda: _get_binary_version("helm", ["version", "--short"]),
        ))
        self.register(ToolProvider(
            name="devworkbench-helm",
            technology=Technology.HELM,
            capability=CapabilityType.HELM_LINT,
            priority=ToolPriority.DEVWORKBENCH,
            source="Internal engine",
            license="Apache-2.0",
            real_command="internal-rule-engine",
            install_method=InstallMethod.BUILTIN,
            is_available_fn=lambda: True,
        ))

        self.register(ToolProvider(
            name="helm",
            technology=Technology.HELM,
            capability=CapabilityType.HELM_RENDER,
            priority=ToolPriority.NATIVE,
            source="CLI binary",
            license="Apache-2.0",
            real_command="helm template",
            install_method=InstallMethod.SYSTEM_PACKAGE,
            install_hint="Install Helm from https://helm.sh/docs/intro/install/",
            documentation_url="https://helm.sh",
            is_available_fn=lambda: _is_binary_available("helm"),
            version_fn=lambda: _get_binary_version("helm", ["version", "--short"]),
        ))

        # ------------------ TERRAFORM / OPENTOFU ------------------
        self.register(ToolProvider(
            name="terraform",
            technology=Technology.TERRAFORM,
            capability=CapabilityType.TERRAFORM_FORMAT,
            priority=ToolPriority.NATIVE,
            source="CLI binary",
            license="BUSL-1.1",
            real_command="terraform fmt -check",
            install_method=InstallMethod.SYSTEM_PACKAGE,
            install_hint="Install Terraform from https://developer.hashicorp.com/terraform or OpenTofu from https://opentofu.org",
            documentation_url="https://developer.hashicorp.com/terraform",
            is_available_fn=lambda: _is_binary_available("terraform") or _is_binary_available("tofu"),
            version_fn=lambda: _get_binary_version("terraform", ["version"]) or _get_binary_version("tofu", ["version"]),
        ))

        self.register(ToolProvider(
            name="terraform",
            technology=Technology.TERRAFORM,
            capability=CapabilityType.TERRAFORM_VALIDATE,
            priority=ToolPriority.NATIVE,
            source="CLI binary",
            license="BUSL-1.1",
            real_command="terraform validate",
            install_method=InstallMethod.SYSTEM_PACKAGE,
            install_hint="Install Terraform from https://developer.hashicorp.com/terraform",
            documentation_url="https://developer.hashicorp.com/terraform",
            is_available_fn=lambda: _is_binary_available("terraform") or _is_binary_available("tofu"),
            version_fn=lambda: _get_binary_version("terraform", ["version"]) or _get_binary_version("tofu", ["version"]),
        ))

        self.register(ToolProvider(
            name="tflint",
            technology=Technology.TERRAFORM,
            capability=CapabilityType.TERRAFORM_LINT,
            priority=ToolPriority.OPENSOURCE,
            source="CLI binary",
            license="MPL-2.0",
            real_command="tflint",
            install_method=InstallMethod.SYSTEM_PACKAGE,
            install_hint="Install TFLint from https://github.com/terraform-linters/tflint",
            documentation_url="https://github.com/terraform-linters/tflint",
            is_available_fn=lambda: _is_binary_available("tflint"),
            version_fn=lambda: _get_binary_version("tflint", ["--version"]),
        ))

        self.register(ToolProvider(
            name="checkov",
            technology=Technology.TERRAFORM,
            capability=CapabilityType.TERRAFORM_SECURITY,
            priority=ToolPriority.OPENSOURCE,
            source="Python package / CLI binary",
            license="Apache-2.0",
            real_command="checkov",
            install_method=InstallMethod.PIP,
            install_package_name="checkov",
            install_hint="Install Checkov via 'pip install checkov'",
            documentation_url="https://www.checkov.io",
            is_available_fn=lambda: _is_module_available("checkov") or _is_binary_available("checkov"),
            version_fn=lambda: _get_binary_version("checkov", ["--version"]),
        ))

        # ------------------ PYTHON ------------------
        self.register(ToolProvider(
            name="python-ast",
            technology=Technology.PYTHON,
            capability=CapabilityType.PYTHON_SYNTAX,
            priority=ToolPriority.NATIVE,
            source="Python standard library",
            license="PSF-2.0",
            real_command="ast.parse",
            install_method=InstallMethod.BUILTIN,
            is_available_fn=lambda: True,
        ))

        self.register(ToolProvider(
            name="ruff",
            technology=Technology.PYTHON,
            capability=CapabilityType.PYTHON_LINT,
            priority=ToolPriority.OPENSOURCE,
            source="Python package / CLI binary",
            license="MIT",
            real_command="ruff check",
            install_method=InstallMethod.PIP,
            install_package_name="ruff",
            install_hint="Install Ruff via 'pip install ruff'",
            documentation_url="https://docs.astral.sh/ruff",
            is_available_fn=lambda: _is_binary_available("ruff") or _is_module_available("ruff"),
            version_fn=lambda: _get_binary_version("ruff", ["--version"]),
        ))

        self.register(ToolProvider(
            name="black",
            technology=Technology.PYTHON,
            capability=CapabilityType.PYTHON_FORMAT,
            priority=ToolPriority.OPENSOURCE,
            source="Python package / CLI binary",
            license="MIT",
            real_command="black --check --diff",
            install_method=InstallMethod.PIP,
            install_package_name="black",
            install_hint="Install Black via 'pip install black'",
            documentation_url="https://black.readthedocs.io",
            is_available_fn=lambda: _is_binary_available("black") or _is_module_available("black"),
            version_fn=lambda: _get_binary_version("black", ["--version"]),
        ))

        self.register(ToolProvider(
            name="ruff",
            technology=Technology.PYTHON,
            capability=CapabilityType.PYTHON_FORMAT,
            priority=ToolPriority.OPENSOURCE,
            source="Python package / CLI binary",
            license="MIT",
            real_command="ruff format",
            install_method=InstallMethod.PIP,
            install_package_name="ruff",
            install_hint="Install Ruff via 'pip install ruff'",
            documentation_url="https://docs.astral.sh/ruff",
            is_available_fn=lambda: _is_binary_available("ruff") or _is_module_available("ruff"),
            version_fn=lambda: _get_binary_version("ruff", ["--version"]),
        ))

        # ------------------ YAML ------------------
        self.register(ToolProvider(
            name="pyyaml",
            technology=Technology.YAML,
            capability=CapabilityType.YAML_PARSING,
            priority=ToolPriority.OPENSOURCE,
            source="Python package",
            license="MIT",
            real_command="yaml.safe_load",
            install_method=InstallMethod.PIP,
            install_package_name="pyyaml",
            install_hint="Install PyYAML via 'pip install pyyaml'",
            documentation_url="https://pyyaml.org",
            is_available_fn=lambda: _is_module_available("yaml"),
        ))

        self.register(ToolProvider(
            name="yamllint",
            technology=Technology.YAML,
            capability=CapabilityType.YAML_LINT,
            priority=ToolPriority.OPENSOURCE,
            source="Python package / CLI binary",
            license="GPL-3.0-or-later",
            real_command="yamllint",
            install_method=InstallMethod.PIP,
            install_package_name="yamllint",
            install_hint="Install yamllint via 'pip install yamllint'",
            documentation_url="https://yamllint.readthedocs.io",
            is_available_fn=lambda: _is_binary_available("yamllint") or _is_module_available("yamllint"),
            version_fn=lambda: _get_binary_version("yamllint", ["--version"]),
        ))

        # ------------------ SHELL ------------------
        self.register(ToolProvider(
            name="shellcheck",
            technology=Technology.SHELL,
            capability=CapabilityType.SHELL_LINT,
            priority=ToolPriority.NATIVE,
            source="CLI binary",
            license="GPL-3.0-or-later",
            real_command="shellcheck -f json",
            install_method=InstallMethod.SYSTEM_PACKAGE,
            install_hint="Install ShellCheck from https://www.shellcheck.net or via 'winget install koalaman.shellcheck'",
            documentation_url="https://github.com/koalaman/shellcheck",
            is_available_fn=lambda: _is_binary_available("shellcheck"),
            version_fn=lambda: _get_binary_version("shellcheck", ["--version"]),
        ))

        # ------------------ DOCKER ------------------
        self.register(ToolProvider(
            name="hadolint",
            technology=Technology.DOCKERFILE,
            capability=CapabilityType.DOCKERFILE_LINT,
            priority=ToolPriority.NATIVE,
            source="CLI binary",
            license="GPL-3.0-or-later",
            real_command="hadolint -f json",
            install_method=InstallMethod.SYSTEM_PACKAGE,
            install_hint="Install Hadolint from https://github.com/hadolint/hadolint",
            documentation_url="https://github.com/hadolint/hadolint",
            is_available_fn=lambda: _is_binary_available("hadolint"),
            version_fn=lambda: _get_binary_version("hadolint", ["--version"]),
        ))
        self.register(ToolProvider(
            name="devworkbench-docker",
            technology=Technology.DOCKERFILE,
            capability=CapabilityType.DOCKERFILE_LINT,
            priority=ToolPriority.DEVWORKBENCH,
            source="Internal engine",
            license="Apache-2.0",
            real_command="internal-rule-engine",
            install_method=InstallMethod.BUILTIN,
            is_available_fn=lambda: True,
        ))

        # ------------------ KUBERNETES & OPENSHIFT ------------------
        self.register(ToolProvider(
            name="kubeconform",
            technology=Technology.KUBERNETES,
            capability=CapabilityType.KUBERNETES_SCHEMA_VALIDATION,
            priority=ToolPriority.OPENSOURCE,
            source="CLI binary",
            license="Apache-2.0",
            real_command="kubeconform -output json",
            install_method=InstallMethod.SYSTEM_PACKAGE,
            install_hint="Install Kubeconform from https://github.com/yannh/kubeconform",
            documentation_url="https://github.com/yannh/kubeconform",
            is_available_fn=lambda: _is_binary_available("kubeconform"),
            version_fn=lambda: _get_binary_version("kubeconform", ["-v"]),
        ))

        self.register(ToolProvider(
            name="kube-linter",
            technology=Technology.KUBERNETES,
            capability=CapabilityType.KUBERNETES_LINT,
            priority=ToolPriority.OPENSOURCE,
            source="CLI binary",
            license="Apache-2.0",
            real_command="kube-linter lint --format json",
            install_method=InstallMethod.SYSTEM_PACKAGE,
            install_hint="Install KubeLinter from https://github.com/stackrox/kube-linter",
            documentation_url="https://github.com/stackrox/kube-linter",
            is_available_fn=lambda: _is_binary_available("kube-linter"),
            version_fn=lambda: _get_binary_version("kube-linter", ["version"]),
        ))

        self.register(ToolProvider(
            name="devworkbench-k8s",
            technology=Technology.KUBERNETES,
            capability=CapabilityType.KUBERNETES_LINT,
            priority=ToolPriority.DEVWORKBENCH,
            source="Internal engine",
            license="Apache-2.0",
            real_command="internal-rule-engine",
            install_method=InstallMethod.BUILTIN,
            is_available_fn=lambda: True,
        ))

        self.register(ToolProvider(
            name="devworkbench-openshift",
            technology=Technology.OPENSHIFT,
            capability=CapabilityType.OPENSHIFT_VALIDATION,
            priority=ToolPriority.DEVWORKBENCH,
            source="Internal engine",
            license="Apache-2.0",
            real_command="internal-rule-engine",
            install_method=InstallMethod.BUILTIN,
            is_available_fn=lambda: True,
        ))

        # ------------------ KUBERNETES TO HELM CONVERSION ------------------
        self.register(ToolProvider(
            name="helmify",
            technology=Technology.KUBERNETES,
            capability=CapabilityType.KUBERNETES_TO_HELM,
            priority=ToolPriority.OPENSOURCE,
            source="CLI binary",
            license="MIT",
            real_command="helmify",
            install_method=InstallMethod.SYSTEM_PACKAGE,
            install_hint="Install Helmify from https://github.com/arttor/helmify",
            documentation_url="https://github.com/arttor/helmify",
            is_available_fn=lambda: _is_binary_available("helmify"),
            version_fn=lambda: _get_binary_version("helmify", ["--version"]),
        ))

        self.register(ToolProvider(
            name="chartify",
            technology=Technology.KUBERNETES,
            capability=CapabilityType.KUBERNETES_TO_HELM,
            priority=ToolPriority.OPENSOURCE,
            source="CLI binary",
            license="Apache-2.0",
            real_command="chartify",
            install_method=InstallMethod.SYSTEM_PACKAGE,
            install_hint="Install Chartify from https://github.com/appscode/chartify",
            documentation_url="https://github.com/appscode/chartify",
            is_available_fn=lambda: _is_binary_available("chartify"),
            version_fn=lambda: _get_binary_version("chartify", ["version"]),
        ))

        self.register(ToolProvider(
            name="devworkbench-to-helm",
            technology=Technology.KUBERNETES,
            capability=CapabilityType.KUBERNETES_TO_HELM,
            priority=ToolPriority.DEVWORKBENCH,
            source="Internal engine",
            license="Apache-2.0",
            real_command="internal-helm-converter",
            install_method=InstallMethod.BUILTIN,
            is_available_fn=lambda: True,
        ))

        # ------------------ KUBERNETES CLEANUP ------------------
        self.register(ToolProvider(
            name="kubectl-neat",
            technology=Technology.KUBERNETES,
            capability=CapabilityType.KUBERNETES_CLEANUP,
            priority=ToolPriority.OPENSOURCE,
            source="CLI binary / kubectl plugin",
            license="Apache-2.0",
            real_command="kubectl neat -f",
            install_method=InstallMethod.SYSTEM_PACKAGE,
            install_hint="Install kubectl-neat via 'kubectl krew install neat' or from https://github.com/itaysk/kubectl-neat",
            documentation_url="https://github.com/itaysk/kubectl-neat",
            is_available_fn=lambda: _is_binary_available("kubectl-neat") or _is_binary_available("kubectl_neat"),
            version_fn=lambda: _get_binary_version("kubectl-neat", ["version"]),
        ))

        self.register(ToolProvider(
            name="devworkbench-k8s-clean",
            technology=Technology.KUBERNETES,
            capability=CapabilityType.KUBERNETES_CLEANUP,
            priority=ToolPriority.DEVWORKBENCH,
            source="Internal engine",
            license="Apache-2.0",
            real_command="internal-resource-cleaner",
            install_method=InstallMethod.BUILTIN,
            is_available_fn=lambda: True,
        ))

        # ------------------ ANSIBLE & CI/CD ------------------
        self.register(ToolProvider(
            name="ansible-lint",
            technology=Technology.ANSIBLE,
            capability=CapabilityType.ANSIBLE_LINT,
            priority=ToolPriority.OPENSOURCE,
            source="Python package / CLI binary",
            license="GPL-3.0-or-later",
            real_command="ansible-lint -f json",
            install_method=InstallMethod.PIP,
            install_package_name="ansible-lint",
            install_hint="Install ansible-lint via 'pip install ansible-lint'",
            documentation_url="https://ansible.readthedocs.io/projects/lint/",
            is_available_fn=lambda: _is_binary_available("ansible-lint") or _is_module_available("ansiblelint"),
            version_fn=lambda: _get_binary_version("ansible-lint", ["--version"]),
        ))

        self.register(ToolProvider(
            name="actionlint",
            technology=Technology.GITHUB_ACTIONS,
            capability=CapabilityType.GITHUB_ACTIONS_LINT,
            priority=ToolPriority.OPENSOURCE,
            source="CLI binary",
            license="MIT",
            real_command="actionlint -format json",
            install_method=InstallMethod.SYSTEM_PACKAGE,
            install_hint="Install actionlint from https://github.com/rhysd/actionlint",
            documentation_url="https://github.com/rhysd/actionlint",
            is_available_fn=lambda: _is_binary_available("actionlint"),
            version_fn=lambda: _get_binary_version("actionlint", ["-version"]),
        ))

        # ------------------ JENKINS & BUILD LOGS ------------------
        self.register(ToolProvider(
            name="devworkbench-jenkins",
            technology=Technology.JENKINS,
            capability=CapabilityType.JENKINS_VALIDATION,
            priority=ToolPriority.DEVWORKBENCH,
            source="Internal engine",
            license="Apache-2.0",
            real_command="internal-pipeline-validator",
            install_method=InstallMethod.BUILTIN,
            is_available_fn=lambda: True,
        ))

        self.register(ToolProvider(
            name="devworkbench-jenkins-sec",
            technology=Technology.JENKINS,
            capability=CapabilityType.JENKINS_SECURITY,
            priority=ToolPriority.DEVWORKBENCH,
            source="Internal engine",
            license="Apache-2.0",
            real_command="internal-security-rules",
            install_method=InstallMethod.BUILTIN,
            is_available_fn=lambda: True,
        ))

        self.register(ToolProvider(
            name="devworkbench-buildlog",
            technology=Technology.BUILD_LOG,
            capability=CapabilityType.BUILD_LOG_ANALYSIS,
            priority=ToolPriority.DEVWORKBENCH,
            source="Internal engine",
            license="Apache-2.0",
            real_command="streaming-log-parser",
            install_method=InstallMethod.BUILTIN,
            is_available_fn=lambda: True,
        ))
