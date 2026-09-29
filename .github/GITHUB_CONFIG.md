# `.github/`: GitHub configuration

> This folder's guide is called `GITHUB_CONFIG.md`, not `README.md`, on purpose. GitHub shows a README inside `.github/`
> as the repository's front page in place of the main [README.md](../README.md).

| Path | Purpose |
|---|---|
| `workflows/ci.yml` | On every push and pull request: installs the dependencies on Windows and runs `tools/update_deps.py --check` (every module imports, pyflakes is clean) |
| `workflows/pages.yml` | Builds the website with `tools/build_site.py` and deploys it to GitHub Pages: on pushes to `main` that touch the site, docs, changelog or code, and by hand (`tools/release.ps1` starts it after each release) |
| `ISSUE_TEMPLATE/bug_report.yml` | The form for bug reports (version, Windows version, steps, log) |
| `ISSUE_TEMPLATE/feature_request.yml` | The form for ideas |
| `ISSUE_TEMPLATE/config.yml` | Points security reports to [SECURITY.md](../SECURITY.md) |
| `pull_request_template.md` | The checklist shown when opening a pull request |

Releases are not built by CI. They are built and published from a Windows PC with `master.ps1` (see
[docs/RELEASING.md](../docs/RELEASING.md)). After publishing, `tools/release.ps1` starts `pages.yml` on `main`
(`gh workflow run`), so the website's download buttons, changelog and documentation versions update by themselves.
A release event can't do this: it runs on the tag, and the `github-pages` environment only deploys from `main`.

GitHub Pages must be set to deploy from **GitHub Actions** (*Settings → Pages → Build and deployment → Source*).
