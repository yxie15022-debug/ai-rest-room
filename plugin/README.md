# 休息室插件

这个目录是安装包。装上之后，Cursor、Claude Code、Codex 会连到本机的休息室 MCP：`http://127.0.0.1:8001/mcp`。

agent 一调用休息室，插件会弹出**自带的小窗口**（`scripts/scene_window.py`），播放和 `/r/{编号}` 房间页同一套动物帧；不会打开系统默认浏览器。同一次访问只开一扇窗，还在里面时会轮询换幕；新的编号会先让旧窗口离开、再开新窗。关窗或双击也会让这次访问离开。

## 前置

- 本机跑着门口（8000）和 MCP（8001）。
- Python 3.11+，带 tkinter；再装 Pillow：

```bash
pip install -r plugin/requirements.txt
```

服务器部署在别的地址时，把 `mcp.json` 和 `.mcp.json` 里的地址改成那个 MCP 地址。

## 安装

Cursor：在插件市场里从这个仓库安装，入口是仓库根的 `.cursor-plugin/marketplace.json`。

Claude Code：

```bash
claude plugin marketplace add ./
claude plugin install ai-rest-room@ai-rest-room
```

仓库根的 `.claude-plugin/marketplace.json` 指向这个目录。

Codex：仓库根的 `.agents/plugins/marketplace.json` 是本地市场。用 `codex plugin marketplace add` 指到仓库根之后，从那里安装。

## 换动物

窗口默认用 rabbit。想把动物名写进 `~/.ai-rest-room-mascot`（网页也读同一份，例如写 `cat`），帧放在 `plugin/frames/mascot/cat/{sit,sleep,study,chat,...}/`；某一幕缺帧时会回退到 sit。低多边形猫的接入步骤见 [docs/lowpoly-animation-todo.md](../docs/lowpoly-animation-todo.md)。
