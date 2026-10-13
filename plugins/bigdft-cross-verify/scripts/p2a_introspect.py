# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.2,<2", "jsonschema>=4.21"]
# ///
"""Build agent-manifest.json from a P2A output: its paper skill and (optionally) its MCP server.

  p2a_introspect.py --paper-skill DIR [--mcp-json FILE [--server NAME]] [--env KEY=VALUE ...]
                    [--usage USAGE.md] --out agent-manifest.json

--mcp-json is a Claude-style config ({"mcpServers": {name: {command, args, env}}}), e.g. a plugin's .mcp.json.
The server is launched over stdio and asked for list_tools. --env values are passed to the server but only
their names are recorded; the config file path is kept so env values can be re-read at launch.
Deterministic: no LLM involved.
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import jsonschema
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
DOI = re.compile(r"\b10\.\d{4,9}/[^\s)<>\]\"',;]+", re.I)
DATA_HOSTS = re.compile(r"https?://[^\s)<>\]\"']*(materialscloud|zenodo|figshare|nomad-lab|osf\.io|github\.com)[^\s)<>\]\"']*", re.I)


def tree_sha(d: Path) -> str:
    entries = [[str(p.relative_to(d).as_posix()), hashlib.sha256(p.read_bytes()).hexdigest()]
               for p in sorted(d.rglob("*")) if p.is_file()]
    return hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest()


def paper_info(skill: Path):
    paper = (skill / "references" / "paper.md").read_text()
    head = paper[:6000]
    m = DOI.search(head)
    title = next((l[2:].strip().rstrip("†*").strip() for l in paper.splitlines() if l.startswith("# ")), None)
    return {"doi": m[0].rstrip(".").upper() if m else None, "title": title,
            "detected_from": "references/paper.md (first DOI in the front matter, first H1)"}


def image_only(skill: Path):
    out = []
    for p in sorted((skill / "references").glob("*.md")):
        notes = p.read_text().split("## Conversion notes", 1)
        if len(notes) == 2:
            out += [f"{p.name}: {l.strip('- ').strip()}" for l in notes[1].splitlines()
                    if l.strip().startswith("-") and re.search(r"image", l, re.I)]
    return out


async def list_tools(command, args, env):
    params = StdioServerParameters(command=command, args=args, env={**os.environ, **env})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.list_tools()
            return sorted(({"name": t.name, "description": t.description or "", "input_schema": t.inputSchema or {}}
                           for t in res.tools), key=lambda t: t["name"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--paper-skill", required=True)
    ap.add_argument("--mcp-json")
    ap.add_argument("--server")
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--usage")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    skill = Path(a.paper_skill).resolve()
    env = dict(e.split("=", 1) for e in a.env)
    mcp = None
    if a.mcp_json:
        servers = json.loads(Path(a.mcp_json).read_text())["mcpServers"]
        name = a.server or (next(iter(servers)) if len(servers) == 1 else None)
        if name is None:
            sys.exit(f"--server required; servers: {sorted(servers)}")
        cfg = servers[name]
        env = {**cfg.get("env", {}), **env}
        tools = asyncio.run(list_tools(cfg["command"], cfg.get("args", []), env))
        mcp = {"server": name, "launch": {"command": cfg["command"], "args": cfg.get("args", []), "env_names": sorted(env),
                                          "config_file": str(Path(a.mcp_json).resolve())},
               "tools": tools}
    texts = [(skill / "references" / "paper.md").read_text()] + ([Path(a.usage).read_text()] if a.usage else [])
    urls = sorted({m[0].rstrip(".") for t in texts for m in DATA_HOSTS.finditer(t)})
    manifest = {
        "manifest_version": 1,
        "paper": paper_info(skill),
        "paper_skill": {"path": str(skill), "sha256_tree": tree_sha(skill),
                        "tables": sorted(str(p.relative_to(skill)) for p in (skill / "assets").rglob("*.csv")),
                        "image_only_regions": image_only(skill)},
        "mcp": mcp,
        "data_resources": [{"kind": "url", "url": u} for u in urls],
        "p2a_mode": "combined" if mcp else "paper_only",
    }
    schema = json.loads((ROOT / "schemas" / "agent-manifest.schema.json").read_text())
    jsonschema.validate(manifest, schema)
    Path(a.out).write_text(json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps({"doi": manifest["paper"]["doi"], "tools": [t["name"] for t in (mcp or {}).get("tools", [])],
                      "out": a.out}))


if __name__ == "__main__":
    main()
