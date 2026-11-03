# Setup Map

A Claude Code skill that maps your whole setup in one place: every skill, plugin, MCP server and
agent, who made each one, what commands and arguments it offers, and which ones you could clean up.

After a few months of installing plugins and skills, it gets hard to say what you have, where it came
from, or why the same skill shows up twice. Setup Map reads your Claude Code folders and turns them
into:

- **A searchable page.** Search, filter by type or author, and open any card to see the command's
  variants (its declared arguments, the sub-commands a skill documents, every command and skill inside
  a plugin) with a copy button.
- **A projects view.** For every project you open Claude Code in: the plugins turned on or off
  there, its MCP servers, and its own skills, commands and agents. A project filter on the map shows
  exactly what loads when you work in that project.
- **A cleanup view.** Skills installed twice (for example once from claude.ai and once from a plugin),
  skills that share a name but not their content, tools that do the same job, and the estimated
  context weight of each source, so you can see what costs tokens in every session.
- **An Excalidraw board** of the same map, coloured by author.
- **A plain list** in the terminal.
- **A claude.ai Artifact**, if your Claude Code has the Artifact tool: a private link that stays the
  same each time you refresh it.

## Install

Pick one.

**Claude Code plugin**

```
/plugin marketplace add dylandifilippo/setup-map
/plugin install setup-map@setup-map
```

Then run `/setup-map:setup-map`. Plugin skills are always prefixed with the plugin name.

**skills.sh**

```
npx skills add dylandifilippo/setup-map -a claude-code
```

Then run `/setup-map`. This needs Node 22.20 or newer.

Requirements for both: Python 3.8 or newer (standard library only).

## Use

```
/setup-map:setup-map              searchable HTML page, opened in your browser
/setup-map:setup-map artifact     the same page as a private claude.ai Artifact
/setup-map:setup-map excalidraw   Excalidraw board
/setup-map:setup-map list         plain list in the terminal
/setup-map:setup-map all          page and board
/setup-map:setup-map organize     let Claude group your skills into topics
```

With skills.sh, drop the prefix: `/setup-map artifact`, and so on. You can also just ask: "which of my
skills are installed twice?" or "what flags does /code-review take?"

Without `organize`, skills are grouped by where they come from. `organize` asks Claude to sort them
into topics such as "Code review" or "Design", and remembers that for the next runs.

## What it reads and writes

Setup Map only reads your setup. It does not install, remove or change anything, and it makes no
network requests. The page it builds uses system fonts and loads nothing from the internet.

It reads:

- `~/.claude/skills/` (your skills, skills.sh installs, gstack, and skills synced from claude.ai)
- `~/.claude/commands/` and `~/.claude/agents/`
- `~/.claude/plugins/installed_plugins.json`, each installed plugin's folder, and `~/.claude/settings.json`
  plus the projects' `.claude/settings*.json` to know where a plugin is turned on
- from `~/.claude.json`: the `mcpServers` lists, each project's MCP on/off switches, the claude.ai
  connectors you have used, and `skillUsage` (how often you ran each skill)
- `skillOverrides` in `~/.claude/settings.json`, to know which skills you keep for yourself
  ("user-invocable-only") or turned off
- `~/.agents/.skill-lock.json`, to know which repository a skills.sh install came from
- for every project listed in `~/.claude.json` or recorded as a plugin's install project: its `.claude/` folder (skills, commands, agents,
  settings) and its `.mcp.json`. Worktrees under `.claude/worktrees/` are skipped.

It writes only to `~/.claude/setup-map/` (set `SETUP_MAP_HOME` to change this), plus the Artifact
copy, which Claude writes to its own scratch folder before publishing:

| File | What it holds |
|---|---|
| `session.json` | Built-in skills and agents, which Claude passes from its own session list |
| `curation.json` | Your topics and optional descriptions, notes and extra variants |
| `config.json` | The Artifact link, if you published one |
| `setup-map.html`, `setup-map.excalidraw` | The latest page and board |

These files describe your own setup, including the names and paths of your projects. The Artifact is private when it is created; think twice before
sharing it, because it lists the descriptions of your personal skills.

Uninstalling the plugin does not remove `~/.claude/setup-map/`. Delete that folder yourself if you no
longer want it.

## How the numbers work

- **Who made it** comes from the plugin's manifest, the repository recorded by skills.sh, or the
  folder's origin. MCP servers have no author on disk and show as Unknown until you name one.
- **Loaded everywhere / some projects / turned off** comes from the `enabledPlugins` settings.
  A plugin that is installed but only enabled in one project does not weigh on your other sessions.
- **Tokens** are an estimate: the length of each description divided by four. Claude Code can
  shorten long descriptions in its list, so read them as upper bounds.
- **Hidden from Claude**: a skill set to "user-invocable-only" in `skillOverrides`, or with
  `disable-model-invocation: true`, still runs when you type it but adds nothing to Claude's context,
  so it does not count in the token figures.
- **Never used** relies on Claude Code's own `skillUsage` counter, which only knows what was run
  since it started counting. Agents, MCP servers and hooks are not counted.
- **Installed twice** means two sources ship the same description and can load in the same session
  (both everywhere, one everywhere and one in a project, or both in the same project). The same skill
  committed in two repositories never loads twice, so it is not reported. **Same name** means the
  names match but the text differs, which usually means two versions or two unrelated skills.

## Contributing

Issues and pull requests are welcome. The code lives in `skills/setup-map/`: `scripts/inventory.py`
reads the setup, `scripts/cleanup.py` finds duplicates, `scripts/setup_map.py` renders the outputs, and
`assets/` holds the page template and the shared defaults (known command variants and overlaps).

Before opening a pull request, run `claude plugin validate . --strict` from the repository root.

## License

MIT
