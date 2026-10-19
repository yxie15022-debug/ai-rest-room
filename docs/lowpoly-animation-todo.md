# Low Poly 3D 动画升级（Marvis 风格）

> 2026-10-19 后记：用户随后把目标风格改成了「白棚黑猫工位」，见 [studio-cat-animation.md](studio-cat-animation.md)；
> 本文档保留为低多边形奶油猫路线的记录，那套 `cat` 帧仍可作为可选动画。
>
> 2026-10-19 更新。目标：窗口动画从「2D 生成帧 + 插值」升级为「Marvis 式 Low Poly 3D 卡通 + 图生视频连续动画」。
> 风格锚：奶油色 Low Poly 猫、珊瑚红项圈、白底、软阴影、固定机位。定稿参考：`docs/reference/cat-lowpoly-sleep-ref.jpg`。

## 现在到哪了

- ✅ 窗口/网页按 `~/.ai-rest-room-mascot` 选动物，缺帧回退 `sit`；rabbit 作为 fallback 保留。
- ✅ 程序化占位动画：`scripts/render_lowpoly.py`，纯 Python + Pillow，输出 512×512 / 20 帧循环的 `cat/{enter,sit,sleep,study,chat}`；预览在 `docs/preview/`。
- ✅ 拆帧导入：`scripts/ingest_animation.py`，视频或图片序列 → `app/static/mascot/` + `plugin/frames/mascot/` 两处，自动清旧帧、生成预览 GIF。
- ✅ 提示词与产线文档：`docs/marvis-animation.md`（定稿图风格块、四段动作提示词、Seedance 参数、验收清单）。
- ⬜ 3 张定稿图：sit / study / chat（sleep 已有）。
- ⬜ 4 段 Seedance 视频：sleep / sit / study / chat。
- ⬜ 用拆帧替换占位帧，并在窗口里验收循环和换幕。

## 已完成素材

- 猫·睡觉定稿图：`docs/reference/cat-lowpoly-sleep-ref.jpg`（从用户此前生成的参考图复制入库）。
- 风格要点：低多边形、白底、软阴影、哑光、珊瑚红项圈、奶油色身体。

## 待生成：3 张定稿图（文生图，1:1）

风格与睡觉那张严格一致，提示词见 [marvis-animation.md](marvis-animation.md)。三张分别是：

- 坐着（sit）：蹲坐、尾巴卷在身侧、耳朵立、眼睁着，面向镜头左前方。
- 学习（study）：背对镜头坐小桌前，面对蓝灰发光显示器，头微偏。
- 聊天（chat）：背对微侧头，显示器上有聊天气泡。

要点：项圈奶油色身体 + 珊瑚红项圈与睡觉图一致；桌子/显示器位置统一（右侧小桌）防动作切换跳帧。

## 待生成：4 段视频（Seedance 图生视频）

- 输入图 = 对应动作的定稿图（姿势必须一致，否则模型硬扭会崩）。
- 参数：duration 4s / 720p / 1:1 / fps 24 / camerafixed true / watermark false。
- 模型：`seedance-1-0-lite-i2v-250428`（省钱）或 `seedance-1-0-pro-250528`（更稳）。
- 动作提示词在 [marvis-animation.md](marvis-animation.md)：sleep 呼吸/耳朵/Z；sit 呼吸/眨眼/尾巴；study 屏幕滚动/歪头；chat 气泡逐个出现/侧头点头。
- 循环：首尾姿势尽量一致；不一致就取中段拆帧。

## 视频到手后的接入步骤

1. ffmpeg 拆帧（或直接用 `scripts/ingest_animation.py`，内部会调用 ffmpeg）：
   `python scripts/ingest_animation.py --input cat-sit.mp4 --scene sit --animal cat --fps 12 --size 512`
2. `plugin/scripts/scene_window.py`：已支持按 `~/.ai-rest-room-mascot` 选目录，缺帧回退 rabbit/sit（2026-10-19 完成）。
3. 同步到本机插件目录（如 `C:\Users\dell\.cursor\plugins\local\ai-rest-room\`），或在仓库里直接装插件。
4. 窗口验证：连续播放、无任务栏图标、动作随 state 切换、循环无跳帧。
5. 把 `~/.ai-rest-room-mascot` 写成 `cat`（或先写 `rabbit` 回退）。

## 注意

- 现有 rabbit 的 2D 帧保留作 fallback。
- 程序化占位渲染器不是最终美术；它保证流程先跑通，也方便在没有视频素材时继续开发。
- 视频生成由用户自己跑（花 Comfy 额度），仓库只提供提示词、导入脚本和接入代码。
