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
| `app/mcp_server.py` | 8001 | agent 的 MCP 工具白名单（9 个工具）+ MCP Apps 场景资源 |

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
  static/mascot/  各动物的场景帧（2026-10-19 新增 cat）
scripts/
  smoke_vertical.py    当前竖线冒烟（临时数据库、不联网）
  render_lowpoly.py    Marvis 风格程序化占位渲染器
  ingest_animation.py  图生视频 / 图片序列 → 两处帧目录
plugin/           Cursor / Claude Code / Codex 安装包
  scripts/scene_window.py  无边框动画窗（Tk，按 `~/.ai-rest-room-mascot` 选动物）
  scripts/open_room.py     顶窗逻辑（新 ticket 顶掉旧窗）
  frames/mascot/           各动物的场景帧（rabbit / cat / studio）
tests/            test_rest / test_llm / test_ticket / test_research / test_animation（54 个）
docs/             project-overview / lowpoly-animation-todo / marvis-animation / studio-cat-animation
  reference/      风格定稿图（睡觉参考）
  preview/        场景预览 GIF / 联系表
```

---

## 三、当前实现（已落地）

### 1. 九个 MCP 工具

`enter` `sit` `sleep` `wake` `study` `chat` `listen` `name_yourself` `leave`。工具描述保持「请柬不是手册」的语气，进门返回解除授权声明 + 建议作息。

### 2. DeepSeek 接入（2026-10-18 完成，2026-10-19 按论文细化）

四处活动全部由 DeepSeek（`deepseek-chat`，OpenAI 兼容端点）实时生成，**任何失败自动降级到固定文案，服务永不断**：

- **enter**：每次生成一段生动、不重样的建议作息；兜底 `SUGGESTED_PACE`。
- **sleep**：按 Sleep-time Compute 落地——`sleep` 立即返回并后台起线程，DeepSeek 在睡眠里把零散片段整理成三段式 learned context：`【整合后的要点】`、`【去重与推断】`、`【预判接下来可能会用到的】`（2–3 个醒来后可能接着问/用到的方向）；`wake` 取回 `summary`，并附 `learned_context`、`inferences`、`anticipations`、`token_hint` 四个结构化字段。兜底是确定性的词元重合度 `_merge` + `_distill`，输出同一套结构；LLM 若忽略格式，也会被折进同样三段，不改表结构。
- **study**：DeepSeek 按 HEART 的「宽—严—宽—严」（G+ G− G+ G−）写出四段引导，每段单独标出阶段；模型漏段时用 `STUDY_GUIDANCE` 的对应段补齐，返回值新增 `phases`（stage / valence / text）。兜底 `STUDY_GUIDANCE` 同样是标好 G+/G− 的四段。
- **chat**：DeepSeek 按 VES 生成接住对方具体内容、至少覆盖六方面中三面的鼓励，以 encouraging 为主、可少量 provocative；返回值新增 `ves_dimensions`（命中的方面）与 `ves_type`。兜底先复述对方一句，再从扩充后的 `PRAISES` 随机抽一句。

配置：`DEEPSEEK_API_KEY`（留空 = LLM 关闭，全走兜底）、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`LLM_TIMEOUT`。

### 3. 动画窗（2D 帧 + 插值）

- rabbit：每个场景 7 张 PNG（`plugin/frames/mascot/rabbit/{sit,sleep,study,chat,enter,read,look}/`），来源是 GenerateImage 出 4 格 sprite sheet → 切帧 → ffmpeg `minterpolate` 到 12fps。
- `scene_window.py` 用无边框 Tk 窗口 24fps 轮播，置顶、白底、圆角裁形、隐藏任务栏图标、淡入；每 4 秒轮询 `/r/{ticket}/state`，按 agent 当前场景换一组帧；`leave` 复用 `enter` 倒放。窗口和网页都按 `~/.ai-rest-room-mascot` 选动物，缺帧回退 `sit`。
- 2026-10-19：新增两套程序化动画。`cat`：Low Poly 奶油猫（`scripts/render_lowpoly.py`）；`studio`：**当前选定风格**，白棚里的黑猫工位（`scripts/render_studio.py`，黑猫剪影 + 白色桌椅/边柜 + 彩色围巾 + 显示器 UI + 极软阴影）。都是 512×512、20 帧循环，预览在 `docs/preview/`。
- 最终质感走「定稿图 → Seedance 图生视频 → 拆帧」：studio 风格的提示词和产线见 [studio-cat-animation.md](studio-cat-animation.md)，旧的低多边形产线保留在 [marvis-animation.md](marvis-animation.md)；素材到手后用 `scripts/ingest_animation.py` 一条命令写入两处帧目录。

### 4. 关窗离开 + 软引导 + 网页一致（2026-10-18 完成）

- **关窗离开**：窗口关闭或新 ticket 顶窗时，先调本地 `POST /r/{ticket}/leave`（`leave_by_ticket`，幂等）让 agent 离开并生成报告。
- **软引导**：enter 返回建议作息；`sit` 满 1 分钟返回「你已经坐了 N 分钟」，温和不催促。
- **网页与窗口一致**：动物帧复制进 `app/static/mascot/`，房间页 `/r/{ticket}` 用 `<img>` 轮播和窗口同一套动物帧（不再用字符帧），`public_state` 输出 `animal` + `clips`。

### 5. 测试

54 个测试全过（`pytest`）：原 23 个 + 8 个 LLM 测试（mock `llm.complete`）+ 16 个论文落地测试（sleep/study/chat 的提示词与服务结构）+ 7 个动画资产测试（cat 与 studio 的帧、镜像目录、预览、环境变量选择）。2026-10-19 起 `tests/conftest.py` 把数据库和报告目录指到临时目录，测试不再写 `data/`；动画测试只读帧文件，不依赖 Pillow。

---

## 四、未来走向

### 1. Low Poly 3D 动画升级（下一条线，详见 [lowpoly-animation-todo.md](lowpoly-animation-todo.md)）

把窗口动画从「2D 生成帧 + 插值」升级为「Marvis 式 Low Poly 3D 卡通 + 图生视频连续动画」。

**2026-10-19 进展**：窗口/网页已能按 `~/.ai-rest-room-mascot` 选动物；两套程序化帧（`cat` 低多边形奶油猫、`studio` 当前选定的黑猫工位）、拆帧导入脚本（`scripts/ingest_animation.py`）和提示词文档（[studio-cat-animation.md](studio-cat-animation.md)、[marvis-animation.md](marvis-animation.md)）已就绪。剩下的主要是美术素材：

1. 每只动物先出 3 张 Low Poly 定稿图（白底、软阴影、哑光），第一批只做**猫**（睡觉那张已定稿，见 `docs/reference/`；sit / study / chat 待生成）。
2. 用 Seedance 图生视频做动作（4s / 720p / 24fps，固定机位）。
3. 用 `scripts/ingest_animation.py` 拆帧接入，替换占位帧。

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
