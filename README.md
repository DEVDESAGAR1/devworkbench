# DevWorkBench

[![CI](https://github.com/DEVDESAGAR1/devworkbench/actions/workflows/ci.yml/badge.svg)](https://github.com/DEVDESAGAR1/devworkbench/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/devworkbench.svg)](https://pypi.org/project/devworkbench/)
[![Python Versions](https://img.shields.io/pypi/pyversions/devworkbench.svg)](https://pypi.org/project/devworkbench/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

> **A local-first, open-source developer & DevOps workbench CLI.**

DevWorkBench is a unified, deterministic command-line workbench for analyzing, formatting, linting, validating, and diagnosing DevOps and developer files across modern stacks.

---

## Core Product Principles

1. **Open Source First**: Permissively licensed, leveraging mature open-source tooling.
2. **Local-First / Privacy-First**: 100% offline and deterministic. DevWorkBench does **NOT** upload source code, Jenkinsfiles, manifests, or logs to any external service. No database or cloud API key required.
3. **Report First, Modify Second**: `scan` and `analyze-build` are strictly read-only and **NEVER** modify files.
4. **Large File Support**: Streaming and chunked processing to safely handle huge Jenkins build logs and data dumps without memory spikes.
5. **Extensible Architecture**: Decoupled adapters and rule registries for multi-technology support.
6. **Zero AI Dependency**: DevWorkBench does not require AI or cloud services to perform its analysis.

---

## Supported Technologies

- **DevOps**: Jenkins / Groovy, Kubernetes, OpenShift, Helm, Terraform / HCL, Ansible, Dockerfile, Docker Compose, GitHub Actions, GitLab CI, Shell / Bash, AWS / Azure / GCP configs.
- **Developer Files**: Python, JSON, YAML, XML, SQL, JavaScript, TypeScript, Java.
- **Build Logs**: Jenkins, Kubernetes, OpenShift, Helm, Docker/Kaniko, Terraform.

---

## Installation & Distribution

DevWorkBench is a standard, cross-platform Python application with no mandatory internet or cloud dependencies.

### 1. From PyPI (Standard)
```bash
python -m pip install devworkbench
```

### 2. From Local Pre-Built Wheel (Air-Gapped / Corporate Network)
```bash
python -m pip install dist/devworkbench-0.1.0-py3-none-any.whl
```

### 3. Fully Offline with Local Wheels Directory
```bash
python -m pip install --no-index --find-links ./packages devworkbench
```

### 4. Development & Source Installation
```bash
# Editable install
python -m pip install -e .

# With dev & test dependencies
python -m pip install -e ".[dev]"
```

### 5. Verify Installation
```bash
# Check version
devworkbench --version

# Run complete environment and tool health diagnostics
devworkbench doctor
```

**Uninstall Safety Guarantee:**
`pip uninstall devworkbench` cleanly removes only the DevWorkBench package. It never touches external CLI tools (`helm`, `terraform`, `shellcheck`), user configurations, or scanned repositories.

---

## Usage

### 1. Flexible Repository & File Scanning

```bash
# Scan current directory
devworkbench scan .

# Scan a single file
devworkbench scan Jenkinsfile

# Scan multiple specific files
devworkbench scan Jenkinsfile deployment.yaml service.yaml

# Scan a mix of files and directories
devworkbench scan Jenkinsfile k8s/ helm/payment-service/

# Output structured JSON (or shortcut --json)
devworkbench scan . --json
devworkbench scan . --format json --output report.json

# Custom ignore patterns and verbose details
devworkbench scan . --ignore "target/*" --verbose
```

---

### 2. Safe Fix Engine (Interactive & Automated)

DevWorkBench provides a safe, deterministic fix workflow. Fixes are classified by safety (`SAFE`, `UNSAFE`, `MANUAL_REVIEW`) and only safe fixes from native open-source engines are applied automatically.

```bash
# Preview what fixes will be applied without touching files
devworkbench fix . --dry-run

# Interactive fix: inspect the plan and confirm before applying [y/N]
devworkbench fix .

# Apply safe fixes automatically (e.g. CI/CD pipelines)
devworkbench fix . --yes

# Fix specific files or directories
devworkbench fix src/app.py terraform/main.tf

# Output fix plan and results as JSON
devworkbench fix . --json
```

**Fix Safety Guarantees:**
- **SHA-256 Pre-Modification Integrity Verification**: Files modified between planning and execution are safely skipped.
- **Multi-Engine Conflict Detection**: If multiple engines suggest conflicting changes to the same file, the file is withheld for manual review.
- **Post-Fix Validation**: Re-scans the repository after fixes are applied to verify diagnostic resolution and verify no syntax regressions.

---

### 3. Build-Log Analysis & Root Cause Identification

Streamingly analyze raw build logs from Jenkins, Kubernetes, OpenShift, Helm, or Docker with cascaded failure detection:

```bash
# Analyze a build log file
devworkbench analyze-build build.log

# Stream from stdin / pipe
cat build.log | devworkbench analyze-build -

# Export build analysis to JSON
devworkbench analyze-build build.log --json -o build-report.json
```

---

### 4. Explicit Tool & Dependency Setup

DevWorkBench **NEVER** downloads or installs tools automatically during normal scan/fix commands. Explicit installation is performed only via `setup`:

```bash
# Preview what tools would be installed without modifying system
devworkbench setup --dry-run

# Run explicit setup and post-install capability verification
devworkbench setup

# Filter setup by technology
devworkbench setup -t python
devworkbench setup -t terraform

# Output structured setup and fallback report as JSON
devworkbench setup --json
```

**Restricted Corporate Network & Air-Gapped Guarantees:**
- **Zero Runtime Downloads**: `scan`, `analyze-build`, `fix`, and `capabilities` operate 100% offline.
- **Structured Error Classification**: Network, proxy, TLS, DNS, or permission failures are classified (`NETWORK_UNAVAILABLE`, `TLS_ERROR`, `PROXY_ERROR`, `PERMISSION_DENIED`) and gracefully fall back to DevWorkBench rule engines.
- **Post-Install Verification Probes**: Every tool installation is checked for executable presence, version, and capability before being marked available.
- **Untrusted Input Isolation**: Scanned project files (`requirements.txt`, `Dockerfile`) are untrusted and never trigger tool installations.

---

### 5. Capabilities & Tool Hierarchy Introspection

DevWorkBench implements a **Mandatory Tool Selection Hierarchy** across all technologies:
1. **Priority 1 (Native)**: Official ecosystem CLI (e.g. `helm`, `terraform`, `tofu`, `shellcheck`, `hadolint`, `ruff`).
2. **Priority 2 (Open-Source)**: Established open-source tool or Python package (e.g. `PyYAML`, `checkov`, `tflint`, `actionlint`, `ansible-lint`, `kube-linter`, `kubeconform`).
3. **Priority 3 (DevWorkBench)**: Deterministic internal rule engines, correlation models, and safe fix planners.
4. **Priority 4 (Manual Review)**: Fallback when no automated provider can safely operate.

```bash
# Inspect all capabilities and active provider resolutions
devworkbench capabilities

# Filter by technology
devworkbench capabilities -t helm
devworkbench capabilities -t kubernetes

# Output capability tree as JSON
devworkbench capabilities --json

# Inspect all installed vs missing tool engines
devworkbench tools
```

---

## Configuration (`.devworkbench.yaml`)

Control provider preferences and rules explicitly in your workspace:

```yaml
providers:
  helm:
    preferred: native
  kubernetes_lint:
    preferred: opensource
  yaml_parsing:
    preferred: auto

rules:
  disabled:
    - JENKINS004

severity_overrides:
  K8S003: warning
```

---

## DevOps Best-Practice Rules & Diagnostics Catalog

DevWorkBench includes deterministic best-practice and security rules with full provider provenance and documentation links:

| Rule ID | Technology | Category | Description | Provider / Priority | Fix Safety |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `JENKINS001` | Jenkins | Security | Detects hard-coded credentials/secrets without leaking secret values | DevWorkBench (P3) | Manual Review |
| `JENKINS002` | Jenkins | Security | Warns on unsafe variable interpolation inside shell steps | DevWorkBench (P3) | Manual Review |
| `JENKINS003` | Jenkins | Best-Practice | Identifies multi-stage pipelines missing timeout protection | DevWorkBench (P3) | Manual Review |
| `JENKINS004` | Jenkins | Best-Practice | Detects error suppression (`\|\| true`) in shell steps | DevWorkBench (P3) | Safe / Manual |
| `K8S001` | Kubernetes | Best-Practice | Flags containers missing resource requests or limits | DevWorkBench (P3) | Manual Review |
| `K8S002` | Kubernetes | Security | Flags containers running in privileged mode (`privileged: true`) | DevWorkBench (P3) | Manual Review |
| `K8S003` | Kubernetes | Best-Practice | Flags containers using unpinned or `:latest` image tags | DevWorkBench (P3) | Manual Review |
| `K8S004` | Kubernetes | Best-Practice | Flags containers missing liveness or readiness probes | DevWorkBench (P3) | Manual Review |
| `OPENSHIFT001` | OpenShift | Security | Flags OpenShift Routes lacking TLS termination | DevWorkBench (P3) | Manual Review |
| `HELM001` | Helm | Schema | Validates required metadata in `Chart.yaml` (name, version, apiVersion) | DevWorkBench (P3) | Manual Review |
| `HELM002` | Helm | Best-Practice | Recommends maintainers and source repository links in `Chart.yaml` | DevWorkBench (P3) | Manual Review |
| `DOCKER001` | Dockerfile | Best-Practice | Base image uses unpinned or `:latest` tag in `FROM` instruction | DevWorkBench (P3) | Manual Review |
| `TERRAFORM001` | Terraform | Security | Flags hard-coded cloud credentials or secret tokens in HCL configurations | DevWorkBench (P3) | Manual Review |

```bash
# List all rules in human catalog format
devworkbench rules

# Filter rules by technology
devworkbench rules -t kubernetes
devworkbench rules -t jenkins

# Export rules with full metadata, rationales, and docs as JSON
devworkbench rules --json
```

---

## License

DevWorkBench is distributed under the [Apache 2.0 License](LICENSE). Third-party dependencies are documented in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

