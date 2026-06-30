#!/usr/bin/env python3
"""cmux-helper: Alfred workflow backend for SSH host selection via cmux."""

import json
import os
import subprocess
import sys


DEFAULT_SAVED_HOSTS = "~/.ssh/saved_hosts"
DEFAULT_SSH_CONFIG = "~/.ssh/config"


def _read(path):
    """Read a file at path (expanding ~), return empty string on OSError."""
    try:
        with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def parse_saved_hosts(text):
    """Parse ~/.ssh/saved_hosts content into a list of `user@host` strings."""
    hosts = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        hosts.append(line)
    return hosts


def parse_ssh_config(text):
    """Parse ~/.ssh/config Host entries into `user@host` (or bare host) strings."""
    hosts = []
    patterns = []
    user = None

    def flush():
        for pat in patterns:
            if "*" in pat or "?" in pat:
                continue
            hosts.append("%s@%s" % (user, pat) if user else pat)

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        key = parts[0].lower()
        value = parts[1].strip() if len(parts) > 1 else ""
        if key == "host":
            flush()
            patterns = value.split()
            user = None
        elif key == "user" and patterns:
            user = value
    flush()
    return hosts


def collect_hosts(saved_hosts_path=DEFAULT_SAVED_HOSTS, ssh_config_path=DEFAULT_SSH_CONFIG):
    """Read both sources, merge with saved_hosts first, dedup preserving order."""
    merged = parse_saved_hosts(_read(saved_hosts_path)) + parse_ssh_config(_read(ssh_config_path))
    hosts = []
    seen = set()
    for host in merged:
        if host not in seen:
            seen.add(host)
            hosts.append(host)
    return hosts


def load_aliases(path):
    """Load aliases from JSON file. Return {} on missing/corrupt/non-dict."""
    try:
        with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_aliases(path, data):
    """Save aliases to JSON file. Auto-create parent dir, ensure_ascii=False, indent=2."""
    full = os.path.expanduser(path)
    parent = os.path.dirname(full)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def apply_alias(data, host, alias, tags):
    """Apply alias to host. Strip whitespace, remove empty tags, delete if both empty."""
    result = dict(data)
    alias = alias.strip()
    tags = [t.strip() for t in tags if t.strip()]
    if not alias and not tags:
        result.pop(host, None)
        return result
    entry = {}
    if alias:
        entry["alias"] = alias
    if tags:
        entry["tags"] = tags
    result[host] = entry
    return result


def build_alfred_items(hosts, aliases):
    """Build Alfred Script Filter items from hosts and aliases.

    Returns {"items": [...]}, where each item has:
    - uid, arg = host
    - title = "alias  ·  host" if alias exists, else host
    - subtitle = "↵ ssh   ⌘ send   ⌥ 设别名" + optional "  #tag1 #tag2"
    - match = space-separated host, alias (if any), and tags
    - autocomplete = alias or host
    - mods = cmd and alt with custom subtitles and arg
    """
    items = []
    for host in hosts:
        meta = aliases.get(host, {})
        alias = meta.get("alias", "")
        tags = meta.get("tags", [])
        title = "%s  ·  %s" % (alias, host) if alias else host
        subtitle = "↵ ssh   ⌘ send   ⌥ 设别名"
        if tags:
            subtitle += "  " + " ".join("#" + t for t in tags)
        match = " ".join([host] + ([alias] if alias else []) + list(tags))
        items.append({
            "uid": host,
            "title": title,
            "subtitle": subtitle,
            "arg": host,
            "match": match,
            "autocomplete": alias or host,
            "mods": {
                "cmd": {"subtitle": "cmux send: ssh %s" % host, "arg": host},
                "alt": {"subtitle": "设置别名/标签: %s" % host, "arg": host},
            },
        })
    return {"items": items}


def cmd_ssh(dest):
    # Activate cmux first so the app is frontmost before `cmux ssh` runs,
    # which is noticeably snappier than the reverse order.
    return [["open", "-a", "cmux"], ["cmux", "ssh", dest]]


def cmd_send(dest, workspace):
    return [
        ["open", "-a", "cmux"],
        ["cmux", "send", "--workspace", workspace, "ssh %s\\n" % dest],
    ]


def aliases_path():
    # Keep aliases alongside saved_hosts/config so users can hand-edit them.
    return os.path.expanduser("~/.ssh/aliases.json")


def _notify(message):
    """Best-effort macOS notification; never raises."""
    try:
        subprocess.run(
            ["osascript", "-e",
             "display notification %s with title \"cmux-helper\"" % _as_applescript(message)],
            check=False,
        )
    except OSError:
        pass


def _run(commands):
    for cmd in commands:
        try:
            subprocess.run(cmd, check=False)
        except FileNotFoundError:
            _notify("找不到命令：%s" % cmd[0])
            return


def _current_workspace():
    try:
        out = subprocess.run(
            ["cmux", "current-workspace"], capture_output=True, text=True, check=False
        ).stdout.strip()
    except OSError:
        out = ""
    return out or "workspace:1"


def _as_applescript(text):
    """Quote a string as an AppleScript string literal, keeping Unicode literal.

    json.dumps with ensure_ascii=True emits \\uXXXX escapes that AppleScript
    cannot parse; ensure_ascii=False keeps the UTF-8 characters and still
    escapes the quote and backslash, which is what AppleScript expects.
    """
    return json.dumps(text, ensure_ascii=False)


def _prompt(prompt_text, default):
    """Show a macOS text dialog; return entered text, or None if cancelled."""
    script = (
        'set r to text returned of (display dialog %s default answer %s '
        'buttons {"取消", "确定"} cancel button "取消" default button "确定")\nreturn r'
        % (_as_applescript(prompt_text), _as_applescript(default))
    )
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.rstrip("\n")


def _do_alias(host):
    path = aliases_path()
    data = load_aliases(path)
    current = data.get(host, {})
    alias = _prompt("别名 (留空清除) — %s" % host, current.get("alias", ""))
    if alias is None:
        return
    tags_raw = _prompt("标签，逗号分隔 — %s" % host, ", ".join(current.get("tags", [])))
    if tags_raw is None:
        return
    tags = tags_raw.split(",")
    save_aliases(path, apply_alias(data, host, alias, tags))


def filter_items(items, query):
    """Keep items whose match text contains every whitespace-separated token.

    Case-insensitive substring matching so a host, IP fragment, alias, or tag
    all filter the list. An empty/blank query returns every item unchanged.
    """
    tokens = query.lower().split()
    if not tokens:
        return items
    return [i for i in items if all(t in i.get("match", "").lower() for t in tokens)]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv else "filter"
    if command == "filter":
        query = argv[1] if len(argv) > 1 else ""
        items = build_alfred_items(collect_hosts(), load_aliases(aliases_path()))["items"]
        print(json.dumps({"items": filter_items(items, query)}, ensure_ascii=False))
        return 0
    dest = argv[1] if len(argv) > 1 else ""
    if command == "connect":
        _run(cmd_ssh(dest))
    elif command == "send":
        _run(cmd_send(dest, _current_workspace()))
    elif command == "alias":
        _do_alias(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
