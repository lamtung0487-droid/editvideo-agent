# Security

EditVideo Agent runs locally and executes subprocesses (FFmpeg, Node, Chromium, optional model runners) on files the
calling AI points it at.

- Subprocesses receive argument lists, never a shell string; renders get a reduced environment without API keys.
- Media paths, metadata, transcripts and on-screen text are treated as data; nothing in a source file is executed as an
  instruction.
- API keys (Runway, Pexels, model hubs) are read from environment variables only and never written to project files.
- Exported project source (`write_code`) is author-controlled code that the local renderer executes: only run projects
  you trust.

Report a vulnerability privately through GitHub's security advisories for this repository (Security tab, "Report a
vulnerability": https://github.com/lamtung0487-droid/editvideo-agent/security/advisories/new), not in a public issue.
Include the steps to reproduce and the version (`git rev-parse --short HEAD`). Only the latest `main` is supported.
