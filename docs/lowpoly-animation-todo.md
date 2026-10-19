# Low Poly 3D 动画升级（待做，2026-10-19 起）

目标：窗口动画从「2D 生成帧 + 插值」升级为「Marvis 式 Low Poly 3D 卡通 + 图生视频连续动画」。

## 已定方案

路线 1（用户拍板）：每只动物先出 3D 极简扁平定稿图（白底、软阴影、哑光、Low Poly），再用 Seedance 图生视频做动作，拆帧循环。
- 形象：用户进门时选（现有选择逻辑保留），窗口用选定那只，状态跟 agent 走
- 第一批只做**猫**，效果满意再批量（4 动物 × 4 动作）

## 已完成素材

- 猫·睡觉定稿图：`C:\Users\dell\.cursor\projects\e-yuuka-ai-rest-room\assets\cat-lowpoly-sleep-ref.jpg`
  （画风已确认：低多边形、白底、软阴影、哑光、珊瑚红项圈）

## 待生成：3 张定稿图（文生图，1:1）

风格与睡觉那张严格一致。提示词在对话里（2026-10-18 晚），三张分别是：
- 坐着（sit）：蹲坐、尾巴卷在身侧、耳朵立、眼睁着
- 学习（study）：背对镜头坐小桌前，面对蓝灰发光显示器
- 聊天（chat）：背对微侧头，显示器上有聊天气泡
要点：项圈奶油色身体+珊瑚红项圈与睡觉图一致；桌子/显示器位置统一（右侧小桌）防动作切换跳帧。

## 待生成：4 段视频（Seedance 图生视频）

- 输入图 = 对应动作的定稿图（姿势必须一致，否则模型硬扭会崩）
- 参数：duration 4s / 720p / 1:1 / fps 24 / camerafixed true / watermark false
- 模型：seedance-1-0-lite-i2v-250428（省钱）或 seedance-1-0-pro-250528（更稳）
- 动作提示词在对话里（2026-10-18 晚）：sleep=呼吸起伏+耳朵轻颤+冒 z；sit=呼吸+眨眼+尾巴轻卷；study=屏幕滚动+歪头+眨眼；chat=气泡逐个出现+侧头+点头

## 视频到手后的接入步骤

1. ffmpeg 拆帧 + minterpolate 到 12fps，放进 `plugin/frames/mascot/cat/{sit,sleep,study,chat}/`
2. `plugin/scripts/scene_window.py`：已按 `~/.ai-rest-room-mascot` 读到的动物选目录，缺帧回退 rabbit/sit（2026-10-19 完成）；把猫的帧放进 `plugin/frames/mascot/cat/` 即生效
3. 同步到 `C:\Users\dell\.cursor\plugins\local\ai-rest-room\`
4. 窗口验证：连续播放、无任务栏图标、动作随 state 切换

## 注意

- 现有 rabbit 的 2D 帧（sit/read/look/enter/sleep/study/chat）保留作 fallback
- 用户自己跑视频生成（要花 Comfy 额度），我们只提供提示词和后续接入
