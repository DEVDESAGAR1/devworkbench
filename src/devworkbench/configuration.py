"""Configuration management and file loading for DevWorkBench."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from devworkbench.models import DiagnosticSeverity

DEFAULT_IGNORED_DIRS: set[str] = {
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "vendor",
    ".terraform",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "ENV",
    "build",
    "dist",
    "target",
    "bin",
    "obj",
    "out",
    "*.egg-info",
    ".idea",
    ".vscode",
    ".devworkbench_cache",
    ".DS_Store",
    "Thumbs.db",
}

DEFAULT_IGNORED_FILES: set[str] = {
    ".DS_Store",
    "Thumbs.db",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "Cargo.lock",
}

MAX_HEADER_INSPECTION_BYTES = 4096


@dataclass
class ScanConfig:
    """Configurable options for the scanner and analysis engines."""

    target_path: str = "."
    ignored_dirs: set[str] = field(default_factory=lambda: set(DEFAULT_IGNORED_DIRS))
    ignored_files: set[str] = field(default_factory=lambda: set(DEFAULT_IGNORED_FILES))
    custom_ignore_patterns: list[str] = field(default_factory=list)
    disabled_engines: set[str] = field(default_factory=set)
    disabled_rules: set[str] = field(default_factory=set)
    severity_overrides: dict[str, DiagnosticSeverity] = field(default_factory=dict)
    provider_preferences: dict[str, str] = field(default_factory=dict)
    follow_symlinks: bool = False
    max_inspection_bytes: int = MAX_HEADER_INSPECTION_BYTES
    verbose: bool = False

    def add_custom_ignores(self, patterns: list[str]) -> None:
        """Add custom ignore glob patterns."""
        for pattern in patterns:
            cleaned = pattern.strip()
            if cleaned:
                self.custom_ignore_patterns.append(cleaned)

    @classmethod
    def load_from_dir(cls, root_dir: Path) -> "ScanConfig":
        """Load configuration from .devworkbench.yaml or .devworkbench.json if present."""
        config = cls()
        yaml_config = root_dir / ".devworkbench.yaml"
        yml_config = root_dir / ".devworkbench.yml"
        json_config = root_dir / ".devworkbench.json"

        target_file = None
        if yaml_config.is_file():
            target_file = yaml_config
        elif yml_config.is_file():
            target_file = yml_config
        elif json_config.is_file():
            target_file = json_config

        if not target_file:
            return config

        try:
            content = target_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content) if target_file.suffix in [".yaml", ".yml"] else json.loads(content)
            if isinstance(data, dict):
                # Parse disabled engines (both formats: engines: {ruff: false} or disabled_engines: ["ruff"])
                engines = data.get("engines", {})
                if isinstance(engines, dict):
                    for engine_name, enabled in engines.items():
                        if enabled is False:
                            config.disabled_engines.add(engine_name.lower())
                elif isinstance(engines, list):
                    config.disabled_engines.update(e.lower() for e in engines)

                top_disabled_engines = data.get("disabled_engines", [])
                if isinstance(top_disabled_engines, list):
                    config.disabled_engines.update(e.lower() for e in top_disabled_engines)

                # Parse rules (both formats: rules: {disabled: [...]}, disabled_rules: [...])
                rules_sec = data.get("rules", {})
                if isinstance(rules_sec, dict):
                    disabled = rules_sec.get("disabled", [])
                    if isinstance(disabled, list):
                        config.disabled_rules.update(disabled)
                elif isinstance(rules_sec, list):
                    config.disabled_rules.update(rules_sec)

                top_disabled_rules = data.get("disabled_rules", [])
                if isinstance(top_disabled_rules, list):
                    config.disabled_rules.update(top_disabled_rules)

                # Parse severity overrides (both formats: severity: {...} or severity_overrides: {...})
                sev_sec = data.get("severity", {}) or data.get("severity_overrides", {})
                if isinstance(sev_sec, dict):
                    for rule_id, sev_str in sev_sec.items():
                        try:
                            config.severity_overrides[rule_id] = DiagnosticSeverity(sev_str.lower())
                        except ValueError:
                            pass

                # Parse provider preferences
                # Format 1: providers: { helm: { preferred: "native" } }
                # Format 2: providers: { helm: "native" }
                # Format 3: provider_preferences: { helm: "native" }
                prov_sec = data.get("providers", {}) or data.get("provider_preferences", {})
                if isinstance(prov_sec, dict):
                    for cap_or_tech, val in prov_sec.items():
                        if isinstance(val, dict):
                            pref = val.get("preferred") or val.get("preference") or "auto"
                            config.provider_preferences[str(cap_or_tech).lower()] = str(pref).lower()
                        elif isinstance(val, str):
                            config.provider_preferences[str(cap_or_tech).lower()] = val.lower()

                # Parse ignore patterns (both formats: ignore: [...] or ignored_patterns: [...])
                ignores = data.get("ignore", []) or data.get("ignored_patterns", []) or data.get("custom_ignore_patterns", [])
                if isinstance(ignores, list):
                    config.add_custom_ignores(ignores)
        except Exception:
            pass

        return config
