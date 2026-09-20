"""Unit tests for the Jenkins adapter and pipeline rules."""

from pathlib import Path

from devworkbench.adapters.jenkins_adapter import JenkinsAdapter
from devworkbench.models import (
    DiagnosticCategory,
    DiagnosticSeverity,
    FileCategory,
    FileDetection,
    Technology,
)


def test_valid_declarative_pipeline(tmp_path: Path) -> None:
    jf = tmp_path / "Jenkinsfile"
    jf.write_text("""
pipeline {
    agent any
    options {
        timeout(time: 1, unit: 'HOURS')
    }
    stages {
        stage('Build') {
            steps {
                echo 'Building...'
            }
        }
    }
}
""")
    det = FileDetection(
        path=str(jf),
        relative_path="Jenkinsfile",
        technology=Technology.JENKINS,
        category=FileCategory.DEVOPS,
    )

    adapter = JenkinsAdapter()
    diags = adapter.analyze_file(jf, det)
    # Should have no syntax or structure errors
    assert not any(d.severity == DiagnosticSeverity.ERROR for d in diags)


def test_unmatched_brace_syntax_error(tmp_path: Path) -> None:
    jf = tmp_path / "Jenkinsfile"
    jf.write_text("""
pipeline {
    agent any
    stages {
        stage('Build') {
            steps {
                echo 'Missing closing brace'
            }
        }
    // missing closing brace for stages and pipeline
""")
    det = FileDetection(
        path=str(jf),
        relative_path="Jenkinsfile",
        technology=Technology.JENKINS,
        category=FileCategory.DEVOPS,
    )

    adapter = JenkinsAdapter()
    diags = adapter.analyze_file(jf, det)
    assert len(diags) >= 1
    syntax_err = next(d for d in diags if d.category == DiagnosticCategory.SYNTAX)
    assert "Unclosed bracket" in syntax_err.message
    assert syntax_err.line is not None


def test_mismatched_brackets(tmp_path: Path) -> None:
    jf = tmp_path / "Jenkinsfile"
    jf.write_text("pipeline { agent any )")
    det = FileDetection(
        path=str(jf),
        relative_path="Jenkinsfile",
        technology=Technology.JENKINS,
        category=FileCategory.DEVOPS,
    )

    adapter = JenkinsAdapter()
    diags = adapter.analyze_file(jf, det)
    assert any("Mismatched bracket" in d.message for d in diags)


def test_missing_agent_or_stages(tmp_path: Path) -> None:
    jf = tmp_path / "Jenkinsfile"
    jf.write_text("""
pipeline {
    echo 'No agent and no stages'
}
""")
    det = FileDetection(
        path=str(jf),
        relative_path="Jenkinsfile",
        technology=Technology.JENKINS,
        category=FileCategory.DEVOPS,
    )

    adapter = JenkinsAdapter()
    diags = adapter.analyze_file(jf, det)
    assert any("missing required 'agent'" in d.message for d in diags)
    assert any("missing required 'stages" in d.message for d in diags)


def test_hardcoded_credential_rule(tmp_path: Path) -> None:
    jf = tmp_path / "Jenkinsfile"
    jf.write_text("""
pipeline {
    agent any
    environment {
        SECRET_KEY = 'super_secret_password_123'
    }
    stages {
        stage('Test') {
            steps {
                echo 'Running'
            }
        }
    }
}
""")
    det = FileDetection(
        path=str(jf),
        relative_path="Jenkinsfile",
        technology=Technology.JENKINS,
        category=FileCategory.DEVOPS,
    )

    adapter = JenkinsAdapter()
    diags = adapter.analyze_file(jf, det)
    cred_diag = next((d for d in diags if d.rule == "JENKINS001"), None)
    assert cred_diag is not None
    assert cred_diag.category == DiagnosticCategory.SECURITY
    # Verify secret value is never printed
    assert "super_secret_password_123" not in cred_diag.message


def test_tool_invocations_extraction(tmp_path: Path) -> None:
    jf = tmp_path / "Jenkinsfile"
    jf.write_text("""
pipeline {
    agent any
    stages {
        stage('Deploy') {
            steps {
                sh 'oc apply -f deployment.yaml'
                sh 'helm upgrade my-app ./chart'
                sh 'kubectl get pods'
            }
        }
    }
}
""")
    det = FileDetection(
        path=str(jf),
        relative_path="Jenkinsfile",
        technology=Technology.JENKINS,
        category=FileCategory.DEVOPS,
    )

    adapter = JenkinsAdapter()
    adapter.analyze_file(jf, det)

    invoked = det.metadata.get("invoked_tools", [])
    assert "oc" in invoked
    assert "helm" in invoked
    assert "kubectl" in invoked
