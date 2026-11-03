---
name: loadout
description: Show the user's Claude Code loadout - everything that loads into their sessions and eats context: every skill, plugin, MCP server and agent, who made each one, which projects load it, the commands and arguments it offers, and which ones are installed twice, overlap or weigh most in context. Renders a searchable HTML page (or a claude.ai Artifact), an Excalidraw board, or a plain list. Use when the user asks what skills or plugins they have, who made a skill, what is turned on in which project, what flags or variants a command takes, which skills are duplicated or waste context, what to clean up, how to free up context, or wants a map of their setup.
argument-hint: "[html|artifact|excalidraw|list|all] [organize]"
compatibility: Claude Code only (reads ~/.claude and ~/.claude.json). Needs Python 3.8+.
license: MIT
allowed-tools: Bash(python3 *loadout.py*)
---

# Loadout

Every step runs one bundled script, read-only on the user's setup:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/loadout.py" <command>
```

It writes only to its data folder, `~/.claude/loadout/` (override with `LOADOUT_HOME`), or
to an `--out` path. It never touches the network, and the page it renders loads nothing from it.

## 1. Tell the script what this session lists

Built-in skills and agents are not on disk, so the script learns them from you. Run `known` first:
it prints the skill and agent names it already found on disk.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/loadout.py" known
```

Then send the rest: every skill in your available-skills list whose name has **no colon** and is
**not** in that output, and every agent type you can dispatch whose name has no colon and is not
in it. One short description each (one sentence, under 200 characters), copied from your listing.
Add the names of the MCP servers whose tools this session has (the part between `mcp__` and the
next `__` in a tool name, such as `computer-use` or `plugin_figma_figma`); the script keeps only the
built-in ones it cannot find on disk.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/loadout.py" session <<'EOF'
{"skills": [{"name": "code-review", "description": "…"}], "agents": [{"name": "Explore", "description": "…"}],
 "mcp": ["claude-in-chrome", "computer-use", "plugin_figma_figma"]}
EOF
```

Skip this step when `~/.claude/loadout/session.json` was saved earlier in this conversation.

## 2. Render what the user asked for

The argument picks the output. With none, render `html`.

| Argument | Command | Then |
|---|---|---|
| `html` | `loadout.py html --open` | Give the file path; it opened in the browser. |
| `artifact` | see below | Give the artifact link. |
| `excalidraw` | `loadout.py excalidraw` | Give the path; it opens at https://excalidraw.com (drag and drop) or in the Excalidraw VS Code extension. |
| `list` | `loadout.py list` | Show the output as is. |
| `all` | `html --open`, then `excalidraw` | Both paths. |

Pass `--out <path>` to `html` or `excalidraw` when the user names a location.

**Artifact.** Only when the user asks for one and the Artifact tool is available in this session.
Without the tool, say so in one line and render `html` instead.

1. `loadout.py config` prints the saved `artifact_url`, if any.
2. `loadout.py html --artifact --out <your scratchpad directory>/loadout.html`.
   `--artifact` leaves out the document head, which the Artifact skeleton provides. The page lists the
   user's skills and project paths, so never write it into the working directory or a repository; if
   this session has no scratchpad, ask the user where to put it.
3. Publish that file with the Artifact tool. With a saved URL, publish to it (read it first if this
   conversation has not), so the link stays the same; on a first publish pass the icon `map`.
4. After a first publish, save the link: `loadout.py config --artifact-url <url>`.
5. Tell the user the artifact is private, and that it lists the descriptions of their own skills,
   which they may not want to share.

## 3. Organize (optional)

Run this when the argument includes `organize`, or offer it in one line when `uncategorized`
reports many skills. It groups skills into topics, which is the only part a script cannot do.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/loadout.py" uncategorized
```

It prints the existing topics and every skill not yet in one. Edit
`~/.claude/loadout/curation.json` (create it if missing; keep every key already there):

```json
{
  "topics": {"Code review": ["/code-review", "/review"], "Design": ["/design-review"]},
  "descriptions": {"/review": "Review the diff before landing"},
  "authors": {"mcp:brave-search": "Brave"},
  "notes": {"claude.ai|plugin document-skills": "Advice shown for that duplicate bundle"},
  "overlaps": [{"title": "…", "members": ["/a", "/b"], "note": "…"}],
  "usage": {"/my-skill": [{"cmd": "/my-skill --fast", "note": "…"}]}
}
```

- `topics`: 8 to 15 short topic names; reuse existing ones before adding a new one. Ids are what
  `uncategorized` prints. Skills left out still appear, grouped by source.
- `descriptions`: optional, at most 50 characters, imperative. They fit the Excalidraw cards.
- `authors`: MCP servers have no author on disk; set one when you know it. Ids look like `mcp:<name>`.
- `notes` and `overlaps`: only when the user wants their own advice in the cleanup view. The key of a
  note is the bundle's sources joined with `|`, as the page shows them.
- `usage`: only for variants you know for certain. Never invent flags.

Then render again.

## Rules

- Report findings; never uninstall, delete or disable anything yourself. The cleanup view gives
  advice, and the user acts on it, or asks you to and confirms first.
- Token figures are estimates (description length divided by 4). Say so when you quote them.
