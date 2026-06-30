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
