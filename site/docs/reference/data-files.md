---
title: Data files and locations
nav_title: Data files
description: Where JBrowser keeps every file, generated from AppPaths.
---

[[generated]]

## Other locations

| What | Where |
|---|---|
| The installed program | `%LOCALAPPDATA%\Programs\JBrowser\` (or Program Files with `/ALLUSERS`) |
| Downloaded updates (temporary) | `%TEMP%\JBrowser-Update\` |
| Build output | `dist\` and `build\` in the repository, or `%LOCALAPPDATA%\JBrowser-build\` for a repository inside OneDrive |

How these files are written and deleted is explained in [persistence](../architecture/persistence.md).
