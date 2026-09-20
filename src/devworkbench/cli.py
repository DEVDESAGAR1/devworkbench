"""Command Line Interface for DevWorkBench."""

import sys
from pathlib import Path

import click
from rich.console import Console

from devworkbench import __version__
from devworkbench.adapters.registry import AdapterRegistry
from devworkbench.configuration import ScanConfig
from devworkbench.reporter import HumanReporter, JsonReporter
from devworkbench.rules.registry import RuleRegistry
from devworkbench.runner import Runner

console = Console(emoji=False, safe_box=True)
error_console = Console(stderr=True, emoji=False, safe_box=True)


@click.group(
    invoke_without_command=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(
    version=__version__,
    prog_name="DevWorkBench",
    message="%(prog)s version %(version)s",
)
def main() -> None:
    """DevWorkBench: A local-first, open-source developer and DevOps workbench CLI.

    Analyze, format, lint, validate, and fix common DevOps and developer files.
    """


@main.command(name="version")
def version_cmd() -> None:
    """Show the DevWorkBench version and exit."""
    console.print(f"[bold cyan]DevWorkBench[/bold cyan] version [bold green]{__version__}[/bold green]")


from devworkbench.capabilities import CapabilityResolver, DependencyInstaller
from devworkbench.doctor import DoctorEngine


@main.command(name="doctor")
@click.option("--json", "json_flag", is_flag=True, default=False, help="Output environment diagnostics as JSON.")
def doctor_cmd(json_flag: bool) -> None:
    """Inspect environment health, Python runtime, external tools, and capabilities."""
    diagnostic = DoctorEngine.diagnose()
    if json_flag:
        print(JsonReporter.format(diagnostic))
    else:
        reporter = HumanReporter()
        reporter.report_doctor_dashboard(diagnostic)


@main.command(name="setup")
@click.option("-t", "--technology", type=str, default=None, help="Install dependencies for a specific technology.")
@click.option("--dry-run", is_flag=True, default=False, help="Preview dependency installations without executing them.")
@click.option("--json", "json_flag", is_flag=True, default=False, help="Output setup report as JSON.")
def setup_cmd(technology: str | None, dry_run: bool, json_flag: bool) -> None:
    """Explicitly verify and install required DevOps tools and libraries."""
    installer = DependencyInstaller()
    report = installer.setup_environment(technology=technology, dry_run=dry_run)

    if json_flag:
        print(JsonReporter.format(report))
    else:
        reporter = HumanReporter()
        reporter.report_setup_results(report)


@main.command(name="capabilities")
@click.option("-t", "--technology", type=str, default=None, help="Filter capabilities by technology.")
@click.option("--json", "json_flag", is_flag=True, default=False, help="Output capabilities and provider selection as JSON.")
def capabilities_cmd(technology: str | None, json_flag: bool) -> None:
    """Inspect supported capabilities and active provider hierarchy resolution."""
    config = ScanConfig.load_from_dir(Path(".").resolve())
    resolver = CapabilityResolver()
    results = resolver.resolve_all(preferences=config.provider_preferences)

    if technology:
        filtered = {}
        for cap, res in results.items():
            if res.selected_provider and res.selected_provider.technology.value.lower() == technology.lower() or any(p.technology.value.lower() == technology.lower() for p in res.all_providers):
                filtered[cap] = res
        results = filtered

    if json_flag:
        json_data = [res.to_dict() for res in results.values()]
        print(JsonReporter.format(json_data))
    else:
        reporter = HumanReporter()
        reporter.report_capabilities_dashboard(results)


@main.command(name="tools")
@click.option("--json", "json_flag", is_flag=True, default=False, help="Output status as JSON.")
def tools_cmd(json_flag: bool) -> None:
    """Show status of all supported open-source analysis engines."""
    registry = AdapterRegistry()
    if json_flag:
        tools_data = []
        seen = set()
        for adapter in registry.adapters:
            if adapter.name in seen:
                continue
            seen.add(adapter.name)
            is_avail, warn = adapter.is_available()
            tools_data.append({
                "name": adapter.name,
                "technology": adapter.technology.value,
                "available": is_avail,
                "install_hint": warn.install_hint if warn else None,
            })
        print(JsonReporter.format(tools_data))
    else:
        reporter = HumanReporter()
        reporter.report_tools_dashboard(registry.adapters)


@main.command(name="rules")
@click.option("-t", "--technology", type=str, default=None, help="Filter rules by technology (e.g. kubernetes, jenkins, openshift, helm).")
@click.option("--json", "json_flag", is_flag=True, default=False, help="Output rules catalog as JSON.")
def rules_cmd(technology: str | None, json_flag: bool) -> None:
    """List all built-in DevOps best-practice and security rules."""
    registry = RuleRegistry()
    if json_flag:
        rules_data = []
        for r in registry.rules:
            meta = r.metadata
            if technology and meta.technology.value.lower() != technology.lower():
                continue
            rules_data.append({
                "rule_id": meta.rule_id,
                "technology": meta.technology.value,
                "severity": meta.severity.value,
                "category": meta.category.value,
                "description": meta.description,
                "rationale": meta.rationale,
                "provider": meta.provider,
                "provider_priority": meta.provider_priority,
                "rule_origin": meta.rule_origin,
                "documentation_url": meta.documentation_url or meta.help_url,
                "autofix_supported": meta.autofix_supported,
                "fix_safety": meta.fix_safety.value if hasattr(meta.fix_safety, "value") else str(meta.fix_safety),
                "false_positive_notes": meta.false_positive_notes,
                "help_url": meta.help_url,
            })
        print(JsonReporter.format(rules_data))
    else:
        reporter = HumanReporter()
        reporter.report_rules_catalog(registry.rules, technology_filter=technology)


@main.command(name="scan")
@click.argument("paths", nargs=-1, type=click.Path(exists=False, file_okay=True, dir_okay=True, readable=True))
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["human", "json"], case_sensitive=False),
    default="human",
    help="Output format (human-readable terminal output or structured JSON).",
)
@click.option(
    "--json",
    "json_flag",
    is_flag=True,
    default=False,
    help="Shortcut for --format json.",
)
@click.option(
    "-i",
    "--ignore",
    "custom_ignores",
    multiple=True,
    help="Custom glob patterns to ignore during scan (can be specified multiple times).",
)
@click.option(
    "-o",
    "--output",
    "output_file",
    type=click.Path(dir_okay=False, writable=True),
    help="Write scan report to specified output file.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Enable detailed/verbose output (includes unknown files and detection hints).",
)
def scan_cmd(
    paths: tuple[str, ...],
    output_format: str,
    json_flag: bool,
    custom_ignores: tuple,
    output_file: str | None,
    verbose: bool,
) -> None:
    """Recursively scan and analyze one or more files and/or directories for DevOps diagnostics."""
    if json_flag:
        output_format = "json"

    target_paths = list(paths) if paths else ["."]

    for p in target_paths:
        target_path = Path(p)
        if not target_path.exists():
            error_console.print(f"[bold red]Error:[/bold red] Target path does not exist: [yellow]{p}[/yellow]")
            sys.exit(1)

    # Load configuration from workspace root if present
    base_dir = Path(target_paths[0]).resolve()
    if base_dir.is_file():
        base_dir = base_dir.parent
    config = ScanConfig.load_from_dir(base_dir)
    config.target_path = target_paths[0]
    config.verbose = verbose

    if custom_ignores:
        config.add_custom_ignores(list(custom_ignores))

    runner = Runner(config=config)
    try:
        runner.run_scan(
            target_paths=target_paths,
            output_format=output_format,
            output_file=output_file,
            verbose=verbose,
        )
    except Exception as e:
        error_console.print(f"[bold red]Scan failed:[/bold red] {e}")
        sys.exit(1)


@main.command(name="fix")
@click.argument("paths", nargs=-1, type=click.Path(exists=False, file_okay=True, dir_okay=True, readable=True))
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    default=False,
    help="Preview planned fixes without modifying any files.",
)
@click.option(
    "-y",
    "--yes",
    "yes_flag",
    is_flag=True,
    default=False,
    help="Automatically approve safe fixes (bypass interactive confirmation).",
)
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["human", "json"], case_sensitive=False),
    default="human",
    help="Output format (human-readable terminal output or structured JSON).",
)
@click.option(
    "--json",
    "json_flag",
    is_flag=True,
    default=False,
    help="Shortcut for --format json.",
)
@click.option(
    "-o",
    "--output",
    "output_file",
    type=click.Path(dir_okay=False, writable=True),
    help="Write fix report to specified output file.",
)
def fix_cmd(
    paths: tuple[str, ...],
    dry_run: bool,
    yes_flag: bool,
    output_format: str,
    json_flag: bool,
    output_file: str | None,
) -> None:
    """Safely apply automated fixes using native open-source engines and best-practice rules."""
    if json_flag:
        output_format = "json"

    target_paths = list(paths) if paths else ["."]

    for p in target_paths:
        target_path = Path(p)
        if not target_path.exists():
            error_console.print(f"[bold red]Error:[/bold red] Target path does not exist: [yellow]{p}[/yellow]")
            sys.exit(1)

    base_dir = Path(target_paths[0]).resolve()
    if base_dir.is_file():
        base_dir = base_dir.parent
    config = ScanConfig.load_from_dir(base_dir)

    runner = Runner(config=config)

    try:
        # Dry-run mode: show plan and make 0 modifications
        if dry_run:
            runner.run_fix(
                target_paths=target_paths,
                dry_run=True,
                confirmed=False,
                output_format=output_format,
                output_file=output_file,
            )
            return

        # Automatic approval via --yes
        if yes_flag:
            runner.run_fix(
                target_paths=target_paths,
                dry_run=False,
                confirmed=True,
                output_format=output_format,
                output_file=output_file,
            )
            return

        # Interactive Confirmation Mode
        scan_res, plan = runner.scanner.plan_fix(target_paths)

        if len(plan.safe_candidates) == 0:
            if output_format == "json":
                runner.run_fix(
                    target_paths=target_paths,
                    plan=plan,
                    dry_run=True,
                    confirmed=False,
                    output_format=output_format,
                    output_file=output_file,
                )
            else:
                console.print("\n[bold cyan]DevWorkBench Fix[/bold cyan]")
                console.print("[dim]---------------------------------------------[/dim]\n")
                console.print("No safe automatic fixes available.")
                if plan.manual_candidates:
                    console.print(f"[yellow]{len(plan.manual_candidates)} issues require manual review.[/yellow]")
                if plan.conflicts:
                    console.print(f"[bold red]{len(plan.conflicts)} conflicting issues skipped.[/bold red]")
                console.print("\n[bold green]No files modified.[/bold green]\n")
            return

        # If json format without --yes, print the plan JSON
        if output_format == "json":
            runner.run_fix(
                target_paths=target_paths,
                plan=plan,
                dry_run=True,
                confirmed=False,
                output_format=output_format,
                output_file=output_file,
            )
            return

        # Show the plan to the user in human format
        reporter = HumanReporter()
        reporter.report_fix_plan(plan, dry_run=False)

        # Mandatory confirmation (default: No)
        prompt_msg = f"Apply {len(plan.safe_candidates)} safe fixes?"
        confirmed = click.confirm(prompt_msg, default=False)

        if not confirmed:
            console.print("\n[bold yellow]No changes applied.[/bold yellow]")
            console.print("[bold green]No files modified.[/bold green]\n")
            return

        # User confirmed 'Yes' -> Apply safe fixes & re-validate
        console.print("\n[bold cyan]Applying safe fixes...[/bold cyan]")
        runner.run_fix(
            target_paths=target_paths,
            plan=plan,
            dry_run=False,
            confirmed=True,
            output_format=output_format,
            output_file=output_file,
        )

    except Exception as e:
        error_console.print(f"[bold red]Fix failed:[/bold red] {e}")
        sys.exit(1)


@main.command(name="analyze-build")
@click.argument("log_path", type=str)
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["human", "json"], case_sensitive=False),
    default="human",
    help="Output format (human-readable terminal output or structured JSON).",
)
@click.option(
    "--json",
    "json_flag",
    is_flag=True,
    default=False,
    help="Shortcut for --format json.",
)
@click.option(
    "-o",
    "--output",
    "output_file",
    type=click.Path(dir_okay=False, writable=True),
    help="Write analysis report to specified output file.",
)
def analyze_build_cmd(
    log_path: str,
    output_format: str,
    json_flag: bool,
    output_file: str | None,
) -> None:
    """Streamingly analyze a Jenkins, Kubernetes, OpenShift, Helm, or Docker build log file (or '-' for stdin)."""
    if json_flag:
        output_format = "json"

    if log_path != "-" and not Path(log_path).exists():
        error_console.print(f"[bold red]Error:[/bold red] Log file does not exist: [yellow]{log_path}[/yellow]")
        sys.exit(1)

    runner = Runner()
    try:
        if log_path == "-":
            stdin_stream = click.get_text_stream("stdin")
            runner.run_analyze_build(
                log_path="-",
                output_format=output_format,
                output_file=output_file,
                stream=stdin_stream,
            )
        else:
            runner.run_analyze_build(
                log_path=log_path,
                output_format=output_format,
                output_file=output_file,
            )
    except Exception as e:
        error_console.print(f"[bold red]Build analysis failed:[/bold red] {e}")
        sys.exit(1)


@main.command(name="clean")
@click.argument("target", type=str, default="-")
@click.option(
    "-w",
    "--write",
    "write_flag",
    is_flag=True,
    default=False,
    help="Overwrite the source file directly with cleaned content.",
)
@click.option(
    "-o",
    "--output",
    "output_file",
    type=click.Path(dir_okay=False, writable=True),
    help="Write cleaned manifest to specified output file.",
)
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["human", "yaml", "diff", "json"], case_sensitive=False),
    default="yaml",
    help="Output format (yaml, diff, human-readable terminal output, or JSON).",
)
@click.option(
    "--json",
    "json_flag",
    is_flag=True,
    default=False,
    help="Shortcut for --format json.",
)
def clean_cmd(
    target: str,
    write_flag: bool,
    output_file: str | None,
    output_format: str,
    json_flag: bool,
) -> None:
    """Clean runtime status and metadata from Kubernetes manifests (file or '-' for stdin)."""
    if json_flag:
        output_format = "json"

    raw_input = ""
    write_target: str | None = output_file

    if target == "-":
        stdin_stream = click.get_text_stream("stdin")
        raw_input = stdin_stream.read()
    else:
        target_path = Path(target)
        if not target_path.is_file():
            error_console.print(f"[bold red]Error:[/bold red] File does not exist: [yellow]{target}[/yellow]")
            sys.exit(1)
        raw_input = str(target_path)
        if write_flag:
            write_target = str(target_path)

    runner = Runner()
    try:
        runner.run_clean(
            target_path_or_content=raw_input,
            write_output_path=write_target,
            output_format=output_format,
            output_file=output_file if not write_flag else None,
        )
    except Exception as e:
        error_console.print(f"[bold red]Clean failed:[/bold red] {e}")
        sys.exit(1)


@main.command(name="convert")
@click.argument("targets", nargs=-1, type=click.Path(exists=False, file_okay=True, dir_okay=True, readable=True))
@click.option(
    "--to",
    "to_format",
    type=click.Choice(["helm"], case_sensitive=False),
    default="helm",
    help="Target conversion format (currently supports 'helm').",
)
@click.option(
    "-o",
    "--output-dir",
    "output_dir",
    type=click.Path(file_okay=False, writable=True),
    default=".",
    help="Target output directory for generated chart.",
)
@click.option(
    "-n",
    "--name",
    "chart_name",
    type=str,
    default=None,
    help="Name of the generated Helm chart.",
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    default=False,
    help="Preview conversion plan without writing any files.",
)
@click.option(
    "--force",
    "force",
    is_flag=True,
    default=False,
    help="Overwrite existing template files in target chart directory.",
)
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["human", "json"], case_sensitive=False),
    default="human",
    help="Output format (human-readable terminal output or structured JSON).",
)
@click.option(
    "--json",
    "json_flag",
    is_flag=True,
    default=False,
    help="Shortcut for --format json.",
)
def convert_cmd(
    targets: tuple[str, ...],
    to_format: str,
    output_dir: str,
    chart_name: str | None,
    dry_run: bool,
    force: bool,
    output_format: str,
    json_flag: bool,
) -> None:
    """Convert Kubernetes YAML manifests into a structured Helm chart."""
    if json_flag:
        output_format = "json"

    if not targets:
        error_console.print("[bold red]Error:[/bold red] Missing input target paths to convert.")
        sys.exit(1)

    target_paths = list(targets)
    for p in target_paths:
        if not Path(p).exists():
            error_console.print(f"[bold red]Error:[/bold red] Path does not exist: [yellow]{p}[/yellow]")
            sys.exit(1)

    runner = Runner()
    try:
        runner.run_convert(
            input_paths=target_paths,
            target_dir=output_dir,
            chart_name=chart_name,
            to_format=to_format,
            dry_run=dry_run,
            force=force,
            output_format=output_format,
        )
    except Exception as e:
        error_console.print(f"[bold red]Conversion failed:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
