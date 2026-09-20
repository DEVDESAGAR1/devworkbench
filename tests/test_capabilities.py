"""Unit and integration tests for the Mandatory Tool Selection Hierarchy."""


from click.testing import CliRunner

from devworkbench.capabilities.model import (
    CapabilityType,
    ToolPriority,
    ToolProvider,
)
from devworkbench.capabilities.registry import CapabilityRegistry
from devworkbench.capabilities.resolver import CapabilityResolver
from devworkbench.cli import main
from devworkbench.models import Technology


def test_priority_1_native_selected_when_available() -> None:
    """Verify that when a Native (Priority 1) provider is available, it is selected."""
    registry = CapabilityRegistry()
    registry.providers.clear()

    native_provider = ToolProvider(
        name="helm-native",
        technology=Technology.HELM,
        capability=CapabilityType.HELM_LINT,
        priority=ToolPriority.NATIVE,
        source="CLI binary",
        license="Apache-2.0",
        is_available_fn=lambda: True,
    )
    oss_provider = ToolProvider(
        name="helm-oss-linter",
        technology=Technology.HELM,
        capability=CapabilityType.HELM_LINT,
        priority=ToolPriority.OPENSOURCE,
        source="Python package",
        license="MIT",
        is_available_fn=lambda: True,
    )
    dwb_provider = ToolProvider(
        name="devworkbench-helm",
        technology=Technology.HELM,
        capability=CapabilityType.HELM_LINT,
        priority=ToolPriority.DEVWORKBENCH,
        source="Internal engine",
        license="Apache-2.0",
        is_available_fn=lambda: True,
    )

    registry.register(native_provider)
    registry.register(oss_provider)
    registry.register(dwb_provider)

    resolver = CapabilityResolver(registry)
    res = resolver.resolve(CapabilityType.HELM_LINT)

    assert res.status == "available"
    assert res.selected_provider is not None
    assert res.selected_provider.name == "helm-native"
    assert res.priority == ToolPriority.NATIVE
    assert int(res.priority) == 1


def test_priority_2_opensource_selected_when_native_unavailable() -> None:
    """Verify that when Native is unavailable, Open-Source (Priority 2) is selected."""
    registry = CapabilityRegistry()
    registry.providers.clear()

    native_provider = ToolProvider(
        name="helm-native",
        technology=Technology.HELM,
        capability=CapabilityType.HELM_LINT,
        priority=ToolPriority.NATIVE,
        source="CLI binary",
        license="Apache-2.0",
        is_available_fn=lambda: False,  # Not installed
    )
    oss_provider = ToolProvider(
        name="helm-oss-linter",
        technology=Technology.HELM,
        capability=CapabilityType.HELM_LINT,
        priority=ToolPriority.OPENSOURCE,
        source="Python package",
        license="MIT",
        is_available_fn=lambda: True,
    )
    dwb_provider = ToolProvider(
        name="devworkbench-helm",
        technology=Technology.HELM,
        capability=CapabilityType.HELM_LINT,
        priority=ToolPriority.DEVWORKBENCH,
        source="Internal engine",
        license="Apache-2.0",
        is_available_fn=lambda: True,
    )

    registry.register(native_provider)
    registry.register(oss_provider)
    registry.register(dwb_provider)

    resolver = CapabilityResolver(registry)
    res = resolver.resolve(CapabilityType.HELM_LINT)

    assert res.status == "available"
    assert res.selected_provider is not None
    assert res.selected_provider.name == "helm-oss-linter"
    assert res.priority == ToolPriority.OPENSOURCE
    assert int(res.priority) == 2


def test_priority_3_devworkbench_selected_when_native_and_oss_unavailable() -> None:
    """Verify fallback to DevWorkBench (Priority 3) when Native and Open-Source are unavailable."""
    registry = CapabilityRegistry()
    registry.providers.clear()

    native_provider = ToolProvider(
        name="helm-native",
        technology=Technology.HELM,
        capability=CapabilityType.HELM_LINT,
        priority=ToolPriority.NATIVE,
        source="CLI binary",
        license="Apache-2.0",
        is_available_fn=lambda: False,
    )
    oss_provider = ToolProvider(
        name="helm-oss-linter",
        technology=Technology.HELM,
        capability=CapabilityType.HELM_LINT,
        priority=ToolPriority.OPENSOURCE,
        source="Python package",
        license="MIT",
        is_available_fn=lambda: False,
    )
    dwb_provider = ToolProvider(
        name="devworkbench-helm",
        technology=Technology.HELM,
        capability=CapabilityType.HELM_LINT,
        priority=ToolPriority.DEVWORKBENCH,
        source="Internal engine",
        license="Apache-2.0",
        is_available_fn=lambda: True,
    )

    registry.register(native_provider)
    registry.register(oss_provider)
    registry.register(dwb_provider)

    resolver = CapabilityResolver(registry)
    res = resolver.resolve(CapabilityType.HELM_LINT)

    assert res.status == "available"
    assert res.selected_provider is not None
    assert res.selected_provider.name == "devworkbench-helm"
    assert res.priority == ToolPriority.DEVWORKBENCH
    assert int(res.priority) == 3


def test_priority_4_manual_review_when_no_automated_provider() -> None:
    """Verify that when no automated provider is available, status is manual_review."""
    registry = CapabilityRegistry()
    registry.providers.clear()

    native_provider = ToolProvider(
        name="k8s-converter",
        technology=Technology.KUBERNETES,
        capability=CapabilityType.KUBERNETES_TO_HELM,
        priority=ToolPriority.NATIVE,
        source="CLI binary",
        license="Apache-2.0",
        is_available_fn=lambda: False,
    )
    oss_provider = ToolProvider(
        name="poly-converter",
        technology=Technology.KUBERNETES,
        capability=CapabilityType.KUBERNETES_TO_HELM,
        priority=ToolPriority.OPENSOURCE,
        source="Python package",
        license="Apache-2.0",
        is_available_fn=lambda: False,
    )

    registry.register(native_provider)
    registry.register(oss_provider)

    resolver = CapabilityResolver(registry)
    res = resolver.resolve(CapabilityType.KUBERNETES_TO_HELM)

    assert res.status == "manual_review"
    assert res.selected_provider is None
    assert res.priority == ToolPriority.MANUAL
    assert int(res.priority) == 4
    assert "Manual review required" in str(res.message)


def test_user_preference_override_and_unavailable_warning() -> None:
    """Verify explicit preference configuration."""
    registry = CapabilityRegistry()
    registry.providers.clear()

    native_provider = ToolProvider(
        name="native-tool",
        technology=Technology.TERRAFORM,
        capability=CapabilityType.TERRAFORM_LINT,
        priority=ToolPriority.NATIVE,
        source="CLI binary",
        license="BUSL-1.1",
        is_available_fn=lambda: True,
    )
    oss_provider = ToolProvider(
        name="tflint",
        technology=Technology.TERRAFORM,
        capability=CapabilityType.TERRAFORM_LINT,
        priority=ToolPriority.OPENSOURCE,
        source="CLI binary",
        license="MPL-2.0",
        is_available_fn=lambda: True,
    )

    registry.register(native_provider)
    registry.register(oss_provider)

    resolver = CapabilityResolver(registry)

    # 1. Preferred OSS override
    res_oss = resolver.resolve(CapabilityType.TERRAFORM_LINT, preference="opensource")
    assert res_oss.status == "available"
    assert res_oss.selected_provider is not None
    assert res_oss.selected_provider.name == "tflint"
    assert res_oss.priority == ToolPriority.OPENSOURCE

    # 2. Configured provider that is unavailable
    oss_provider.is_available_fn = lambda: False
    res_unavail = resolver.resolve(CapabilityType.TERRAFORM_LINT, preference="opensource")
    assert res_unavail.status == "configured_unavailable"
    assert res_unavail.selected_provider is None
    assert "unavailable" in str(res_unavail.message).lower()


def test_capabilities_cli_human_and_json_output() -> None:
    """Test devworkbench capabilities CLI command."""
    runner = CliRunner()

    # Human output
    res_human = runner.invoke(main, ["capabilities"])
    assert res_human.exit_code == 0
    assert "DevWorkBench - Capability Providers & Hierarchy" in res_human.output
    assert "yaml_parsing" in res_human.output

    # JSON output
    res_json = runner.invoke(main, ["capabilities", "--json"])
    assert res_json.exit_code == 0
    assert '"capability":' in res_json.output
    assert '"priority":' in res_json.output

    # Technology filter
    res_filtered = runner.invoke(main, ["capabilities", "-t", "yaml"])
    assert res_filtered.exit_code == 0
    assert "yaml_parsing" in res_filtered.output
