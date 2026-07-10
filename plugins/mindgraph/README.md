# MindGraph (plugin)

This directory is the installable Claude Code plugin — the code that ships
when you run `/plugin install mindgraph@mindgraph`. It's read-only at
runtime: all data (config, `.env`, the palace, generated adapters) is written
to `~/.mempalace` (or `$MINDGRAPH_HOME`), never back into this folder. See the
[repo-root README](../../README.md) for install instructions, architecture,
and the full skill list.
