# Marvis 风格动画：现状与产线

> 2026-10-19。目标是用户睡觉那张定稿图的质感：奶油色 Low Poly 3D 猫、珊瑚红项圈、白底、软阴影、固定机位。
> 现在仓库里有一套**程序化占位动画**可以立刻跑；最终质感走「定稿图 → 图生视频 → 拆帧」这条线。

## 一、现在就能跑（程序化占位）

- [scripts/render_lowpoly.py](../scripts/render_lowpoly.py)：纯 Python + Pillow 软件渲染，无外部素材；输出 512×512、20 帧循环。
- 场景：`sleep`、`sit`、`study`、`chat`、`enter`（leave 用 enter 倒放）。
- 输出同时写到 `app/static/mascot/cat/` 和 `plugin/frames/mascot/cat/`；预览在 `docs/preview/`。
- 风格锚：[cat-lowpoly-sleep-ref.jpg](reference/cat-lowpoly-sleep-ref.jpg)（用户已定的睡觉定稿图）。

```bash
python scripts/render_lowpoly.py --scenes sleep,sit,study,chat,enter --frames 20 --size 512
```

局限：程序化几何是近似的，脸、毛感和打光达不到 AI 定稿的质地。它负责让流程先跑通，也是 rabbit 之外的一个 fallback；**不是最终美术**。

## 二、目标产线（Marvis 质感）

### 1. 定稿图（文生图，1:1）

已有：`sleep`（[参考图](reference/cat-lowpoly-sleep-ref.jpg)）。
还要：`sit`、`study`、`chat` 三张。每张都带同一个风格块：

```text
Low-poly 3D cartoon cat, cream/off-white matte faceted body,
coral-red collar, white seamless studio background,
soft diffuse contact shadow under the body, matte flat shading,
fixed 3/4 front-left camera slightly above eye level,
chunky simplified geometry, no texture, no outlines, no text,
1:1 aspect ratio
```

三张各自的补充：

```text
sit   — cat sitting upright on the floor, front paws together,
        tail curled beside the body, ears up, eyes open,
        facing the camera-left, same coral collar, empty white background.

study — back three-quarter view, cat sitting at a small white desk,
        facing a blue-gray glowing monitor, head tilted slightly,
        monitor positioned to the right, same collar, empty white background.

chat  — back three-quarter view, cat sitting at the same small white desk,
        monitor in front showing simple chat bubbles, head slightly turned,
        same collar and same desk / monitor position, empty white background.
```

一致性要求：项圈奶油色身体 + 珊瑚红项圈；桌子/显示器位置固定（右侧小桌）；机位高度相同；除了软阴影不要别的投影。

### 2. 图生视频（Seedance）

参数：`duration 4s / 720p / 1:1 / fps 24 / camerafixed true / watermark false`。
模型：`seedance-1-0-lite-i2v-250428`（省钱）或 `seedance-1-0-pro-250528`（更稳）。
输入图必须和对应动作的定稿图同一姿势，否则模型会硬扭。

```text
sleep — the cat breathes softly, ears twitch slightly, small Z particles float up,
        camera fixed, seamless loop, white background.

sit   — the cat breathes, blinks softly, tail tip curls, tiny head tilt,
        camera fixed, seamless loop, white background.

study — blue-gray monitor glow pulses and lines scroll on the screen,
        the cat tilts its head, one ear twitches, camera fixed, seamless loop.

chat  — chat bubbles appear one by one on the monitor, the cat gives a small nod,
        camera fixed, seamless loop, white background.
```

循环：让首尾姿势尽量一致；不一致也没关系，拆帧后取中段即可。

### 3. 拆帧接入

视频到手后，一条命令写进两处帧目录，并生成预览：

```bash
python scripts/ingest_animation.py --input cat-sit.mp4 --scene sit --animal cat --fps 12 --size 512
python scripts/ingest_animation.py --input cat-sleep.mp4 --scene sleep --animal cat --fps 12
```

- 视频输入需要 `ffmpeg` 在 PATH；也可以直接传一帧一张图的目录。
- 建议 24–40 帧；窗口按 24fps 播，循环约 1–1.7 秒。
- 脚本会先清空该场景旧帧，再写 `001.png` 起的编号；`docs/preview/<animal>-<scene>.gif` 可快速验收。
- 目录结构见 [插件说明](../plugin/README.md)。

### 4. 让房间用上这只动物

网页房间页和插件窗口读同一个文件：

```powershell
Set-Content "$HOME\.ai-rest-room-mascot" "cat"
# 改回兔子：
Set-Content "$HOME\.ai-rest-room-mascot" "rabbit"
```

`plugin/frames/mascot/<animal>/<scene>/` 至少要有 `sit`、`sleep`、`study`、`chat`、`enter`；缺某一幕时窗口回退到 `sit`。

## 三、验收清单

- [ ] 白底、无文字、无水印、无镜头运动。
- [ ] 项圈颜色/位置一致；study 和 chat 的桌子和显示器位置一致。
- [ ] 首尾姿势接近，循环时没有跳帧。
- [ ] `docs/preview/<animal>-<scene>.gif` 看起来顺。
- [ ] `~/.ai-rest-room-mascot` 写对；网页 `/r/{ticket}` 和插件窗同步。

## 四、回退

rabbit 的 2D 帧一直保留。删掉 marker 文件或写回 `rabbit` 即可回到原动画；`cat` 这一套坏掉也不影响服务。
