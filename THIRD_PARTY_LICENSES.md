# Third-Party Licenses and Dependencies

DevWorkBench is committed to remaining fully open-source and maintaining a clean, permissively licensed dependency tree.

## Policy
1. Only permissively licensed core Python dependencies (MIT, BSD, Apache-2.0) are required for the base package.
2. No proprietary, telemetry-laden, or paid components are introduced.
3. Every external dependency and CLI engine integrated into DevWorkBench is documented in this registry.

---

## Direct Core Python Dependencies

| Package | Version Constraint | License | Project URL / Repository | Purpose in DevWorkBench |
| :--- | :--- | :--- | :--- | :--- |
| **`click`** | `>=8.1.0` | BSD-3-Clause | https://github.com/pallets/click | CLI argument parsing, subcommands, and exit code handling |
| **`rich`** | `>=13.0.0` | MIT | https://github.com/Textualize/rich | Terminal output styling, trees, tables, and colors |
| **`pyyaml`** | `>=6.0.1` | MIT | https://github.com/yaml/pyyaml | Offline YAML syntax parsing and error location extraction |

---

## Optional Python Packages (`[python]`, `[yaml]`, `[all]`, `[dev]`)

| Package | Optional Group | License | Project URL / Repository | Purpose in DevWorkBench |
| :--- | :--- | :--- | :--- | :--- |
| **`ruff`** | `python`, `all`, `dev` | MIT / Apache-2.0 | https://github.com/astral-sh/ruff | Python fast linting and formatting diagnostics |
| **`yamllint`** | `yaml`, `all`, `dev` | GPL-3.0 | https://github.com/adrienverge/yamllint | YAML style, indentation, and formatting linting |
| **`pytest`** | `dev` | MIT | https://github.com/pytest-dev/pytest | Unit and integration test runner |

---

## Evaluated & Integrated Open-Source Engines

DevWorkBench orchestrates these mature tools via local subprocess execution when installed on PATH:

| Engine | Technology | Typical License | Primary Interface | Integration Role in DevWorkBench |
| :--- | :--- | :--- | :--- | :--- |
| **`Ruff`** | Python | MIT / Apache-2.0 | Python package / CLI | Python linting, formatting check, and error code normalization |
| **`Python AST`** | Python | Python Software Foundation | Built-in stdlib | Fallback deterministic syntax error extraction with line/column |
| **`PyYAML`** | YAML | MIT | Python library | Fast, offline, memory-safe YAML document parsing |
| **`yamllint`** | YAML | GPL-3.0 | CLI / Python module | YAML formatting and indentation rule checking |
| **`ShellCheck`** | Shell | GPL-3.0 | Local CLI binary | Shell and Bash static analysis and security rule verification |
| **`Hadolint`** | Dockerfile | GPL-3.0 | Local CLI binary | Dockerfile linting and best-practice checks (`DL` rules) |
| **`actionlint`** | GitHub Actions | MIT | Local CLI binary | GitHub Actions workflow expression and schema verification |
| **`ansible-lint`**| Ansible | MIT / GPL-3.0 | Local CLI binary | Ansible playbook style and task linting |
| **`Terraform` / `OpenTofu`** | Terraform | MPL-2.0 / BSL | Local CLI binary | HCL format verification (`fmt -check`) and validation (`validate -json`) |
| **`TFLint`** | Terraform | MPL-2.0 | Local CLI binary | Terraform provider rule and deprecated syntax linting |
| **`KubeLinter`** | Kubernetes | Apache-2.0 | Local CLI binary | Kubernetes manifest security and best-practice checks |
| **`kubeconform`**| Kubernetes | Apache-2.0 | Local CLI binary | Kubernetes OpenAPI / JSONSchema validation |
| **`Checkov`** | Security / IaC | Apache-2.0 | Local CLI binary | Static code analysis for infrastructure as code security policies |
| **`Helm`** | Helm | Apache-2.0 | Local CLI binary | Chart linting (`helm lint`) and dry-run rendering (`helm template`) |
