#!/usr/bin/env python3
"""setup-map: inventory a Claude Code setup and render it as a list, an HTML page or an Excalidraw board.

Usage:
  setup_map.py session < session.json   save what the current session lists (built-in skills and agents)
  setup_map.py list                     print every skill, plugin, MCP server and agent, grouped by author
  setup_map.py html [--out FILE] [--open]
  setup_map.py excalidraw [--out FILE]
  setup_map.py known                    skill and agent names already found on disk
  setup_map.py uncategorized            skills not yet placed in a topic (for the curation step)
  setup_map.py config [--artifact-url URL]

Everything is read from ~/.claude and ~/.claude.json. Files are written only to the data folder
(~/.claude/setup-map, or $SETUP_MAP_HOME) unless --out says otherwise. No network access.
"""
import argparse
import datetime
import json
import os
import sys
import textwrap
import webbrowser

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cleanup  # noqa: E402
import inventory  # noqa: E402

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
DATA_DIR = os.path.expanduser(os.environ.get("SETUP_MAP_HOME", "~/.claude/setup-map"))


def path(name):
    return os.path.join(DATA_DIR, name)


def load(name, default):
    return inventory.read_json(path(name), default)


def save(name, value):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path(name), "w") as f:
        json.dump(value, f, indent=1, ensure_ascii=False)


def clean_curation(raw):
    """curation.json with every part forced into the shape the renderers expect; bad parts are dropped."""
    obj, lst, text = inventory.obj, inventory.lst, inventory.text_of
    raw = obj(raw)
    topics = {t: [x for x in lst(ids) if isinstance(x, str)] for t, ids in obj(raw.get("topics")).items()}
    strings = {k: {i: v for i, v in obj(raw.get(k)).items() if isinstance(v, str) and v.strip()}
               for k in ("descriptions", "authors", "notes")}
    overlaps = [{"title": text(o.get("title")) or "Overlap", "note": text(o.get("note")),
                 "members": [m for m in lst(o.get("members")) if isinstance(m, str)]}
                for o in map(obj, lst(raw.get("overlaps")))]
    usage = {cmd: [{"cmd": u["cmd"], **({"note": u["note"]} if isinstance(u.get("note"), str) else {})}
                   for u in map(obj, lst(rows)) if isinstance(u.get("cmd"), str)]
             for cmd, rows in obj(raw.get("usage")).items()}
    return {"topics": topics, **strings, "overlaps": [o for o in overlaps if o["members"]], "usage": usage}


def collect():
    defaults = inventory.read_json(os.path.join(ASSETS, "defaults.json"), {})
    curation = clean_curation(load("curation.json", {}))
    items, projects = inventory.scan(load("session.json", {}))
    usage = {**defaults.get("usage", {}), **curation.get("usage", {})}
    for i in items:
        curated = curation.get("descriptions", {}).get(i["id"])
        if curated and i["kind"] == "mcp":
            i["long"] = curated
        elif curated:
            i["desc"] = curated
        i["author"] = curation.get("authors", {}).get(i["id"], i["author"])
        extra = usage.get(i["cmd"], [])
        if extra:
            known = {u["cmd"] for u in extra}
            i["usage"] = extra + [u for u in i.get("usage", []) if u["cmd"] not in known]
    forms = {}
    for i in items:
        spelled = forms.setdefault(i["author"].casefold(), {})
        spelled[i["author"]] = spelled.get(i["author"], 0) + 1
    preferred = {key: max(spelled, key=lambda a: (spelled[a], not a.islower(), not a.isupper(), a))
                 for key, spelled in forms.items()}
    for i in items:
        i["author"] = preferred[i["author"].casefold()]
    return items, curation, defaults, projects


def colors(items, defaults):
    fixed = defaults.get("fixed_colors", {})
    palette = defaults.get("palette", [])
    counts = {}
    for i in items:
        counts[i["author"]] = counts.get(i["author"], 0) + 1
    ranked = [a for a, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if a not in fixed]
    out = {a: c for a, c in fixed.items() if a in counts}
    for author, color in zip([a for a in ranked if a != "Unknown"], palette):
        out[author] = color
    return out


def sections(items, curation):
    by_id = {i["id"]: i for i in items}
    out, placed = [], set()
    for title, ids in curation.get("topics", {}).items():
        members = [by_id[x] for x in ids if x in by_id and by_id[x]["kind"] == "skill"]
        if members:
            out.append({"title": title, "kind": "skill", "items": members})
            placed.update(m["id"] for m in members)
    rest = [i for i in items if i["kind"] == "skill" and i["id"] not in placed]
    groups = {}
    for i in rest:
        if i["source"] == "built-in":
            title = "Built into Claude Code"
        elif i["source"] == "claude.ai":
            title = "claude.ai skills"
        elif i["source"].startswith("project "):
            title = f"Project skills · {i['source'][len('project '):]}"
        else:
            title = f"Skills · {i['author']}"
        groups.setdefault(title, []).append(i)
    for title, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        out.append({"title": title, "kind": "skill", "items": members})
    for status, title in (("everywhere", "Plugins · loaded everywhere"), ("projects", "Plugins · some projects only"),
                          ("off", "Plugins · installed, turned off")):
        members = [i for i in items if i["kind"] == "plugin" and i["status"] == status]
        if members:
            out.append({"title": title, "kind": "plugin", "items": members})
    for kind, title in (("mcp", "MCP servers"), ("agent", "Agents")):
        members = [i for i in items if i["kind"] == kind]
        if members:
            out.append({"title": title, "kind": kind, "items": members})
    return out


def project_list(items, projects):
    """One entry per project that changes what loads there, for the Projects view."""
    home = os.path.expanduser("~")
    out = []
    for path, label in sorted(projects.items(), key=lambda kv: kv[1].lower()):
        own = [i["id"] for i in items if label in i.get("projects", [])]
        off = [i["id"] for i in items if label in i.get("disabled_in", [])]
        if own or off:
            short = "~" + path[len(home):] if path.startswith(home) else path
            out.append({"name": label, "path": short, "items": own, "disabled": off})
    return out


def render_html(out_file, artifact=False):
    items, curation, defaults, projects = collect()
    payload = {
        "generated": datetime.date.today().isoformat(),
        "sections": sections(items, curation),
        "cleanup": cleanup.build(items, curation, defaults, has_usage=inventory.usage_since() is not None),
        "colors": colors(items, defaults),
        "projects": project_list(items, projects),
        "usage_since": inventory.usage_since(),
        "other": defaults.get("other_color", ["#e9ecf2", "#262c38"]),
    }
    blob = json.dumps(payload, ensure_ascii=False)
    blob = blob.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    with open(os.path.join(ASSETS, "template.html")) as f:
        html = f.read().replace("__DATA__", blob)
    if not artifact:
        html = ('<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n' + html)
    os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
    with open(out_file, "w") as f:
        f.write(html)
    return len(items), len(html)


def render_excalidraw(out_file):
    items, curation, defaults, _ = collect()
    secs = sections(items, curation)
    palette = colors(items, defaults)
    other = defaults.get("other_color", ["#e9ecf2"])[0]
    els, counter = [], [0]

    def base(kind, x, y, w, h, **extra):
        counter[0] += 1
        return {"id": f"el{counter[0]}", "type": kind, "x": x, "y": y, "width": w, "height": h,
                "angle": 0, "strokeColor": "#1e1e1e", "backgroundColor": "transparent", "fillStyle": "solid",
                "strokeWidth": 1, "strokeStyle": "solid", "roughness": 0, "opacity": 100, "groupIds": [],
                "frameId": None, "roundness": {"type": 3}, "seed": counter[0], "version": 1,
                "versionNonce": counter[0], "isDeleted": False, "boundElements": None, "updated": 1,
                "link": None, "locked": False, **extra}

    def rect(x, y, w, h, bg, stroke="#495057", sw=1):
        return base("rectangle", x, y, w, h, backgroundColor=bg, strokeColor=stroke, strokeWidth=sw)

    def text(x, y, s, size=16, color="#1e1e1e"):
        lines = s.split("\n")
        w = max(len(line) for line in lines) * size * 0.55
        return base("text", x, y, w, len(lines) * size * 1.25, text=s, fontSize=size, fontFamily=2,
                    textAlign="left", verticalAlign="top", containerId=None, originalText=s,
                    autoResize=True, lineHeight=1.25, strokeColor=color, roundness=None)

    card_w, card_h, gap, cols = 330, 92, 16, 5
    sec_w = cols * (card_w + gap) + gap
    x0, y = 40, 40
    els.append(text(x0, y, "MY CLAUDE CODE SETUP", 36)); y += 56
    els.append(text(x0, y, f"{len(items)} items · skills, plugins, MCP servers & agents · colour = author",
                    18, "#868e96")); y += 44
    lx = x0
    for label, color in [(a, c[0]) for a, c in palette.items()] + [("Other", other)]:
        els.append(rect(lx, y, 22, 22, color))
        els.append(text(lx + 30, y + 3, label, 14, "#343a40"))
        lx += 30 + len(label) * 9 + 40
        if lx > x0 + sec_w - 200:
            lx, y = x0, y + 34
    y += 56
    for sec in secs:
        rows = -(-len(sec["items"]) // cols)
        sec_h = 58 + rows * (card_h + gap) + gap
        els.append(rect(x0, y, sec_w, sec_h, "#ffffff", "#adb5bd", 2))
        els.append(text(x0 + 20, y + 16, f"{sec['title'].upper()}  ({len(sec['items'])})", 22, "#343a40"))
        for n, i in enumerate(sec["items"]):
            cx = x0 + gap + (n % cols) * (card_w + gap)
            cy = y + 58 + (n // cols) * (card_h + gap)
            els.append(rect(cx, cy, card_w, card_h, palette.get(i["author"], [other])[0]))
            els.append(text(cx + 12, cy + 8, i["cmd"][:38], 15))
            if i["desc"]:
                els.append(text(cx + 12, cy + 32, "\n".join(textwrap.wrap(i["desc"], 44)[:2]), 12, "#343a40"))
            els.append(text(cx + 12, cy + card_h - 20, i["author"], 10.5, "#66707a"))
        y += sec_h + 28
    doc = {"type": "excalidraw", "version": 2, "source": "https://excalidraw.com", "elements": els,
           "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20}, "files": {}}
    os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(doc, f)
    return len(items)


def print_list():
    items, _, _, _ = collect()
    groups = {}
    for i in items:
        groups.setdefault(i["author"], []).append(i)
    width = min(48, max(len(i["cmd"]) for i in items)) if items else 10
    for author, members in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0].lower())):
        print(f"\n## {author} ({len(members)})")
        for i in sorted(members, key=lambda m: (m["kind"], m["cmd"])):
            status = "" if i["status"] == "everywhere" else f"  [{i['status']}]"
            print(f"  {i['kind']:<6} {i['cmd']:<{width}}  {i['desc']}{status}")
    print(f"\n{len(items)} items")


def session_problem(data):
    """Why a session payload has the wrong shape, or None when it is fine."""
    if not isinstance(data, dict):
        return 'expected an object like {"skills": [...], "agents": [...], "mcp": [...]}'
    for key in ("skills", "agents"):
        rows = data.get(key, [])
        if not isinstance(rows, list):
            return f'"{key}" must be a list'
        for n, row in enumerate(rows):
            if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"].strip():
                return f'{key}[{n}] needs a "name" string'
            if not isinstance(row.get("description", ""), str):
                return f'{key}[{n}].description must be a string'
    mcp = data.get("mcp", [])
    if not isinstance(mcp, list) or not all(isinstance(m, str) for m in mcp):
        return '"mcp" must be a list of server names'
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("session", help="read the session's skill and agent list as JSON on stdin")
    sub.add_parser("list")
    h = sub.add_parser("html")
    h.add_argument("--out", default=path("setup-map.html"))
    h.add_argument("--open", action="store_true", help="open the page in the default browser")
    h.add_argument("--artifact", action="store_true", help="leave out the document head, for an Artifact publish")
    e = sub.add_parser("excalidraw")
    e.add_argument("--out", default=path("setup-map.excalidraw"))
    sub.add_parser("uncategorized")
    sub.add_parser("known", help="skill and agent names already found on disk")
    c = sub.add_parser("config")
    c.add_argument("--artifact-url")
    args = parser.parse_args()

    if args.command == "session":
        try:
            data = json.load(sys.stdin)
        except ValueError as err:
            sys.exit(f"session: the input is not valid JSON ({err}). Nothing was saved.")
        problem = session_problem(data)
        if problem:
            sys.exit(f"session: {problem}. Nothing was saved.")
        save("session.json", {"skills": data.get("skills", []), "agents": data.get("agents", []),
                              "mcp": data.get("mcp", []),
                              "saved": datetime.datetime.now().isoformat(timespec="seconds")})
        print(f"saved {len(data.get('skills', []))} skills, {len(data.get('agents', []))} agents and "
              f"{len(data.get('mcp', []))} MCP servers to {path('session.json')}")
    elif args.command == "list":
        print_list()
    elif args.command == "html":
        count, size = render_html(args.out, args.artifact)
        print(f"wrote {args.out}: {count} items, {size // 1024} KB")
        if args.open:
            webbrowser.open("file://" + os.path.abspath(args.out))
    elif args.command == "excalidraw":
        print(f"wrote {args.out}: {render_excalidraw(args.out)} items")
    elif args.command == "known":
        items, projects = inventory.scan({})
        here = projects.get(os.path.realpath(os.getcwd()))
        items = [i for i in items if i["status"] == "everywhere" or i.get("projects") == [here]]
        print("skills: " + ", ".join(sorted(i["name"] for i in items if i["kind"] == "skill" and ":" not in i["name"])))
        print("agents: " + ", ".join(sorted(i["name"] for i in items if i["kind"] == "agent")))
    elif args.command == "uncategorized":
        items, curation, _, _ = collect()
        placed = {x for ids in curation.get("topics", {}).values() for x in ids}
        topics = list(curation.get("topics", {}))
        rest = [i for i in items if i["kind"] == "skill" and i["id"] not in placed]
        print(json.dumps({"topics": topics, "uncategorized": [
            {"id": i["id"], "author": i["author"], "desc": i["desc"]} for i in rest]}, indent=1, ensure_ascii=False))
    elif args.command == "config":
        config = load("config.json", {})
        if args.artifact_url:
            config["artifact_url"] = args.artifact_url
            save("config.json", config)
        print(json.dumps({**config, "data_dir": DATA_DIR}, indent=1))


if __name__ == "__main__":
    main()
