# 像素风动画

> 2026-10-20。3D 那条线（Marvis 质感）用代码拼基本体做不出猫的神态，所以另做了像素风。
> 先是纯代码手摆像素（工位版→房间版），细腻度到不了星露谷；最终换成**真实手绘素材拼贴**（现在的 `room`）。

## room（素材拼贴版，选定）

- 房间底图：[Cozy Farm Interiors](https://aquumgifts.itch.io/cozy-farm-interiors)（by Spaceyyy，免费可商用）的 2x 素材拼成 512×512：蜂蜜木地板、sage 墙纸、带窗墙块×2、带门墙块、沙发、书架、落地灯、圆地毯、猫床、盆栽、挂画、座钟。床用 4x 素材缩到 96px（2x 的床太小，猫躺不下）。
- 猫：手摆黑猫精灵（尖耳、腹影、围巾随场景换色），代码就在 `render_pixel_room.py` 里。曾经试过 [Free Cat Pack by Glem](https://octopusinkus.itch.io/cat-pack) 的素材猫，圆头小耳像小熊，弃用。
- 代码只画动态元素：桌上显示器（代码行滚动+光标）、聊天气泡、睡觉的 Z、夜晚调暗、壁炉 3 帧火苗（sleep 场景替换书架位置）。
- 场景：`enter` 猫从墙上的门正面走向地毯；`sit` 趴猫床摆尾；`sleep` 入夜+壁炉点火+猫侧躺床上飘 Z；`study` 背坐椅子看显示器；`chat` 侧坐沙发冒气泡（最后一个是红心）。
- 素材在 `assets/`（git 已忽略，许可要求不当素材包再分发；渲染产物进 git 没问题）。署名：Spaceyyy。

## pixel（纯代码手摆版，初版保留）

- 128×128 画布 ×4 → 512；白棚工位固定机位，显示器 UI 随场景变化。
- 中间还有个 256 纯代码房间版（星露谷化尝试），已被素材版取代，代码在 git 历史里。

## 生成

```bash
# 素材版（room/），需要 assets/ 里的两个素材包
python scripts/render_pixel_room.py --scenes enter,sit,sleep,study,chat --frames 20

# 工位版（pixel/），纯代码无依赖
python scripts/render_pixel.py --scenes sleep,sit,study,chat,enter --frames 20
```

都同时写到 `app/static/mascot/<名>/` 和 `plugin/frames/mascot/<名>/`，预览在 `docs/preview/<名>-*.gif` + `<名>-contact.png`。

## 切换

```powershell
Set-Content "$HOME\.ai-rest-room-mascot" "room"
# 或启动前：
$env:AI_REST_ROOM_MASCOT = "room"
```

可选值：`room`（像素房间）、`pixel`（像素工位）、`studio`（Blender 影棚）、`cat`（Low Poly 占位）、`rabbit`（最初的兔子）。

## 想调的话

- 调色板：两个脚本顶部常量（`FLOOR` / `RUG` / `SCARF` 等）。
- 房间布局：`render_pixel_room.py` 里 `bed()` / `sofa()` / `desk()` 等函数，坐标都是 256 网格整数。
- 猫精灵：`cat_back()`（背面走路）/ `cat_front()`（正面坐）/ `cat_side()`（侧面）/ `cat_sleeping()`（蜷缩），尺寸 ~40px。
- 场景编排：`frame_enter()` 等五个函数；走路路径在 `frame_enter` 的插值里。
- 夜晚效果：`apply_night()` 的整体调暗 + `windows(night=True)` 的月亮星星。
- 播放器不用动：`scene_window.py` 自动读 mascot 目录，缺失场景回落 `sit`。
