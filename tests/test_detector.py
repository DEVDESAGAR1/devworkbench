"""Unit tests for the DetectionEngine."""

from pathlib import Path
import pytest

from devworkbench.detector import DetectionEngine
from devworkbench.models import FileCategory, Technology


def test_detect_jenkinsfile(tmp_path: Path) -> None:
    jf = tmp_path / "Jenkinsfile"
    jf.write_text("pipeline { agent any }")
    det = DetectionEngine.detect_file(jf, Path("Jenkinsfile"))
    assert det.technology == Technology.JENKINS
    assert det.category == FileCategory.DEVOPS
    assert det.confidence == 1.0


def test_detect_kubernetes_manifest(tmp_path: Path) -> None:
    k8s_file = tmp_path / "deployment.yaml"
    k8s_file.write_text("apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: my-app")
    det = DetectionEngine.detect_file(k8s_file, Path("deployment.yaml"))
    assert det.technology == Technology.KUBERNETES
    assert det.category == FileCategory.DEVOPS


def test_detect_openshift_manifest(tmp_path: Path) -> None:
    os_file = tmp_path / "route.yaml"
    os_file.write_text("apiVersion: route.openshift.io/v1\nkind: Route\nmetadata:\n  name: my-route")
    det = DetectionEngine.detect_file(os_file, Path("route.yaml"))
    assert det.technology == Technology.OPENSHIFT
    assert det.category == FileCategory.DEVOPS


def test_detect_helm_template_vs_k8s(tmp_path: Path) -> None:
    helm_tmpl = tmp_path / "templates" / "service.yaml"
    helm_tmpl.parent.mkdir(parents=True)
    helm_tmpl.write_text("apiVersion: v1\nkind: Service\nmetadata:\n  name: {{ .Release.Name }}")
    
    # When scanned in a Helm template context
    det = DetectionEngine.detect_file(
        helm_tmpl,
        Path("templates/service.yaml"),
        is_helm_template=True,
        is_helm_chart=True,
    )
    assert det.technology == Technology.HELM
    assert "Template" in (det.details or "")


def test_detect_terraform_files(tmp_path: Path) -> None:
    tf = tmp_path / "main.tf"
    tf.write_text('provider "aws" { region = "us-east-1" }')
    det = DetectionEngine.detect_file(tf, Path("main.tf"))
    assert det.technology == Technology.TERRAFORM
    assert det.category == FileCategory.DEVOPS


def test_detect_dockerfile(tmp_path: Path) -> None:
    df = tmp_path / "Dockerfile"
    df.write_text("FROM alpine:latest\nCMD ['echo', 'hi']")
    det = DetectionEngine.detect_file(df, Path("Dockerfile"))
    assert det.technology == Technology.DOCKERFILE


def test_detect_docker_compose(tmp_path: Path) -> None:
    dc = tmp_path / "docker-compose.yml"
    dc.write_text("version: '3.8'\nservices:\n  app:\n    image: nginx")
    det = DetectionEngine.detect_file(dc, Path("docker-compose.yml"))
    assert det.technology == Technology.DOCKER_COMPOSE


def test_detect_github_actions(tmp_path: Path) -> None:
    wf = tmp_path / ".github" / "workflows" / "build.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text("name: Build\non: [push]\njobs: {}")
    det = DetectionEngine.detect_file(wf, Path(".github/workflows/build.yml"))
    assert det.technology == Technology.GITHUB_ACTIONS


def test_detect_gitlab_ci(tmp_path: Path) -> None:
    gl = tmp_path / ".gitlab-ci.yml"
    gl.write_text("stages: [test]")
    det = DetectionEngine.detect_file(gl, Path(".gitlab-ci.yml"))
    assert det.technology == Technology.GITLAB_CI


def test_detect_shell_script_extension_and_shebang(tmp_path: Path) -> None:
    # Extension
    sh1 = tmp_path / "script.sh"
    sh1.write_text("echo 'hello'")
    det1 = DetectionEngine.detect_file(sh1, Path("script.sh"))
    assert det1.technology == Technology.SHELL

    # Extensionless with shebang
    sh2 = tmp_path / "my-executable"
    sh2.write_text("#!/bin/bash\necho 'hello'")
    det2 = DetectionEngine.detect_file(sh2, Path("my-executable"))
    assert det2.technology == Technology.SHELL


def test_detect_developer_files(tmp_path: Path) -> None:
    # Python
    py = tmp_path / "main.py"
    py.write_text("print('hello')")
    assert DetectionEngine.detect_file(py, Path("main.py")).technology == Technology.PYTHON

    # JSON
    jsn = tmp_path / "data.json"
    jsn.write_text('{"key": "val"}')
    assert DetectionEngine.detect_file(jsn, Path("data.json")).technology == Technology.JSON

    # XML
    xml = tmp_path / "pom.xml"
    xml.write_text("<project></project>")
    assert DetectionEngine.detect_file(xml, Path("pom.xml")).technology == Technology.XML

    # SQL
    sql = tmp_path / "query.sql"
    sql.write_text("SELECT 1;")
    assert DetectionEngine.detect_file(sql, Path("query.sql")).technology == Technology.SQL

    # JS / TS / Java
    js = tmp_path / "index.js"
    js.write_text("console.log(1);")
    assert DetectionEngine.detect_file(js, Path("index.js")).technology == Technology.JAVASCRIPT

    ts = tmp_path / "app.ts"
    ts.write_text("const x: number = 1;")
    assert DetectionEngine.detect_file(ts, Path("app.ts")).technology == Technology.TYPESCRIPT

    java = tmp_path / "App.java"
    java.write_text("public class App {}")
    assert DetectionEngine.detect_file(java, Path("App.java")).technology == Technology.JAVA


def test_detect_unknown_file(tmp_path: Path) -> None:
    unk = tmp_path / "blob.bin"
    unk.write_bytes(b"\x00\x01\x02\x03\x04")
    det = DetectionEngine.detect_file(unk, Path("blob.bin"))
    assert det.technology == Technology.UNKNOWN
    assert det.category == FileCategory.UNKNOWN
