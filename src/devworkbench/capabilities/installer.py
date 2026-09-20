"""Safe dependency installation and error classification engine."""

import subprocess
import sys

from devworkbench.capabilities.model import (
    InstallationErrorKind,
    InstallationResult,
    InstallMethod,
    SetupReport,
    ToolPriority,
    ToolProvider,
)
from devworkbench.capabilities.registry import CapabilityRegistry


class DependencyInstaller:
    """Safe, verifiable dependency installation manager for DevWorkBench."""

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self.registry = registry or CapabilityRegistry()

    @staticmethod
    def classify_error(returncode: int, stdout: str, stderr: str) -> InstallationErrorKind:
        """Analyze subprocess output to categorize dependency and network errors."""
        combined = f"{stdout}\n{stderr}".lower()

        if "ssl" in combined or "certificate_verify_failed" in combined or "tls" in combined:
            return InstallationErrorKind.TLS_ERROR
        if "proxyerror" in combined or "cannot connect to proxy" in combined or "407" in combined:
            return InstallationErrorKind.PROXY_ERROR
        if "name resolution" in combined or "dns" in combined or "getaddrinfo failed" in combined:
            return InstallationErrorKind.DNS_ERROR
        if "connection" in combined or "unreachable" in combined or "offline" in combined or "refused" in combined:
            return InstallationErrorKind.NETWORK_UNAVAILABLE
        if "permission denied" in combined or "access is denied" in combined or "winerror 5" in combined:
            return InstallationErrorKind.PERMISSION_DENIED
        if "no matching distribution" in combined or "could not find a version" in combined or "not found" in combined:
            return InstallationErrorKind.PACKAGE_NOT_FOUND
        if "timed out" in combined or "timeout" in combined:
            return InstallationErrorKind.TIMEOUT
        if "resolutionimpossible" in combined or "incompatible" in combined or "conflict" in combined:
            return InstallationErrorKind.VERSION_INCOMPATIBLE
        if "command not found" in combined or "not recognized" in combined:
            return InstallationErrorKind.COMMAND_NOT_FOUND

        return InstallationErrorKind.INSTALL_COMMAND_FAILED

    def install_provider(
        self,
        provider: ToolProvider,
        dry_run: bool = False,
    ) -> InstallationResult:
        """Attempt to install and verify a single tool provider."""
        # 1. Check if already available
        if provider.is_available:
            return InstallationResult(
                tool_name=provider.name,
                technology=provider.technology,
                status="already_available",
                message="Tool is already installed and verified locally.",
                version=provider.version,
                verified=True,
            )

        # Find potential fallback provider
        fallback = None
        caps = self.registry.get_providers_for_capability(provider.capability)
        for p in caps:
            if p.name != provider.name and p.is_available:
                fallback = f"{p.priority.name}:{p.name}"
                break
        if not fallback:
            fallback = "MANUAL_REVIEW"

        # 2. Check installation method
        if provider.install_method in [InstallMethod.MANUAL, InstallMethod.BUILTIN] or not provider.install_package_name:
            hint = provider.install_hint or "Manual installation required."
            return InstallationResult(
                tool_name=provider.name,
                technology=provider.technology,
                status="skipped",
                error_kind=InstallationErrorKind.PACKAGE_MANAGER_UNAVAILABLE,
                message=f"Automated installation not supported for this tool. {hint}",
                fallback_provider=fallback,
                verified=False,
            )

        if dry_run:
            return InstallationResult(
                tool_name=provider.name,
                technology=provider.technology,
                status="skipped",
                message=f"Dry run: Would install '{provider.install_package_name}' via {provider.install_method.value}.",
                fallback_provider=fallback,
                verified=False,
            )

        # 3. Execute installation (PIP package in current Python environment)
        if provider.install_method == InstallMethod.PIP:
            cmd = [sys.executable, "-m", "pip", "install", provider.install_package_name]
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60.0,
                    check=False,
                )
                if proc.returncode == 0:
                    # Post-installation verification probe
                    if provider.is_available:
                        return InstallationResult(
                            tool_name=provider.name,
                            technology=provider.technology,
                            status="success",
                            message=f"Successfully installed and verified '{provider.install_package_name}'.",
                            version=provider.version,
                            verified=True,
                        )
                    else:
                        return InstallationResult(
                            tool_name=provider.name,
                            technology=provider.technology,
                            status="failed",
                            error_kind=InstallationErrorKind.VERIFICATION_FAILED,
                            message="Package installed successfully, but capability verification failed.",
                            fallback_provider=fallback,
                            verified=False,
                        )
                else:
                    err_kind = self.classify_error(proc.returncode, proc.stdout, proc.stderr)
                    return InstallationResult(
                        tool_name=provider.name,
                        technology=provider.technology,
                        status="failed",
                        error_kind=err_kind,
                        message=f"Installation failed: {proc.stderr.strip() or proc.stdout.strip() or 'Unknown error'}",
                        fallback_provider=fallback,
                        verified=False,
                    )
            except subprocess.TimeoutExpired:
                return InstallationResult(
                    tool_name=provider.name,
                    technology=provider.technology,
                    status="failed",
                    error_kind=InstallationErrorKind.TIMEOUT,
                    message="Installation command timed out after 60 seconds.",
                    fallback_provider=fallback,
                    verified=False,
                )
            except Exception as ex:
                return InstallationResult(
                    tool_name=provider.name,
                    technology=provider.technology,
                    status="failed",
                    error_kind=InstallationErrorKind.UNKNOWN,
                    message=f"Unexpected installation error: {ex!s}",
                    fallback_provider=fallback,
                    verified=False,
                )

        return InstallationResult(
            tool_name=provider.name,
            technology=provider.technology,
            status="skipped",
            message="No installer strategy defined.",
            fallback_provider=fallback,
            verified=False,
        )

    def setup_environment(
        self,
        technology: str | None = None,
        dry_run: bool = False,
    ) -> SetupReport:
        """Run setup for all registered providers, attempting installation and reporting fallbacks."""
        report = SetupReport()
        seen_tools: set[str] = set()

        for provider in self.registry.providers:
            if provider.name in seen_tools:
                continue
            if technology and provider.technology.value.lower() != technology.lower():
                continue
            if provider.priority == ToolPriority.DEVWORKBENCH:
                continue

            seen_tools.add(provider.name)
            res = self.install_provider(provider, dry_run=dry_run)

            if res.status == "already_available":
                report.already_available.append(res)
            elif res.status == "success":
                report.successful.append(res)
            elif res.status == "failed":
                report.failed.append(res)
                if res.fallback_provider:
                    report.fallbacks.append({
                        "tool": res.tool_name,
                        "technology": res.technology.value,
                        "fallback": res.fallback_provider,
                        "reason": res.error_kind.value if res.error_kind else "FAILED",
                    })
            else:
                report.skipped.append(res)

        return report
