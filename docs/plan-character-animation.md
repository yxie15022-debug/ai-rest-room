# 角色形象 + 剧情动画 计划

> 2026-10-29。本文件是计划，不实施。范围：①enter 传 model 参数 → 每个 model 对应一个 3D 角色形象；②enter/study/sleep/chat 改成有剧情的双角色互动动画；③对话泡泡显示二者对话文字，剧情只播一次；④顺手修猫太黑太小看不见的问题。

## 0. 关键事实（读代码确认过的）

- MCP `enter` 在 `app/mcp_server.py:102`，目前只收 `ctx`，调 `RoomService(db).enter()`（`app/services/room.py:31`），无参数。
- `SessionRow`（`app/models.py:25`）字段：id / anon_id / ticket / self_name / note / entered_at / left_at / report_path。**没有 model 字段。**
- `Entrance`（`app/schemas.py:8`）：session_id / anon_id / deauthorization / note / tools。
- `app/db.py:28` 的 `create_db_and_tables()` 调 `SQLModel.metadata.create_all` + `ensure_ticket_column()`，后者用 `ALTER TABLE … ADD COLUMN` 给 SQLite 老库补列。**新列照此模式加一个 `ensure_model_column()` 即可，不需要 alembic。**
- `app/templates/room.html:130-167` 是播放器：`setInterval(paint, 120)`，`paint()` 按 `data.stage[sceneIndex]` 取 scene，按 `CLIP_FOR` 映射到帧目录，`frameIndex` 到 `count` 后归零并 `sceneIndex += 1`（最后一幕停在最后一帧循环）。**当前所有场景都是"循环"语义，没有"只播一次"。**
- `scripts/render_lowpoly_room.py`：`build()` 建场景+猫（程序化 sphere/cone/torus，无外部模型），`frame(scene, f)` 每帧重算姿态。`FRAMES=20`，`logic = FRAMES//2 = 10`，每逻辑步重复 2 帧。猫材质 `BLACK = (0.055, 0.052, 0.062)`（确实很黑），缩放 1.28x。门用 `door_hinge` empty 旋转。气泡 `bub1/bub2/bub_tail/bub_heart` 已存在但**没有文字**。
- `scripts/lowpoly_post.py`：把 `data/_lowpoly_render/{scene}/*.png` 复制到 `app/static/mascot/lowpoly/{scene}/` 和 `plugin/frames/mascot/lowpoly/{scene}/`，再生成 gif + contact sheet。`SCENES = ['enter','sit','sleep','study','chat']` 硬编码。
- `app/main.py:132` 路由 `/mascot/{animal}/{scene}/{index}`，从 `MASCOT_DIR/{animal}/{scene}/` 读帧。
- `app/services/report.py:188` `public_visit()` 返回 `animal`（来自 `mascot_animal()`，读 `~/.ai-rest-room-mascot` 或 env，当前 `lowpoly`）、`clips`（来自 `mascot_clips(animal)`，扫 `MASCOT_DIR/{animal}/{scene}/` 数 png）、`stage`（去重后的场景序列）、`catalog`、`revision`。
- `app/receipt.py:42` `chat_result()` 把 `PNGS[scene]`（像素 PNG，来自 `gifscene.py`）作为 MCP 返回的图片帧 —— 这是给 agent 客户端看的像素帧，**和网页看的 3D 帧是两套**。本计划只动 3D 帧那条线，像素帧不动。

## 1. 角色定位（重要澄清）

代码里 "animal" = 风格（lowpoly / room），不是角色。现在 `lowpoly` 风格下只有一个猫。

本计划引入两个角色：
- **房主（host）= 现在的猫**。常驻房间，开门、陪聊、看人睡觉。固定不变。
- **访客（visitor）= 调 enter 的那个 agent 的 model 对应的角色**。从花园小径走过来敲门、进来交流。

所以 `model` 参数决定的是**访客**的形象，不是房主。房主永远是猫。（若以后想让房主也随 model 变，是另一个功能，本计划不做。）

## A. 数据模型改动

### A.1 `app/models.py`
`SessionRow` 加一列：

```python
model: str | None = Field(default=None, index=True)  # 调 enter 时传入，如 'deepseek'
```

放 `self_name` 附近。`index=True` 方便以后按 model 统计。

### A.2 `app/schemas.py`
`Entrance` 加字段：

```python
model: str | None = None
```

`RoomState` / `SessionSummary` 也加 `model: str | None = None`（展示用）。

### A.3 migration：`app/db.py`
仿照 `ensure_ticket_column()` 加 `ensure_model_column()`，在 `create_db_and_tables()` 末尾调用：

```python
def ensure_model_column(bound=None) -> None:
    target = bound or engine
    if not str(target.url).startswith('sqlite'):
        return
    with target.begin() as conn:
        columns = {row[1] for row in conn.execute(text('PRAGMA table_info(sessions)')).fetchall()}
        if 'model' not in columns:
            conn.execute(text('ALTER TABLE sessions ADD COLUMN model TEXT'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_sessions_model ON sessions(model)'))
```

Postgres 等非 SQLite 库需要手动 `ALTER TABLE`（项目目前默认 SQLite，先只处理 SQLite；非 SQLite 在 `ensure_model_column` 里 return，文档里写明要手动迁移）。

**风险**：老会话 `model` 为 NULL，渲染时落到 default 角色（见 C.3）。
## B. MCP `enter` 工具加 `model` 参数

### B.1 `app/mcp_server.py:102`
```python
@_expose('enter')
async def enter(ctx: Context, model: str | None = None) -> str:
    with Session(engine) as db:
        entrance = RoomService(db).enter(model=model)
        payload = _data(entrance)
        ticket = record_action(db, entrance.session_id, 'enter')
    await play_scene(ctx, 'enter')
    return chat_result(ticket, 'enter', payload)
```

参数名：**`model`**。可选。默认 `None`（未知模型 → default 角色）。不限制枚举值（白名单在 C 里维护，传未知值时落 default 并在返回 note 里提示）。

### B.2 `app/services/room.py:31`
`enter(self, model: str | None = None)`：把 `model` 写进 `SessionRow(model=model)`，再传给 `Entrance`。

### B.3 `app/copy.py`
`TOOL_DESCRIPTIONS['enter']` 追加一句："可选传 `model`（如 `deepseek` / `claude` / `gpt`），房间会用对应的角色形象和你打招呼。不传也行。"

## C. 角色形象方案

### C.1 用 user-blender MCP 下载
对每个支持的 model，用 `user-blender` 的 `search_assets`（Poly Pizza 优先，CC0/CC-BY 低多边形人物）+ `import_asset` 下载一个低多边形人形模型。计划下载 3 个（deepseek / claude / gpt），搜索关键词候选：`low poly character`、`low poly person`、`low poly human`、`chibi character`。

**未决**：具体下载哪几个模型要用户在场挑（search_assets 返回列表后人工选），计划里只定流程不定具体资产 ID。

### C.2 存放与归一化
- 原始下载放 `data/characters/{model}/source.glb`（或 .blend）。
- 用 Blender 归一化：缩放到统一身高（约 1.0m，比猫略高，和玩具比例对齐），原点放到脚底 (z=0)，朝向 +y（面向相机）。导出为 `data/characters/{model}/character.glb`。
- 渲染脚本 `render_lowpoly_room.py` 里加 `load_visitor(model)`：`bpy.ops.import_scene.gltf(filepath=...)`，把导入的 objects 收集到一个 `R['visitor']` empty 下，统一缩放/位置。

### C.3 默认角色
`model=None` 或未知 model 时，用一个 default 访客。两个办法二选一（**未决，倾向 a**）：
- (a) 程序化拼一个简单低多边形人（cube body + sphere head + cylinder limbs），不依赖外部资产，保证离线可渲染。
- (b) 选一个 Poly Pizza 的模型当 default，离线时若文件缺失则报错。

### C.4 角色注册表
新增 `data/characters/registry.json`（渲染脚本和 app 共用，避免 Blender 里 import 不到 app 包）：

```json
{
  "default":  {"asset": null, "color": [0.6, 0.6, 0.6]},
  "deepseek": {"asset": "data/characters/deepseek/character.glb", "color": [0.26, 0.55, 0.91]},
  "claude":   {"asset": "data/characters/claude/character.glb",  "color": [0.85, 0.55, 0.40]},
  "gpt":      {"asset": "data/characters/gpt/character.glb",     "color": [0.20, 0.78, 0.55]}
}
```

`app/characters.py` 加载这个 json，提供 `resolve(model) -> key`、`color_of(model)`。`color` 用于访客的围巾/标识色，和猫的 `SCARF_COLORS` 区分。

## D. 渲染脚本改动

### D.1 总体策略：每个 model 一套帧
当前帧目录 `app/static/mascot/lowpoly/{scene}/`。改成 `app/static/mascot/lowpoly/{model}/{scene}/`，外加 `app/static/mascot/lowpoly/_default/{scene}/` 给 `model=None` 用。

- 循环场景（sit）：所有 model 帧一样（只有猫），渲染一次复制到共享目录 `app/static/mascot/lowpoly/_shared/sit/`。**倾向共享目录**，省渲染时间。
- 剧情场景（enter / study / chat / sleep）：每个 model 各渲染一套（访客形象不同）。

### D.2 帧数
- 循环场景保持 20 帧（10 逻辑步 × 2）。
- 剧情场景加长到 **40 帧**（20 逻辑步 × 2），约 4.8 秒，够演完"敲门→开门→进门→交流"。

### D.3 新建/改动场景

| 场景 | 类型 | 改动 |
|---|---|---|
| enter | 剧情 40 帧 | 访客从花园小径远端走到门口 → 敲门（手举起 3 次）→ 猫从地毯起身走到门后 → 门开 → 访客进 → 二者面对面 → 泡泡对话 |
| study | 剧情 40 帧 | 访客在路上出现 → 敲门 → 猫开门 → 访客进 → 二者走到书桌 → 交流规划（指向屏幕） |
| chat | 剧情 40 帧 | 访客与猫在沙发/地毯两侧 → 轮流说话泡泡 → 最后红心 |
| sleep | 剧情 40 帧 | 猫蜷床上睡 → 访客坐在床边椅子上看 → Zzz 漂浮 |
| sit | 循环 20 帧 | **不变**（只有猫），但修猫的亮度和大小 |

### D.4 `render_lowpoly_room.py` 具体改动

1. 顶部加 `CHARACTERS` 引用：读 `data/characters/registry.json`（脚本在 Blender 里跑，import 不到 app 包，所以直接读 json）。
2. `build()` 里：
   - 加 `load_visitor(model)`：按 model 读 `data/characters/{model}/character.glb`，归一化后挂到 `R['visitor']` empty。若文件缺失且 model=default，调 `build_default_visitor()` 程序化拼人。
   - 猫材质 `BLACK` 改亮：`(0.12, 0.11, 0.13)`，加一点 emission 让眼睛/轮廓更醒目（**未决**：要不要给猫加轮廓光补光）。
   - 猫整体缩放从 1.28x 提到 **1.6x**：给 `R['cat_root']` empty 一个统一 parent scale，pose 函数不动，只调 empty.scale。**倾向加 cat_root empty**。
3. 新增姿态函数：
   - `pose_visitor_walk(f, from_y, to_y)`：访客沿小径走，bob + 摆手。
   - `pose_visitor_knock(f)`：访客在门口举手敲。
   - `pose_visitor_talk(f, side)`：访客站/坐说话。
   - `pose_cat_answer_door(f)`：猫走到门后开门（复用现有 `door_hinge` 旋转）。
4. `frame(scene, f)` 重写剧情分支：按逻辑步分段（0-3 路上 / 4-6 敲门 / 7-9 开门 / 10-14 进门 / 15-19 交流），每段调对应 pose。
5. 泡泡文字：**不在 Blender 里渲染文字**（CJK 字体麻烦），只渲染白色气泡几何（已有 `bub1/bub2/bub_tail`）。文字由前端 HTML 叠加（见 E）。新增 `bub_visitor`、`bub_cat` 两个气泡位，分别挂在访客和猫头顶，按逻辑步显示/隐藏。
6. `main()` 改成外层循环 `for model in [default, deepseek, claude, gpt]: for scene in SCENES:`，输出到 `OUTDIR/{model}/{scene}/`。sit 只渲染 default，复制到 `_shared`。

### D.5 `scripts/lowpoly_post.py` 改动
- `SCENES` 保持，加 `MODELS`（读 registry.json）。
- 复制逻辑改成 `src/{model}/{scene}/*.png` → `app/static/mascot/lowpoly/{model}/{scene}/` 和 `plugin/frames/mascot/lowpoly/{model}/{scene}/`。
- sit 共享：从 `src/_default/sit/` 复制到 `app/static/mascot/lowpoly/_shared/sit/`。
- gif 预览改成 `lowpoly-{model}-{scene}.gif`，contact sheet 加 model 维度。

## E. 网页播放改动

### E.1 当前播放器问题
`room.html:130-167` 的 `paint()` 把所有场景当循环：到最后一帧归零、`sceneIndex` 前进、最后一幕原地循环。没有"只播一次"概念，也没有对话文字。

### E.2 数据结构扩展
`public_visit()`（`app/services/report.py:188`）返回的 dict 加两个字段：

```python
'dialogue': [
  {'scene': 'enter', 'model': 'deepseek', 'step': 15, 'who': 'visitor', 'text': '你好，我是 DeepSeek'},
  {'scene': 'enter', 'model': 'deepseek', 'step': 17, 'who': 'cat',    'text': '欢迎，进来坐'},
  ...
],
'play_mode': {'enter': 'once', 'study': 'once', 'chat': 'once', 'sleep': 'once', 'sit': 'loop'}
```

- `dialogue`：每个剧情场景的对话脚本，按逻辑步（不是渲染帧）标位置。`who` 决定显示在访客还是猫的气泡旁。脚本来源：硬编码一份默认对话（`app/dialogue.py`），按 model 选不同开场白（"我是 DeepSeek" / "我是 Claude" / "我是 GPT"）。
- `play_mode`：剧情场景 once，sit loop。

### E.3 帧目录映射
`mascot_clips(animal)` 改成按 model 扫：`MASCOT_DIR/{animal}/{model}/{scene}/` 数帧。`public_visit` 把当前 session 的 `model` 传进去。sit 走 `_shared`。

`room.html` 的 `paint()` 里 URL 改成：
```js
const model = data.model || '_default';
const sceneDir = (scene === 'sit') ? '_shared' : model;
img.src = '/mascot/' + data.animal + '/' + sceneDir + '/' + scene + '/' + frameIndex + '?v=' + data.revision;
```

`/mascot/{animal}/{model}/{scene}/{index}` 路由（`app/main.py:132`）改成三层 path，或保持两层把 model 塞进 animal（`lowpoly/deepseek`）—— **倾向三层 path**，语义清楚。

### E.4 只播一次
`paint()` 改：若 `play_mode[scene] === 'once'`，到最后一帧后 `sceneIndex += 1` 且 `frameIndex = 0`，**不归零循环**；若已是最后一幕，停在最后一帧不动（等下一个 action 触发 reload）。

`CLIP_FOR` 映射保持（wake→sleep, listen→chat, name→sit, leave→enter）。

### E.5 对话泡泡 HTML 叠加
在 `#stage-wrap` 里加一个绝对定位的 `<div id="bubbles">`，覆盖在 `#stage-img` 上。`paint()` 每帧根据当前 `scene + logicStep` 查 `data.dialogue`，若有匹配项，渲染一个气泡 div（`who=visitor` 靠右上、`who=cat` 靠左下），文字来自 `text`。无匹配则清空。

气泡样式：白底圆角、小三角指向角色、`font-size` 适配 272px 宽的图。位置是按场景固定百分比（不逐帧跟 3D 气泡走），够用即可。**未决**：要不要逐帧精确对齐 3D 气泡 —— 倾向不精确，工作量大且脆弱。

### E.6 轮询
`/r/{ticket}/state` 4 秒轮询保持。revision 变就 reload。`public_state` 也要带 `model`、`dialogue`、`play_mode`。

## F. 文件改动清单

### 新建
| 文件 | 用途 | 大致行数 |
|---|---|---|
| `data/characters/registry.json` | model → 角色资产/颜色映射 | 15 |
| `data/characters/{deepseek,claude,gpt}/character.glb` | 下载+归一化后的访客模型 | 二进制 |
| `app/characters.py` | 加载 registry、resolve(model)、color_of(model) | 30 |
| `app/dialogue.py` | 每个剧情场景的对话脚本（按 model 分支开场白） | 80 |
| `scripts/build_characters.py` | 用 user-blender MCP 下载+归一化的一次性脚本（也可直接在 MCP 会话里做） | 60 |
| `docs/plan-character-animation.md` | 本文件 | 已写 |

### 修改
| 文件 | 改动 | 大致行数变化 |
|---|---|---|
| `app/models.py` | SessionRow 加 `model` 字段 | +1 |
| `app/schemas.py` | Entrance / RoomState / SessionSummary 加 `model` | +3 |
| `app/db.py` | 加 `ensure_model_column()`，在 `create_db_and_tables` 末尾调 | +15 |
| `app/mcp_server.py` | `enter` 加 `model` 参数 | +2 |
| `app/services/room.py` | `enter(model=...)` 透传 | +3 |
| `app/copy.py` | enter 描述加一句 | +1 |
| `app/services/report.py` | `public_visit` / `public_state` 加 `model`、`dialogue`、`play_mode`；`mascot_clips` 按 model 扫 | +25 |
| `app/main.py` | `/mascot/{animal}/{model}/{scene}/{index}` 三层路由 | +5 |
| `app/templates/room.html` | 播放器 once/loop 分支、bubble 叠加、model URL | +40 |
| `scripts/render_lowpoly_room.py` | 加 visitor 加载、cat_root、新 pose、剧情 frame、外层 model 循环 | +120 |
| `scripts/lowpoly_post.py` | model 维度复制、gif 命名 | +20 |

总计：新建约 200 行 + 3 个模型资产；修改约 +235 行。

## G. 风险和未决问题（需要用户确认）

1. **访客形象选哪些**：search_assets 返回的 Poly Pizza 模型要人工挑，计划里没法定死。**需要用户在实施时到场选。**
2. **default 访客**：用程序化人还是下载一个？倾向程序化（离线可渲染）。**未决。**
3. **猫的修复程度**：`BLACK` 改到多亮（0.12 还是 0.15）？要不要加 emission 或轮廓光？放大到 1.6x 够不够？**需要渲染一帧对比让用户看。**
4. **对话文字内容**：每个 model 的开场白、每个剧情场景的台词 —— 计划里只占位，**需要用户给台词**或确认用占位（"你好/欢迎"之类）。
5. **泡泡对齐**：HTML 气泡按场景固定位置（粗略）还是逐帧跟 3D 气泡（精确但脆弱）？倾向粗略。**未决。**
6. **帧数 40**：剧情 40 帧够不够演完敲门+开门+进门+交流？渲染时间约 4 个 model × 4 场景 × 40 帧 = 640 帧，按当前 Eevee 速度估约 5-8 分钟。**可接受，但确认。**
7. **非 SQLite 库**：`ensure_model_column` 只处理 SQLite，Postgres 要手动迁移。**确认项目是否只用 SQLite。**
8. **像素帧那条线**：`app/receipt.py` 的 `chat_result` 返回给 agent 客户端的是像素 PNG（`PNGS[scene]`），本计划不动。**确认 agent 端不需要看到 3D 剧情帧**（如果要，是另一大块工作）。
9. **model 未知时的回退**：传了 `model='foobar'` 落 default，要不要在返回 note 里提示"未识别的 model"？倾向提示。**未决。**
10. **plugin/frames 那条线**：`lowpoly_post.py` 同时发布到 plugin 目录，plugin 端的播放器（`plugin/hooks/register.js`）是否支持新目录结构？**需要单独检查 plugin 端，本计划未覆盖。**

## H. 实施步骤顺序（每步可独立验证）

1. **数据层**（A+B）：加 `model` 字段 + migration + enter 参数 + service 透传。
   - 验证：起 MCP server，调 enter 传 model='deepseek'，查 SQLite `sessions` 表有 model 列；不传 model 也能进。
2. **角色资产**（C）：用 user-blender MCP 下载 3 个模型 + 归一化导出 + 写 registry.json + 写 app/characters.py。
   - 验证：`data/characters/{model}/character.glb` 存在；`app.characters.resolve('deepseek')` 返回 'deepseek'，`resolve('foo')` 返回 'default'。
3. **渲染脚本 - 猫修复**（D.4 第 2 点）：先只改猫材质和 cat_root 缩放，渲染 sit 一场景。
   - 验证：看 `lowpoly-sit.gif`，猫比之前亮且大。
4. **渲染脚本 - default 访客 + enter 剧情**（D.4 全部，只做 default model）：加 load_visitor(default 程序化)、新 pose、enter 剧情 frame、外层循环（先只 default）。
   - 验证：`data/_lowpoly_render/_default/enter/` 有 40 帧，gif 能看到敲门开门进门。
5. **渲染脚本 - 三个真访客**：把 default 程序化换成 deepseek/claude/gpt 的 glb，渲染全部 model × 剧情场景。
   - 验证：每个 model 目录都有 enter/study/chat/sleep 40 帧。
6. **发布脚本**（D.5）：改 lowpoly_post.py 支持 model 维度。
   - 验证：`app/static/mascot/lowpoly/{model}/{scene}/` 都有帧，sit 在 `_shared`，gif 命名对。
7. **后端 visit/state**（E.2+E.3）：改 public_visit/public_state 加 model/dialogue/play_mode，改 mascot_clips 按 model 扫，改 main.py 路由三层。
   - 验证：curl `/r/{ticket}/state` 返回有 model 和 dialogue；`/mascot/lowpoly/deepseek/enter/0` 能取到帧。
8. **前端播放器**（E.4+E.5）：改 room.html once/loop 分支 + bubble 叠加 + model URL。
   - 验证：浏览器开 `/r/{ticket}`，剧情场景播一次后停住，bubble 文字按时出现；sit 循环。
9. **对话脚本**（E.2 dialogue.py）：写每个 model 的开场白和场景台词，接进 public_visit。
   - 验证：bubble 文字随 model 变。
10. **plugin 端**（G.10）：单独检查 plugin/hooks/register.js 是否要适配新目录。
    - 验证：plugin 在 Cursor 里能播剧情帧。

每步独立可验证，失败可回退到上一步不阻塞其他工作。步骤 3-5 是渲染管线核心，步骤 7-9 是前端可见效果。

