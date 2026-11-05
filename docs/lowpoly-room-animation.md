# Low Poly 3D 房间动画（选定路线）

> 2026-10-20。美术方向定案：走 Marvis 式 Low Poly 3D。房间和猫全部在 Blender 里建模，Eevee 渲染序列帧。
> 像素房间（room）保留为可切换的备选风格。

## 管线

```bash
# 渲染 5 场景 × 20 帧（Eevee，约 1 分钟）
& "C:\Users\dell\AppData\Local\Programs\blender-4.2.4-windows-x64\blender.exe" `
    --background --python scripts/render_lowpoly_room.py -- `
    --frames 20 --outdir data/_lowpoly_render

# 发布到 app/static/mascot/lowpoly + plugin/frames/mascot/lowpoly，并生成预览
python scripts/lowpoly_post.py
```

- [render_lowpoly_room.py](../scripts/render_lowpoly_room.py)：场景库 + 猫姿态库 + 帧编排，全部程序化（无外部模型依赖）。
- [lowpoly_post.py](../scripts/lowpoly_post.py)：复制帧 + 生成 `lowpoly-{scene}.gif` 和 `lowpoly-contact.png`。

## 场景

- 房间：木地板、鼠尾草绿后墙（两窗+门）、大床、书桌+发光显示器、沙发、圆地毯、壁挂书架、落地灯、盆栽。正交 3/4 机位。
- 猫：玩具比例黑猫（大圆头、圆耳、带高光的绿眼睛、卷尾），围巾随场景换色。
- `enter`：门开，猫正面 bob 着走到地毯坐下
- `sit`：正面坐，呼吸（身体缩放）+ 眨眼（眼睛压扁+高光消失）+ 耳朵抖
- `sleep`：夜晚（冷光+深蓝窗+窗外月亮+落地灯暖光），猫蜷在床上呼吸，3 个 Z 字漂浮上升
- `study`：背对坐椅子看显示器（屏幕发光），偶尔歪头
- `chat`：侧坐沙发，3D 气泡逐个冒出（最后一个带红心）

## 切换

```powershell
Set-Content "$HOME\.ai-rest-room-mascot" "lowpoly"   # 3D 房间（当前）
Set-Content "$HOME\.ai-rest-room-mascot" "room"      # 像素房间（备选）
```

## 想调的话

- 调色板/围巾色：脚本顶部常量。
- 房间布局：`build()` 里的 `cube/sphere/...` 坐标（米为单位）。
- 猫姿态：`pose_sit / pose_walk / pose_sleep / pose_study / pose_chat`，每帧重算部件位置。
- 昼夜：`set_day() / set_night()`（灯光能量与颜色、窗玻璃材质、月亮、落地灯）。
- 帧数：`--frames 20`（>10 时按 2 帧一逻辑步重复）。

## 注意

- Blender 是便携版 4.2.4（`%LOCALAPPDATA%\Programs\blender-4.2.4-windows-x64`），批处理渲染不需要开 GUI。
- 节点查找一律按 `type == 'BSDF_PRINCIPLED'`，不按名字（会本地化）。
