# 像素风动画

> 2026-10-20。3D 那条线（Marvis 质感）用代码拼基本体做不出猫的神态，所以另做了像素风：低分辨率、有限调色板、手摆像素，简单形状也能显得完整。

## 现在是什么

- 逻辑画布 128×128，最近邻 ×4 → 512×512；20 帧循环（10 个逻辑步 ×2）。
- 场景：`sit` / `study` / `chat` / `sleep` / `enter`，构图和 `studio` 一致：白棚、白桌、显示器、转椅、黑猫、彩色围巾。
- 像素细节：蓝色显示器 UI（文件列表 / 折线图 / 聊天气泡 / 黑屏月亮 / 开机进度）、围巾随场景换色、呼吸/耳朵抽动、睡觉飘 Z、进门时猫从第 3 帧出现。

## 生成

```bash
python scripts/render_pixel.py --scenes sleep,sit,study,chat,enter --frames 20
```

写到 `app/static/mascot/pixel/` 和 `plugin/frames/mascot/pixel/`，预览 `docs/preview/pixel-*.gif` + `pixel-contact.png`。

## 切换

```powershell
Set-Content "$HOME\.ai-rest-room-mascot" "pixel"
# 或启动前：
$env:AI_REST_ROOM_MASCOT = "pixel"
```

想换回 3D 就写 `studio`，回兔子写 `rabbit`。

## 想调的话

- 调色板：`scripts/render_pixel.py` 顶部常量（BG / WHITE / BLACK / SCREEN_BLUE / SCARF）。
- 构图：`desk()` / `monitor()` / `cat()` / `chair()` 里的坐标都是 128 网格上的整数。
- 动画节奏：`frame(scene, logic)` 里的 `bob` / `head_drop` / 取模条件；输出帧数由 `--frames` 控制。
- 想让像素风更「房间」一点（木地板、暖灯、书架），改 `background()` / `desk()` 即可，不用动播放器。
