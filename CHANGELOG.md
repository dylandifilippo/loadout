# Changelog

## 0.1.0 (2026-11-03)

First release. Published briefly as setup-map, renamed before anyone else installed it.

- Inventory of standalone skills, custom commands, claude.ai synced skills, plugins (with their
  commands, skills, agents and MCP servers), MCP servers, agents, and every project Claude Code knows
  (its own `.claude/` folder and `.mcp.json`). Built-in skills, agents and MCP servers come from the
  session's own list.
- Load status for plugins and MCP servers: loaded everywhere, only in some projects, turned off in a
  project, or installed and turned off. claude.ai connectors are listed separately.
- Skill visibility from `skillOverrides` and `disable-model-invocation`, and use counts from
  `skillUsage`.
- Searchable HTML page with author colours, type, author and project filters, per-command variants
  (`argument-hint` plus the variants a skill's text cites) and a copy button. Views have their own
  address (`#map`, `#map-<project>`, `#projects`, `#cleanup`), so a filtered view can be bookmarked.
- Projects view: what each project adds to or removes from what loads everywhere.
- Cleanup view: skills that load twice, same-name clashes, overlapping tools, skills and plugins never
  used, and estimated context weight per source.
- Excalidraw board and a plain text list from the same data.
- Optional claude.ai Artifact publish that keeps the same link across refreshes.
