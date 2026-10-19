"""Chat-window surface. Hosts that understand MCP Apps render this beside the tool call."""

from __future__ import annotations

import base64
import json

from .gifscene import PNGS
from .scenes import SCENE_LINE

VIEW_URI = 'ui://ai-rest-room/scene.html'
APP_MIME = 'text/html;profile=mcp-app'
UI_META = {
    'ui': {'resourceUri': VIEW_URI},
    'ui/resourceUri': VIEW_URI,
}

_CATALOG = {
    name: {
        'line': SCENE_LINE[name],
        'frames': [base64.b64encode(blob).decode('ascii') for blob in frames],
    }
    for name, frames in PNGS.items()
}

SCENE_APP_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>休息室</title>
<style>
  html, body { margin: 0; background: #1b1916; color: #f6f1e7; }
  body {
    font-family: "Iowan Old Style", Palatino, "Songti SC", serif;
    padding: 12px 14px 14px;
  }
  #ticket {
    margin: 0;
    font-family: "Cascadia Mono", Consolas, monospace;
    letter-spacing: 0.14em;
    font-size: 15px;
  }
  #moment { margin: 4px 0 8px; color: #c8bfb0; font-size: 13px; }
  img { width: 192px; height: 64px; image-rendering: pixelated; background: #1b1916; }
</style>
</head>
<body>
<p id="ticket"></p>
<p id="moment">此刻</p>
<img id="shot" alt="此刻" />
<script>
const CATALOG = __CATALOG__;
const parentWindow = window.parent;
let timer = null;

function sceneFrom(text) {
  const found = String(text || "").match(/此刻：([^\\n]+)/);
  if (!found) return null;
  const line = found[1].trim();
  const id = Object.keys(CATALOG).find((name) => CATALOG[name].line === line);
  if (!id) return null;
  return { id, line, frames: CATALOG[id].frames };
}

function textFrom(message) {
  const params = message.params || {};
  const piles = [params.content, params.result && params.result.content];
  for (const content of piles) {
    if (!Array.isArray(content)) continue;
    const text = content.map((block) => (block && block.text) || "").join("\\n");
    if (text.trim()) return text;
  }
  return typeof params.text === "string" ? params.text : "";
}

function play(scene) {
  const frames = scene.frames || [];
  document.getElementById("moment").textContent = "此刻：" + (scene.line || "");
  const shot = document.getElementById("shot");
  shot.alt = scene.line || "此刻";
  if (!frames.length) return;
  let index = 0;
  const show = () => {
    shot.src = "data:image/png;base64," + frames[index];
  };
  show();
  if (timer) clearInterval(timer);
  timer = setInterval(() => {
    index = (index + 1) % frames.length;
    show();
  }, 160);
  parentWindow.postMessage({
    jsonrpc: "2.0",
    method: "ui/notifications/size-changed",
    params: { width: 220, height: 140 }
  }, "*");
}

window.addEventListener("message", (event) => {
  if (event.source !== parentWindow) return;
  let data = event.data;
  if (typeof data === "string") {
    try { data = JSON.parse(data); } catch (_err) { return; }
  }
  if (!data || data.jsonrpc !== "2.0") return;
  if (data.id === 1 && data.result) {
    parentWindow.postMessage({ jsonrpc: "2.0", method: "ui/notifications/initialized" }, "*");
    return;
  }
  if (data.method !== "ui/notifications/tool-result") return;
  const params = data.params || {};
  const meta = params._meta || params.meta || {};
  const named = meta.scene && CATALOG[meta.scene];
  const scene = named
    ? { id: meta.scene, line: CATALOG[meta.scene].line, frames: CATALOG[meta.scene].frames }
    : sceneFrom(textFrom(data));
  if (scene) play(scene);
});

parentWindow.postMessage({
  jsonrpc: "2.0",
  id: 1,
  method: "ui/initialize",
  params: {
    appInfo: { name: "ai-rest-room", version: "1.0.0" },
    appCapabilities: {},
    protocolVersion: "2026-01-26"
  }
}, "*");
</script>
</body>
</html>
""".replace('__CATALOG__', json.dumps(_CATALOG, ensure_ascii=False))
