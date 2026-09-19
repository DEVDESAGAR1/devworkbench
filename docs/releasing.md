# Releasing DevWorkBench to PyPI

This document describes the automated CI/CD and release process for **DevWorkBench** using [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) with GitHub Actions OpenID Connect (OIDC).

---

## 1. Overview & Security Architecture

DevWorkBench uses **PyPI Trusted Publishing**, which eliminates the need to store long-lived PyPI API tokens or passwords in GitHub repository secrets:

- **Zero Hardcoded Secrets**: No PyPI token or password is stored in repository secrets or configuration files.
- **Short-Lived OIDC Tokens**: PyPI exchanges a short-lived, cryptographically signed GitHub OIDC token for a scoped upload token.
- **Minimal Permissions**: The release workflow uses `permissions: contents: read` globally, granting `id-token: write` only to the isolated publishing job.
- **Immutable Artifacts**: Distribution packages (`.whl` and `.tar.gz`) are built and validated with `twine check` before publishing.

---

## 2. One-Time Setup Instructions

Before publishing releases, the repository owner must configure GitHub Environments and PyPI Trusted Publishers.

### Step 2.1: Configure GitHub Environments

In the GitHub repository (`DEVDESAGAR1/devworkbench`):
1. Navigate to **Settings** → **Environments**.
2. Click **New environment** and create an environment named `pypi`.
   - *(Optional but recommended)*: Under **Deployment protection rules**, configure **Required reviewers** for production releases.
3. Click **New environment** and create a second environment named `testpypi`.

---

### Step 2.2: Configure PyPI Trusted Publisher (Production)

1. Log in to [PyPI](https://pypi.org/).
2. Go to **Account Settings** → **Publishing** (or if the project already exists on PyPI, **Project Settings** → **Publishing**).
3. Add a new **GitHub** publisher with the following details:
   - **PyPI Project Name**: `devworkbench`
   - **Owner / Organization**: `DEVDESAGAR1`
   - **Repository**: `devworkbench`
   - **Workflow name**: `release.yml`
   - **Environment name**: `pypi`
4. Save the configuration.

---

### Step 2.3: Configure TestPyPI Trusted Publisher (Testing / Staging)

1. Log in to [TestPyPI](https://test.pypi.org/).
2. Go to **Account Settings** → **Publishing** (or **Project Settings** → **Publishing**).
3. Add a new **GitHub** publisher with:
   - **PyPI Project Name**: `devworkbench`
   - **Owner / Organization**: `DEVDESAGAR1`
   - **Repository**: `devworkbench`
   - **Workflow name**: `test-release.yml`
   - **Environment name**: `testpypi`
4. Save the configuration.

---

## 3. Step-by-Step Release Workflow

### Step 1: Update Version in `pyproject.toml`
Ensure the version in `pyproject.toml` reflects the new release:

```toml
[project]
name = "devworkbench"
version = "0.2.0"
```

> **Note**: PyPI does not allow re-uploading or overwriting an existing version number. Every release must have a unique, incremented version string.

---

### Step 2: Verify Locally
Run all test suites, linters, and package builds locally before releasing:

```bash
# 1. Run unit and integration tests
python -m pytest

# 2. Run Ruff linter
ruff check src tests

# 3. Build source distribution and wheel
python -m build

# 4. Validate package metadata with twine
python -m twine check dist/*
```

---

### Step 3: Commit and Push to Main
```bash
git add pyproject.toml
git commit -m "chore(release): bump version to 0.2.0"
git push origin main
```

---

### Step 4: Create and Push Git Version Tag
Create an annotated tag matching the version string (prefixed with `v`):

```bash
git tag v0.2.0
git push origin v0.2.0
```

---

### Step 5: Automated GitHub Actions Execution
Pushing the `v*` tag automatically triggers the `.github/workflows/release.yml` workflow:
1. **Test Job**: Runs the full pytest test suite across Python 3.10, 3.11, 3.12, and 3.13.
2. **Build Job**: Builds the source archive (`.tar.gz`) and wheel (`.whl`), validates package integrity via `twine check`, and uploads the build artifact.
3. **Publish Job**: Requests a cryptographic OIDC token from GitHub, connects to PyPI, and publishes the validated distributions to [PyPI](https://pypi.org/project/devworkbench/).

---

### Step 6: Verify Published Package
Once the workflow completes, verify installation from PyPI:

```bash
# Install new release
python -m pip install --upgrade devworkbench

# Verify CLI entry point
devworkbench --version
devworkbench doctor
```

---

## 4. Manual Test Releases to TestPyPI

To test distribution building and publishing without affecting production PyPI:

1. In GitHub, go to **Actions** → **TestPyPI Release**.
2. Click **Run workflow** on the `main` branch.
3. The `.github/workflows/test-release.yml` workflow will build and publish to [TestPyPI](https://test.pypi.org/project/devworkbench/).
4. Test installation from TestPyPI:
   ```bash
   pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ devworkbench
   ```
