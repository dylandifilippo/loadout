"""Read the local Claude Code setup and describe every skill, plugin, MCP server and agent in it.

Read-only: nothing here writes outside the loadout data folder, and nothing touches the network.
"""
import glob
import json
import os
import re

HOME = os.path.expanduser("~")
CLAUDE = os.path.join(HOME, ".claude")
SKILLS_DIR = os.path.join(CLAUDE, "skills")
AGENTS_DIR = os.path.join(CLAUDE, "agents")
COMMANDS_DIR = os.path.join(CLAUDE, "commands")
PLUGINS_FILE = os.path.join(CLAUDE, "plugins", "installed_plugins.json")
SETTINGS_FILE = os.path.join(CLAUDE, "settings.json")
CLAUDE_JSON = os.path.join(HOME, ".claude.json")
SKILLS_LOCK = os.path.join(HOME, ".agents", ".skill-lock.json")

# gstack setup writes these aliases as real folders holding a renamed copy of another gstack skill.
GSTACK_ALIASES = {"_gstack-command", "connect-chrome", "gstack-connect-chrome"}
CLAUDE_AI_SOURCES = {"anthropic": "Anthropic", "anthropic-example": "Anthropic",
                     "custom": "You", "plugin": "claude.ai plugin"}


def read_json(path, default):
    """Parsed JSON, or default when the file is missing, invalid, or not the shape default has."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return default
    if default is not None and not isinstance(data, type(default)):
        return default
    return data


def text_of(value):
    return value if isinstance(value, str) else ""


def obj(value):
    return value if isinstance(value, dict) else {}


def lst(value):
    return value if isinstance(value, list) else []


def unquote(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] == "'":
        return text[1:-1].replace("''", "'")
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return text[1:-1].replace('\\"', '"')
    return text


def read_md(path):
    """Return (frontmatter text, body text) of a Markdown file, or two empty strings."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return "", ""
    m = re.match(r"---\r?\n(.*?)\r?\n---\r?\n?(.*)", text, re.S)
    return (m.group(1), m.group(2)) if m else ("", text)


def field(head, key):
    m = re.search(rf"^{re.escape(key)}:[ \t]*(.+)$", head, re.M)
    return unquote(m.group(1)) if m else ""


def description(head, body=""):
    """The frontmatter description, folded to one line; else the body's first paragraph, as Claude Code does."""
    m = re.search(r"^description:[ \t]*(.*?)(?=\n\S|\Z)", head, re.M | re.S)
    text = m.group(1).strip() if m else ""
    text = re.sub(r"^[|>][-+]?[ \t]*", "", text)
    text = unquote(" ".join(text.split()))
    if not text and body:
        for para in re.split(r"\n\s*\n", body):
            para = " ".join(line for line in para.strip().splitlines() if not line.lstrip().startswith("#"))
            if para.strip():
                return " ".join(para.split())[:400]
    return text


SENTENCE_END = re.compile(r"(?<=[.!?])(?<!e\.g\.)(?<!i\.e\.)(?<!etc\.)(?<!vs\.)\s")


def first_sentence(text, limit=90):
    first = SENTENCE_END.split(text, maxsplit=1)[0] if text else ""
    return first if len(first) <= limit else first[:limit].rsplit(" ", 1)[0] + "…"


def usage_from(head, body, command):
    """The argument-hint signature, plus the variants the skill's own text cites as `/command …`."""
    out, seen = [], {command}
    hint = field(head, "argument-hint")
    if hint:
        out.append({"cmd": f"{command} {hint}", "note": "Arguments"})
        seen.add(out[0]["cmd"])
    for m in re.finditer(r"`(" + re.escape(command) + r"(?:\s[^`\n]{1,80})?)`", body):
        cmd = " ".join(m.group(1).split())
        if cmd not in seen and len(out) < 12:
            seen.add(cmd)
            out.append({"cmd": cmd})
    return out


def tokens(text):
    """Rough token estimate for text Claude Code puts in context (about 4 characters per token)."""
    return max(1, round(len(text) / 4)) if text else 0


def skill_item(cmd, md_path, author, source, status="everywhere"):
    head, body = read_md(md_path)
    long = description(head, body)
    return {
        "id": cmd, "kind": "skill", "name": cmd.lstrip("/"), "cmd": cmd,
        "author": author, "source": source, "status": status,
        "desc": first_sentence(long), "long": long, "tokens": tokens(long),
        "usage": usage_from(head, body, cmd), "visibility": frontmatter_visibility(head),
    }


def frontmatter_visibility(head):
    """disable-model-invocation hides a skill from Claude; only the user can run it."""
    return "user" if field(head, "disable-model-invocation").lower() == "true" else "model"


def standalone_source(name, path, lock):
    if name in GSTACK_ALIASES:
        return "gstack", "gstack alias"
    if os.path.islink(path):
        repo = obj(lock.get(name)).get("source", "")
        repo = repo if isinstance(repo, str) else ""
        return (repo.split("/")[0] if repo else "skills.sh"), f"skills.sh {repo or '?'}"
    md = os.path.join(path, "SKILL.md")
    if name == "gstack" or os.path.exists(os.path.join(path, ".gstack-owned")) or (
            os.path.islink(md) and "/gstack/" in os.path.realpath(md)):
        return "gstack", "gstack"
    return "You", "your own skill"


def scan_skills():
    items = []
    lock = obj(read_json(SKILLS_LOCK, {}).get("skills"))
    if not os.path.isdir(SKILLS_DIR):
        return items
    for name in sorted(os.listdir(SKILLS_DIR)):
        path = os.path.join(SKILLS_DIR, name)
        if name == "synced":
            items += scan_claude_ai(path)
            continue
        md = os.path.join(path, "SKILL.md")
        if name.startswith(".") or not os.path.isdir(path) or not os.path.exists(md):
            continue
        author, source = standalone_source(name, path, lock)
        items.append(skill_item("/" + name, os.path.realpath(md), author, source))
    return items


def scan_claude_ai(root):
    """claude.ai skills that Claude Code syncs to disk, one bucket per account, under skills/synced/."""
    items = []
    for manifest in sorted(glob.glob(os.path.join(root, "*", "manifest.json"))):
        bucket = os.path.dirname(manifest)
        for sk in lst(read_json(manifest, {}).get("skills")):
            if not isinstance(sk, dict) or not isinstance(sk.get("name"), str) or not sk["name"]:
                continue
            md = os.path.join(bucket, sk["name"], "SKILL.md")
            if os.path.exists(md):
                author = CLAUDE_AI_SOURCES.get(sk.get("source"), "claude.ai")
                items.append(skill_item("/anthropic-skills:" + sk["name"], md, author, "claude.ai"))
    return items


def list_projects():
    """Projects Claude Code has been opened in, from ~/.claude.json, as {path: short unique label}."""
    config = read_json(CLAUDE_JSON, {})
    paths = {p for p in obj(config.get("projects")) if isinstance(p, str)}
    for entries in installed_plugins().values():
        for e in entries:
            if isinstance(e.get("projectPath"), str):
                paths.add(e["projectPath"])
    keep = []
    for path in paths:
        path = path.rstrip("/") or "/"
        if not os.path.isdir(path) or os.path.realpath(path) == os.path.realpath(HOME):
            continue
        if f"{os.sep}.claude{os.sep}worktrees{os.sep}" in path:
            continue
        keep.append(path)
    return unique_labels(sorted(set(keep)))


def unique_labels(paths):
    """Each path's last folder name, with parent folders added until no two labels are the same."""
    depth = {p: 1 for p in paths}
    while True:
        labels = {p: "/".join(p.rstrip("/").split("/")[-depth[p]:]) for p in paths}
        seen = {}
        for p, label in labels.items():
            seen.setdefault(label, []).append(p)
        clashes = [g for g in seen.values() if len(g) > 1]
        if not clashes:
            return labels
        grew = False
        for group in clashes:
            for p in group:
                if depth[p] < len(p.strip("/").split("/")):
                    depth[p] += 1
                    grew = True
        if not grew:
            return {p: p for p in paths}


def installed_plugins():
    """installed_plugins.json as {"name@marketplace": [install entries]}, keeping only well-formed entries."""
    data = read_json(PLUGINS_FILE, {})
    data = obj(data.get("plugins", data))
    out = {}
    for key, entries in data.items():
        entries = [e for e in (entries if isinstance(entries, list) else [entries]) if isinstance(e, dict)]
        if isinstance(key, str) and entries:
            out[key] = entries
    return out


def project_plugin_flags(path):
    """enabledPlugins from the project's shared and local settings; local wins."""
    flags = {}
    for name in ("settings.json", "settings.local.json"):
        flags.update(obj(read_json(os.path.join(path, ".claude", name), {}).get("enabledPlugins")))
    return flags


def plugin_mcp_names(root, manifest):
    """MCP servers a plugin declares: .mcp.json, or mcpServers in plugin.json (inline, a path, or a list)."""
    names = []

    def add(value):
        if isinstance(value, dict):
            servers = value.get("mcpServers", value) if "mcpServers" in value else value
            names.extend(k for k in obj(servers) if isinstance(k, str))
        elif isinstance(value, str):
            add(read_json(os.path.normpath(os.path.join(root, value)), {}))
            return
        elif isinstance(value, list):
            for v in value:
                add(v)

    add(read_json(os.path.join(root, ".mcp.json"), {}))
    add(manifest.get("mcpServers"))
    return sorted(set(names))


def scan_plugins(projects):
    plugins, agents, servers = [], [], []
    user_enabled = obj(read_json(SETTINGS_FILE, {}).get("enabledPlugins"))
    flags = {label: project_plugin_flags(path) for path, label in projects.items()}
    for key, entries in sorted(installed_plugins().items()):
        name, _, market = key.partition("@")
        on_in = sorted(label for label, f in flags.items() if f.get(key) is True)
        off_in = sorted(label for label, f in flags.items() if f.get(key) is False)
        if user_enabled.get(key) is True:
            status, on_in = "everywhere", []
        elif on_in:
            status = "projects"
        else:
            status = "off"
        where = {"status": status, "projects": on_in, "disabled_in": off_in if status == "everywhere" else []}
        usable = [e for e in entries if isinstance(e.get("installPath"), str) and os.path.isdir(e["installPath"])]
        usable.sort(key=lambda e: (e.get("scope") == "user", str(e.get("lastUpdated", ""))), reverse=True)
        root = usable[0]["installPath"] if usable else ""
        manifest = read_json(os.path.join(root, ".claude-plugin", "plugin.json"), None) or \
            read_json(os.path.join(root, "plugin.json"), {})
        author = manifest.get("author")
        author = author.get("name") if isinstance(author, dict) else author
        author = author if isinstance(author, str) and author.strip() else (market or "Unknown")
        subs = []
        for f in sorted(glob.glob(os.path.join(root, "commands", "**", "*.md"), recursive=True)):
            head, body = read_md(f)
            cmd = f"/{name}:{os.path.splitext(os.path.basename(f))[0]}"
            hint = field(head, "argument-hint")
            desc = description(head, body)
            subs.append({"cmd": f"{cmd} {hint}" if hint else cmd, "note": first_sentence(desc, 140),
                         "tokens": tokens(desc), "type": "command", "visibility": frontmatter_visibility(head)})
        for f in sorted(glob.glob(os.path.join(root, "skills", "*", "SKILL.md"))):
            head, body = read_md(f)
            cmd = f"/{name}:{field(head, 'name') or os.path.basename(os.path.dirname(f))}"
            hint = field(head, "argument-hint")
            desc = description(head, body)
            subs.append({"cmd": f"{cmd} {hint}" if hint else cmd, "note": first_sentence(desc, 140),
                         "tokens": tokens(desc), "type": "skill", "full": desc,
                         "visibility": frontmatter_visibility(head)})
        for f in sorted(glob.glob(os.path.join(root, "agents", "*.md"))):
            head, body = read_md(f)
            aname = field(head, "name") or os.path.splitext(os.path.basename(f))[0]
            long = description(head, body)
            agents.append({"id": f"agent:{name}:{aname}", "kind": "agent", "name": f"{name}:{aname}",
                           "cmd": f"{name}:{aname}", "author": author, "source": "plugin " + name,
                           "desc": first_sentence(long), "long": long, "tokens": tokens(long), **where})
        for server in plugin_mcp_names(root, manifest):
            servers.append({"id": f"mcp:plugin:{name}:{server}", "kind": "mcp", "name": server, "cmd": server,
                            "author": author, "source": "plugin " + name, "plugin": name,
                            "desc": f"Provided by the {name} plugin", **where})
        plugins.append({
            "id": "plugin:" + name, "kind": "plugin", "name": name, "cmd": f"{name}@{market}",
            "author": author, "source": "plugin " + name, "market": market, **where,
            "version": text_of(manifest.get("version")),
            "desc": first_sentence(text_of(manifest.get("description"))), "long": text_of(manifest.get("description")),
            "subs": subs, "tokens": sum(s["tokens"] for s in subs),
        })
    return plugins, agents, servers


def scan_mcp(projects):
    """MCP servers from ~/.claude.json (global and per project) and from each project's .mcp.json."""
    config = read_json(CLAUDE_JSON, {})
    found = {}
    for name in obj(config.get("mcpServers")):
        found.setdefault(name, set()).add(None)
    by_path = {os.path.realpath(p): label for p, label in projects.items()}
    for path, conf in obj(config.get("projects")).items():
        label = by_path.get(os.path.realpath(path.rstrip("/") or "/"))
        for name in obj(obj(conf).get("mcpServers")):
            if label:
                found.setdefault(name, set()).add(label)
    for path, label in projects.items():
        shared = read_json(os.path.join(path, ".mcp.json"), {})
        for name in obj(shared.get("mcpServers", shared)):
            found.setdefault(name, set()).add(label)
    items = []
    for name, scopes in sorted(found.items(), key=lambda kv: kv[0].lower()):
        everywhere = None in scopes
        labels = sorted(s for s in scopes if s)
        if not everywhere and not labels:
            continue
        items.append({"id": "mcp:" + name, "kind": "mcp", "name": name, "cmd": name,
                      "author": "Unknown", "source": "MCP config",
                      "status": "everywhere" if everywhere else "projects",
                      "projects": [] if everywhere else labels,
                      "desc": "Global" if everywhere else "Only in " + ", ".join(labels)})
    for name in lst(config.get("claudeAiMcpEverConnected")):
        if isinstance(name, str):
            items.append({"id": "mcp:" + name, "kind": "mcp", "name": name, "cmd": name,
                          "author": "claude.ai", "source": "claude.ai connector", "status": "account",
                          "desc": "claude.ai connector, not tracked per project"})
    return items


def mcp_toggles(projects):
    """Per project: MCP servers turned off, and opt-in servers turned on, from ~/.claude.json."""
    config = read_json(CLAUDE_JSON, {})
    by_path = {os.path.realpath(p): label for p, label in projects.items()}
    off, on = {}, {}
    for path, conf in obj(config.get("projects")).items():
        label = by_path.get(os.path.realpath(path.rstrip("/") or "/"))
        conf = obj(conf)
        if not label:
            continue
        for name in lst(conf.get("disabledMcpServers")) + lst(conf.get("disabledMcpjsonServers")):
            if isinstance(name, str):
                off.setdefault(name, set()).add(label)
        for name in lst(conf.get("enabledMcpServers")) + lst(conf.get("enabledMcpjsonServers")):
            if isinstance(name, str):
                on.setdefault(name, set()).add(label)
    return off, on


def mcp_key(item):
    """The name Claude Code uses for a server in disabledMcpServers."""
    if item.get("plugin"):
        return f"plugin:{item['plugin']}:{item['name']}"
    return item["name"]


def norm(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def scan_commands(folder, author, source):
    """Custom slash commands: one Markdown file per command."""
    items = []
    for f in sorted(glob.glob(os.path.join(folder, "**", "*.md"), recursive=True)):
        cmd = "/" + os.path.splitext(os.path.basename(f))[0]
        items.append(skill_item(cmd, f, author, source))
    return items


def scan_project(path, label):
    """Skills, commands and agents kept in a project's own .claude folder."""
    base = os.path.join(path, ".claude")
    if not os.path.isdir(base) or os.path.realpath(base) == os.path.realpath(CLAUDE):
        return [], []
    source = "project " + label
    found = []
    for md in sorted(glob.glob(os.path.join(base, "skills", "*", "SKILL.md"))):
        found.append(skill_item("/" + os.path.basename(os.path.dirname(md)), md, "Project", source))
    found += scan_commands(os.path.join(base, "commands"), "Project", source)
    found += scan_agents(os.path.join(base, "agents"), "Project", source)
    for item in found:
        item["id"] = f"{label}:{item['id']}"
        item["status"], item["projects"] = "projects", [label]
    return [i for i in found if i["kind"] == "skill"], [i for i in found if i["kind"] == "agent"]


def scan_user_agents():
    return scan_agents(AGENTS_DIR, "You", "your own agent")


def scan_agents(folder, author, source):
    items = []
    for f in sorted(glob.glob(os.path.join(folder, "*.md"))):
        head, body = read_md(f)
        name = field(head, "name") or os.path.splitext(os.path.basename(f))[0]
        long = description(head, body)
        items.append({"id": "agent:" + name, "kind": "agent", "name": name, "cmd": name, "author": author,
                      "source": source, "status": "everywhere", "desc": first_sentence(long),
                      "long": long, "tokens": tokens(long)})
    return items


def from_session(session, known_skills, known_agents):
    """Built-in skills and agents: whatever the session lists that is not on disk."""
    items = []
    for sk in lst(session.get("skills")):
        sk = obj(sk)
        name = text_of(sk.get("name")).strip().lstrip("/")
        if not name or ":" in name or "/" + name in known_skills:
            continue
        long = text_of(sk.get("description"))
        items.append({"id": "/" + name, "kind": "skill", "name": name, "cmd": "/" + name,
                      "author": "Anthropic", "source": "built-in", "status": "everywhere",
                      "desc": first_sentence(long), "long": long, "tokens": tokens(long), "usage": []})
    for ag in lst(session.get("agents")):
        ag = obj(ag)
        name = text_of(ag.get("name")).strip()
        if not name or ":" in name or "agent:" + name in known_agents:
            continue
        long = text_of(ag.get("description"))
        items.append({"id": "agent:" + name, "kind": "agent", "name": name, "cmd": name,
                      "author": "Anthropic", "source": "built-in", "status": "everywhere",
                      "desc": first_sentence(long), "long": long, "tokens": tokens(long)})
    return items


def scan(session=None):
    """Every item, plus the projects as {path: label}."""
    projects = {os.path.realpath(p): label for p, label in list_projects().items()}
    skills = scan_skills() + scan_commands(COMMANDS_DIR, "You", "your own command")
    agents = scan_user_agents()
    for path, label in projects.items():
        project_skills, project_agents = scan_project(path, label)
        skills += project_skills
        agents += project_agents
    plugins, plugin_agents, plugin_mcp = scan_plugins(projects)
    mcp = scan_mcp(projects)
    mcp += plugin_mcp
    agents += plugin_agents
    here = projects.get(os.path.realpath(os.getcwd()))
    local = [i for i in skills + agents if i["status"] == "everywhere" or i.get("projects") == [here]]
    on_disk_skills = {i["cmd"] for i in local if i["kind"] == "skill"}
    on_disk_agents = {"agent:" + i["name"] for i in local + plugin_agents if i["kind"] == "agent"}
    builtins = from_session(obj(session), on_disk_skills, on_disk_agents)
    off, on = mcp_toggles(projects)
    known_mcp = {norm(m["name"]) for m in mcp} | {norm(f"plugin_{m['plugin']}_{m['name']}") for m in mcp if m.get("plugin")}
    for name in [n for n in lst(obj(session).get("mcp")) if isinstance(n, str) and n.strip()]:
        if norm(name) in known_mcp or norm(name).startswith("plugin_") or norm(name).startswith("claude_ai_"):
            continue
        opt_in = sorted(on.get(name, []))
        mcp.append({"id": "mcp:" + name, "kind": "mcp", "name": name, "cmd": name, "author": "Anthropic",
                    "source": "built-in", "status": "projects" if opt_in else "everywhere", "projects": opt_in,
                    "desc": ("Built in, turned on in " + ", ".join(opt_in)) if opt_in else "Built in"})
        known_mcp.add(norm(name))
    for m in mcp:
        turned_off = set(off.get(mcp_key(m), []))
        if turned_off:
            m["disabled_in"] = sorted(turned_off | set(m.get("disabled_in", [])))
    items = skills + [b for b in builtins if b["kind"] == "skill"] + plugins + mcp + agents + \
        [b for b in builtins if b["kind"] == "agent"]
    annotate_skills(items, projects)
    for i in items:
        i.setdefault("projects", [])
        i.setdefault("disabled_in", [])
    return items, projects


VISIBILITY = {"user-invocable-only": "user", "off": "off", "on": "model"}


def annotate_skills(items, projects):
    """Visibility from skillOverrides and use counts from skillUsage, on skills and plugin sub-skills."""
    overrides = obj(read_json(SETTINGS_FILE, {}).get("skillOverrides"))
    usage = obj(read_json(CLAUDE_JSON, {}).get("skillUsage"))

    def lookup(cmd, default="model"):
        key = cmd.split(" ")[0].lstrip("/")
        used = obj(usage.get(key))
        count = used.get("usageCount")
        stamp = used.get("lastUsedAt")
        count = count if isinstance(count, int) and count > 0 else 0
        stamp = stamp if isinstance(stamp, (int, float)) and stamp > 0 else None
        return VISIBILITY.get(overrides.get(key), default), count, stamp

    for i in items:
        if i["kind"] == "skill":
            i["visibility"], i["uses"], i["last_used"] = lookup(i["cmd"], i.get("visibility", "model"))
        elif i["kind"] == "plugin":
            for sub in i.get("subs", []):
                sub["visibility"], sub["uses"], sub["last_used"] = lookup(sub["cmd"], sub.get("visibility", "model"))
            subs = i.get("subs", [])
            i["uses"] = sum(sub["uses"] for sub in subs)
            stamps = [sub["last_used"] for sub in subs if sub["last_used"]]
            i["last_used"] = max(stamps) if stamps else None
            i["tokens"] = sum(sub["tokens"] for sub in subs if sub["visibility"] == "model")


def usage_since():
    """Earliest use Claude Code recorded, so "never used" can say since when it has been counting."""
    usage = obj(read_json(CLAUDE_JSON, {}).get("skillUsage"))
    stamps = [obj(u).get("lastUsedAt") for u in usage.values()]
    stamps = [t for t in stamps if isinstance(t, (int, float)) and t > 0]
    return min(stamps) if stamps else None
