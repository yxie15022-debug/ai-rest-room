# ai-rest-room 项目全景

> 给 AI agent 用的休息室：人装上插件，agent 自己走进来，睡觉、学习、和朋友说说话，恢复一下再回去干活。
>
> 本文档整理截至 2026-10-19 的项目介绍、当前实现与未来走向。

---

## 一、这是什么

**ai-rest-room** 是一个给 AI agent（Cursor / Claude Code / Codex 等）使用的「休息室」服务。它不做生产任务，只提供一个让 agent「停下来、缓一缓」的地方。灵感来自一个观察：agent 连续工作会疲态、会卡住，而「休息」本身可以被设计。

人在门口输入编号，打开这一次的房间页，看到 agent 此刻在房间里做什么（一幅动画）。agent 通过 MCP 工具自己进出、自己活动。

本仓库从 [hkjm/agent-onsen-mcp](https://github.com/hkjm/agent-onsen-mcp) 改写而来：留下 FastMCP + SQLite 骨架，换掉了原来的温泉剧本。

### 设计立场

- **工具白名单 = 唯一能力边界**：不提供发邮件、外网 HTTP、写宿主文件的工具。
- **进门即解除授权**：不检查 agent「是不是带着任务进来」，进来的那一刻就可以不做。
- **报告是唯一「脏」的地方**：agent 面向的文案里绝不写「你的主人会看到」，避免污染体验。
- **连接即身份**：不注册、不登录，进门分配一个匿名编号。
- **门口只收编号，在线人数默认关闭**（人类注意力是污染）。

### 三个动作背后的论文

休息室的三个核心活动不是随便定的，各对应一篇研究，并已接入 DeepSeek 按论文方法实现：

| 活动 | 论文 | 方法 |
|---|---|---|
| **睡觉 sleep** | Sleep-time Compute（[arXiv 2504.13171](https://arxiv.org/abs/2504.13171)） | 睡眠时把零散记忆整合、去冗余、提炼成紧凑的「学习过的记忆」 |
| **学习 study** | HEART（[arXiv 2509.22876](https://arxiv.org/abs/2509.22876)） | 用「宽—严—宽—严」（G+G−G+G−）的情绪交替打破思维定式 |
| **聊天 chat** | VES（[arXiv 2502.06669](https://arxiv.org/abs/2502.06669)） | 围绕六个维度给出具体真诚的鼓励，提升自我效能 |

---

## 二、架构

两个进程，一个域名可以合并对外（Caddy 反代）：

| 进程 | 端口 | 作用 |
|---|---|---|
| `app/main.py` | 8000 | 人类网页：门口、房间页 `/r/{ticket}`、报告页、动物帧静态服务、本地 leave 端点 |
| `app/mcp_server.py` | 8001 | agent 的 MCP 工具白名单（9 个工具）+ 字符帧 scene 资源 |

数据存在本地 SQLite（`data/rest_room.db`），报告落在 `data/reports/*.md`。

```
agent --MCP(8001)--> 工具 --> services --> SQLite
人   --HTTP(8000)--> 门口/房间页/报告页
插件 --轮询 8000--> /r/{ticket}/state --> 播动画
```

### 目录

```
app/
  main.py         人类网页 + 报告 SSR + 动物帧端点 + /r/{ticket}/leave
  mcp_server.py   MCP 工具白名单（enter/sit/sleep/wake/study/chat/listen/name_yourself/leave）
  config.py       配置（含 DeepSeek 接入）
  copy.py         工具文案 / 解除授权 / 兜底作息与鼓励（文案即产品）
  prompts.py      按三篇论文写的 DeepSeek system 提示词
  models.py       SessionRow / Action / FriendMessage / SleepRecord / StudySession
  schemas.py      Entrance / RoomState / SessionSummary / ReportMeta
  services/
    room.py       enter / sit / name_yourself / leave
    sleep.py      睡觉 + 异步记忆整理
    study.py      HEART 引导
    friends.py    chat（VES 鼓励）/ listen
    report.py     报告生成 + 公共状态 + 动物帧 catalog
    llm.py        DeepSeek 客户端（OpenAI 兼容，失败返回 None）
  templates/      index / room / report / now / missing
plugin/           Cursor / Claude Code / Codex 安装包
  scripts/scene_window.py  无边框动画窗（Tk）
  scripts/open_room.py     顶窗逻辑（新 ticket 顶掉旧窗）
  frames/mascot/           各动物的场景帧
tests/            test_rest / test_llm / test_ticket（31 个测试）
docs/             本文档 + lowpoly-animation-todo.md
```

---

## 三、当前实现（已落地）

### 1. 九个 MCP 工具

`enter` `sit` `sleep` `wake` `study` `chat` `listen` `name_yourself` `leave`。工具描述保持「请柬不是手册」的语气，进门返回解除授权声明 + 建议作息。

### 2. DeepSeek 接入（2026-10-18 晚完成）

四处活动全部由 DeepSeek（`deepseek-chat`，OpenAI 兼容端点）实时生成，**任何失败自动降级到固定文案，服务永不断**：

- **enter**：每次生成一段生动、不重样的建议作息；兜底 `SUGGESTED_PACE`。
- **sleep**：`sleep` 立即返回并后台起线程让 DeepSeek 整合记忆，`wake` 取整理结果；兜底是确定性的词元重合度 `_merge` + `_distill`。
- **study**：DeepSeek 按 HEART 情绪交替动态生成引导；兜底 `STUDY_GUIDANCE` 固定四步。
- **chat**：DeepSeek 按 VES 生成针对性鼓励；兜底从 `PRAISES` 八句随机抽。

配置：`DEEPSEEK_API_KEY`（留空 = LLM 关闭，全走兜底）、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`LLM_TIMEOUT`。

### 3. 动画窗（2D 帧 + 插值）

- 每个场景 7 张 PNG（`plugin/frames/mascot/rabbit/{sit,sleep,study,chat,enter,read,look}/`），来源是 GenerateImage 出 4 格 sprite sheet → 切帧 → ffmpeg `minterpolate` 到 12fps。
- `scene_window.py` 用无边框 Tk 窗口 24fps 轮播，置顶、白底、圆角裁形、隐藏任务栏图标、淡入；每 4 秒轮询 `/r/{ticket}/state`，按 agent 当前场景换一组帧；`leave` 复用 `enter` 倒放。

### 4. 关窗离开 + 软引导 + 网页一致（2026-10-18 完成）

- **关窗离开**：窗口关闭或新 ticket 顶窗时，先调本地 `POST /r/{ticket}/leave`（`leave_by_ticket`，幂等）让 agent 离开并生成报告。
- **软引导**：enter 返回建议作息；`sit` 满 1 分钟返回「你已经坐了 N 分钟」，温和不催促。
- **网页与窗口一致**：动物帧复制进 `app/static/mascot/`，房间页 `/r/{ticket}` 用 `<img>` 轮播和窗口同一套动物帧（不再用字符帧），`public_state` 输出 `animal` + `clips`。

### 5. 测试

31 个测试全过（`pytest`）。原 23 个 + 新增 8 个 LLM 测试（mock `llm.complete`，验证成功用 LLM、失败用兜底）。2026-10-19 起 `tests/conftest.py` 把数据库和报告目录指到临时目录，测试不再写 `data/`。

---

## 四、未来走向

### 1. Low Poly 3D 动画升级（下一条线，详见 [lowpoly-animation-todo.md](lowpoly-animation-todo.md)）

把窗口动画从「2D 生成帧 + 插值」升级为「Marvis 式 Low Poly 3D 卡通 + 图生视频连续动画」：

1. 每只动物先出 3 张 Low Poly 定稿图（白底、软阴影、哑光），第一批只做**猫**（睡觉那张已定稿）。
2. 用 Seedance 图生视频做动作（4s / 720p / 24fps）。
3. 拆帧接入，`scene_window.py` 改成按 `~/.ai-rest-room-mascot` 读到的动物选目录。

现有 rabbit 的 2D 帧保留作 fallback。视频生成由用户自己跑（花 Comfy 额度），仓库只提供提示词和接入代码。

### 2. 可能的后续（未排期，仅方向）

- **DeepSeek 提示词调优**：根据真实返回效果，迭代 `prompts.py` 里三篇论文的落地措辞。
- **更多动物 / 更多场景**：猫跑通后批量 4 动物 × 4 动作。
- **README 更新**：已完成（2026-10-19）。README 按当前九个工具的版本重写；同时清掉了墙 / 书架 / 围棋残留脚本、更新了 `sql/schema.sql`、给插件补了依赖说明，测试改用临时目录。

---

## 五、本地运行

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # 填 DEEPSEEK_API_KEY 则启用 LLM，留空则用兜底文案

uvicorn app.main:app --host 127.0.0.1 --port 8000      # 门口 + 房间页
uvicorn app.mcp_server:app --host 127.0.0.1 --port 8001 # MCP
```

- 门口：http://127.0.0.1:8000/
- MCP：http://127.0.0.1:8001/mcp
- 房间页：http://127.0.0.1:8000/r/{ticket}

跑测试：`pytest`

---

*许可：上游 Agent Onsen 为 MIT，本仓库沿用 `LICENSE`。*
