---
title: Command line and environment
nav_title: Command line
description: JBrowser's command-line options and the environment variables it reads.
---

[[generated]]

## Examples

```powershell
JBrowser.exe https://example.com "search terms"          # open two cards (in the running window if there is one)
JBrowser.exe --incognito                                  # start in a new incognito space
JBrowser.exe --profile-dir D:\PortableJBrowser            # portable mode: everything in that folder
.\.venv\Scripts\python.exe main.py --profile-dir "$env:TEMP\jb-dev" --debug --no-restore
```
