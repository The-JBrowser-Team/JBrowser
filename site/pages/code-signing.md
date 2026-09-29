---
title: Code signing policy
kicker: Project
lead: How JBrowser's programs are signed, who can change the code and who approves each release.
description: JBrowser's code signing policy: what is signed, how builds are made, team roles and privacy.
---

<p class="note"><strong>Status:</strong> JBrowser is set up to be signed through SignPath Foundation's free code signing
for open-source software, and is applying for it. Until it is approved, releases are not code-signed, and Windows SmartScreen may show
"Windows protected your PC" for a downloaded installer. The <a href="../download/index.html">download page</a>
explains how to install without the warning. This policy applies from the first signed release.</p>

Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by
[SignPath Foundation](https://signpath.org/).

## What is signed

- `JBrowser.exe`, the browser itself, and `JBrowser-Setup-<version>.exe`, its installer, for every release
  published on [GitHub Releases](https://github.com/The-JBrowser-Team/JBrowser/releases).
- Nothing else: JBrowser signs only programs built from its own source code. The Qt, Python and Chromium files
  inside JBrowser are signed by their own publishers or not at all.

## How signed builds are made

- Every signed release is built from its tagged source code by the
  [release-build workflow](https://github.com/The-JBrowser-Team/JBrowser/blob/main/.github/workflows/release-build.yml)
  on GitHub's own (GitHub-hosted) Windows machines, never on a personal computer.
- The workflow sends the built programs to SignPath, which checks that they came from this repository and this
  workflow, and that their product name (JBrowser) and version match the release.
- Each signing request is approved by hand by an approver before anything is signed.
- Installed copies of JBrowser that are signed accept an update only if it is signed by the same publisher, in
  addition to checking its SHA-256 fingerprint.

## Team roles

| Role | Who |
|---|---|
| Committers and reviewers | [Members of The JBrowser Team](https://github.com/orgs/The-JBrowser-Team/people) on GitHub. Changes from anyone else are reviewed by a committer before they are merged. |
| Approvers | [Owners of The JBrowser Team](https://github.com/orgs/The-JBrowser-Team/people?query=role%3Aowner) on GitHub. An approver approves every signing request. |

Team members use multi-factor authentication for GitHub and SignPath.

## Privacy

JBrowser sends nothing about you or your browsing to the JBrowser team. The connections it makes by itself (update
checks, protection lists, secure DNS and search suggestions) are listed in the [privacy policy](../privacy/index.html).

## Reporting a problem

If you believe a signed JBrowser program behaves maliciously, or was signed without following this policy, report it
privately as described in the [security policy](https://github.com/The-JBrowser-Team/JBrowser/blob/main/SECURITY.md).
