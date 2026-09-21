"""Presentation and reporting layer for DevWorkBench."""

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.tree import Tree

from devworkbench.adapters.base import BaseAdapter
from devworkbench.models import (
    BuildLogReport,
    CleanupResult,
    ConversionPlan,
    ConversionResult,
    Diagnostic,
    DiagnosticSeverity,
    FileDetection,
    FixCandidate,
    FixPlan,
    FixReport,
    ScanResult,
    Technology,
    ToolWarning,
)
from devworkbench.rules.base import BaseRule


class HumanReporter:
    """Renders scan, analysis, build-log, tools, and rules results in a clear terminal format."""

    def __init__(self, console: Console | None = None) -> None:
        enc = (getattr(sys.stdout, "encoding", "") or "").lower()
        self.supports_unicode = "utf" in enc
        if console:
            self.console = console
        else:
            self.console = Console(
                emoji=False,
                safe_box=True,
                legacy_windows=False,
            )

    @property
    def icon_ok(self) -> str:
        return "[green]✓[/green]" if self.supports_unicode else "[green]OK[/green]"

    @property
    def icon_warn(self) -> str:
        return "[bold yellow]![/bold yellow]"

    @property
    def icon_err(self) -> str:
        return "[bold red]X[/bold red]"

    @property
    def icon_info(self) -> str:
        return "[bold blue]i[/bold blue]"

    def report(self, result: ScanResult, verbose: bool = False) -> None:
        """Print the complete human-readable report for repository scan."""
        self.console.print("\n[bold cyan]DevWorkBench[/bold cyan]")
        self.console.print("[dim]---------------------------------------------[/dim]")
        self.console.print(f"Scanning: [bold]{result.target_path}[/bold]\n")

        # Group detections by Technology
        grouped_detections: dict[Technology, list[FileDetection]] = defaultdict(list)
        for det in result.detections:
            grouped_detections[det.technology].append(det)

        # Group diagnostics by Technology
        path_to_tech: dict[str, Technology] = {
            det.relative_path: det.technology for det in result.detections
        }
        for hc in result.helm_charts:
            path_to_tech[hc.relative_root] = Technology.HELM

        grouped_diags: dict[Technology, list[Diagnostic]] = defaultdict(list)
        for diag in result.diagnostics:
            tech = path_to_tech.get(diag.path)
            if not tech:
                for p_key, t_val in path_to_tech.items():
                    if diag.path.startswith(p_key) or p_key in diag.path:
                        tech = t_val
                        break
            if not tech:
                src = diag.source.lower()
                if "jenkins" in src:
                    tech = Technology.JENKINS
                elif "k8s" in src or "kubernetes" in src or "kube" in src:
                    tech = Technology.KUBERNETES
                elif "openshift" in src or "ocp" in src:
                    tech = Technology.OPENSHIFT
                elif "helm" in src:
                    tech = Technology.HELM
                elif "ruff" in src or "python" in src:
                    tech = Technology.PYTHON
                elif "yaml" in src:
                    tech = Technology.YAML
                elif "tf" in src or "terraform" in src or "tofu" in src:
                    tech = Technology.TERRAFORM
                elif "shell" in src:
                    tech = Technology.SHELL
                elif "hadolint" in src or "docker" in src:
                    tech = Technology.DOCKERFILE
                elif "actionlint" in src:
                    tech = Technology.GITHUB_ACTIONS
                elif "ansible" in src:
                    tech = Technology.ANSIBLE
                else:
                    tech = Technology.UNKNOWN
            grouped_diags[tech].append(diag)

        tool_warn_by_tech: dict[Technology, list[ToolWarning]] = defaultdict(list)
        for tw in result.tool_warnings:
            tool_warn_by_tech[tw.technology].append(tw)

        tech_order = [
            Technology.JENKINS,
            Technology.KUBERNETES,
            Technology.OPENSHIFT,
            Technology.HELM,
            Technology.PYTHON,
            Technology.YAML,
            Technology.TERRAFORM,
            Technology.SHELL,
            Technology.DOCKERFILE,
            Technology.DOCKER_COMPOSE,
            Technology.GITHUB_ACTIONS,
            Technology.GITLAB_CI,
            Technology.ANSIBLE,
            Technology.AWS,
            Technology.AZURE,
            Technology.GCP,
            Technology.JAVASCRIPT,
            Technology.TYPESCRIPT,
            Technology.JAVA,
            Technology.SQL,
            Technology.JSON,
            Technology.XML,
        ]

        active_techs = set(grouped_detections.keys()) | set(grouped_diags.keys()) | set(tool_warn_by_tech.keys())

        for tech in tech_order:
            if tech not in active_techs:
                continue

            files = grouped_detections.get(tech, [])
            diags = grouped_diags.get(tech, [])
            t_warnings = tool_warn_by_tech.get(tech, [])

            self.console.print(f"[bold yellow]{tech.value}[/bold yellow]")

            if files:
                self.console.print(f"  {self.icon_ok} {len(files)} file{'s' if len(files) != 1 else ''} analyzed")

            if tech == Technology.HELM and result.helm_charts:
                for chart in result.helm_charts:
                    chart_tree = Tree(f"[bold cyan]{chart.relative_root}/[/bold cyan]")
                    if chart.chart_yaml:
                        chart_tree.add(f"[green]{Path(chart.chart_yaml).name}[/green]")
                    for vf in chart.values_files:
                        chart_tree.add(f"[green]{Path(vf).name}[/green]")
                    if chart.template_files or chart.helper_files:
                        tmpl_node = chart_tree.add("[bold]templates/[/bold]")
                        for hf in chart.helper_files:
                            tmpl_node.add(f"[green]{Path(hf).name}[/green]")
                        for tf in chart.template_files:
                            tmpl_node.add(f"[green]{Path(tf).name}[/green]")
                    self.console.print(chart_tree)

            for tw in t_warnings:
                self.console.print(f"  {self.icon_warn} [bold yellow]{tw.tool_name} unavailable[/bold yellow]")
                self.console.print(f"    [dim]{tw.install_hint}[/dim]")

            for diag in diags:
                loc_str = ""
                if diag.line is not None:
                    loc_str = f":{diag.line}"
                    if diag.column is not None:
                        loc_str += f":{diag.column}"

                if diag.severity == DiagnosticSeverity.ERROR:
                    icon = self.icon_err
                elif diag.severity == DiagnosticSeverity.WARNING:
                    icon = self.icon_warn
                else:
                    icon = self.icon_info

                rule_str = f" [{diag.rule}]" if diag.rule else ""
                cat_str = f" ({diag.category.value})" if diag.category else ""
                self.console.print(f"  {icon} [bold]{diag.path}{loc_str}[/bold]{rule_str}{cat_str}")
                self.console.print(f"    {diag.message}")

                # Provider Provenance & Lineage
                prov_str = ""
                if diag.provider:
                    p_pri = f"P{diag.provider_priority}:" if diag.provider_priority else ""
                    p_type = f"{diag.provider_type}" if diag.provider_type else ""
                    p_badge = f"({p_pri}{p_type})" if (p_pri or p_type) else ""
                    prov_str = f"source: {diag.provider} {p_badge}".strip()
                else:
                    prov_str = f"source: {diag.source}"

                if diag.rule_origin:
                    prov_str += f" | {diag.rule_origin}"
                self.console.print(f"    [dim]{prov_str}[/dim]")

                if diag.contributing_sources:
                    contrib_str = ", ".join(diag.contributing_sources)
                    self.console.print(f"    [dim italic]Also detected by: {contrib_str}[/dim italic]")

                doc_url = diag.documentation_url or diag.help_url
                if doc_url:
                    self.console.print(f"    [dim]Docs: {doc_url}[/dim]")

            self.console.print()

        # Cross-Tool Correlations
        if result.correlations:
            self.console.print("[bold cyan]Cross-Tool Correlations[/bold cyan]")
            for corr in result.correlations:
                chain_str = " -> ".join(corr.technology_chain)
                self.console.print(f"  [bold magenta]{chain_str}[/bold magenta] (Confidence: {int(corr.confidence*100)}%)")
                self.console.print(f"    {corr.explanation}")
                if corr.root_cause_candidate:
                    self.console.print(f"    [bold red]Root Cause:[/bold red] {corr.root_cause_candidate.title}")
            self.console.print()

        # Executions (verbose or when errors occur)
        if verbose and result.executions:
            self.console.print("[bold cyan]Execution Details & Transparency[/bold cyan]")
            for ex in result.executions:
                st_icon = self.icon_ok if ex.status == "PASS" else (self.icon_warn if ex.status == "UNAVAILABLE" else self.icon_err)
                v_str = f" v{ex.tool_version}" if ex.tool_version else ""
                self.console.print(f"  {st_icon} [bold]{ex.technology}[/bold] / {ex.capability} -> [cyan]{ex.provider_name}[/cyan]{v_str} [dim]({ex.duration_ms:.1f}ms, exit={ex.exit_code})[/dim]")
                self.console.print(f"    [dim]cmd: {ex.command}[/dim]")
                if ex.unavailable_reason:
                    self.console.print(f"    [dim yellow]reason: {ex.unavailable_reason}[/dim yellow]")
            self.console.print()

        # Summary Footer
        summary = result.summary
        self.console.print("[dim]---------------------------------------------[/dim]")
        self.console.print("[bold]Analysis Summary[/bold]")
        self.console.print("[dim]---------------------------------------------[/dim]")
        if summary.errors_count > 0:
            self.console.print(f"Errors:            [bold red]{summary.errors_count}[/bold red]")
        else:
            self.console.print("Errors:            [green]0[/green]")

        if summary.warnings_count > 0:
            self.console.print(f"Warnings:          [bold yellow]{summary.warnings_count}[/bold yellow]")
        else:
            self.console.print("Warnings:          [green]0[/green]")

        self.console.print(f"Files with issues: [bold]{summary.files_with_issues}[/bold]")
        if summary.root_causes_count > 0:
            self.console.print(f"Correlations:      [bold cyan]{summary.root_causes_count}[/bold cyan]")
        self.console.print(f"Files discovered:  {summary.total_files_discovered}")

        cov_val = summary.coverage.value if hasattr(summary.coverage, "value") else str(summary.coverage)
        cov_color = "green" if cov_val == "FULL" else ("yellow" if cov_val == "PARTIAL" else "red")
        self.console.print(f"Tool Coverage:     [bold {cov_color}]{cov_val}[/bold {cov_color}] (Passed: {summary.checks_passed}, Failed: {summary.checks_failed}, Unavailable: {summary.checks_unavailable})")
        self.console.print(f"Scan duration:     [dim]{summary.duration_ms:.2f} ms[/dim]")
        self.console.print("\n[bold green]No files modified.[/bold green]\n")

    def report_cleanup_result(self, result: CleanupResult, format_mode: str = "human") -> None:
        """Print the result of manifest cleanup."""
        if format_mode == "diff":
            if result.diff:
                self.console.print(result.diff)
            else:
                self.console.print("[dim]Manifest is already clean. No changes.[/dim]")
            return

        if format_mode == "yaml":
            self.console.print(result.cleaned_yaml)
            return

        self.console.print("\n[bold cyan]DevWorkBench - Kubernetes Manifest Cleaner[/bold cyan]")
        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]")
        self.console.print(f"Target: [bold]{result.source_path}[/bold] (Engine: [green]{result.engine_used}[/green])\n")

        if result.fields_removed:
            self.console.print("[bold yellow]Removed Runtime Metadata & Status:[/bold yellow]")
            for f in result.fields_removed:
                self.console.print(f"  {self.icon_ok} [dim]{f}[/dim]")
            self.console.print()

        if result.diff:
            self.console.print("[bold]Diff Preview:[/bold]")
            self.console.print(f"[dim]{result.diff}[/dim]")
        else:
            self.console.print("[bold green]Manifest was already clean. No fields removed.[/bold green]\n")

        if result.written and result.output_path:
            self.console.print(f"[bold green]Cleaned manifest written to:[/bold green] [bold cyan]{result.output_path}[/bold cyan]\n")
        elif not result.written:
            self.console.print("[bold green]No files modified.[/bold green] (Use [cyan]--write[/cyan] or [cyan]--output[/cyan] to save changes)\n")
        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]\n")

    def report_conversion_plan(self, plan: ConversionPlan) -> None:
        """Print the Kubernetes-to-Helm conversion plan."""
        self.console.print("\n[bold cyan]DevWorkBench - Kubernetes to Helm Conversion Plan[/bold cyan]")
        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]")
        self.console.print(f"Target Chart:  [bold green]{plan.target_chart_name}[/bold green]")
        self.console.print(f"Destination:   [bold]{plan.target_dir}[/bold]")
        exist_color = "yellow" if plan.existing_chart_detected else "green"
        exist_text = "Yes (non-destructive merge mode)" if plan.existing_chart_detected else "No (new chart creation)"
        self.console.print(f"Chart Exists:  [bold {exist_color}]{exist_text}[/bold {exist_color}]\n")

        self.console.print("[bold]Planned Resource Actions:[/bold]")
        for item in plan.resource_items:
            action_color = "green" if item.action.value == "CREATE" else ("yellow" if item.action.value == "UPDATE" else "cyan")
            self.console.print(f"  [{action_color}][{item.action.value}][/{action_color}] [bold]{item.kind}/{item.name}[/bold] -> [cyan]{item.target_file}[/cyan]")
            self.console.print(f"     [dim]{item.reason}[/dim]")
        self.console.print("\n[dim]--------------------------------------------------------------------------------[/dim]\n")

    def report_conversion_results(self, result: ConversionResult) -> None:
        """Print the Kubernetes-to-Helm conversion completion report."""
        self.console.print("\n[bold cyan]DevWorkBench - Kubernetes to Helm Conversion Result[/bold cyan]")
        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]")
        self.console.print(f"Chart Name:    [bold green]{result.chart_name}[/bold green]")
        self.console.print(f"Chart Dir:     [bold]{result.target_dir}[/bold]\n")

        if result.created_files:
            self.console.print("[bold green]Created Files:[/bold green]")
            for cf in result.created_files:
                self.console.print(f"  {self.icon_ok} [green]{cf}[/green]")
            self.console.print()

        if result.updated_files:
            self.console.print("[bold yellow]Updated / Merged Files:[/bold yellow]")
            for uf in result.updated_files:
                self.console.print(f"  {self.icon_warn} [yellow]{uf}[/yellow]")
            self.console.print()

        if result.kept_files:
            self.console.print("[bold cyan]Preserved Existing Files:[/bold cyan]")
            for kf in result.kept_files:
                self.console.print(f"  {self.icon_ok} [dim]{kf}[/dim]")
            self.console.print()

        if result.validation_diagnostics:
            self.console.print("[bold yellow]Post-Conversion Validation Diagnostics:[/bold yellow]")
            for vd in result.validation_diagnostics:
                loc = f":{vd.line}" if vd.line else ""
                self.console.print(f"  {self.icon_warn} [bold]{vd.path}{loc}[/bold] [{vd.rule}]")
                self.console.print(f"    {vd.message}")
            self.console.print()
        else:
            self.console.print("[bold green]Post-conversion validation passed with 0 issues.[/bold green]\n")

        self.console.print(f"Duration: [dim]{result.duration_ms:.2f} ms[/dim]")
        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]\n")

    def report_build_log(self, report: BuildLogReport) -> None:
        """Print the complete human-readable report for build log analysis."""
        self.console.print("\n[bold cyan]DevWorkBench - Build Log Analysis[/bold cyan]")
        self.console.print("[dim]---------------------------------------------[/dim]")
        self.console.print(f"Log source: [bold]{report.source_path}[/bold] ({report.total_lines} lines analyzed)\n")

        if report.root_causes:
            self.console.print("[bold red]Root Cause Candidates[/bold red]")
            for rc in report.root_causes:
                self.console.print(f"  {self.icon_err} [bold red]{rc.title}[/bold red]")
                self.console.print(f"    [bold]Status:[/bold] {rc.confidence}")
                self.console.print(f"    [bold]Category:[/bold] {rc.category} | [bold]Source:[/bold] {rc.source}")
                self.console.print(f"    [dim]{rc.description}[/dim]")

                if rc.related_failures:
                    self.console.print("    [bold yellow]Related / Cascaded Failures:[/bold yellow]")
                    for rf in rc.related_failures:
                        self.console.print(f"      [dim]-> {rf}[/dim]")
                self.console.print()
        else:
            self.console.print("[bold green]No critical root-cause failure signatures detected in build log.[/bold green]\n")

        if report.diagnostics:
            self.console.print("[bold yellow]Detected Error & Warning Events[/bold yellow]")
            for diag in report.diagnostics:
                loc = f":{diag.line}" if diag.line else ""
                self.console.print(f"  {self.icon_err} [bold]{diag.path}{loc}[/bold] [{diag.rule}]")
                self.console.print(f"    {diag.message}")
                self.console.print(f"    [dim]source: {diag.source} | category: {diag.category.value}[/dim]")
            self.console.print()

        self.console.print("[dim]---------------------------------------------[/dim]")
        self.console.print(f"Total log lines:   [bold]{report.total_lines}[/bold]")
        self.console.print(f"Error events:      [bold red]{len(report.diagnostics)}[/bold red]")
        self.console.print(f"Root causes:       [bold cyan]{len(report.root_causes)}[/bold cyan]")
        self.console.print(f"Analysis duration: [dim]{report.duration_ms:.2f} ms[/dim]")
        self.console.print("\n[bold green]No files modified.[/bold green]\n")

    def report_tools_dashboard(self, adapters: list[BaseAdapter]) -> None:
        """Print dashboard of available vs missing analysis engines."""
        self.console.print("\n[bold cyan]DevWorkBench - Analysis Engines Status[/bold cyan]")
        self.console.print("[dim]---------------------------------------------[/dim]\n")

        seen_names = set()
        for adapter in adapters:
            if adapter.name in seen_names:
                continue
            seen_names.add(adapter.name)

            is_avail, warn = adapter.is_available()
            if is_avail:
                self.console.print(f"  {self.icon_ok} [bold green]{adapter.name:<25}[/bold green] [dim]({adapter.technology.value})[/dim]")
            else:
                self.console.print(f"  {self.icon_warn} [bold yellow]{adapter.name:<25}[/bold yellow] [dim]({adapter.technology.value})[/dim] - [italic]Unavailable[/italic]")
                if warn:
                    self.console.print(f"     [dim]{warn.install_hint}[/dim]")

        self.console.print("\n[dim]---------------------------------------------[/dim]\n")

    def report_capabilities_dashboard(self, results: dict[Any, Any]) -> None:
        """Print dashboard of capabilities, priority selection, and provider availability."""
        self.console.print("\n[bold cyan]DevWorkBench - Capability Providers & Hierarchy[/bold cyan]")
        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]\n")

        for cap, res in results.items():
            cap_name = cap.value if hasattr(cap, "value") else str(cap)
            selected = res.selected_provider
            p_val = int(res.priority)
            p_name = res.priority.name if hasattr(res.priority, "name") else str(res.priority)

            if res.status == "available" and selected:
                status_icon = self.icon_ok
                status_color = "green"
                ver_str = f" v{selected.version}" if selected.version else ""
                cmd_str = f" [cyan]`{selected.real_command}`[/cyan]" if selected.real_command else ""
                provider_desc = f"[bold green]{selected.name}[/bold green]{ver_str}{cmd_str} ([dim]{selected.source} | {selected.license}[/dim])"
            elif res.status == "configured_unavailable":
                status_icon = self.icon_err
                status_color = "red"
                provider_desc = f"[bold red]Configured Unavailable[/bold red] - [dim]{res.message}[/dim]"
            else:
                status_icon = self.icon_warn
                status_color = "yellow"
                provider_desc = "[bold yellow]Manual Review Required[/bold yellow] - [dim]No automated provider[/dim]"

            priority_badge = f"[bold {status_color}]P{p_val}:{p_name}[/bold {status_color}]"
            self.console.print(f"  {status_icon} [bold cyan]{cap_name:<30}[/bold cyan] {priority_badge:<25} {provider_desc}")
            if res.reason:
                self.console.print(f"     [dim]Reason: {res.reason}[/dim]")
            if res.fallback_provider:
                self.console.print(f"     [dim]Fallback: {res.fallback_provider}[/dim]")

        self.console.print("\n[dim]Hierarchy: 1=Native Ecosystem | 2=Open-Source Library | 3=DevWorkBench Logic | 4=Manual Review[/dim]")
        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]\n")

    def report_setup_results(self, report: Any) -> None:
        """Print the dependency installation and setup summary report."""
        self.console.print("\n[bold cyan]DevWorkBench - Dependency & Tool Setup[/bold cyan]")
        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]\n")

        if report.successful:
            self.console.print("[bold green]Installed & Verified Successfully:[/bold green]")
            for r in report.successful:
                ver = f" (v{r.version})" if r.version else ""
                self.console.print(f"  {self.icon_ok} [bold green]{r.tool_name}[/bold green]{ver} [dim]({r.technology.value})[/dim]: {r.message}")
            self.console.print()

        if report.already_available:
            self.console.print("[bold cyan]Already Installed & Verified:[/bold cyan]")
            for r in report.already_available:
                ver = f" (v{r.version})" if r.version else ""
                self.console.print(f"  {self.icon_ok} [cyan]{r.tool_name}[/cyan]{ver} [dim]({r.technology.value})[/dim]")
            self.console.print()

        if report.failed:
            self.console.print("[bold red]Installation Failed (Safe Fallbacks Active):[/bold red]")
            for r in report.failed:
                err_code = f" [{r.error_kind.value}]" if r.error_kind else ""
                self.console.print(f"  {self.icon_err} [bold red]{r.tool_name}[/bold red]{err_code} [dim]({r.technology.value})[/dim]")
                self.console.print(f"     [dim]{r.message}[/dim]")
                if r.fallback_provider:
                    self.console.print(f"     [yellow]→ Fallback provider: {r.fallback_provider}[/yellow]")
            self.console.print()

        if report.skipped:
            self.console.print("[bold yellow]Manual Setup / Skipped:[/bold yellow]")
            for r in report.skipped:
                self.console.print(f"  {self.icon_warn} [yellow]{r.tool_name}[/yellow] [dim]({r.technology.value})[/dim]: {r.message}")
            self.console.print()

        if report.fallbacks:
            self.console.print("[bold]Active Fallback Summary:[/bold]")
            for fb in report.fallbacks:
                self.console.print(f"  → [yellow]{fb['tool']}[/yellow] ({fb['technology']}) → [bold]{fb['fallback']}[/bold] [dim](Reason: {fb['reason']})[/dim]")
            self.console.print()

        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]\n")

    def report_doctor_dashboard(self, diagnostic: Any) -> None:
        """Print the environment diagnostic health dashboard."""
        self.console.print("\n[bold cyan]DevWorkBench - Environment Doctor & Health Diagnostics[/bold cyan]")
        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]\n")

        self.console.print("[bold]System Information:[/bold]")
        self.console.print(f"  DevWorkBench: [bold green]v{diagnostic.devworkbench_version}[/bold green]")
        self.console.print(f"  Python:       [bold]{diagnostic.python_version}[/bold] ({diagnostic.platform_name} {diagnostic.platform_release} {diagnostic.architecture})")
        self.console.print(f"  Executable:   [dim]{diagnostic.python_executable}[/dim]\n")

        self.console.print("[bold]Core Python Runtime Dependencies:[/bold]")
        for dep in diagnostic.core_dependencies:
            icon = self.icon_ok if dep.available else self.icon_err
            status_style = "green" if dep.available else "red"
            ver_str = f" v{dep.version}" if dep.version else ""
            self.console.print(f"  {icon} [{status_style}]{dep.name}[/{status_style}]{ver_str}")
        self.console.print()

        self.console.print("[bold]External Tools & Engines Status:[/bold]")
        for tool in diagnostic.external_tools:
            if tool.available:
                ver_str = f" v{tool.version}" if tool.version else ""
                self.console.print(f"  {self.icon_ok} [bold green]{tool.name:<22}[/bold green]{ver_str:<18} [dim]({tool.source} | {tool.license})[/dim]")
            else:
                self.console.print(f"  {self.icon_warn} [bold yellow]{tool.name:<22}[/bold yellow] [dim]Unavailable locally[/dim]")
                if tool.install_hint:
                    self.console.print(f"     [dim]{tool.install_hint}[/dim]")
        self.console.print()

        self.console.print("[bold]Capability Priority Resolution:[/bold]")
        cap = diagnostic.capability_summary
        self.console.print(f"  Total Capabilities:       [bold]{cap.get('total_capabilities', 0)}[/bold]")
        self.console.print(f"  Native Ecosystem (P1):    [bold green]{cap.get('native_active', 0)}[/bold green]")
        self.console.print(f"  Open-Source Library (P2): [bold green]{cap.get('opensource_active', 0)}[/bold green]")
        self.console.print(f"  DevWorkBench Logic (P3):  [bold cyan]{cap.get('devworkbench_active', 0)}[/bold cyan]")
        self.console.print(f"  Manual Review (P4):       [bold yellow]{cap.get('manual_review_required', 0)}[/bold yellow]\n")

        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]\n")

    def report_rules_catalog(self, rules: list[BaseRule], technology_filter: str | None = None) -> None:
        """Print catalog of all built-in DevOps best-practice rules."""
        self.console.print("\n[bold cyan]DevWorkBench - DevOps Best-Practice Rules[/bold cyan]")
        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]\n")

        for rule in rules:
            meta = rule.metadata
            if technology_filter and meta.technology.value.lower() != technology_filter.lower():
                continue

            sev_color = "red" if meta.severity == DiagnosticSeverity.ERROR else "yellow"
            p_badge = f"[P{meta.provider_priority}:{meta.provider}]"
            self.console.print(f"  [bold cyan]{meta.rule_id:<14}[/bold cyan] [{sev_color}]{meta.severity.value.upper():<7}[/{sev_color}] [bold]{meta.technology.value:<14}[/bold] [dim]{meta.category.value:<14}[/dim] [dim]{p_badge}[/dim]")
            self.console.print(f"    [bold]Description:[/bold] {meta.description}")
            if meta.rationale:
                self.console.print(f"    [dim]Rationale:   {meta.rationale}[/dim]")

            safety_val = meta.fix_safety.value if hasattr(meta.fix_safety, "value") else str(meta.fix_safety)
            autofix_str = "Yes" if meta.autofix_supported else "No"
            self.console.print(f"    [dim]Fix Safety:  {safety_val} (Autofix: {autofix_str})[/dim]")

            if meta.false_positive_notes:
                self.console.print(f"    [dim]False Positives: {meta.false_positive_notes}[/dim]")

            doc_url = meta.documentation_url or meta.help_url
            if doc_url:
                self.console.print(f"    [dim]Docs:        {doc_url}[/dim]")
            self.console.print()

        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]\n")

    def report_fix_plan(self, plan: FixPlan, dry_run: bool = False) -> None:
        """Print the human-readable fix plan before execution."""
        title = "DevWorkBench - Fix (Dry Run)" if dry_run else "DevWorkBench Fix"
        self.console.print(f"\n[bold cyan]{title}[/bold cyan]")
        self.console.print("[dim]---------------------------------------------[/dim]\n")

        self.console.print(f"Files to modify:       [bold]{len(plan.files_to_modify)}[/bold]")
        self.console.print(f"Safe fixes available:  [bold green]{len(plan.safe_candidates)}[/bold green]")
        self.console.print(f"Manual fixes:          [bold yellow]{len(plan.manual_candidates)}[/bold yellow]")
        if plan.conflicts:
            self.console.print(f"Conflicts detected:    [bold red]{len(plan.conflicts)}[/bold red]")
        self.console.print()

        if plan.safe_candidates:
            self.console.print("[bold]Planned changes:[/bold]\n")
            # Group by file
            by_file: dict[str, list[FixCandidate]] = {}
            for c in plan.safe_candidates:
                if c.path not in by_file:
                    by_file[c.path] = []
                by_file[c.path].append(c)

            for path_str, candidates in by_file.items():
                self.console.print(f"[bold cyan]{path_str}[/bold cyan]")
                for c in candidates:
                    rule_str = f"[{c.rule}] " if c.rule else ""
                    line_str = f":{c.line}" if c.line else ""
                    self.console.print(f"  {self.icon_ok} {rule_str}{c.description}{line_str}")
                    self.console.print(f"    [dim]Engine: {c.source} | Safety: {c.fix_safety.value}[/dim]")
                self.console.print()

        if plan.conflicts:
            self.console.print("[bold red]Conflicting automatic fixes:[/bold red]\n")
            for conf in plan.conflicts:
                self.console.print(f"  {self.icon_warn} [bold]{conf.path}[/bold]")
                self.console.print(f"    [dim]{conf.reason}[/dim]")
                self.console.print("    [italic]Automatic modification skipped. Manual review required.[/italic]\n")

        if dry_run:
            self.console.print("[dim]---------------------------------------------[/dim]")
            self.console.print("[bold green]No files modified.[/bold green]\n")

    def report_fix_results(self, report: FixReport) -> None:
        """Print the human-readable post-fix validation report."""
        self.console.print("\n[bold cyan]DevWorkBench Fix[/bold cyan]")
        self.console.print("[dim]---------------------------------------------[/dim]\n")

        sum_data = report.summary
        self.console.print("[bold]Before:[/bold]")
        self.console.print(f"  Errors:   {sum_data.before_errors}")
        self.console.print(f"  Warnings: {sum_data.before_warnings}\n")

        self.console.print("[bold]Applied:[/bold]")
        if sum_data.applied_count > 0:
            self.console.print(f"  {self.icon_ok} [bold green]{sum_data.applied_count} fixes applied[/bold green]")
        else:
            self.console.print("  [dim]0 fixes applied[/dim]")

        if sum_data.failed_count > 0:
            self.console.print(f"  {self.icon_err} [bold red]{sum_data.failed_count} fixes failed[/bold red]")
            for r in report.results:
                if r.status == "failed":
                    self.console.print(f"    [red]{r.path}[/red]: {r.message}")

        if sum_data.skipped_count > 0:
            self.console.print(f"  {self.icon_warn} [bold yellow]{sum_data.skipped_count} fixes skipped[/bold yellow]")
            for r in report.results:
                if r.status == "skipped":
                    self.console.print(f"    [yellow]{r.path}[/yellow]: {r.message}")
        self.console.print()

        self.console.print("[bold]Validation:[/bold]")
        self.console.print(f"  {self.icon_ok} [bold green]{sum_data.resolved_count} issues resolved[/bold green]")
        if sum_data.remaining_count > 0:
            self.console.print(f"  {self.icon_warn} [bold yellow]{sum_data.remaining_count} issues remain[/bold yellow]")
        else:
            self.console.print("  [bold green]0 issues remain[/bold green]")
        self.console.print()

        self.console.print("[bold]After:[/bold]")
        self.console.print(f"  Errors:         {sum_data.after_errors}")
        self.console.print(f"  Warnings:       {sum_data.after_warnings}")
        self.console.print(f"  Files modified: [bold]{sum_data.files_modified}[/bold]")
        self.console.print(f"  Duration:       [dim]{sum_data.duration_ms:.2f} ms[/dim]\n")
        self.console.print("[dim]---------------------------------------------[/dim]\n")

    def report_workspace_candidates(self, info: dict[str, Any]) -> None:
        """Report discovered candidates in current workspace."""
        self.console.print("\n[bold cyan]Scanning current directory...[/bold cyan]\n")
        self.console.print("[bold]Detected technologies:[/bold]")
        if info.get("k8s_resources_count", 0) > 0:
            self.console.print(f"  {self.icon_ok} [green]Kubernetes manifests[/green]")
        if info.get("helm_charts"):
            self.console.print(f"  {self.icon_ok} [green]Existing Helm chart(s):[/green] {', '.join(info['helm_charts'])}")
        for tech in info.get("other_technologies", []):
            self.console.print(f"  {self.icon_ok} [cyan]{tech}[/cyan]")
        self.console.print()

        k8s_by_kind = info.get("k8s_by_kind", {})
        if k8s_by_kind:
            self.console.print("[bold]Kubernetes resources:[/bold]")
            for kind, count in k8s_by_kind.items():
                self.console.print(f"  {kind:<18} [bold cyan]{count}[/bold cyan]")
            self.console.print()

    def report_migration_plan(self, plan: Any) -> None:
        """Render migration plan and dependency graph."""
        self.console.print("\n[bold cyan]DevWorkBench - Kubernetes to Helm Migration Plan[/bold cyan]")
        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]\n")

        self.console.print(f"Target Chart Name: [bold green]{plan.target_chart_name}[/bold green]")
        self.console.print(f"Target Directory:  [bold]{plan.target_directory}[/bold]")
        if plan.reference_name:
            self.console.print(f"Reference Pattern: [bold cyan]{plan.reference_name}[/bold cyan]")
        self.console.print(f"Discovered:        [bold]{len(plan.discovered_resources)} Kubernetes resources[/bold]\n")

        if plan.relationships:
            self.console.print("[bold yellow]Resource References & Dependencies:[/bold yellow]")
            for rel in plan.relationships:
                status_str = rel.status.value if hasattr(rel.status, "value") else str(rel.status)
                if status_str == "REFERENCED_AND_PRESENT":
                    icon = self.icon_ok
                    st_desc = "[green]PRESENT[/green]"
                elif status_str == "REFERENCED_BUT_MISSING":
                    icon = self.icon_err
                    st_desc = "[bold red]MISSING[/bold red]"
                else:
                    icon = self.icon_info
                    st_desc = f"[dim]{status_str}[/dim]"

                self.console.print(f"  {icon} [bold]{rel.source_kind}/{rel.source_name}[/bold] -> [cyan]{rel.target_kind}/{rel.target_name}[/cyan] ({st_desc})")
                if rel.details:
                    self.console.print(f"     [dim]{rel.details}[/dim]")
            self.console.print()

        self.console.print("[bold]Planned Helm Templates:[/bold]")
        for item in plan.planned_items:
            priority_str = f" [{item.priority}]" if hasattr(item, "priority") and item.priority else ""
            prov = f"[dim]({item.provider}{priority_str})[/dim]"
            self.console.print(f"  {self.icon_ok} [bold green]{item.target_file:<30}[/bold green] from [cyan]{item.source_resource:<25}[/cyan] {prov}")
            self.console.print(f"     [dim]{item.reason}[/dim]")
        self.console.print("\n[dim]--------------------------------------------------------------------------------[/dim]\n")

    def report_migration_results(self, result: Any) -> None:
        """Render final migration results, traceability, and validation."""
        self.console.print("\n[bold green]DevWorkBench - Migration Completed Successfully[/bold green]")
        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]\n")

        self.console.print(f"Chart Generated:   [bold cyan]{result.chart_name}[/bold cyan]")
        self.console.print(f"Chart Location:    [bold]{result.target_dir}[/bold]")
        self.console.print(f"Execution Time:    [dim]{result.duration_ms:.2f} ms[/dim]\n")

        if result.created_files:
            self.console.print("[bold]Generated Files:[/bold]")
            for f in result.created_files:
                self.console.print(f"  {self.icon_ok} [green]{f}[/green]")
            self.console.print()

        if result.plan and result.plan.planned_items:
            self.console.print("[bold]Resource Traceability:[/bold]")
            for item in result.plan.planned_items:
                priority_str = f" [{item.priority}]" if hasattr(item, "priority") and item.priority else ""
                self.console.print(f"  [bold cyan]{item.target_file}[/bold cyan]")
                self.console.print(f"    Source:    {item.source_resource}")
                self.console.print(f"    Provider:  [bold]{item.provider}[/bold]{priority_str}")
                if item.pattern_applied:
                    self.console.print(f"    Reference: {item.pattern_applied}")
                if item.reason:
                    self.console.print(f"    Detail:    [dim]{item.reason}[/dim]")
            self.console.print()

        if result.validation_executions:
            self.console.print("[bold]Validation Telemetry:[/bold]")
            for ex in result.validation_executions:
                if ex.status == "PASS":
                    self.console.print(f"  {self.icon_ok} [bold green]{ex.command:<20}[/bold green] [dim]PASS ({ex.duration_ms:.1f}ms)[/dim]")
                elif ex.status == "UNAVAILABLE":
                    self.console.print(f"  {self.icon_warn} [bold yellow]{ex.command:<20}[/bold yellow] [dim]UNAVAILABLE ({ex.unavailable_reason})[/dim]")
                else:
                    self.console.print(f"  {self.icon_err} [bold red]{ex.command:<20}[/bold red] [red]FAIL (exit {ex.exit_code})[/red]")
            self.console.print()

        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]\n")

    def report_examples_list(self, examples: list[dict[str, Any]]) -> None:
        """Render list of ingested reference examples."""
        self.console.print("\n[bold cyan]DevWorkBench - Ingested Reference Chart Examples[/bold cyan]")
        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]\n")

        if not examples:
            self.console.print("  [italic dim]No reference examples ingested yet. Add one using:[/italic dim]")
            self.console.print("  [cyan]devworkbench examples add ./my-chart --name company-standard[/cyan]\n")
            return

        for ex in examples:
            features: list[str] = []
            if ex.get("has_hpa"):
                features.append("HPA")
            if ex.get("has_ingress"):
                features.append("Ingress")
            feat_str = f" [cyan][{', '.join(features)}][/cyan]" if features else ""
            self.console.print(f"  {self.icon_ok} [bold green]{ex['name']:<25}[/bold green] (Chart: {ex['chart_name']} v{ex['chart_version']}) {feat_str}")
            self.console.print(f"     [dim]{ex['templates_count']} templates | Prefix: '{ex.get('helper_prefix', '')}'[/dim]")
        self.console.print("\n[dim]--------------------------------------------------------------------------------[/dim]\n")

    def report_example_details(self, pattern: Any) -> None:
        """Render detailed inspection of an ingested reference chart."""
        self.console.print(f"\n[bold cyan]Reference Chart Example: [bold green]{pattern.name}[/bold green][/bold cyan]")
        self.console.print("[dim]--------------------------------------------------------------------------------[/dim]\n")

        self.console.print(f"Chart Name:     [bold]{pattern.chart_name}[/bold]")
        self.console.print(f"Chart Version:  {pattern.chart_version}")
        self.console.print(f"App Version:    {pattern.app_version}")
        self.console.print(f"Helper Prefix:  [cyan]{pattern.helper_prefix}[/cyan]")
        self.console.print(f"Source Path:    [dim]{pattern.source_dir or 'N/A'}[/dim]\n")

        self.console.print("[bold]Detected Templates:[/bold]")
        for t in pattern.templates_found:
            self.console.print(f"  {self.icon_ok} {t}")
        self.console.print()

        if pattern.label_scheme:
            self.console.print("[bold]Label Scheme Conventions:[/bold]")
            for k, v in list(pattern.label_scheme.items())[:6]:
                self.console.print(f"  [dim]{k}:[/dim] {v}")
            self.console.print()

        self.console.print(f"HPA Support:     {'[green]Yes[/green]' if pattern.has_hpa else '[dim]No[/dim]'}")
        self.console.print(f"Ingress Support: {'[green]Yes[/green]' if pattern.has_ingress else '[dim]No[/dim]'}")
        self.console.print("\n[dim]--------------------------------------------------------------------------------[/dim]\n")


class JsonReporter:
    """Serializes scan and build log results into formatted, stable JSON output."""

    @classmethod
    def format(cls, result: Any, indent: int = 2) -> str:
        """Return JSON string representation."""
        if hasattr(result, "to_dict"):
            return json.dumps(result.to_dict(), indent=indent)
        return json.dumps(result, indent=indent)

    @classmethod
    def write_to_file(cls, result: Any, file_path: str, indent: int = 2) -> None:
        """Write JSON output to a file."""
        content = cls.format(result, indent=indent)
        Path(file_path).write_text(content, encoding="utf-8")
