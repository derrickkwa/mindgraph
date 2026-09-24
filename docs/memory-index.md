# Memory index: keeping `MEMORY.md` small on purpose

Claude Code's auto-memory file (`MEMORY.md`) loads into every session
automatically. That's what makes it valuable — and what makes it dangerous.
It has a load ceiling: past a certain size, the tail of the file silently
stops loading. No error, no warning. You just lose whatever's below the
cutoff, and you won't notice until you act on stale information.

The fix isn't a bigger ceiling. It's discipline about what earns a place in
the always-loaded file at all.

## The admission test

Before adding a line to `MEMORY.md`, ask: **would missing this cause a wrong
action, and would I not think to look it up first?**

- Identity facts, hard feedback rules, gotchas that bite silently — yes.
- Anything you'd naturally think to search for, or that only matters in one
  context — no.

A concrete gotcha like "retries against this endpoint need exponential
backoff or it 429s the whole account" passes the test — you wouldn't think to
check for it before writing the retry loop, and getting it wrong is a real
outage. A note like "worked on the onboarding flow last Tuesday" fails —
you'd look that up if it mattered, and forgetting it doesn't break anything.

Everything that fails the test still gets written down — it just doesn't go
in `MEMORY.md`.

## Topic hubs

Memories that fail the admission test go into a topic hub file —
`hub_<topic>.md` — instead. `MEMORY.md` keeps one short pointer line per hub,
naming what's inside it, and links to the file. A session that needs the
detail follows the pointer and reads the hub; a session that doesn't, never
pays the load cost.

Example: instead of writing a project's retry policy directly into
`MEMORY.md`, it goes in its own memory file, `feedback_retry_policy.md`. The
topic hub (`hub_tools.md`) carries only a one-line pointer to that file, and
`MEMORY.md` carries a line pointing to the hub:

```
- [Tools & integrations — retry policy, deploy steps, API quirks](hub_tools.md)
```

Pick hub boundaries by domain, not by size — a hub for clients, a hub for a
specific project, a hub for tooling gotchas. Splitting further only when a
hub itself grows unwieldy keeps the index shallow and predictable.

## One current verdict per file, past ones in the ledger

Memory files drift: a belief you recorded six months ago gets revised, and if
you just edit the line in place, you lose the "why" and the history. Keep
only the **current verdict** inline in the memory file. When it changes,
record the old one in the belief ledger rather than deleting it silently:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/belief_ledger.py --record-conclusion \
  --concept 'retry-policy' --belief 'fixed 3 retries, no backoff' \
  --memory-file feedback_retry_policy.md \
  --effective-date 2026-08-01

# later, when the verdict changes:
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/belief_ledger.py --record-revision \
  --concept 'retry-policy' \
  --old 'fixed 3 retries, no backoff' \
  --new 'exponential backoff, cap at 5' \
  --revision-kind refinement \
  --effective-date 2026-09-01 \
  --why 'endpoint started 429ing under fixed retry load' \
  --memory-file feedback_retry_policy.md
```

`--revision-kind` is `reversal` (the old belief was wrong) or `refinement`
(the old belief still holds, narrowed or extended). After recording a
revision, add one line to the memory file itself:

```
history: ledger → retry-policy
```

That's the whole footprint the revision leaves in the always-loaded file —
a pointer, not a paragraph.

If a single file accumulates verdicts on more than one distinct claim, key
each one separately with `<file-stem>--<claim-slug>`, e.g.
`feedback_retry_policy--retry-policy` and
`feedback_retry_policy--deploy-cadence`, so a query for one claim's history
doesn't return another's.

**Quoting:** the ledger CLI reads its arguments from the shell, and `$` is
stripped by unquoted shell expansion — always single-quote text you pass to
`--belief`, `--old`, `--new`, and `--why`.

## Enabling sync

Memory-file sync is opt-in, asked once during `/mindgraph-setup` (step 6b).
Saying yes turns on a hook that fires after file edits and exits immediately
unless the edited file is a Claude Code memory file — it installs nothing
new. `MEMORY.md`, `hub_*.md`, and `archive.md` are never synced into the
palace (they're index/rollup files, not searchable content); the memory
files they point to are.

After a bulk sync — enabling it for the first time, or re-running it across
many files at once — **restart Claude Code**. The retrieval MCP server
caches its database client on startup and won't see writes made by another
process until it restarts.

## See also

- `docs/lessons.md` — the write path and read path this index feeds into.
