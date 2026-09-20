"""Tests for `devworkbench tools` and `devworkbench rules` CLI commands."""

import json

from click.testing import CliRunner

from devworkbench.cli import main


def test_tools_command_human_output():
    runner = CliRunner()
    result = runner.invoke(main, ["tools"])
    assert result.exit_code == 0
    assert "Analysis Engines Status" in result.output
    assert "Jenkins Pipeline Analyzer" in result.output
    assert "Ruff / Python AST" in result.output
    assert "PyYAML / Yamllint" in result.output


def test_tools_command_json_output():
    runner = CliRunner()
    result = runner.invoke(main, ["tools", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) > 0

    # Check structure of tool info
    tool = data[0]
    assert "name" in tool
    assert "technology" in tool
    assert "available" in tool


def test_rules_command_human_output():
    runner = CliRunner()
    result = runner.invoke(main, ["rules"])
    assert result.exit_code == 0
    assert "DevOps Best-Practice Rules" in result.output
    assert "K8S001" in result.output
    assert "JENKINS001" in result.output


def test_rules_command_json_output():
    runner = CliRunner()
    result = runner.invoke(main, ["rules", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) > 0

    rule_ids = [r["rule_id"] for r in data]
    assert "K8S001" in rule_ids
    assert "OPENSHIFT001" in rule_ids
    assert "JENKINS001" in rule_ids
    assert "HELM001" in rule_ids
