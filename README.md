# shared-pipelines

Reusable GitHub Actions workflows for .NET repositories. Callers stay tiny: all
the logic lives here, so a fix in this repository reaches every consumer as soon
as they move their `@vX.Y.Z` reference.

| Workflow | What it does |
|---|---|
| [`dotnet-ci-build.yml`](.github/workflows/dotnet-ci-build.yml) | restore → build → test, with optional SonarQube/SonarCloud analysis |
| [`release-nuget.yml`](.github/workflows/release-nuget.yml) | restore → build → test → pack → publish to GitHub Packages and/or nuget.org |
| [`increment-version.yml`](.github/workflows/increment-version.yml) | bump `<Version>`, build/test a release branch, open a release PR, then tag the merged version |

## Quick start

```yaml
# .github/workflows/ci.yml in the calling repository
name: CI

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

permissions:
  contents: read
  packages: read

jobs:
  build:
    uses: bjornbouetsmith/shared-pipelines/.github/workflows/dotnet-ci-build.yml@v1.1.0
```

That is a complete pipeline: it finds the first `*.slnx` or `*.sln` in the
repository root, installs the .NET 10 SDK, restores, builds and tests it.

## Pinning

| Reference | Behaviour |
|---|---|
| `@v1.1.0` | Exact release — **recommended**. Nothing changes under your feet. |
| `@<sha>` | Fully immutable, best for audited environments. |
| `@main` | Bleeding edge, every commit here lands in every consumer immediately. Not recommended. |

Only exact `vX.Y.Z` tags are published; there is no moving `v1` alias. Bump the
reference in your callers when you want a newer release.

| Release | Highlights |
|---|---|
| `v1.1.0` | SonarQube/SonarCloud option, pending/success/failure commit statuses |
| `v1.0.0` | First release: reusable CI, release and versioning workflows |

## Requirements for every workflow

- **Runner:** the steps are `bash`, so `runs-on` must be Linux or macOS. Windows
  runners are not supported.
- **`actions/checkout` is done for you** and checks out the *calling* repository,
  because the `github` context always belongs to the caller.
- **Permissions are the caller's responsibility.** These workflows declare no
  `permissions:` block, because a called workflow that *declares* a scope the
  caller did not grant fails the whole run at startup with
  `The workflow is requesting 'statuses: write', but is only allowed 'statuses: none'`.
  Declaring the minimum would force every caller to grant permissions for
  features it never uses, so grant exactly what you need in the calling job.
  The tables below list the requirement per feature.
- **Secrets are not inherited implicitly:** pass them explicitly, or use
  `secrets: inherit`.

---

## `dotnet-ci-build.yml`

```yaml
jobs:
  ci:
    permissions:
      contents: read
      packages: read
    uses: bjornbouetsmith/shared-pipelines/.github/workflows/dotnet-ci-build.yml@v1.1.0
    with:
      solution: Source/MyApp.slnx
      nuget-feed-owner: my-github-user
```

### Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `solution` | string | `''` | Solution/project/directory to build. Empty = first `*.slnx`/`*.sln` in `working-directory`. |
| `working-directory` | string | `'.'` | Directory containing the solution. |
| `dotnet-version` | string | `'10.0.x'` | SDK to install, e.g. `8.0.x,10.0.x`. |
| `global-json-file` | string | `''` | Use a `global.json` instead of `dotnet-version`. |
| `configuration` | string | `'Release'` | Build configuration. |
| `runs-on` | string | `'ubuntu-latest'` | Runner label(s); JSON array for several. |
| `timeout-minutes` | number | `30` | Job timeout. |
| `cache` | boolean | `true` | Cache `~/.nuget/packages`. |
| `run-tests` | boolean | `true` | Run `dotnet test`. |
| `test-project` | string | `''` | What to test. Empty = the resolved build target. Must be part of the built target because `--no-build` is used. |
| `restore-args` / `build-args` / `test-args` | string | `''` / `''` / `'--verbosity normal'` | Extra CLI arguments. Quoted values are preserved. |
| `upload-test-results` | boolean | `false` | Upload the generated `.trx`. |
| `artifact-name` | string | `'test-results'` | Artifact name. |
| `nuget-feed-owner` | string | `''` | Add `https://nuget.pkg.github.com/<owner>/index.json` as the `github` source. |
| `set-commit-status` | boolean | `false` | Post `pending`/`success`/`failure` commit statuses for the build. |
| `status-context` | string | `'continuous-integration/build'` | Context for those statuses. |
| `sonar` | boolean | `false` | Run a SonarQube/SonarCloud analysis around the build. See [Sonar analysis](#sonarqube--sonarcloud-analysis). |
| `sonar-host-url` | string | `'https://sonarcloud.io'` | SonarQube or SonarCloud server URL. |
| `sonar-project-key` | string | `''` | `owner_repository` style project key. Required when `sonar` is true. |
| `sonar-organization` | string | `''` | SonarCloud organization; empty = omit `/o` (self-hosted SonarQube). |
| `sonar-java-version` | string | `'17'` | JDK version for the scanner. |
| `sonar-java-distribution` | string | `'oracle'` | JDK distribution for `actions/setup-java`. |
| `sonar-scanner-version` | string | `''` | `dotnet-sonarscanner` tool version; empty = latest. |
| `sonar-coverage-reports` | string | `''` | `sonar.cs.opencover.reportsPaths`, relative to `working-directory`. Empty = no coverage import. |
| `sonar-quality-gate-wait` | boolean | `true` | Set `sonar.qualitygate.wait=true` so a failing gate fails the job. |
| `sonar-extra-args` | string | `''` | Extra arguments for `dotnet-sonarscanner begin`. |
| `sonar-end-args` | string | `''` | Extra arguments for `dotnet-sonarscanner end`. |
| `sonar-publish-status` | boolean | `true` | Post `pending`/`success`/`failure` commit statuses for the quality gate. |
| `sonar-status-context` | string | `'continuous-integration/sonarcloud'` | Context for the quality gate statuses. |

### Secrets

| Secret | Required | Description |
|---|---|---|
| `nuget-token` | no | Token for the GitHub Packages feed. Defaults to `github.token`. |
| `sonar-token` | when `sonar: true` | SonarQube/SonarCloud token. |

### Outputs

| Output | Description |
|---|---|
| `target` | The solution/project that was built. |

### Permissions

Grant these in the calling job:

| Scope | Needed for |
|---|---|
| `contents: read` | checking out the repository |
| `packages: read` | `nuget-feed-owner` |
| `statuses: write` | `set-commit-status` and `sonar-publish-status` |

### SonarQube / SonarCloud analysis

Opt in with `sonar: true`. Everything Sonar-specific is a parameter:

```yaml
jobs:
  ci:
    permissions:
      contents: read
      packages: read
      statuses: write            # only for the commit status options
    uses: bjornbouetsmith/shared-pipelines/.github/workflows/dotnet-ci-build.yml@v1.1.0
    with:
      solution: Source/MyApp.slnx
      sonar: true
      sonar-project-key: my-org_MyApp
      sonar-organization: my-org
      sonar-coverage-reports: '**/coverage.opencover*.xml'
      test-args: >-
        --verbosity normal
        /p:AltCover=true
        /p:AltCoverReport=/home/runner/work/MyApp/MyApp/Source/MyApp.Tests/coverage.opencover.xml
        /p:AltCoverAttributeFilter=ExcludeFromCodeCoverage
        /p:AltCoverVisibleBranches=true
    secrets: inherit
```

What the option changes:

1. Checks out with `fetch-depth: 0` so blame and new-code detection work.
2. Installs the JDK and the `dotnet-sonarscanner` tool, and puts
   `$HOME/.dotnet/tools` on `PATH`.
3. Runs `dotnet-sonarscanner begin` after restore and before build.
4. Runs `dotnet-sonarscanner end` after build and test; with
   `sonar-quality-gate-wait: true` a failing gate fails the job.
5. Publishes `pending` → `success`/`failure` commit statuses on
   `sonar-status-context` (default `continuous-integration/sonarcloud`), so the
   quality gate can be a required check in branch protection — same mechanism as
   `continuous-integration/build`.

Coverage generation stays in the caller's hands through `test-args` (AltCover,
coverlet, whatever the repository already uses); `sonar-coverage-reports` only
tells Sonar where to read the OpenCover reports from.

Notes:

- Self-hosted SonarQube: set `sonar-host-url`, leave `sonar-organization` empty.
- Exclusions, duplications, extra sensors and similar go in `sonar-extra-args`,
  for example `/d:sonar.exclusions=**/Migrations/**`.
- A missing `sonar-project-key` or `sonar-token` fails in a dedicated
  "Validate Sonar inputs" step with a clear message instead of a scanner error.
- The status calls need `statuses: write`. On `pull_request` events from forks
  the token is read-only, so those calls fail there; run the pipeline on
  same-repository branches or pass a PAT-based token instead.

---

## `release-nuget.yml`

```yaml
jobs:
  release:
    permissions:
      contents: read
      packages: write
      id-token: write
    uses: bjornbouetsmith/shared-pipelines/.github/workflows/release-nuget.yml@v1.1.0
    with:
      solution: Source/MyApp.slnx
      allowed-actors: my-github-user
      publish-nuget-org: true
      nuget-org-user: my-nuget-account
```

Packs every packable project in the solution into `artifacts/packages` and pushes
the `.nupkg` files. GitHub Packages is on by default and uses
`github.repository_owner` as the feed owner; nuget.org is opt-in.

### Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `solution` | string | `''` | Solution/project to build and pack. |
| `working-directory` | string | `'.'` | Directory containing the solution. |
| `dotnet-version` | string | `'10.0.x'` | SDK to install. |
| `global-json-file` | string | `''` | Alternative to `dotnet-version`. |
| `configuration` | string | `'Release'` | Configuration for build, test and pack. |
| `runs-on` | string | `'ubuntu-latest'` | Runner label(s). |
| `timeout-minutes` | number | `45` | Job timeout. |
| `cache` | boolean | `true` | Cache `~/.nuget/packages`. |
| `run-tests` | boolean | `true` | Test before packing. |
| `test-project` | string | `''` | What to test; empty = the build target. |
| `restore-args` / `build-args` / `test-args` / `pack-args` | string | see workflow | Extra CLI arguments. |
| `packages-directory` | string | `'artifacts/packages'` | Output directory for `.nupkg`. |
| `upload-packages-artifact` | boolean | `true` | Upload the `.nupkg` files as an artifact. |
| `artifact-name` | string | `'nuget-packages'` | Artifact name. |
| `allowed-actors` | string | `''` | Comma separated allow-list of `github.triggering_actor`. Empty = no check. |
| `nuget-feed-owner` | string | `''` | GitHub Packages owner. Empty = `github.repository_owner`. |
| `publish-github-packages` | boolean | `true` | Push to GitHub Packages. |
| `publish-nuget-org` | boolean | `false` | Push to nuget.org. |
| `nuget-org-user` | string | `''` | nuget.org profile, required for OIDC. |
| `nuget-org-source` | string | `'https://api.nuget.org/v3/index.json'` | nuget.org feed. |
| `push-args` | string | `'--skip-duplicate'` | Extra `dotnet nuget push` arguments. |

### Secrets

| Secret | Required | Description |
|---|---|---|
| `nuget-token` | no | GitHub Packages token. Defaults to `github.token`. |
| `nuget-org-api-key` | no | Classic nuget.org key. When empty the workflow uses OIDC and `NuGet/login`. |

### Outputs

| Output | Description |
|---|---|
| `packages_path` | Directory containing the packed `.nupkg` files. |

### Permissions

Grant these in the calling job:

| Scope | Needed for |
|---|---|
| `contents: read` | checking out the repository |
| `packages: write` | `publish-github-packages` |
| `id-token: write` | `publish-nuget-org` (OIDC login) |

Publishing to nuget.org also needs a **trusted publishing policy** on nuget.org
pointing at this workflow file.

---

## `increment-version.yml`

One workflow, two halves, selected with `mode`:

- **`prepare`** — reads `<Version>` from `version-file`, increments
  `patch`/`minor`/`major`, builds and tests the change on
  `<branch-prefix><version>`, pushes that branch and opens a pull request.
- **`tag`** — reads the version from the merged branch and creates
  `<tag-prefix><version>` on the commit that introduced that version.
- **`auto`** (default) — `workflow_dispatch` runs `prepare`, `push` runs `tag`.

```yaml
name: Increment Version and Tag Release

on:
  workflow_dispatch:
    inputs:
      version_part:
        type: choice
        options: [ Patch, Minor, Major ]
        default: Patch
  push:
    branches: [ main ]

permissions:
  contents: write
  pull-requests: write

jobs:
  release:
    uses: bjornbouetsmith/shared-pipelines/.github/workflows/increment-version.yml@v1.1.0
    with:
      version-part: ${{ inputs.version_part || 'patch' }}
    secrets: inherit
```

### Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `mode` | string | `'auto'` | `auto`, `prepare` or `tag`. |
| `version-part` | string | `'patch'` | `patch`, `minor` or `major` (case insensitive). |
| `version-file` | string | `'Directory.Build.props'` | File containing `<Version>x.y.z</Version>`, relative to the repository root. |
| `solution` | string | `''` | Solution to build/test on the release branch. |
| `working-directory` | string | `'.'` | Directory containing the solution. |
| `dotnet-version` | string | `'10.0.x'` | SDK to install. |
| `global-json-file` | string | `''` | Alternative to `dotnet-version`. |
| `configuration` | string | `'Release'` | Build configuration. |
| `runs-on` | string | `'ubuntu-latest'` | Runner label(s). |
| `timeout-minutes` | number | `30` | Timeout of the `prepare` job. |
| `cache` | boolean | `true` | Cache `~/.nuget/packages`. |
| `run-tests` | boolean | `true` | Build and test the release branch before opening the PR. |
| `restore-args` / `build-args` / `test-args` | string | see workflow | Extra CLI arguments. |
| `nuget-feed-owner` | string | `''` | Add a GitHub Packages source while restoring. |
| `target-branch` | string | `'main'` | Branch the bump is based on and tagged. |
| `branch-prefix` | string | `'release/v'` | Prefix for the release branch. |
| `tag-prefix` | string | `'v'` | Prefix for the tag. |
| `create-pr` | boolean | `true` | Open the pull request. When `false` only the branch is pushed and the compare URL is printed. |
| `pr-title` | string | `''` | PR title. Empty = `Creating release <tag>`. |
| `commit-author-name` / `commit-author-email` | string | bot defaults | Git identity for the bump commit and the tag. |

### Secrets

| Secret | Required | Description |
|---|---|---|
| `release-token` | no | Token for the push, PR and tag. Defaults to `github.token`. |
| `nuget-token` | no | GitHub Packages token. Defaults to `github.token`. |

### Outputs

| Output | Description |
|---|---|
| `version` | New (`prepare`) or tagged (`tag`) version. |
| `branch` | Release branch created by `prepare`. |
| `tag` | Tag created by `tag`. |

### Permissions

Grant these in the calling job:

| Scope | Needed for |
|---|---|
| `contents: write` | pushing the release branch and the release tag |
| `pull-requests: write` | opening the release pull request (`create-pr: true`) |

### Gotchas

- Events created with `GITHUB_TOKEN` do **not** start other workflows. The pull
  request opened by `prepare` therefore shows no CI unless you pass a PAT (or
  GitHub App token) as `release-token`.
- To let the bot open pull requests at all, enable **Settings → Actions →
  General → Allow GitHub Actions to create and approve pull requests** in the
  calling repository.
- The release PR must be merged for `tag` to see the new version; `tag` never
  creates a tag that already exists, so re-runs are safe.
- `tag` creates the annotated tag object and the `refs/tags/<tag>` ref through
  the GitHub REST API instead of `git push origin <tag>`. `GITHUB_TOKEN` is a
  GitHub App token, and an App may not create a ref that introduces a workflow
  file without the `workflows` permission — which `GITHUB_TOKEN` can never have.
  Tagging a commit that *adds* a `.github/workflows/*.yml` file therefore fails
  with *"refusing to allow a GitHub App to create or update workflow … without
  `workflows` permission"*. The API path is not subject to the push-time check
  (a release commit that only edits an existing workflow file is fine), needs
  only `contents: write`, and leaves the annotated tag message, tagger name and
  tagger e-mail under the usual inputs. If a release commit ever adds a workflow
  file, pass a PAT or GitHub App token holding `workflows` as `release-token`.
- If `main` is protected against direct pushes, add `release-token` with a
  bypass, or merge the release PR and let `tag` push only the tag.

---

## Repository settings checklist (calling side)

1. **Actions → General → Actions permissions:** "Allow all actions and reusable
   workflows", or explicitly allow `bjornbouetsmith/shared-pipelines`.
2. **Actions → General → Workflow permissions:** read and write if a workflow
   pushes, tags or opens PRs.
3. **Allow GitHub Actions to create and approve pull requests** for
   `increment-version`.
4. For `release-nuget` with `publish-nuget-org`: a trusted publishing policy on
   nuget.org for the exact repository and workflow file.

## Consuming these pipelines from a private repository

This repository is public, so no access configuration is needed. If it is ever
made private, every caller must be in the same account/org and the repository's
**Actions → General → Access** setting must allow it.

## Migrating an existing repository

1. Delete the copied `ci`/`release` workflow bodies.
2. Replace each with a 10-line caller like the ones in the quick start.
3. Keep the triggers (`on:`) in the caller — the called workflows have no
   triggers of their own.
