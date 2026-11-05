# 角色形象 + 剧情动画 计划 审核结论

> 2026-10-29。审核 `docs/plan-character-animation.md`，对照实际代码。不实施代码，只给结论。

## A. 总体判断：可行，但有 3 个必须先修的点

计划对代码现状的描述准确（关键事实章节经逐条核对均属实），用户需求 ①-⑤ 都有对应改动点覆盖，步骤顺序基本合理。**总体可行**，但实施前必须先解决以下三件事：

1. **测试更新缺失**：`tests/test_animation.py` 的 `LowPolyAnimationTest` 直接扫 `APP_LOWPOLY / scene`（2 层）并断言 `mascot_clips('lowpoly')` 返回 `scene -> count`。改成 3 层 + model 维度后这两类断言全断。计划完全没提测试改动。
2. **访客姿态假设过强**：`pose_visitor_walk / knock / talk` 要求能动访客的手臂/腿。但 Poly Pizza 的 CC0 低多边形人形模型绝大多数是静态整身 mesh、无 armature，只能整体平移旋转，不能举手敲、不能摆手走。计划只把"程序化拼人"留给 default，三个真访客默认能摆姿势——这个假设大概率落空。
3. **`mascot_clips` 签名变更未理清**：从 `mascot_clips(animal) -> dict[scene,int]` 改成"按 model 扫"会牵连 `public_visit`、`latest_view`、`public_state` 以及 `tests/test_rest.py` 的 `MascotClipTest`。计划只在 E.3 一笔带过，没说新签名、没说旧调用点怎么改、没说向后兼容。

## B. 必须修的问题（实施前要改计划）

### B1. 测试策略要写进计划

现状（`tests/test_animation.py:127-143`）：`LowPolyAnimationTest` 遍历 `SCENES` 扫 `APP_LOWPOLY / scene`，并断言 `mascot_clips('lowpoly')` 每个 scene 至少 10 帧、`lowpoly-{scene}.gif` 存在。改成 3 层后这些都断。计划必须补一节"测试改动"：

- `LowPolyAnimationTest` 改成遍历 `registry.json` 里的每个 model + `_default` + `_shared`，扫 `APP_LOWPOLY / model / scene`，断言每个剧情场景 40 帧、sit 20 帧。
- `mascot_clips` 签名变了，`MascotClipTest`（`tests/test_rest.py:137-145`）和 `test_animation.py` 里所有 `mascot_clips('lowpoly')` / `mascot_clips('cat')` 调用都要改。
- GIF 命名从 `lowpoly-{scene}.gif` 改成 `lowpoly-{model}-{scene}.gif` 后，要么保留旧名生成一份兼容、要么同步改测试断言。`lowpoly-all.gif` 和 `lowpoly-contact.png` 也要重新定义（contact sheet 加 model 维度）。
- `test_chat_window_app`（`tests/test_ticket.py:178-184`）检查 `plugin/frames/sit/0.png`——这是顶层 `sit/`，不是 `mascot/lowpoly/sit/`，不受影响，不用动。

### B2. 访客姿态可行性要降级

计划 D.4 第 3 点列了 `pose_visitor_walk / knock / talk`，要求举手、摆手。但：

- `user-blender` 的 `search_assets(source='polypizza')` 返回的 CC0 低多边形人形通常是单 mesh、无骨骼（已确认 tool schema：`import_asset` 只下载并放入场景，`target_size` 归一尺寸，不保证可绑骨）。
- 没有 armature 的模型，`pose_visitor_knock`（举手）只能靠整体旋转或缩放整个访客，视觉上不像"敲门"。
- 计划 C.3 的"程序化拼人（cube+sphere+cylinder）"反而可以做 limb posing，因为各部位是独立 mesh。

**建议把计划改成二选一**：

- (a) **所有访客都用程序化拼人**，只是按 model 换颜色/比例/配饰（deepseek 蓝、claude 橙、gpt 绿）。这样姿态函数对每个 model 都能跑，离线可渲染，不依赖 Poly Pizza。Poly Pizza 下载退化为"可选美化"。
- (b) **下载模型只做整体平移**，姿态函数降级为 `pose_visitor_translate(f, from_y, to_y)` + `pose_visitor_bob(f)`，不举手不摆手。"敲门"改成访客整体前倾/后撤暗示。剧情靠镜头和泡泡文字撑，不靠肢体。

倾向 (a)：用户要的是"每个模型一个角色"，区分度靠颜色和配饰比靠肢体动作更稳。计划现在的写法（下载模型 + 完整肢体 pose）是两者最差的组合。

### B3. `mascot_clips` 签名和调用点要写清

计划 E.3 说"`mascot_clips(animal)` 改成按 model 扫"，但没给新签名。现状调用点（已 grep 确认）：

- `app/services/report.py:214`：`'clips': mascot_clips(mascot_animal())`（在 `public_visit` 里）
- `tests/test_rest.py:139`：`mascot_clips('rabbit')`
- `tests/test_animation.py`：每个 animal 一处

`public_visit` 拿到的 `session.model` 在同一次调用里，但 `mascot_clips` 现在只收 animal。计划必须明确：

- 新签名建议 `mascot_clips(animal, model) -> dict[scene, int]`，内部按 `(animal, model, scene)` 扫，sit 走 `_shared`。
- `public_visit` 改成 `mascot_clips(mascot_animal(), session.model or '_default')`。
- `latest_view` 走 `public_visit`，自动带 model；`public_state` 同样。
- 旧测试 `mascot_clips('rabbit')` 要么加默认 model 参数兼容、要么改调用。

不写清这层，步骤 7 一改 `public_visit`，`latest_view` 和 `/now/state` 就拿不到 clips，前端图全 404。

## C. 建议但非必须的改进

### C1. `ensure_model_column` 加表存在检查

计划 A.3 的代码直接 `PRAGMA table_info(sessions)`，若表不存在（极端情况），columns 为空集，`'model' not in columns` 会触发 `ALTER TABLE sessions ADD COLUMN` 报错。现有 `ensure_ticket_column`（`app/db.py:28-37`）先查 `sqlite_master` 确认表存在再 PRAGMA。建议照抄这个守卫。实际触发概率低（create_all 先跑），但对称性和健壮性更好。

### C2. `leave` 场景语义

现状 `CLIP_FOR = {wake:'sleep', listen:'chat', name:'sit', leave:'enter'}`（`room.html:135`）。`leave` 复用 `enter` 帧。改完 enter 后 enter 是"访客敲门进来"，leave 还放这个就是"访客又敲门进来"——语义反了。计划没提。建议：要么给 leave 单独渲染一套"访客出门回头挥手"的 40 帧，要么把 `CLIP_FOR.leave` 改成一个新的 `leave` 场景。非阻塞，但用户看会觉得别扭。

### C3. 报告里记一笔 model

`app/services/report.py` 的 `TEMPLATE`（第 49 行起）记录 ticket / self_name / 时间线，没有 model。访客形象是会话的一个属性，写在报告头一行（"访客形象：deepseek"）对未来回看有用。改动 1 行。可选。

### C4. registry.json 双读要加测试

计划让渲染脚本（Blender 内）和 `app/characters.py` 都直接读 `data/characters/registry.json`（因为 Blender 里 import 不到 app 包）。两处独立读同一份 json，容易漂移。建议加一个测试：`app.characters.resolve` 的结果和渲染脚本读出来的 key 集合一致。可选。

### C5. default 访客目录命名统一

计划用 `_default` 放 default 访客的剧情帧，用 `_shared` 放 sit。但 default 访客的 sit 也走 `_shared`。命名前缀 `_` 容易和未来真名叫 `_default` 的 model 撞。建议把目录改成 `_default/{scene}` 和 `_shared/sit`，并在 `mascot_clips` 里把以 `_` 开头的目录当特殊目录处理（不当成 model 名）。计划已经隐含这个意思，写明即可。

## D. 遗漏的关键点

### D1. plugin 端播放器其实不播 3D 帧（计划的担心错位）

计划 G.10 担心 `plugin/hooks/register.js` 是否支持新目录结构。实际读 `register.js`：它只读 `DATA.scenes[id]`（硬编码在 js 里的 ASCII 像素帧，`register.js:1` 那个 DATA 常量），**完全不读 `plugin/frames/mascot/lowpoly/*.png`**。所以 3D 帧目录从 2 层改 3 层对 plugin 播放没有任何影响。

`lowpoly_post.py` 之所以镜像 PNG 到 `plugin/frames/mascot/lowpoly/`，只是为了让 `tests/test_animation.py` 的 `test_*_frames_and_mirror` 断言 app 和 plugin 两边帧数相等。所以步骤 10 真正要做的是：

- 确认 `lowpoly_post.py` 把 3 层结构原样镜像过去（计划 D.5 已覆盖）。
- 更新 `test_animation.py` 的 mirror 断言走 3 层（B1 已覆盖）。
- `register.js` **不用动**。

计划把这条列为"单独检查 plugin 端"是个小误判，但结论方向对（要检查）。审核建议把步骤 10 的描述改成"更新 test_animation.py 的 mirror 断言"，而不是"检查 register.js"。

### D2. 像素帧那条线确实不用动（已确认）

`app/receipt.py:42` 的 `chat_result` 用 `PNGS[scene]`（来自 `gifscene.py`，ASCII 像素渲染成 PNG），是给 agent 客户端看的。本计划只动 3D 帧（`scripts/render_lowpoly_room.py` → `app/static/mascot/lowpoly/`）。两条线独立。计划 G.8 的判断正确。**但**用户需求 ⑤"对话泡泡"在像素帧那条线上是已经有的（`register.js` 的 `DATA.scenes.chat` 里能看到形状泡泡），只是没文字。如果用户希望 agent 客户端也看到台词文字，那是另一块工作（要在 `chat_result` 的 text content 里加台词）。计划没问这个，建议补一句确认。

### D3. 渲染时间估计偏乐观

计划 G.6 估 640 帧 5-8 分钟。实际 `render_lowpoly_room.py` 现在每帧 Eevee Next 512x512，含植被（60+ 草丛、12 灌木、18 花、9 路石、12 路灯）和 herringbone 图纹理。当前 5 场景 × 20 帧 = 100 帧的实测时间没在计划里给。按经验 512 平方 Eevee Next 含这种几何量，单帧 0.3-0.8 秒，640 帧约 3-9 分钟，**但加访客 glb（多几千面）会拉长**。建议步骤 3 先实测单帧耗时，再外推。非阻塞，但计划 G.6 应写"先测单帧再估"而不是直接给 5-8 分钟。

### D4. 访客 glb 的材质/纹理处理没提

计划 C.2 说"归一化缩放/原点/朝向"，没提材质。Poly Pizza 的 glb 自带 PBR 材质，导入后可能和场景的 `mat()` 风格不一致（玩具低多边形 vs PBR 真实感）。如果访客是 PBR 真实人，猫是 `(0.055,0.052,0.062)` 平涂，风格会割裂。建议在 `load_visitor` 里把访客材质替换成场景的 `mat()` 平涂风格，或至少统一 roughness。计划 D.4 第 2 点只提了猫材质，没提访客材质。

### D5. 多访客并发

`mcp_server.enter` 可被多个 agent 并发调用。每个 session 一个 model。网页按 ticket 看自己的访客。但渲染是离线一次性出 4 个 model 的帧，运行时只是选目录。所以并发不是问题。计划隐含了这点，没写明，建议在 D.1 总体策略里加一句"运行时不渲染，只选目录，并发安全"。

## E. 需要用户确认的未决问题（从计划的 10 个里挑真正必须问的）

计划的 10 个未决里，**必须问用户的只有 3 个**，其余可以由实施者定或自动验证：

### 必须问用户：

- **#1 访客选哪些具体模型**：`search_assets` 返回列表后要人工挑。这个无法自动定，必须用户到场。**但**前提是 B2 决定走"下载模型"路线。若按审核建议走"程序化拼人 + 换色"，#1 就消失了，用户只需确认 3 个 model 的代表色（计划已给候选：deepseek 蓝 / claude 橙 / gpt 绿）。
- **#4 对话台词**：每个 model 的开场白和剧情台词，要么用户给、要么确认用占位（"你好/欢迎/我是 DeepSeek"）。这个必须问，否则步骤 9 写不下去。
- **#3 猫修复程度**：`BLACK` 改多亮、放大到多少。这个必须渲染一帧给用户看一眼定。计划步骤 3 的验证方式（看 gif）就是干这个，对的。

### 可以由实施者定、不必问：

- **#2 default 访客**：审核建议改成"所有访客程序化"，#2 自动消解。
- **#5 泡泡对齐**：粗略即可，实施者定。
- **#6 帧数 40**：够演完敲门+开门+进门+交流，实施者按剧情分 5 段每段 8 逻辑步即可。
- **#7 非 SQLite**：项目默认 SQLite（`app/config.py` 的 `database_url` 默认 sqlite），`ensure_ticket_column` 也只处理 SQLite，照搬即可。
- **#8 像素帧不动**：已确认不用动。
- **#9 model 未知回退提示**：在返回 note 里加一句即可，实施者定。
- **#10 plugin 端**：见 D1，register.js 不用动，只剩 test_animation mirror 断言要改。

## F. 推荐的实施顺序调整

计划的 10 步顺序基本合理，建议三处微调：

1. **步骤 1 拆成 1a + 1b**：1a 是 `models.py` + `schemas.py` + `db.py` 加 model 字段和 migration（纯数据层，不改 service）；1b 是 `mcp_server.enter` 加参数 + `room.enter(model=)` 透传。1a 可以独立合入（不破坏任何东西），1b 改了 MCP 工具签名要确认 agent 端兼容。分开便于回滚。

2. **步骤 3 后插一个"单帧耗时实测"**：在步骤 3 渲染 sit 一场景时，记下单帧耗时，外推 640 帧总时间，写到计划 G.6。若超 15 分钟，回头和用户确认是否减帧数或减 model 数。

3. **步骤 10 改名**：从"检查 plugin/hooks/register.js"改成"更新 tests/test_animation.py 的 mirror 和 clips 断言"。register.js 不用动（D1）。

4. **B2 的决策要在步骤 2 之前做**：步骤 2 现在是"下载 3 个模型 + 归一化"。若按审核建议走程序化，步骤 2 改成"写程序化访客生成函数 + registry.json + app/characters.py"，不依赖 user-blender MCP，离线可做，且步骤 5 不再有"下载模型能不能摆姿势"的风险。这一步定下来之前不要开始步骤 3-5。

## G. 用户需求覆盖核对

| 用户需求 | 计划覆盖 | 备注 |
|---|---|---|
| ① 每个模型一个角色 | ✅ A+B+C 全覆盖 | model 参数 → 访客形象；区分度靠颜色（C4 registry） |
| ② 进门动画是访客敲门开门交流 | ✅ D3 enter 剧情 40 帧 | 注意 B2：敲门动作能否实现取决于访客是否可动 |
| ③ 睡觉时访客在旁看 | ✅ D3 sleep 剧情 | 猫蜷床上睡 + 访客坐床边椅看 + Zzz |
| ④ 学习时访客有对应动作 | ✅ D3 study 剧情 | 访客敲门进 → 走到书桌 → 交流规划（指向屏幕） |
| ⑤ 对话泡泡 | ✅ E5 HTML 叠加 | 3D 渲白色气泡几何 + 前端 HTML 文字叠加；按 logicStep 显示 |

五条需求都有对应改动点，无遗漏。唯一风险点是 ②④的"访客动作"在下载模型上能否做出来（见 B2）。

## H. 一句话结论

计划可行，但实施前必须：(1) 补测试改动一节；(2) 把"访客姿态"从"下载模型 + 肢体 pose"降级为"程序化拼人 + 换色"或"下载模型 + 整体平移"；(3) 写清 `mascot_clips` 新签名和所有调用点。然后按调整后的步骤 1a → 1b → 2 → 3（含单帧测时）→ 4 → 5 → 6 → 7 → 8 → 9 → 10（改测试）实施。
