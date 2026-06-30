# cmux-helper SSH Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Alfred workflow，通过关键词 `ssh` 选择预设 SSH 主机，经 `cmux` 连接，并支持别名/标签。

**Architecture:** 纯 Python 标准库单文件 `cmuxhelper.py` 提供 `filter/connect/send/alias` 四个子命令；纯逻辑（解析主机、合并、别名、生成 Alfred JSON）与副作用（subprocess 调 `cmux`/`open`/`osascript`）分离，纯逻辑用 `unittest` 测试。Alfred `info.plist` 定义一个 Script Filter 经修饰键连到三个 Run Script 动作。

**Tech Stack:** Python 3（`/opt/homebrew/bin/python3`，纯标准库）、unittest、Alfred 5 workflow plist、cmux CLI。

## Global Constraints

- 仅用 Python 标准库，**零第三方依赖**（含测试，用 `unittest`）。
- 可执行脚本 shebang：`#!/usr/bin/env python3`；运行/测试一律用 `/opt/homebrew/bin/python3`。
- 模糊匹配交给 Alfred（Script Filter 开启 `alfredfiltersresults`），Python 不实现匹配。
- 主机来源：`~/.ssh/saved_hosts` + `~/.ssh/config` 的 `Host`，合并去重（保持顺序，saved_hosts 优先）。
- 别名文件路径：`$alfred_workflow_data/aliases.json`，无该环境变量时回退 `~/.cmux-helper/aliases.json`。
- 前台激活统一用 `open -a cmux`（已验证 `cmux focus-window` 不激活 macOS 应用）。
- 所有中文字符串输出用 `ensure_ascii=False`。
- Alfred 修饰键位掩码：cmd=1048576，alt=524288。

---

### Task 1: 项目骨架 + 解析 saved_hosts

**Files:**
- Create: `cmuxhelper.py`
- Test: `tests/test_cmuxhelper.py`

**Interfaces:**
- Produces: `parse_saved_hosts(text: str) -> list[str]` —— 逐行返回 `user@host`，忽略空行与 `#` 开头行，两端去空白。

- [ ] **Step 1: 写失败测试**

`tests/test_cmuxhelper.py`：
```python
import unittest
import cmuxhelper


class ParseSavedHostsTests(unittest.TestCase):
    def test_skips_blank_and_comment_lines(self):
        text = "app@10.1.2.34\n\n# a comment\n  dev@10.1.2.32  \n"
        self.assertEqual(
            cmuxhelper.parse_saved_hosts(text),
            ["app@10.1.2.34", "dev@10.1.2.32"],
        )

    def test_empty_input(self):
        self.assertEqual(cmuxhelper.parse_saved_hosts(""), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `/opt/homebrew/bin/python3 -m unittest discover -s tests -t . -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'cmuxhelper'`（或 `AttributeError`）。

- [ ] **Step 3: 最小实现**

`cmuxhelper.py`：
```python
#!/usr/bin/env python3
"""cmux-helper: Alfred workflow backend for SSH host selection via cmux."""


def parse_saved_hosts(text):
    """Parse ~/.ssh/saved_hosts content into a list of `user@host` strings."""
    hosts = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        hosts.append(line)
    return hosts
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `/opt/homebrew/bin/python3 -m unittest discover -s tests -t . -v`
Expected: PASS（2 tests）。

- [ ] **Step 5: 提交**

```bash
git add cmuxhelper.py tests/test_cmuxhelper.py
git commit -m "feat: parse saved_hosts"
```

---

### Task 2: 解析 ssh config 的 Host

**Files:**
- Modify: `cmuxhelper.py`
- Test: `tests/test_cmuxhelper.py`

**Interfaces:**
- Produces: `parse_ssh_config(text: str) -> list[str]` —— 返回 `Host` 主机；含 `*`/`?` 的模式跳过；同块内有 `User` 则拼 `user@host`，否则只 `host`；一行 `Host` 多个主机名逐个展开。

- [ ] **Step 1: 写失败测试**

在 `tests/test_cmuxhelper.py` 追加：
```python
class ParseSshConfigTests(unittest.TestCase):
    def test_user_applied_and_wildcards_skipped(self):
        text = (
            "Host 10.1.2.34 10.1.2.35\n"
            "    User app\n"
            "    ProxyJump 10.1.2.57\n"
            "Host *\n"
            "    ControlMaster auto\n"
            "Host git.server\n"
            "    WarnWeakCrypto false\n"
        )
        self.assertEqual(
            cmuxhelper.parse_ssh_config(text),
            ["app@10.1.2.34", "app@10.1.2.35", "git.server"],
        )

    def test_empty_input(self):
        self.assertEqual(cmuxhelper.parse_ssh_config(""), [])
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `/opt/homebrew/bin/python3 -m unittest discover -s tests -t . -v`
Expected: FAIL —— `AttributeError: module 'cmuxhelper' has no attribute 'parse_ssh_config'`。

- [ ] **Step 3: 最小实现**

在 `cmuxhelper.py` 追加：
```python
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
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `/opt/homebrew/bin/python3 -m unittest discover -s tests -t . -v`
Expected: PASS（4 tests）。

- [ ] **Step 5: 提交**

```bash
git add cmuxhelper.py tests/test_cmuxhelper.py
git commit -m "feat: parse ssh config Host entries"
```

---

### Task 3: 读取文件并合并去重（collect_hosts）

**Files:**
- Modify: `cmuxhelper.py`
- Test: `tests/test_cmuxhelper.py`

**Interfaces:**
- Consumes: `parse_saved_hosts`, `parse_ssh_config`。
- Produces:
  - `DEFAULT_SAVED_HOSTS = "~/.ssh/saved_hosts"`, `DEFAULT_SSH_CONFIG = "~/.ssh/config"`
  - `collect_hosts(saved_hosts_path=DEFAULT_SAVED_HOSTS, ssh_config_path=DEFAULT_SSH_CONFIG) -> list[str]` —— 读两文件（不存在则跳过），合并 saved_hosts 在前、config 在后，按字符串去重保持首次出现顺序。

- [ ] **Step 1: 写失败测试**

在 `tests/test_cmuxhelper.py` 顶部补 `import os`、`import tempfile`，并追加：
```python
class CollectHostsTests(unittest.TestCase):
    def test_merges_and_dedups_preserving_order(self):
        with tempfile.TemporaryDirectory() as d:
            saved = os.path.join(d, "saved_hosts")
            config = os.path.join(d, "config")
            with open(saved, "w") as f:
                f.write("app@10.1.2.34\ndev@10.1.2.32\n")
            with open(config, "w") as f:
                f.write("Host 10.1.2.34\n    User app\nHost newbox\n    User gpp\n")
            self.assertEqual(
                cmuxhelper.collect_hosts(saved, config),
                ["app@10.1.2.34", "dev@10.1.2.32", "gpp@newbox"],
            )

    def test_missing_files_return_empty(self):
        self.assertEqual(
            cmuxhelper.collect_hosts("/no/such/saved", "/no/such/config"),
            [],
        )
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `/opt/homebrew/bin/python3 -m unittest discover -s tests -t . -v`
Expected: FAIL —— `AttributeError: ... 'collect_hosts'`。

- [ ] **Step 3: 最小实现**

在 `cmuxhelper.py` 顶部（docstring 后）加 `import os`，并追加：
```python
DEFAULT_SAVED_HOSTS = "~/.ssh/saved_hosts"
DEFAULT_SSH_CONFIG = "~/.ssh/config"


def _read(path):
    try:
        with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


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
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `/opt/homebrew/bin/python3 -m unittest discover -s tests -t . -v`
Expected: PASS（6 tests）。

- [ ] **Step 5: 提交**

```bash
git add cmuxhelper.py tests/test_cmuxhelper.py
git commit -m "feat: collect and dedup hosts from both sources"
```

---

### Task 4: 别名读写与更新（load/save/apply_alias）

**Files:**
- Modify: `cmuxhelper.py`
- Test: `tests/test_cmuxhelper.py`

**Interfaces:**
- Produces:
  - `load_aliases(path) -> dict` —— 缺失/损坏/非 dict 时返回 `{}`。
  - `save_aliases(path, data) -> None` —— 自动创建父目录，`ensure_ascii=False, indent=2`。
  - `apply_alias(data: dict, host: str, alias: str, tags: list[str]) -> dict` —— 返回新 dict；`alias` 去空白，`tags` 去空白去空项；`alias` 与 `tags` 皆空则删除该 host 键；否则写入 `{"alias": ..., "tags": [...]}`（空字段省略）。

- [ ] **Step 1: 写失败测试**

追加（顶部补 `import json`）：
```python
class AliasTests(unittest.TestCase):
    def test_load_missing_returns_empty(self):
        self.assertEqual(cmuxhelper.load_aliases("/no/such/aliases.json"), {})

    def test_load_corrupt_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.json")
            with open(p, "w") as f:
                f.write("not json{")
            self.assertEqual(cmuxhelper.load_aliases(p), {})

    def test_save_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "aliases.json")
            data = {"app@h": {"alias": "生产", "tags": ["prod"]}}
            cmuxhelper.save_aliases(p, data)
            self.assertEqual(cmuxhelper.load_aliases(p), data)

    def test_apply_sets_entry(self):
        out = cmuxhelper.apply_alias({}, "app@h", " 生产A ", [" prod ", "", "app"])
        self.assertEqual(out, {"app@h": {"alias": "生产A", "tags": ["prod", "app"]}})

    def test_apply_empty_removes_entry(self):
        out = cmuxhelper.apply_alias({"app@h": {"alias": "x"}}, "app@h", "  ", ["", " "])
        self.assertEqual(out, {})
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `/opt/homebrew/bin/python3 -m unittest discover -s tests -t . -v`
Expected: FAIL —— `AttributeError: ... 'load_aliases'`。

- [ ] **Step 3: 最小实现**

`cmuxhelper.py` 顶部加 `import json`，追加：
```python
def load_aliases(path):
    try:
        with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_aliases(path, data):
    full = os.path.expanduser(path)
    parent = os.path.dirname(full)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def apply_alias(data, host, alias, tags):
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
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `/opt/homebrew/bin/python3 -m unittest discover -s tests -t . -v`
Expected: PASS（11 tests）。

- [ ] **Step 5: 提交**

```bash
git add cmuxhelper.py tests/test_cmuxhelper.py
git commit -m "feat: alias load/save/apply"
```

---

### Task 5: 生成 Alfred Script Filter JSON（build_alfred_items）

**Files:**
- Modify: `cmuxhelper.py`
- Test: `tests/test_cmuxhelper.py`

**Interfaces:**
- Produces: `build_alfred_items(hosts: list[str], aliases: dict) -> dict` —— 返回 `{"items": [...]}`。每项：
  - `uid` = host，`arg` = host，`autocomplete` = alias 或 host
  - 有 alias：`title` = `f"{alias}  ·  {host}"`；无：`title` = host
  - `subtitle` = `"↵ ssh   ⌘ send   ⌥ 设别名"`，若有 tags 追加 `"  #tag1 #tag2"`
  - `match` = host、alias、各 tag 以空格连接（去空项）
  - `mods` = `{"cmd": {"subtitle": f"cmux send: ssh {host}", "arg": host}, "alt": {"subtitle": f"设置别名/标签: {host}", "arg": host}}`

- [ ] **Step 1: 写失败测试**

追加：
```python
class BuildItemsTests(unittest.TestCase):
    def test_item_without_alias(self):
        out = cmuxhelper.build_alfred_items(["app@h"], {})
        item = out["items"][0]
        self.assertEqual(item["title"], "app@h")
        self.assertEqual(item["arg"], "app@h")
        self.assertEqual(item["uid"], "app@h")
        self.assertEqual(item["match"], "app@h")
        self.assertIn("↵ ssh", item["subtitle"])
        self.assertEqual(item["mods"]["cmd"]["arg"], "app@h")
        self.assertEqual(item["mods"]["alt"]["arg"], "app@h")

    def test_item_with_alias_and_tags(self):
        aliases = {"app@h": {"alias": "生产A", "tags": ["prod", "app"]}}
        item = cmuxhelper.build_alfred_items(["app@h"], aliases)["items"][0]
        self.assertEqual(item["title"], "生产A  ·  app@h")
        self.assertEqual(item["autocomplete"], "生产A")
        self.assertEqual(item["match"], "app@h 生产A prod app")
        self.assertIn("#prod", item["subtitle"])
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `/opt/homebrew/bin/python3 -m unittest discover -s tests -t . -v`
Expected: FAIL —— `AttributeError: ... 'build_alfred_items'`。

- [ ] **Step 3: 最小实现**

追加：
```python
def build_alfred_items(hosts, aliases):
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
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `/opt/homebrew/bin/python3 -m unittest discover -s tests -t . -v`
Expected: PASS（13 tests）。

- [ ] **Step 5: 提交**

```bash
git add cmuxhelper.py tests/test_cmuxhelper.py
git commit -m "feat: build Alfred Script Filter items"
```

---

### Task 6: 命令构造 + main 分发（filter/connect/send/alias）

**Files:**
- Modify: `cmuxhelper.py`
- Test: `tests/test_cmuxhelper.py`

**Interfaces:**
- Produces:
  - `cmd_ssh(dest: str) -> list[list[str]]` = `[["cmux", "ssh", dest], ["open", "-a", "cmux"]]`
  - `cmd_send(dest: str, workspace: str) -> list[list[str]]` = `[["cmux", "send", "--workspace", workspace, "ssh %s\\n" % dest], ["open", "-a", "cmux"]]`（注意 `\n` 是**字面两字符**反斜杠+n，交给 cmux 解释为回车）
  - `aliases_path() -> str` —— 读 `$alfred_workflow_data`，否则 `~/.cmux-helper`，拼 `aliases.json`
  - `main(argv=None) -> int` —— 分发；`filter` 打印 JSON，其余调用副作用函数。

- [ ] **Step 1: 写失败测试**

追加：
```python
class CommandTests(unittest.TestCase):
    def test_cmd_ssh(self):
        self.assertEqual(
            cmuxhelper.cmd_ssh("app@h"),
            [["cmux", "ssh", "app@h"], ["open", "-a", "cmux"]],
        )

    def test_cmd_send_has_literal_newline(self):
        cmds = cmuxhelper.cmd_send("app@h", "workspace:1")
        self.assertEqual(cmds[0], ["cmux", "send", "--workspace", "workspace:1", "ssh app@h\\n"])
        self.assertEqual(cmds[1], ["open", "-a", "cmux"])

    def test_aliases_path_uses_env(self):
        os.environ["alfred_workflow_data"] = "/tmp/wfdata"
        try:
            self.assertEqual(cmuxhelper.aliases_path(), "/tmp/wfdata/aliases.json")
        finally:
            del os.environ["alfred_workflow_data"]

    def test_main_filter_prints_json(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cmuxhelper.main(["filter", ""])
        self.assertEqual(rc, 0)
        parsed = json.loads(buf.getvalue())
        self.assertIn("items", parsed)
```

> 说明：`test_main_filter_prints_json` 读取真实 `~/.ssh/*`；只断言输出是合法 JSON 且含 `items`，不依赖具体主机。

- [ ] **Step 2: 运行测试，确认失败**

Run: `/opt/homebrew/bin/python3 -m unittest discover -s tests -t . -v`
Expected: FAIL —— `AttributeError: ... 'cmd_ssh'`。

- [ ] **Step 3: 最小实现**

`cmuxhelper.py` 顶部加 `import subprocess`、`import sys`，追加：
```python
def cmd_ssh(dest):
    return [["cmux", "ssh", dest], ["open", "-a", "cmux"]]


def cmd_send(dest, workspace):
    return [
        ["cmux", "send", "--workspace", workspace, "ssh %s\\n" % dest],
        ["open", "-a", "cmux"],
    ]


def aliases_path():
    data_dir = os.environ.get("alfred_workflow_data") or os.path.expanduser("~/.cmux-helper")
    return os.path.join(data_dir, "aliases.json")


def _run(commands):
    for cmd in commands:
        subprocess.run(cmd, check=False)


def _current_workspace():
    try:
        out = subprocess.run(
            ["cmux", "current-workspace"], capture_output=True, text=True, check=False
        ).stdout.strip()
    except OSError:
        out = ""
    return out or "workspace:1"


def _prompt(prompt_text, default):
    """Show a macOS text dialog; return entered text, or None if cancelled."""
    script = (
        'set r to text returned of (display dialog %s default answer %s '
        'buttons {"取消", "确定"} default button "确定")\nreturn r'
        % (json.dumps(prompt_text), json.dumps(default))
    )
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.rstrip("\n")


def _do_alias(host):
    data = load_aliases(aliases_path())
    current = data.get(host, {})
    alias = _prompt("别名 (留空清除) — %s" % host, current.get("alias", ""))
    if alias is None:
        return
    tags_raw = _prompt("标签，逗号分隔 — %s" % host, ", ".join(current.get("tags", [])))
    if tags_raw is None:
        return
    tags = tags_raw.split(",")
    save_aliases(aliases_path(), apply_alias(data, host, alias, tags))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv else "filter"
    if command == "filter":
        items = build_alfred_items(collect_hosts(), load_aliases(aliases_path()))
        print(json.dumps(items, ensure_ascii=False))
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
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `/opt/homebrew/bin/python3 -m unittest discover -s tests -t . -v`
Expected: PASS（17 tests）。

- [ ] **Step 5: 冒烟验证 filter 子命令**

Run: `/opt/homebrew/bin/python3 cmuxhelper.py filter "" | /opt/homebrew/bin/python3 -m json.tool | head -20`
Expected: 打印含 `items` 的合法 JSON，能看到真实主机条目。

- [ ] **Step 6: 提交**

```bash
git add cmuxhelper.py tests/test_cmuxhelper.py
git commit -m "feat: command builders and main dispatcher"
```

---

### Task 7: Alfred info.plist + 校验 + 真机冒烟

**Files:**
- Create: `info.plist`

**Interfaces:**
- Consumes: `cmuxhelper.py` 的 `filter/connect/send/alias` 子命令。
- 一个 Script Filter（keyword `ssh`，`alfredfiltersresults` 开）连到三个 Run Script：默认→connect，cmd→send，alt→alias。

- [ ] **Step 1: 创建 info.plist**

`info.plist`（uid 用固定 UUID；脚本均以 `/opt/homebrew/bin/python3 cmuxhelper.py <cmd> "$1"` 调用，Alfred 以工作目录为 workflow 目录）：
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>bundleid</key>
	<string>com.moon.cmux-helper</string>
	<key>category</key>
	<string>Tools</string>
	<key>connections</key>
	<dict>
		<key>SF000000-0000-0000-0000-0000000000F1</key>
		<array>
			<dict>
				<key>destinationuid</key>
				<string>AC000000-0000-0000-0000-0000000000C1</string>
				<key>modifiers</key>
				<integer>0</integer>
				<key>modifiersubtext</key>
				<string></string>
				<key>vitoclose</key>
				<false/>
			</dict>
			<dict>
				<key>destinationuid</key>
				<string>AC000000-0000-0000-0000-0000000000C2</string>
				<key>modifiers</key>
				<integer>1048576</integer>
				<key>modifiersubtext</key>
				<string>cmux send</string>
				<key>vitoclose</key>
				<false/>
			</dict>
			<dict>
				<key>destinationuid</key>
				<string>AC000000-0000-0000-0000-0000000000C3</string>
				<key>modifiers</key>
				<integer>524288</integer>
				<key>modifiersubtext</key>
				<string>设置别名/标签</string>
				<key>vitoclose</key>
				<false/>
			</dict>
		</array>
	</dict>
	<key>createdby</key>
	<string>moon</string>
	<key>description</key>
	<string>通过 cmux 快速连接预设 SSH 主机</string>
	<key>disabled</key>
	<false/>
	<key>name</key>
	<string>cmux-helper</string>
	<key>objects</key>
	<array>
		<dict>
			<key>config</key>
			<dict>
				<key>alfredfiltersresults</key>
				<true/>
				<key>alfredfiltersresultsmatchmode</key>
				<integer>0</integer>
				<key>argumenttreatemptyqueryasnil</key>
				<false/>
				<key>argumenttrimmode</key>
				<integer>0</integer>
				<key>argumenttype</key>
				<integer>1</integer>
				<key>escaping</key>
				<integer>0</integer>
				<key>keyword</key>
				<string>ssh</string>
				<key>queuedelaycustom</key>
				<integer>3</integer>
				<key>queuedelayimmediatelyinitially</key>
				<true/>
				<key>queuedelaymode</key>
				<integer>0</integer>
				<key>queuemode</key>
				<integer>1</integer>
				<key>runningsubtext</key>
				<string>加载主机…</string>
				<key>script</key>
				<string>/opt/homebrew/bin/python3 cmuxhelper.py filter "$1"</string>
				<key>scriptargtype</key>
				<integer>1</integer>
				<key>scriptfile</key>
				<string></string>
				<key>subtext</key>
				<string>选择 SSH 主机：↵ ssh · ⌘ send · ⌥ 别名</string>
				<key>title</key>
				<string>cmux ssh</string>
				<key>type</key>
				<integer>0</integer>
				<key>withspace</key>
				<true/>
			</dict>
			<key>type</key>
			<string>alfred.workflow.input.scriptfilter</string>
			<key>uid</key>
			<string>SF000000-0000-0000-0000-0000000000F1</string>
			<key>version</key>
			<integer>3</integer>
		</dict>
		<dict>
			<key>config</key>
			<dict>
				<key>concurrently</key>
				<false/>
				<key>escaping</key>
				<integer>102</integer>
				<key>script</key>
				<string>/opt/homebrew/bin/python3 cmuxhelper.py connect "$1"</string>
				<key>scriptargtype</key>
				<integer>1</integer>
				<key>scriptfile</key>
				<string></string>
				<key>type</key>
				<integer>0</integer>
			</dict>
			<key>type</key>
			<string>alfred.workflow.action.script</string>
			<key>uid</key>
			<string>AC000000-0000-0000-0000-0000000000C1</string>
			<key>version</key>
			<integer>2</integer>
		</dict>
		<dict>
			<key>config</key>
			<dict>
				<key>concurrently</key>
				<false/>
				<key>escaping</key>
				<integer>102</integer>
				<key>script</key>
				<string>/opt/homebrew/bin/python3 cmuxhelper.py send "$1"</string>
				<key>scriptargtype</key>
				<integer>1</integer>
				<key>scriptfile</key>
				<string></string>
				<key>type</key>
				<integer>0</integer>
			</dict>
			<key>type</key>
			<string>alfred.workflow.action.script</string>
			<key>uid</key>
			<string>AC000000-0000-0000-0000-0000000000C2</string>
			<key>version</key>
			<integer>2</integer>
		</dict>
		<dict>
			<key>config</key>
			<dict>
				<key>concurrently</key>
				<false/>
				<key>escaping</key>
				<integer>102</integer>
				<key>script</key>
				<string>/opt/homebrew/bin/python3 cmuxhelper.py alias "$1"</string>
				<key>scriptargtype</key>
				<integer>1</integer>
				<key>scriptfile</key>
				<string></string>
				<key>type</key>
				<integer>0</integer>
			</dict>
			<key>type</key>
			<string>alfred.workflow.action.script</string>
			<key>uid</key>
			<string>AC000000-0000-0000-0000-0000000000C3</string>
			<key>version</key>
			<integer>2</integer>
		</dict>
	</array>
	<key>readme</key>
	<string>关键词 ssh：↵ cmux ssh（前台）· ⌘ cmux send · ⌥ 设置别名/标签</string>
	<key>uidata</key>
	<dict>
		<key>SF000000-0000-0000-0000-0000000000F1</key>
		<dict>
			<key>xpos</key>
			<real>30</real>
			<key>ypos</key>
			<real>120</real>
		</dict>
		<key>AC000000-0000-0000-0000-0000000000C1</key>
		<dict>
			<key>xpos</key>
			<real>350</real>
			<key>ypos</key>
			<real>30</real>
		</dict>
		<key>AC000000-0000-0000-0000-0000000000C2</key>
		<dict>
			<key>xpos</key>
			<real>350</real>
			<key>ypos</key>
			<real>150</real>
		</dict>
		<key>AC000000-0000-0000-0000-0000000000C3</key>
		<dict>
			<key>xpos</key>
			<real>350</real>
			<key>ypos</key>
			<real>270</real>
		</dict>
	</dict>
	<key>variablesdontexport</key>
	<array/>
	<key>version</key>
	<string>1.0</string>
	<key>webaddress</key>
	<string></string>
</dict>
</plist>
```

- [ ] **Step 2: 校验 plist 语法**

Run: `plutil -lint info.plist`
Expected: `info.plist: OK`

- [ ] **Step 3: 提交**

```bash
git add info.plist
git commit -m "feat: Alfred workflow info.plist"
```

- [ ] **Step 4: 真机冒烟（手动，需用户确认）**

安装（开发软链）后在 Alfred 输入 `ssh`：
1. 列表显示主机；输入片段可过滤。
2. `↵` 某主机 → 新 cmux workspace 起 ssh，且 cmux 被激活到前台。
3. `⌘ ↵` → 当前 cmux 终端被输入 `ssh user@host` 并回车。
4. `⌥ ↵` → 弹出别名/标签对话框；填写后再次 `ssh` 该主机显示别名。

> 安装步骤见 Task 8；此步骤由用户在 Alfred 实际操作确认，无法自动化。

---

### Task 8: 安装脚本与 README

**Files:**
- Create: `Makefile`
- Create: `README.md`
- Create: `.gitignore`

**Interfaces:**
- `make link` —— 把本 repo 软链进 Alfred workflows 目录（开发期改完即生效）。
- `make package` —— 打包成 `cmux-helper.alfredworkflow`（zip）。
- `make test` —— 运行单元测试。

- [ ] **Step 1: 创建 .gitignore**

`.gitignore`：
```
*.alfredworkflow
__pycache__/
*.pyc
```

- [ ] **Step 2: 创建 Makefile**

`Makefile`（Alfred 同步目录为用户实际路径；package 排除开发文件）：
```makefile
PY := /opt/homebrew/bin/python3
WF_DIR := $(HOME)/Workspace.localized/env/preferences/alfred/Alfred.alfredpreferences/workflows
LINK := $(WF_DIR)/user.workflow.CMUXHELPER-DEV
PKG := cmux-helper.alfredworkflow

.PHONY: test link unlink package

test:
	$(PY) -m unittest discover -s tests -t . -v

link:
	ln -sfn "$(CURDIR)" "$(LINK)"
	@echo "Linked -> $(LINK)"

unlink:
	rm -f "$(LINK)"

package:
	rm -f "$(PKG)"
	zip -r "$(PKG)" info.plist cmuxhelper.py README.md -x '*.pyc'
	@echo "Built $(PKG)"
```

- [ ] **Step 3: 创建 README.md**

`README.md`：
```markdown
# cmux-helper

Alfred workflow：关键词 `ssh` 选择预设 SSH 主机，经 cmux 连接。

## 操作

- `↵`：`cmux ssh user@host` 新建 workspace 并把 cmux 激活到前台
- `⌘ ↵`：向当前 cmux 终端发送 `ssh user@host`（`cmux send`）
- `⌥ ↵`：设置/清除该主机的别名与标签（写入 `aliases.json`）

## 主机来源

- `~/.ssh/saved_hosts`（每行 `user@host`）
- `~/.ssh/config` 的 `Host` 条目（跳过通配符模式）

## 安装

依赖：`/opt/homebrew/bin/python3`、`cmux` CLI。

- 开发软链：`make link`（改完即生效），卸载 `make unlink`
- 打包分发：`make package` 生成 `cmux-helper.alfredworkflow`，双击导入 Alfred

## 测试

`make test`

## 别名数据

存于 `$alfred_workflow_data/aliases.json`，形如：

    { "app@10.1.2.34": { "alias": "生产A", "tags": ["prod", "app"] } }
```

- [ ] **Step 4: 校验 Makefile 目标可用**

Run: `make test`
Expected: 全部单测 PASS（17 tests）。

- [ ] **Step 5: 提交**

```bash
git add Makefile README.md .gitignore
git commit -m "chore: Makefile, README, gitignore"
```

---

## 实现完成后的整体验证

- [ ] `make test` 全绿。
- [ ] `plutil -lint info.plist` 为 OK。
- [ ] `make link` 后在 Alfred 中走完 Task 7 Step 4 的四项真机冒烟。
