# shared-pipelines

Reusable GitHub Actions workflows for .NET repositories. Callers stay tiny: all
the logic lives here, so a fix in this repository reaches every consumer as soon
as they move their `@vX.Y.Z` reference.

| Workflow | What it does |
|---|---|
| [`dotnet-ci-build.yml`](.github/workflows/dotnet-ci-build.yml) | restore → build → test, with optional SonarQube/SonarCloud analysis |
| [`dotnet-docker-ci-build.yml`](.github/workflows/dotnet-docker-ci-build.yml) | restore → start Docker Compose services → build → wait for readiness → test → stop services |
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
    uses: bjornbouetsmith/shared-pipelines/.github/workflows/dotnet-ci-build.yml@v1.4.0
```

That is a complete pipeline: it finds the first `*.slnx` or `*.sln` in the
repository root, installs the .NET 10 SDK, restores, builds and tests it.

## Pinning

| Reference | Behaviour |
|---|---|
| `@v1.4.0` | Exact release — **recommended**. Nothing changes under your feet. |
| `@<sha>` | Fully immutable, best for audited environments. |
| `@main` | Bleeding edge, every commit here lands in every consumer immediately. Not recommended. |

Only exact `vX.Y.Z` tags are published; there is no moving `v1` alias. Bump the
reference in your callers when you want a newer release.

`dotnet-docker-ci-build.yml` and the Docker Compose actions were introduced in
`v1.3.0`. From `v1.3.0` on, `dotnet-ci-build.yml`, `release-nuget.yml` and
`increment-version.yml` reference the shared composite actions at the same tag,
so a single release pins the workflows and the actions they use together.

| Release | Highlights |
|---|---|
| `v1.4.0` | Public `publish-nuget` composite action so cross-repository callers can publish to nuget.org with OIDC; workflows and internal actions pinned to `v1.4.0` |
| `v1.3.0` | New Docker-aware CI pipeline and shared `docker-compose-up`, `docker-compose-wait` and `docker-compose-down` actions; all workflows now pin their composite actions to `v1.3.0` |
| `v1.2.0` | Shared composite actions for checkout, SDK/cache setup, restore, build, test, Sonar and commit statuses; no workflow input changes |
| `v1.1.0` | SonarQube/SonarCloud option, pending/success/failure commit statuses |
| `v1.0.0` | First release: reusable CI, release and versioning workflows |

## Dependabot and CI

[`.github/dependabot.yml`](.github/dependabot.yml) keeps every action used by
these workflows and composite actions up to date. It checks weekly, groups
minor/patch bumps into one pull request and leaves major bumps separate.

Dependabot's `github-actions` ecosystem only scans `.github/workflows` for a
root `directory: "/"` entry; it does not discover composite actions under
`.github/actions` on its own. The configuration therefore lists the root and
every action directory explicitly. **When you add a composite action, add its
directory to `dependabot.yml`** — the validation step in CI fails if the list
and the directory contents drift apart.

CI runs on every push, pull request and manual dispatch:

| Job | What it checks |
|---|---|
| `lint` | `actionlint` (with shellcheck), `action-validator`, and [`tests/validate-workflows.py`](tests/validate-workflows.py) |
| `actions` | Calls the composite actions directly against a small .NET fixture: checkout, SDK/cache setup, restore, build, test, version, Docker Compose, and the input-validation failure paths |
| `dotnet-ci` | Calls the local `dotnet-ci-build.yml` against the fixture |
| `dotnet-docker-ci` | Calls the local `dotnet-docker-ci-build.yml` against the fixture and a tiny Compose stack |

`tests/validate-workflows.py` also enforces that all references back into this
repository use the same release tag, that every action is pinned to a version
tag or commit SHA rather than a branch, and that every `with:`/`secrets:` key
exists on the target action or reusable workflow. The fixtures live in
[`tests/fixtures`](tests/fixtures).

The publishing, Sonar and branch/tag mutation paths are not executed in CI:
they need real credentials or would mutate the repository. The composite
actions behind them are still schema-validated, and their input-validation
failure paths are exercised. The fixtures are deliberately small, so the suite
stays focused on the pipeline plumbing rather than on .NET test coverage.

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
  `secrets: inherit`. `inherit` forwards secrets under their *own* names, so a
  repository secret called `SONAR_TOKEN` will not fill the `sonar-token`
  input — map it: `secrets: { sonar-token: <repo secret> }`.

---

## Shared composite actions

The reusable workflows are the first consumers of the composite actions in
[`.github/actions`](.github/actions). Most are implementation details of the
workflows, not additional public entry points. The exception is
[`publish-nuget`](.github/actions/publish-nuget/action.yml), which is intended to
be called directly from a caller's job so nuget.org OIDC trusts the caller's
workflow. Listing them makes the structure easy to follow:

| Action | Used for |
|---|---|
| [`checkout`](.github/actions/checkout/action.yml) | Checking out the caller repository, optionally with full history and a release token. |
| [`setup-dotnet`](.github/actions/setup-dotnet/action.yml) | Installing the .NET SDK, caching `~/.nuget/packages` and adding the GitHub Packages source. |
| [`restore`](.github/actions/restore/action.yml) | Resolving the solution and running `dotnet restore`. |
| [`build`](.github/actions/build/action.yml) | Running `dotnet build --no-restore`. |
| [`test`](.github/actions/test/action.yml) | Running `dotnet test --no-build` with code coverage using AltCover. |
| [`publish-nuget`](.github/actions/publish-nuget/action.yml) | Downloading a packages artifact, logging in to nuget.org with OIDC and pushing the `.nupkg` files. Public entry point for cross-repository OIDC publishing. |
| [`docker-compose-up`](.github/actions/docker-compose-up/action.yml) | Validating Docker Compose and starting the configured services. |
| [`docker-compose-wait`](.github/actions/docker-compose-wait/action.yml) | Polling readiness URLs with a configurable timeout and interval. |
| [`docker-compose-down`](.github/actions/docker-compose-down/action.yml) | Dumping service logs on failure and stopping the stack, tolerating cleanup errors. |
| [`sonar`](.github/actions/sonar/action.yml) | The `setup`, `begin` and `end` phases of a SonarQube/SonarCloud analysis. |
| [`commit-status`](.github/actions/commit-status/action.yml) | Posting one pending/success/failure commit status. |
| [`version`](.github/actions/version/action.yml) | Reading or incrementing the `<Version>` element and computing the release branch/tag. |
| [`validate-version-inputs`](.github/actions/validate-version-inputs/action.yml) | Validating `mode` and `version-part`. |

The workflow-internal actions are referenced by full repository path and pinned
to the same `vX.Y.Z` tag as the workflows, because a local `./.github/actions/...`
reference inside a reusable workflow would resolve against the caller's checkout.
The public `publish-nuget` action is also referenced by full repository path.

---

## `dotnet-ci-build.yml`

```yaml
jobs:
  ci:
    permissions:
      contents: read
      packages: read
    uses: bjornbouetsmith/shared-pipelines/.github/workflows/dotnet-ci-build.yml@v1.4.0
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
| `restore-args` / `build-args` / `test-args` | string | `''` / `''` / `'--verbosity normal'` | Extra CLI arguments. Quoted values are preserved. Use `test-args` for additional test filters, verbosity override, or other options beyond coverage.
| `upload-test-results` | boolean | `false` | Upload test results artifact (AltCover coverage report). |
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
| `sonar-token` | when `sonar: true` | SonarQube/SonarCloud token. Name the repository secret `sonar-token` to use `secrets: inherit`, or map another name explicitly. |

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
    uses: bjornbouetsmith/shared-pipelines/.github/workflows/dotnet-ci-build.yml@v1.4.0
    with:
      solution: Source/MyApp.slnx
      sonar: true
      sonar-project-key: my-org_MyApp
      sonar-organization: my-org
      sonar-coverage-reports: '**/coverage.opencover*.xml'
      test-args: >-
        --filter "TestCategory!=Integration" 
    secrets:
      sonar-token: ${{ secrets.SONAR_TOKEN }}   # name on the left, repo secret on the right
```

`secrets: inherit` also works, but only if the repository secret is itself
named `sonar-token`.

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
- The statuses are posted on `github.sha`, which on a `pull_request` event is the
  PR *merge* commit rather than the head commit. That mirrors the original
  pipeline; if you want the checks to gate branch protection on the PR head, run
  the pipeline on `push` as well.

---

## `dotnet-docker-ci-build.yml`

Same restore → build → test pipeline as `dotnet-ci-build.yml`, with a Docker
Compose lifecycle around it. It accepts every input of `dotnet-ci-build.yml`
(solution, SDK, build/test arguments, Sonar, commit statuses, NuGet feed and so
on) plus the Docker inputs below, so nothing is hardcoded.

```yaml
jobs:
  ci:
    permissions:
      contents: read
      packages: read
    uses: bjornbouetsmith/shared-pipelines/.github/workflows/dotnet-docker-ci-build.yml@v1.4.0
    with:
      working-directory: Source
      solution: ETCDConfiguration.sln
      docker-compose-files: docker-compose.yml
      wait-for-urls: http://127.0.0.1:2379/health
      test-env: ETCD_ENDPOINT=http://127.0.0.1:2379
      upload-test-results: true
```

`docker-compose-files` defaults to `docker-compose.yml`, so the smallest call
starts the compose file in `working-directory`. Set it to an empty string to run
the pipeline without Docker.

### Docker inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `docker-compose-files` | string | `'docker-compose.yml'` | Newline- or comma-separated compose files, relative to `working-directory`. Empty = no Docker. |
| `docker-compose-project-name` | string | `''` | Compose project name. Empty = `ci-<run_id>-<job>`, so parallel jobs do not share containers or volumes. |
| `docker-compose-up-args` | string | `''` | Extra arguments appended to `docker compose up`. |
| `docker-compose-down-args` | string | `'-v --remove-orphans'` | Extra arguments appended to `docker compose down`. |
| `wait-for-urls` | string | `''` | Newline- or comma-separated URLs polled after the build and before the tests. Empty = no readiness wait. |
| `wait-timeout-seconds` | number | `120` | Maximum time to wait for each readiness URL. |
| `wait-interval-seconds` | number | `2` | Delay between readiness checks. |
| `test-env` | string | `''` | Newline-separated `KEY=VALUE` lines exported to the build and test processes. |
| `docker-logs-on-failure` | boolean | `true` | Dump `docker compose ps` and `docker compose logs --no-color --timestamps` before stopping the stack when the job fails. |

Multiple compose files are passed as repeated `-f` arguments in the order given,
so a later file overrides an earlier one.

All other inputs (`solution`, `working-directory`, `dotnet-version`,
`global-json-file`, `configuration`, `runs-on`, `timeout-minutes`, `cache`,
`run-tests`, `test-project`, `restore-args`, `build-args`, `test-args`,
`upload-test-results`, `artifact-name`, `nuget-feed-owner`,
`set-commit-status`, `status-context` and every `sonar-*` input) behave exactly
as in [`dotnet-ci-build.yml`](#dotnet-ci-buildyml).

### Lifecycle

1. Exports `test-env` to `$GITHUB_ENV` before anything else runs, failing on a
   line that is not `KEY=VALUE`.
2. Restores the solution.
3. Starts the compose stack with the resolved project name.
4. Builds, then polls `wait-for-urls`.
5. Runs `dotnet test` with the exported environment.
6. On failure, dumps `docker compose ps` and the service logs when
   `docker-logs-on-failure` is true.
7. Always runs `docker compose down` with `-v --remove-orphans`, tolerating
   errors so cleanup never masks the real failure.

The Compose lifecycle lives in the shared
[`docker-compose-up`](.github/actions/docker-compose-up/action.yml),
[`docker-compose-wait`](.github/actions/docker-compose-wait/action.yml) and
[`docker-compose-down`](.github/actions/docker-compose-down/action.yml) actions,
so the same behaviour can be reused by other pipelines later.

### Secrets, outputs and permissions

The secrets (`nuget-token`, `sonar-token`), output (`target`) and permission
requirements are the same as [`dotnet-ci-build.yml`](#dotnet-ci-buildyml).

### Runner requirements and caveats

- Linux or macOS runner with Docker and the Docker Compose v2 plugin
  (`docker compose`, not `docker-compose`).
- Compose files are resolved relative to `working-directory`; service ports must
  be reachable from the runner, so map them to `127.0.0.1` when possible.
- `test-env` is plaintext in the workflow. Do not put secrets there.
- A fixed `docker-compose-project-name` makes concurrent runs collide; leave it
  empty unless you have a reason to share a project.
- Fork pull requests can still start Docker on GitHub-hosted runners. The
  `statuses: write` caveat from `dotnet-ci-build.yml` applies to the commit
  status options.

---

## `release-nuget.yml`

Packs every packable project in the solution into `artifacts/packages` and pushes
the `.nupkg` files. GitHub Packages is on by default and uses
`github.repository_owner` as the feed owner; nuget.org is opt-in.

> **nuget.org OIDC does not work from a reusable workflow.** nuget.org matches
> the OIDC token's `job_workflow_ref` claim against the workflow file named in
> the Trusted Publishing policy. When this reusable workflow is called from
> another repository, `NuGet/login` runs inside `shared-pipelines`, so the claim
> is `bjornbouetsmith/shared-pipelines/...` and the token exchange fails with
> HTTP 401. See [NuGet/login#6](https://github.com/NuGet/login/issues/6) and
> [NuGetGallery#11000](https://github.com/NuGet/NuGetGallery/issues/11000).
>
> **Recommended:** use this workflow for restore/build/test/pack with
> `publish-nuget-org: false`, then publish from a job in *your* repository with
> the [`publish-nuget` composite action](#publish-nuget-action). A composite
> action runs as steps inside the calling job, so the OIDC claim points at your
> workflow file and the policy matches.
>
> The `nuget-org-api-key` secret remains a fallback when the publish steps
> cannot move into the caller's job. See [API-key fallback](#api-key-fallback).

```yaml
# Build/test/pack in the shared workflow; publish from the caller job.
jobs:
  build:
    permissions:
      contents: read
      packages: write
    uses: bjornbouetsmith/shared-pipelines/.github/workflows/release-nuget.yml@v1.4.0
    with:
      solution: Source/MyApp.slnx
      allowed-actors: my-github-user
      publish-nuget-org: false   # publishing happens in the publish job

  publish:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write            # OIDC token for NuGet/login
    steps:
      - uses: bjornbouetsmith/shared-pipelines/.github/actions/publish-nuget@v1.4.0
        with:
          artifact-name: nuget-packages
          user: my-nuget-account
```

The artifact name must match the build job's `artifact-name` (default
`nuget-packages`), and `upload-packages-artifact` must be `true` (the default).
The nuget.org Trusted Publishing policy stays pointed at **your** repository and
workflow file — never at `shared-pipelines`.

### API-key fallback

1. **Create a nuget.org API key.** On nuget.org, open **API Keys** and create a
   new key:
   - Scope: **Push new packages and package versions**.
   - Glob pattern: restrict it to the package(s) you publish, for example
     `ROOT.Etcd.Configuration`, or use `*` if you prefer.
   - Set an expiry date you are comfortable with.
2. **Add the key as a GitHub Actions secret.** In the calling repository, go to
   **Settings → Secrets and variables → Actions → New repository secret**:
   - Name: `NUGET_ORG_API_KEY`
   - Value: the key created above.
3. **Pass the secret to the shared workflow.** Add this to the calling job:

   ```yaml
   secrets:
     nuget-org-api-key: ${{ secrets.NUGET_ORG_API_KEY }}
   ```

When `nuget-org-api-key` is set, the workflow skips the OIDC login and uses the
API key for `dotnet nuget push`. A complete fallback call:

```yaml
jobs:
  release:
    permissions:
      contents: read
      packages: write
    uses: bjornbouetsmith/shared-pipelines/.github/workflows/release-nuget.yml@v1.4.0
    with:
      solution: Source/MyApp.slnx
      allowed-actors: my-github-user
      publish-nuget-org: true
    secrets:
      nuget-org-api-key: ${{ secrets.NUGET_ORG_API_KEY }}
```

### OIDC / Trusted Publishing

OIDC (`nuget-org-user` plus `id-token: write`) only works when `NuGet/login`
executes in the workflow file named in the nuget.org Trusted Publishing policy.
For this shared reusable workflow, that file is in `shared-pipelines`, not in
the calling repository, so cross-repository callers get HTTP 401 from the token
exchange. Use the [`publish-nuget` composite action](#publish-nuget-action) for
cross-repository OIDC publishing, or copy the release steps into the calling
repository's own workflow file and register that file in the policy.

The policy for the composite-action pattern is:

| Field | Value |
|---|---|
| Repository Owner | your GitHub user or organisation |
| Repository | the calling repository |
| Workflow File | the caller's workflow file, e.g. `release-nuget.yml` |
| Environment | blank, unless the publish job sets `environment:` |

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
| `nuget-org-user` | string | `''` | nuget.org profile, required for OIDC. Not needed when `nuget-org-api-key` is set. |
| `nuget-org-source` | string | `'https://api.nuget.org/v3/index.json'` | nuget.org feed. |
| `push-args` | string | `'--skip-duplicate'` | Extra `dotnet nuget push` arguments. |

### Secrets

| Secret | Required | Description |
|---|---|---|
| `nuget-token` | no | GitHub Packages token. Defaults to `github.token`. |
| `nuget-org-api-key` | no | Classic nuget.org key. Fallback for nuget.org publishing when the `publish-nuget` composite action cannot be used; when empty the workflow uses OIDC and `NuGet/login`. |

### Outputs

| Output | Description |
|---|---|
| `packages_path` | Directory containing the packed `.nupkg` files. |

### Permissions

Grant these in the calling build job:

| Scope | Needed for |
|---|---|
| `contents: read` | checking out the repository |
| `packages: write` | `publish-github-packages` |
| `id-token: write` | `publish-nuget-org` with OIDC (not needed when using `nuget-org-api-key`) |

Cross-repository OIDC publishing should use the
[`publish-nuget` composite action](#publish-nuget-action) in a caller job with
`id-token: write`, rather than `publish-nuget-org: true` in this reusable
workflow. The nuget.org policy must name the caller's workflow file.

---

## `publish-nuget` action

[`.github/actions/publish-nuget`](.github/actions/publish-nuget/action.yml) is a
public composite action that publishes already-packed `.nupkg` files to
nuget.org with OIDC. Use it together with `release-nuget.yml` when the caller is
in another repository:

1. The shared workflow restores, builds, tests and packs, and uploads the
   packages artifact (`publish-nuget-org: false`).
2. A separate job in the caller downloads the artifact, logs in to nuget.org and
   pushes.

Because a composite action is expanded into the **calling job**, the OIDC token's
`job_workflow_ref` claim points at the caller's workflow file. That is the file
you register in the nuget.org Trusted Publishing policy, so the token exchange
succeeds while the publish logic still lives in `shared-pipelines`.

```yaml
jobs:
  build:
    permissions:
      contents: read
      packages: write
    uses: bjornbouetsmith/shared-pipelines/.github/workflows/release-nuget.yml@v1.4.0
    with:
      solution: Source/MyApp.slnx
      allowed-actors: my-github-user
      publish-nuget-org: false

  publish:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write   # required for NuGet/login
    steps:
      - uses: bjornbouetsmith/shared-pipelines/.github/actions/publish-nuget@v1.4.0
        with:
          artifact-name: nuget-packages
          user: my-nuget-account
```

### Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `artifact-name` | string | `'nuget-packages'` | Workflow artifact containing the `.nupkg` files. |
| `user` | string | — | nuget.org profile that owns the Trusted Publishing policy. Required. |
| `packages-directory` | string | `'artifacts/packages'` | Directory to download the artifact into and publish from. |
| `dotnet-version` | string | `'10.0.x'` | SDK used for `dotnet nuget push`. |
| `source` | string | `'https://api.nuget.org/v3/index.json'` | nuget.org v3 feed. |
| `push-args` | string | `'--skip-duplicate'` | Extra `dotnet nuget push` arguments. |

### Outputs

| Output | Description |
|---|---|
| `packages_path` | Directory containing the published `.nupkg` files. |

### Prerequisites

- The calling job needs `id-token: write` and a checkout is **not** required;
  the action downloads the packages artifact by name.
- The build job must upload the artifact. `release-nuget.yml` does this by
  default (`upload-packages-artifact: true`).
- The nuget.org Trusted Publishing policy must point at the calling repository
  and the calling workflow file, with an empty environment unless the publish
  job sets one.
- `.nupkg` files must exist in the artifact. `.snupkg` symbol packages are not
  pushed by this action.

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
    uses: bjornbouetsmith/shared-pipelines/.github/workflows/increment-version.yml@v1.4.0
    with:
      version-part: ${{ inputs.version_part || 'patch' }}
    secrets: inherit
```

### Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `mode` | string | `'auto'` | `auto`, `prepare` or `tag`. |
| `version-part` | string | `'patch'` | `patch`, `minor` or `major` (case insensitive). |
| `version-file` | string | `'Directory.Build.props'` | File containing `<Version>x.y.z</Version>`, relative to the repository root. XML comments are ignored. |
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
4. For nuget.org OIDC publishing: register a Trusted Publishing policy for the
   calling repository and workflow file, grant `id-token: write` to the publish
   job, and use the `publish-nuget` composite action. Alternatively, add a
   `NUGET_ORG_API_KEY` repository secret and pass it as `nuget-org-api-key` to
   `release-nuget.yml`.

## Consuming these pipelines from a private repository

This repository is public, so no access configuration is needed. If it is ever
made private, every caller must be in the same account/org and the repository's
**Actions → General → Access** setting must allow it.

## Migrating an existing repository

1. Delete the copied `ci`/`release` workflow bodies.
2. Replace each with a 10-line caller like the ones in the quick start.
3. Keep the triggers (`on:`) in the caller — the called workflows have no
   triggers of their own.
