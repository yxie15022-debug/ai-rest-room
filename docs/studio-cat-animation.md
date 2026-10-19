# Studio 黑猫动画：风格与产线

> 2026-10-19。当前选定的动画风格：白棚里一只黑色剪影猫，坐在白色工位前，脖子上围着一条彩色围巾，
> 显示器上是随场景变化的蓝色 UI，地面只有一层很软的灰影。固定机位，从背后略高处看。

参考图：[studio-cat reference](https://)（用户 2026-10-19 提供的六格风格参考；仓库预览见 `docs/preview/studio-contact.png`）。

## 一、风格拆解

- **场景**：纯白无缝影棚，白色桌面 + 细桌腿、白色边柜、白色五爪转椅、白色显示器，几乎没纹理，只有极淡的灰边。
- **角色**：纯黑猫剪影（不画毛、不画高光），只保留圆头、两只三角耳、两条搭在桌上的胳膊、圆身体；睡觉时头歪向一侧，露出闭眼和鼻子。
- **围巾**：粗粗一条彩色布，绕在脖子上；颜色随场景变化（学习蓝、聊天红、坐着绿、睡觉蓝紫、进门黄）。
- **显示器**：小屏 UI 随场景换：文件列表、折线图看板、聊天气泡、黑屏月亮、开机进度。
- **光**：高键、极软；桌面和地面各一层大而淡的接触阴影，没有明显方向光。
- **机位**：固定 3/4 背后略高处，猫挡住显示器下半部分。

## 二、现在就能跑：程序化版本

[scripts/render_studio.py](../scripts/render_studio.py)：Pillow 画的 2.5D 场景，不需要外部素材，输出 512×512 / 20 帧循环：

```bash
python scripts/render_studio.py --scenes sleep,sit,study,chat,enter --frames 20
```

- 写到 `app/static/mascot/studio/` 和 `plugin/frames/mascot/studio/`，预览在 `docs/preview/studio-*.gif`。
- 动画：呼吸、点头、耳朵轻微抽动、围巾颜色按场景、屏幕 UI 内容动（折线、气泡、进度条、月亮）、睡觉飘 Z、进门淡入。
- 切换：`AI_REST_ROOM_MASCOT=studio`（或把 `studio` 写进 `~/.ai-rest-room-mascot`）。rabbit 仍可回退。

## 三、如果要 AI 生成同款（更接近参考图的 3D 质感）

### 1. 定稿图（文生图，1:1）

统一风格块：

```text
minimal 3D render, pure white seamless studio, soft diffuse contact shadow,
a black cat silhouette sitting on a white rolling chair at a white desk,
seen from behind at a fixed 3/4 high camera, a thick pastel scarf around the neck,
a white monitor on the desk showing a simple blue UI, no text, no watermark,
matte flat shading, clean geometry, 1:1 aspect ratio
```

四张的动作/屏幕：

```text
sit   — cat sitting upright, paws on desk, monitor showing a calm file-list UI, mint green scarf.
study — cat leaning slightly toward the monitor, monitor showing a blue chart dashboard, blue scarf.
chat  — cat with head slightly tilted, monitor showing a chat window with bubbles, coral red scarf.
sleep — cat's head tilted to one side, eyes closed, monitor dark with a small moon, periwinkle scarf.
```

### 2. 图生视频（Seedance）

`duration 4s / 720p / 1:1 / fps 24 / camerafixed true / watermark false`，模型 `seedance-1-0-lite-i2v-250428`（省钱）或 `seedance-1-0-pro-250528`。

```text
sit   — the cat breathes gently, one ear twitches, the monitor list scrolls a little,
        camera fixed, soft shadows, seamless loop.
study — chart line grows and bars pulse, the cat tilts its head, ear twitch, camera fixed.
chat  — chat bubbles appear one by one on the monitor, the cat gives a small nod, camera fixed.
sleep — slow breathing, head tilted, Z letters float up, the dark monitor's moon dims, camera fixed.
```

### 3. 拆帧接入

```bash
python scripts/ingest_animation.py --input studio-study.mp4 --scene study --animal studio --fps 12 --size 512
```

脚本会清空 `studio/` 下该场景旧帧、同时写 app 与 plugin 两处，并生成 `docs/preview/studio-<scene>.gif`。

### 4. 切换

```powershell
Set-Content "$HOME\.ai-rest-room-mascot" "studio"
# 或环境变量
$env:AI_REST_ROOM_MASCOT = "studio"
```

## 四、验收清单

- [ ] 纯白背景、无文字/水印、机位完全固定。
- [ ] 猫保持纯黑剪影；围巾颜色/位置一致且不闪烁。
- [ ] 显示器 UI 每幕不同，但窗口/边框风格一致。
- [ ] 阴影软、没有硬边；首尾姿势接近，循环不跳。
- [ ] 窗口和房间页同步（同一 `~/.ai-rest-room-mascot` / 环境变量）。

## 五、取舍

- 程序化版本是即时可跑、可改色/改 UI 的近似；AI 定稿图的质感更好，但需要外部生成。
- 参考图里围巾颜色和屏幕内容每张都不同，程序化版本按场景固定颜色；想让围巾在循环里变色，改 `SCARF` 字典或按帧插值即可。
