"""Find skills that load more than once, name clashes, overlapping tools, unused skills and the heaviest sources."""

STATUS_LABEL = {"everywhere": "loaded everywhere", "projects": "some projects", "off": "installed, turned off",
                "account": "claude.ai connector"}
VISIBILITY_LABEL = {"user": "you only (hidden from Claude)", "off": "turned off"}


def plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def skill_entries(items):
    """One entry per skill or command Claude Code can list, including the ones inside plugins."""
    out = []
    for i in items:
        if i["kind"] == "skill":
            visible = i.get("visibility", "model") == "model"
            out.append({"base": i["cmd"].split(":")[-1].lstrip("/"), "cmd": i["cmd"], "source": i["source"],
                        "status": i["status"], "projects": i.get("projects", []),
                        "visibility": i.get("visibility", "model"), "desc": i.get("long") or i["desc"],
                        "tokens": i.get("tokens", 0) if visible else 0, "uses": i.get("uses", 0)})
        elif i["kind"] == "plugin":
            for s in i.get("subs", []):
                cmd = s["cmd"].split(" ")[0]
                visible = s.get("visibility", "model") == "model"
                out.append({"base": cmd.split(":")[-1], "cmd": cmd, "source": i["source"], "status": i["status"],
                            "projects": i.get("projects", []), "visibility": s.get("visibility", "model"),
                            "desc": s.get("full") or s.get("note", ""), "tokens": s["tokens"] if visible else 0,
                            "uses": s.get("uses", 0)})
    return out


def contexts(e):
    """Where an entry loads: "*" for every session, else the projects it loads in."""
    if e["status"] == "everywhere":
        return {"*"}
    if e["status"] == "projects":
        return set(e["projects"])
    return set()


def collide(a, b):
    ca, cb = contexts(a), contexts(b)
    return bool(ca and cb) and ("*" in ca or "*" in cb or bool(ca & cb))


def loading_together(group):
    """The copies in a group that can load in the same session as a copy from another source."""
    return [e for e in group if any(o is not e and o["source"] != e["source"] and collide(e, o) for o in group)]


def extra_tokens(copies):
    visible = [c["tokens"] for c in copies if c["visibility"] == "model"]
    return sum(visible) - max(visible) if len(visible) > 1 else 0


def plugin_of(source):
    return source[len("plugin "):] if source.startswith("plugin ") else None


def advice(sources, group_cmds, items):
    """Plain-language next step for one bundle of identical skills."""
    if "gstack alias" in sources:
        return "Aliases that gstack setup writes on purpose. gstack recreates them on every upgrade, so leave them."
    plugins = {i["name"]: i for i in items if i["kind"] == "plugin"}
    names = [plugin_of(s) for s in sources if plugin_of(s) in plugins]
    if not names:
        if any(s.startswith("project ") for s in sources):
            return ("A project keeps its own copy of a skill you also have everywhere, so in that project it "
                    "loads twice. Keep one of the two.")
        return "The same skill from two places that load together. Keep the copy you update, remove the other."
    target = min(names, key=lambda n: len(plugins[n].get("subs", [])))
    subs = [s["cmd"].split(" ")[0] for s in plugins[target].get("subs", [])]
    rest = [c for c in subs if c not in group_cmds]
    agents = sum(1 for i in items if i["kind"] == "agent" and i["source"] == "plugin " + target)
    servers = sum(1 for i in items if i["kind"] == "mcp" and i["source"] == "plugin " + target)
    if not rest and not agents and not servers:
        return f"Everything in the {target} plugin exists elsewhere: uninstall it with /plugin."
    kept = []
    if rest:
        shown = ", ".join(c.split(":")[-1] for c in rest[:6]) + ("…" if len(rest) > 6 else "")
        kept.append(plural(len(rest), "other skill or command", "other skills and commands") + f" ({shown})")
    if agents:
        kept.append(plural(agents, "agent", "agents"))
    if servers:
        kept.append(plural(servers, "MCP server", "MCP servers"))
    listed = kept[0] if len(kept) == 1 else ", ".join(kept[:-1]) + " and " + kept[-1]
    return f"Uninstall the {target} plugin with /plugin, unless you use its {listed}."


def build(items, curation, defaults, has_usage=True):
    entries = skill_entries(items)
    notes = curation.get("notes", {})

    by_desc = {}
    for e in entries:
        if len(e["desc"]) > 40:
            by_desc.setdefault(" ".join(e["desc"].lower().split()), []).append(e)

    duplicated, bundles = set(), {}
    for group in by_desc.values():
        group = loading_together(group)
        if len({e["source"] for e in group}) < 2:
            continue
        duplicated.update(e["cmd"] for e in group)
        sources = sorted({e["source"] for e in group})
        key = "|".join(sources)
        b = bundles.setdefault(key, {"key": key, "sources": sources, "skills": []})
        everywhere = [e for e in group if e["status"] == "everywhere"]
        b["skills"].append({
            "copies": [{"cmd": e["cmd"], "source": e["source"], "status": e["status"],
                        "visibility": e["visibility"]} for e in group],
            "extra_tokens": extra_tokens(group),
            "extra_everywhere": extra_tokens(everywhere),
        })
    for b in bundles.values():
        cmds = {c["cmd"] for s in b["skills"] for c in s["copies"]}
        b["note"] = notes.get(b["key"]) or advice(b["sources"], cmds, items)
    identical = sorted(bundles.values(), key=lambda b: -sum(s["extra_tokens"] for s in b["skills"]))

    by_name = {}
    for e in entries:
        by_name.setdefault(e["base"], []).append(e)
    same_name = []
    for name, group in sorted(by_name.items()):
        group = loading_together(group)
        if len({e["source"] for e in group}) > 1 and not all(e["cmd"] in duplicated for e in group):
            same_name.append({"name": name, "copies": [
                {"cmd": e["cmd"], "source": e["source"], "status": e["status"], "visibility": e["visibility"],
                 "desc": e["desc"][:160]} for e in group]})

    present = {i["cmd"].split(" ")[0] for i in items} | {e["cmd"] for e in entries}
    overlaps = []
    for o in defaults.get("overlaps", []) + curation.get("overlaps", []):
        members = [m for m in o.get("members", []) if m in present]
        if len(members) >= 2:
            overlaps.append({**o, "members": members})

    weight = {}

    def bucket(source, status):
        return weight.setdefault(source, {"source": source, "status": status, "skills": 0, "agents": 0, "tokens": 0})

    for e in entries:
        w = bucket(e["source"], e["status"])
        w["skills"] += 1
        w["tokens"] += e["tokens"]
    for i in items:
        if i["kind"] == "agent":
            w = bucket(i["source"], i["status"])
            w["agents"] += 1
            w["tokens"] += i.get("tokens", 0)
    order = {"everywhere": 0, "projects": 1, "off": 2}
    by_source = sorted(weight.values(), key=lambda w: (order.get(w["status"], 3), -w["tokens"]))

    loaded = [e for e in entries if e["status"] == "everywhere" and e["visibility"] == "model"]
    never, idle_plugins = [], []
    if has_usage:
        never = sorted((e for e in loaded if not e["uses"] and not e["source"].startswith("plugin ")),
                       key=lambda e: -e["tokens"])
        for i in items:
            if i["kind"] == "plugin" and i["status"] == "everywhere" and i.get("subs") and not i.get("uses"):
                idle_plugins.append({"cmd": i["cmd"], "skills": len(i["subs"]), "tokens": i.get("tokens", 0)})
    return {
        "identical": identical,
        "same_name": same_name,
        "overlaps": overlaps,
        "by_source": by_source,
        "never_used": [{"cmd": e["cmd"], "source": e["source"], "tokens": e["tokens"]} for e in never],
        "idle_plugins": sorted(idle_plugins, key=lambda p: -p["tokens"]),
        "has_usage": has_usage,
        "hidden": sum(1 for e in entries if e["visibility"] != "model"),
        "listed": len(loaded),
        "listed_tokens": sum(e["tokens"] for e in loaded),
        "duplicate_tokens": sum(s["extra_everywhere"] for b in identical for s in b["skills"]),
        "status_label": STATUS_LABEL,
        "visibility_label": VISIBILITY_LABEL,
    }
