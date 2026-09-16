"""Technology and file type detection engine for DevWorkBench."""

import os
import re
from pathlib import Path
from typing import Optional, Tuple

from devworkbench.configuration import MAX_HEADER_INSPECTION_BYTES
from devworkbench.models import (
    TECHNOLOGY_CATEGORIES,
    FileCategory,
    FileDetection,
    Technology,
)


class DetectionEngine:
    """Multi-tiered detection engine: path patterns, extensions, and chunk-streamed content inspection."""

    # Pre-compiled regex patterns for streaming header content inspection
    RE_SHEBANG = re.compile(r"^#!\s*(/[^\s]+|/usr/bin/env\s+([^\s]+))", re.MULTILINE)
    RE_JENKINS_PIPELINE = re.compile(
        r"(pipeline\s*\{|node\s*\{|node\s*\(|stage\s*\(|def\s+[a-zA-Z_]\w*\s*=)",
        re.MULTILINE,
    )
    RE_OPENSHIFT_KIND = re.compile(
        r"(kind:\s*(Route|DeploymentConfig|BuildConfig|ImageStream|SecurityContextConstraints|ProjectRequest|Template)|apiVersion:\s*[a-zA-Z0-9.-]+\.openshift\.io/)",
        re.IGNORECASE,
    )
    RE_K8S_HEADER = re.compile(
        r"(apiVersion:\s*(apps/v1|v1|networking\.k8s\.io|batch/v1|rbac\.authorization\.k8s\.io|policy/v1|autoscaling/v[0-9]|admissionregistration\.k8s\.io)|kind:\s*(Deployment|Service|StatefulSet|DaemonSet|Ingress|ConfigMap|Secret|ServiceAccount|ClusterRole|ClusterRoleBinding|Role|RoleBinding|Job|CronJob|PersistentVolumeClaim|PersistentVolume|Namespace|Pod|HorizontalPodAutoscaler|NetworkPolicy))",
        re.MULTILINE,
    )
    RE_ANSIBLE_HEADER = re.compile(
        r"(^\s*-\s*hosts:|^\s*tasks:|^\s*-\s*name:|gather_facts:)",
        re.MULTILINE,
    )
    RE_CLOUDFORMATION = re.compile(
        r"(AWSTemplateFormatVersion|AWS::[a-zA-Z0-9]+::[a-zA-Z0-9]+)",
        re.MULTILINE,
    )

    @classmethod
    def read_header_sample(
        cls, file_path: Path, max_bytes: int = MAX_HEADER_INSPECTION_BYTES
    ) -> str:
        """Safely read the first few KB of a file without loading the entire file into memory."""
        try:
            with open(file_path, "rb") as f:
                raw = f.read(max_bytes)
                try:
                    return raw.decode("utf-8")
                except UnicodeDecodeError:
                    return raw.decode("latin-1", errors="ignore")
        except Exception:
            return ""

    @classmethod
    def detect_file(
        cls,
        file_path: Path,
        relative_path: Path,
        is_helm_template: bool = False,
        is_helm_chart: bool = False,
        max_bytes: int = MAX_HEADER_INSPECTION_BYTES,
    ) -> FileDetection:
        """Detect the technology and category of a given file."""
        filename = file_path.name
        filename_lower = filename.lower()
        suffix_lower = file_path.suffix.lower()
        rel_path_str = str(relative_path).replace("\\", "/")
        rel_parts_lower = [p.lower() for p in relative_path.parts]

        file_size = 0
        try:
            file_size = file_path.stat().st_size
        except Exception:
            pass

        # 1. Helm Specific Context (Chart structure takes priority)
        if is_helm_template or is_helm_chart:
            if filename_lower in ["chart.yaml", "chart.yml", "chart.lock"]:
                return FileDetection(
                    path=str(file_path),
                    relative_path=str(relative_path),
                    technology=Technology.HELM,
                    category=FileCategory.DEVOPS,
                    confidence=1.0,
                    details="Helm Chart metadata definition",
                    size_bytes=file_size,
                )
            if filename_lower.startswith("values") and suffix_lower in [".yaml", ".yml"]:
                return FileDetection(
                    path=str(file_path),
                    relative_path=str(relative_path),
                    technology=Technology.HELM,
                    category=FileCategory.DEVOPS,
                    confidence=1.0,
                    details="Helm Values configuration",
                    size_bytes=file_size,
                )
            if is_helm_template or filename_lower.endswith(".tpl"):
                return FileDetection(
                    path=str(file_path),
                    relative_path=str(relative_path),
                    technology=Technology.HELM,
                    category=FileCategory.DEVOPS,
                    confidence=0.95,
                    details="Helm Chart Template",
                    size_bytes=file_size,
                )

        # 2. Jenkins & Groovy
        if (
            filename_lower == "jenkinsfile"
            or filename_lower.startswith("jenkinsfile.")
            or filename_lower.endswith(".jenkinsfile")
        ):
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.JENKINS,
                category=FileCategory.DEVOPS,
                confidence=1.0,
                details="Jenkins Pipeline definition",
                size_bytes=file_size,
            )
        if suffix_lower in [".groovy", ".gvy", ".jenkins"]:
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.JENKINS,
                category=FileCategory.DEVOPS,
                confidence=0.9,
                details="Groovy / Jenkins script",
                size_bytes=file_size,
            )

        # 3. Docker & Containers
        if (
            filename_lower == "dockerfile"
            or filename_lower.startswith("dockerfile.")
            or filename_lower.endswith(".dockerfile")
            or filename_lower == "containerfile"
            or filename_lower.startswith("containerfile.")
        ):
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.DOCKERFILE,
                category=FileCategory.DEVOPS,
                confidence=1.0,
                details="Docker / Container build file",
                size_bytes=file_size,
            )

        if (
            filename_lower.startswith("docker-compose")
            or filename_lower.startswith("compose")
        ) and suffix_lower in [".yaml", ".yml"]:
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.DOCKER_COMPOSE,
                category=FileCategory.DEVOPS,
                confidence=1.0,
                details="Docker Compose configuration",
                size_bytes=file_size,
            )

        # 4. CI/CD: GitHub Actions & GitLab CI & Azure Pipelines
        if ".github" in rel_parts_lower and "workflows" in rel_parts_lower and suffix_lower in [".yaml", ".yml"]:
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.GITHUB_ACTIONS,
                category=FileCategory.DEVOPS,
                confidence=1.0,
                details="GitHub Actions Workflow",
                size_bytes=file_size,
            )

        if filename_lower in [".gitlab-ci.yml", ".gitlab-ci.yaml"] or filename_lower.endswith(".gitlab-ci.yml"):
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.GITLAB_CI,
                category=FileCategory.DEVOPS,
                confidence=1.0,
                details="GitLab CI configuration",
                size_bytes=file_size,
            )

        if filename_lower in ["azure-pipelines.yml", "azure-pipelines.yaml"]:
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.AZURE,
                category=FileCategory.DEVOPS,
                confidence=1.0,
                details="Azure DevOps Pipeline",
                size_bytes=file_size,
            )

        if filename_lower in ["cloudbuild.yaml", "cloudbuild.yml"]:
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.GCP,
                category=FileCategory.DEVOPS,
                confidence=1.0,
                details="GCP Cloud Build definition",
                size_bytes=file_size,
            )

        # 5. Terraform & HCL
        if suffix_lower in [".tf", ".tfvars", ".hcl", ".tf.json"]:
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.TERRAFORM,
                category=FileCategory.DEVOPS,
                confidence=1.0,
                details="Terraform / HCL configuration",
                size_bytes=file_size,
            )

        # 6. Shell scripts
        if suffix_lower in [".sh", ".bash", ".zsh", ".ksh"]:
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.SHELL,
                category=FileCategory.DEVOPS,
                confidence=1.0,
                details=f"Shell script ({suffix_lower[1:]})",
                size_bytes=file_size,
            )

        # 7. General Developer Languages by Extension
        if suffix_lower in [".py", ".pyi"]:
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.PYTHON,
                category=FileCategory.DEVELOPER,
                confidence=1.0,
                details="Python source file",
                size_bytes=file_size,
            )

        if suffix_lower == ".json":
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.JSON,
                category=FileCategory.CONFIG,
                confidence=0.9,
                details="JSON data/config",
                size_bytes=file_size,
            )

        if suffix_lower in [".xml", ".xsd", ".pom"]:
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.XML,
                category=FileCategory.CONFIG,
                confidence=0.9,
                details="XML document",
                size_bytes=file_size,
            )

        if suffix_lower in [".sql", ".ddl", ".dml"]:
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.SQL,
                category=FileCategory.DEVELOPER,
                confidence=1.0,
                details="SQL query/migration script",
                size_bytes=file_size,
            )

        if suffix_lower in [".js", ".mjs", ".cjs"]:
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.JAVASCRIPT,
                category=FileCategory.DEVELOPER,
                confidence=1.0,
                details="JavaScript source file",
                size_bytes=file_size,
            )

        if suffix_lower in [".ts", ".tsx", ".mts", ".cts"]:
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.TYPESCRIPT,
                category=FileCategory.DEVELOPER,
                confidence=1.0,
                details="TypeScript source file",
                size_bytes=file_size,
            )

        if suffix_lower == ".java":
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.JAVA,
                category=FileCategory.DEVELOPER,
                confidence=1.0,
                details="Java source file",
                size_bytes=file_size,
            )

        # 8. Streaming Content Inspection for Extensionless / Disambiguated files
        sample = cls.read_header_sample(file_path, max_bytes=max_bytes)

        # Check Shebangs
        shebang_match = cls.RE_SHEBANG.search(sample)
        if shebang_match:
            shebang_line = shebang_match.group(0).lower()
            if any(sh in shebang_line for sh in ["bash", "sh", "zsh", "ksh"]):
                return FileDetection(
                    path=str(file_path),
                    relative_path=str(relative_path),
                    technology=Technology.SHELL,
                    category=FileCategory.DEVOPS,
                    confidence=0.95,
                    details="Shell script via shebang header",
                    size_bytes=file_size,
                )
            if "python" in shebang_line:
                return FileDetection(
                    path=str(file_path),
                    relative_path=str(relative_path),
                    technology=Technology.PYTHON,
                    category=FileCategory.DEVELOPER,
                    confidence=0.95,
                    details="Python script via shebang header",
                    size_bytes=file_size,
                )
            if "node" in shebang_line:
                return FileDetection(
                    path=str(file_path),
                    relative_path=str(relative_path),
                    technology=Technology.JAVASCRIPT,
                    category=FileCategory.DEVELOPER,
                    confidence=0.95,
                    details="Node/JS script via shebang header",
                    size_bytes=file_size,
                )

        # Check Jenkins Pipeline content
        if cls.RE_JENKINS_PIPELINE.search(sample):
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.JENKINS,
                category=FileCategory.DEVOPS,
                confidence=0.85,
                details="Jenkins DSL signature in file header",
                size_bytes=file_size,
            )

        # Disambiguate YAML files (.yaml / .yml)
        if suffix_lower in [".yaml", ".yml"]:
            # CloudFormation / AWS SAM
            if cls.RE_CLOUDFORMATION.search(sample):
                return FileDetection(
                    path=str(file_path),
                    relative_path=str(relative_path),
                    technology=Technology.AWS,
                    category=FileCategory.DEVOPS,
                    confidence=0.9,
                    details="AWS CloudFormation / SAM Template",
                    size_bytes=file_size,
                )

            # OpenShift Manifests
            if cls.RE_OPENSHIFT_KIND.search(sample):
                return FileDetection(
                    path=str(file_path),
                    relative_path=str(relative_path),
                    technology=Technology.OPENSHIFT,
                    category=FileCategory.DEVOPS,
                    confidence=0.95,
                    details="OpenShift Manifest",
                    size_bytes=file_size,
                )

            # Kubernetes Manifests
            if cls.RE_K8S_HEADER.search(sample):
                return FileDetection(
                    path=str(file_path),
                    relative_path=str(relative_path),
                    technology=Technology.KUBERNETES,
                    category=FileCategory.DEVOPS,
                    confidence=0.95,
                    details="Kubernetes Manifest",
                    size_bytes=file_size,
                )

            # Ansible Playbooks / Tasks
            if cls.RE_ANSIBLE_HEADER.search(sample) or any(
                part in rel_parts_lower for part in ["tasks", "roles", "playbooks"]
            ):
                return FileDetection(
                    path=str(file_path),
                    relative_path=str(relative_path),
                    technology=Technology.ANSIBLE,
                    category=FileCategory.DEVOPS,
                    confidence=0.85,
                    details="Ansible Playbook / Tasks definition",
                    size_bytes=file_size,
                )

            # Generic YAML fallback
            return FileDetection(
                path=str(file_path),
                relative_path=str(relative_path),
                technology=Technology.YAML,
                category=FileCategory.CONFIG,
                confidence=0.8,
                details="YAML configuration",
                size_bytes=file_size,
            )

        # Fallback: Unknown file
        return FileDetection(
            path=str(file_path),
            relative_path=str(relative_path),
            technology=Technology.UNKNOWN,
            category=FileCategory.UNKNOWN,
            confidence=0.0,
            details=f"Unrecognized file type ({suffix_lower or 'no extension'})",
            size_bytes=file_size,
        )
