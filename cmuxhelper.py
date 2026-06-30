#!/usr/bin/env python3
"""cmux-helper: Alfred workflow backend for SSH host selection via cmux."""

import os


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
