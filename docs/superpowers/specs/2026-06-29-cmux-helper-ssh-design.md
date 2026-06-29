# cmux-helper Alfred Workflow — SSH 设计

日期：2026-06-29
状态：已确认，待实现

## 目标

实现一个 Alfred workflow，通过关键词 `ssh` 快速选择并连接到预设 SSH 主机，连接经由 `cmux` 终端。来源于 `GOAL.md`：

1. Alfred 输入 `ssh` 触发 workflow
2. 快速选择并连接预设 SSH 主机
3. 可选 `cmux ssh user@host` 或 `cmux send 'ssh user@host\n'`
4. 使用 `cmux ssh` 时把其所在窗口/应用移到前台
5. 主机来源之一是 `~/.ssh/saved_hosts`
6. 可为主机设置别名/标签，方便快速连接

## 已确认的关键决策

- **连接方式选择**：默认 `↵` 走 `cmux ssh`；`⌘ ↵` 走 `cmux send`。
- **别名/标签存储**：独立 JSON 配置文件，提供 workflow 内的设置入口（`⌥ ↵`）。
- **主机来源**：`~/.ssh/saved_hosts` + `~/.ssh/config` 的 `Host` 条目，合并去重。
- **实现语言**：Python 3，纯标准库，零第三方依赖。模糊匹配交给 Alfred 自身（"Alfred filters results"）。
- **前台激活**：实测 `cmux focus-window` 不会把 cmux.app 激活到 macOS 前台，故统一用 `open -a cmux`。

### 已验证的 cmux 行为

- `cmux ssh <dest>` 新建 workspace、标记为 remote-SSH 并 focus（仅 app 内切换，不激活 app）。
- `cmux focus-window --window <UUID>` 只接受 UUID（不接受 index `0` 或 ref `window:1`），且**不激活 macOS 应用**。
- `cmux current-workspace` 在 cmux 外（Alfred 环境，无 `CMUX_WORKSPACE_ID`）仍返回当前选中的 workspace（如 `workspace:1`）。
- `cmux send` 原生支持转义 `\n`（发送回车）。

## 总体结构

源码放在本 repo，开发期通过软链接进 Alfred 的 `workflows/` 目录实现"改完即生效"。

```
cmux-helper/
├── info.plist          # Alfred workflow 定义（Script Filter + 3 个动作 + 修饰键连线）
├── cmuxhelper.py       # 单入口，子命令分发（纯标准库，无依赖）
├── icon.png            # 图标（可选，先占位）
└── README.md           # 安装/使用说明
```

`cmuxhelper.py <subcommand>` 单文件分发四类操作，共享主机解析逻辑：

- `filter [query]` — 输出 Alfred Script Filter JSON
- `connect <user@host>` — `cmux ssh` + `open -a cmux`
- `send <user@host>` — `cmux send` + `open -a cmux`
- `alias <user@host>` — 弹 osascript 对话框设置别名/标签并写回 JSON

## 主机数据来源与合并

- **来源 A**：`~/.ssh/saved_hosts`，每行 `user@host`（忽略空行与 `#` 注释行）。
- **来源 B**：`~/.ssh/config` 的 `Host` 条目。
  - 跳过含通配符 `*` / `?` 的模式。
  - 一行 `Host` 可声明多个主机名，逐个展开。
  - 解析该 Host 块内的 `User`：有则拼成 `user@host`，无则仅 `host`。
- A、B 合并后按字符串去重（A 大概率已涵盖 B）。
- **别名层 C**：`$alfred_workflow_data/aliases.json`：
  ```json
  { "app@10.1.2.34": { "alias": "生产A", "tags": ["prod", "app"] } }
  ```
  叠加到对应主机条目。

## Script Filter（关键词 `ssh`）

- 输出全部合并后的主机为 Alfred items；开启 "Alfred filters results"，由 Alfred 做模糊过滤。
- 每个 item：
  - **title**：有别名 → `生产A  ·  app@10.1.2.34`；无别名 → `app@10.1.2.34`
  - **subtitle**：`↵ ssh   ⌘ send   ⌥ 设别名` + tags（若有）
  - **match**：`user@host` + 别名 + tags 拼接，保证按别名/标签也能搜到
  - **arg**：`user@host`
  - **mods**：为 `⌘` / `⌥` 提供各自的 subtitle 提示

## 三个动作（按修饰键区分）

| 操作 | 行为 |
|---|---|
| `↵`（默认） | `cmux ssh <user@host>` 新建并 focus workspace，再 `open -a cmux` 激活到前台 |
| `⌘ ↵` | `cmux send --workspace "$(cmux current-workspace)" "ssh <user@host>\n"`，随后 `open -a cmux` 前台 |
| `⌥ ↵` | 弹 `osascript` 对话框输入别名/标签，写回 `aliases.json` |

别名设置对话框：预填当前别名与以逗号分隔的标签；用户确认后写回 `aliases.json`（别名为空则移除该条目）。

## 错误处理 & 边界

- `saved_hosts` / `config` 不存在 → 跳过该源，不报错。
- `aliases.json` 不存在/损坏 → 视为空别名表，不阻断主流程。
- Script Filter 永远至少返回可用列表；解析异常时输出一条提示 item 而非崩溃。
- `$alfred_workflow_data` 目录不存在时，写别名前先创建。

## 安装

README 提供两种方式：
1. 把 repo 目录软链接进 Alfred 的 workflows 目录（开发推荐）。
2. `make package` 打成 `.alfredworkflow`（分发用，后续可选）。

## 不做（YAGNI）

- 不在 Python 内实现模糊匹配（交给 Alfred）。
- 不支持 `cmux ssh` 的端口/identity 等高级参数（saved_hosts/ssh config 已能覆盖；后续按需再加）。
- 暂不实现别名的批量管理 UI，单条 `⌥ ↵` 设置即可。
