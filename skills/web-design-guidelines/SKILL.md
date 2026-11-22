---
name: web-design-guidelines
description: Review UI code against Vercel's Web Interface Guidelines. Use when the user asks to "check against the Web Interface Guidelines", "review my UI against the guidelines", or "check my site against best practices".
argument-hint: <file-or-pattern>
metadata:
  author: vercel
  version: '1.0.0'
---

# Web Interface Guidelines

Review files for compliance with the Web Interface Guidelines.

The rules and the output format are in [guidelines.md](guidelines.md) in this folder, copied from a fixed upstream commit. Read that file; never fetch the guidelines from the web at run time, so the rules cannot change after this plugin was reviewed.

If no files or pattern were given, ask the user which files to review.
