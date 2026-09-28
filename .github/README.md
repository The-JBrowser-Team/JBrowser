# `.github/`: GitHub configuration

| Path | Purpose |
|---|---|
| `workflows/ci.yml` | On every push and pull request: installs the dependencies on Windows and runs `tools/update_deps.py --check` (every module imports, pyflakes is clean) |
| `ISSUE_TEMPLATE/bug_report.yml` | The form for bug reports (version, Windows version, steps, log) |
| `ISSUE_TEMPLATE/feature_request.yml` | The form for ideas |
| `ISSUE_TEMPLATE/config.yml` | Points security reports to [SECURITY.md](../SECURITY.md) |
| `pull_request_template.md` | The checklist shown when opening a pull request |

Releases are not built by CI. They are built and published from a Windows PC with `tools\release.ps1` (see
[docs/RELEASING.md](../docs/RELEASING.md)).
