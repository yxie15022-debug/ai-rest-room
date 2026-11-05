/* Wires the stage to a visit.
 *
 *   /static/anim/stage.html?ticket=ABCD-EFGH   follow a real visit, live
 *   /static/anim/stage.html?follow=now         follow whoever is in the room
 *   /static/anim/stage.html?scene=enter        rehearse one scene on a loop
 */

import { Stage, clamp } from './stage.js';
import { Director, SCENES, sceneFor } from './scenes.js';

const params = new URLSearchParams(location.search);
const TICKET = (params.get('ticket') || '').toUpperCase();
const FOLLOW_NOW = params.get('follow') === 'now';
const TEACHER = 'deepseek';

const host = document.getElementById('stage');
const veil = document.getElementById('veil');
const caption = document.getElementById('caption');

// In the desktop-pet window there is no title bar to close, so the page offers
// the only way out. pywebview hands the window over as `window.pywebview.api`.
if (params.has('pet')) {
  document.body.classList.add('pet');
  // The root element paints the viewport, so it has to be told as well: a
  // background here is what shows through the window's clip wherever the page
  // itself draws nothing.
  document.documentElement.classList.add('pet');
  const shut = document.getElementById('shut');
  shut.hidden = false;
  shut.addEventListener('click', () => window.pywebview?.api?.close());
}

const manifest = await (await fetch('/static/anim/stage.json')).json();

const art = {
  room: { bg: '/static/anim/room/bg.png', size: manifest.room.size },
  cast: {},
  // How each model is named on screen. The art is per model and the voices are
  // per visit, so without this a bubble could only ever say "visitor" or
  // "teacher", which is no help when the visitor is an agent with its own name.
  labels: {
    deepseek: 'DeepSeek',
    qwen: '通义千问',
    grok: 'Grok',
    gpt: 'GPT',
    claude: 'Claude',
    gemini: 'Gemini',
    kimi: 'Kimi',
    glm: 'GLM',
    doubao: '豆包',
    default: '访客',
  },
};
for (const [model, entry] of Object.entries(manifest.cast)) {
  const poses = {};
  for (const [pose, size] of Object.entries(entry.poses)) {
    poses[pose] = { url: `/static/anim/cast/${model}/${pose}.png`, size };
  }
  const clips = {};
  for (const [action, clip] of Object.entries(entry.clips || {})) {
    clips[action] = {
      url: `/static/anim/cast/${model}/${action}.webm`,
      size: clip.size,
      scale: clip.scale,
    };
  }
  art.cast[model] = { poses, clips, rig: entry.rig };
}

const has = (model) => Object.prototype.hasOwnProperty.call(art.cast, model);
const castKey = (model) => (has(model) ? model : (has('default') ? 'default' : TEACHER));

/** Decode every sprite up front: a half-drawn puppet mid-walk looks broken. */
async function preload() {
  const urls = [art.room.bg];
  for (const entry of Object.values(art.cast)) {
    for (const pose of Object.values(entry.poses)) urls.push(pose.url);
  }
  const clips = [];
  for (const entry of Object.values(art.cast)) {
    for (const clip of Object.values(entry.clips)) clips.push(clip.url);
  }
  await Promise.all([
    ...urls.map((src) => new Promise((done) => {
      const img = new Image();
      img.onload = img.onerror = done;
      img.src = src;
    })),
    // Clips only need to be in the HTTP cache; the video element reads them
    // from there, so the first frame of an action is never a blank box.
    ...clips.map((src) => fetch(src).then((r) => r.blob()).catch(() => {})),
  ]);
}
await preload();

const stage = new Stage(host, art);
const director = new Director();

let visitorModel = castKey(params.get('model') || TEACHER);
let visitor = stage.puppet(visitorModel, 'visitor');
let teacher = stage.puppet(TEACHER, 'teacher');
teacher.root.classList.toggle('twin', visitorModel === TEACHER);
const ctx = { stage, visitor, teacher };

stage.setNight(false);
visitor.setVisible(false);
// The teacher only comes in once there is a rest to plan, so the room starts
// empty: an untouched house is what the pet shows while it waits.
teacher.placeAt('teacher');
teacher.face(1);
teacher.setVisible(false);

/* ------------------------------------------------------------------ queue */

const queue = [];
let playing = '';

function enqueue(scene) {
  queue.push(scene);
}

function pump() {
  if (!director.done || !queue.length) return;
  const scene = queue.shift();
  playing = scene;
  caption.textContent = CAPTION[scene] || '';
  caption.classList.toggle('on', Boolean(CAPTION[scene]));
  director.run(SCENES[scene](ctx));
}

const CAPTION = {
  enter: '回到休息室',
  plan: '和老师商量',
  sit: '坐一会儿',
  study: '在桌前做事',
  chat: '说说话',
  sleep: '睡下了',
  leave: '离开了',
};

/* ------------------------------------------------------------------- loop */

let last = performance.now();
let clock = 0;

function frame(now) {
  const dt = Math.min((now - last) / 1000, 1 / 20);
  last = now;
  step(dt);
  requestAnimationFrame(frame);
}

function step(dt) {
  clock += dt;
  pump();
  director.update(dt);
  visitor.update(clock, dt);
  teacher.update(clock, dt);
}

/* ------------------------------------------------------------------- live */

let seenActions = 0;
let seenVoices = 0;
let revision = '';

function applyState(state, first) {
  if (!state) return;
  const model = castKey(state.model || TEACHER);
  if (model !== visitorModel) {
    visitorModel = model;
    visitor = stage.puppet(model, 'visitor');
    ctx.visitor = visitor;
    teacher.root.classList.toggle('twin', model === TEACHER);
  }
  // An agent that named itself is called that, not by its model: the name is
  // the one thing here that is genuinely its own.
  visitor.setLabel(state.self_name || art.labels[model] || model);

  const timeline = state.timeline || [];
  if (first) {
    // Joining a visit already in progress: open on where it stands now.
    seenActions = timeline.length;
    const current = timeline.length ? timeline[timeline.length - 1].scene : 'enter';
    enqueue(sceneFor(current === 'enter' ? 'enter' : current));
  } else {
    for (const item of timeline.slice(seenActions)) enqueue(sceneFor(item.scene));
    seenActions = timeline.length;
  }

  const voices = state.voices || [];
  // On the first state there is no history to replay: the visit is already
  // over, and saying everything it ever said would be a wall of text on
  // arrival. Only the last line is worth showing, and it still goes through
  // the queue so it fades in like anything else.
  const fresh = first
    ? voices.slice(-1)
    : voices.slice(seenVoices);
  seenVoices = voices.length;
  speak(fresh);
  revision = state.revision || revision;
}

/* Speech arrives in a queue, not all at once.
 *
 * One tool call produces several lines -- what she was doing, what she felt,
 * the room's answer -- and they all carry the same timestamp. Saying them in
 * the same tick put a wall of text on screen in one instant, which reads as an
 * agent that is silent for minutes and then dumps everything. So each line
 * gets its own turn: it appears, the previous one is allowed to be read, and
 * the next follows. The room's own answer waits a beat longer, because it is
 * replying and the reply should visibly follow.
 */
const SAY_GAP = 2600; // ms between two lines said together
const REPLY_GAP = 1500; // extra wait before the room answers
const sayQueue = [];

/* Long answers are said in parts.
 *
 * The room's guidance is a few labelled paragraphs -- think wide, check
 * closely, think wide again, check again. Saying that as one bubble is a
 * page of text dropped on the screen; said a paragraph at a time it reads as
 * the room actually talking you through it. Splitting on blank lines keeps the
 * author's own structure instead of inventing one.
 */
function partsOf(text) {
  const blocks = String(text || '').split(/\n\s*\n/).map((b) => b.trim()).filter(Boolean);
  if (blocks.length <= 1) return [String(text || '').trim()];
  // A trailing fragment is easier to read joined back onto its neighbour than
  // as a bubble of its own.
  return blocks;
}

function speak(lines) {
  for (const voice of lines) {
    const mouth = voice.who === 'teacher' ? teacher : visitor;
    const parts = voice.who === 'teacher' ? partsOf(voice.text) : [voice.text];
    parts.forEach((part, index) => {
      sayQueue.push({
        mouth,
        text: part,
        kind: voice.kind === 'think' ? 'think' : 'say',
        who: voice.who,
        // A longer line needs longer to read, so the gap scales with it.
        hold: clamp(900 + part.length * 42, 1100, 5200),
        // Only the first part waits for the speaker it answers.
        wait: voice.who === 'teacher' && index === 0 ? REPLY_GAP : 0,
      });
    });
  }
  pumpSpeech();
}

let speaking = false;

function pumpSpeech() {
  if (speaking || !sayQueue.length) return;
  speaking = true;
  const next = sayQueue.shift();
  // The reply gets a pause *before* it, so it does not land in the same
  // instant as the line it is answering.
  setTimeout(() => {
    next.mouth.say(next.text, next.kind, next.who);
    setTimeout(() => {
      speaking = false;
      pumpSpeech();
    }, next.hold);
  }, next.wait);
}

/** Watch one visit. Returns the function that stops watching it. */
function follow(ticket) {
  seenActions = 0;
  seenVoices = 0;
  revision = '';

  let first = true;
  const take = (state) => {
    if (!first && state.revision === revision) return;
    applyState(state, first);
    first = false;
  };

  const poll = () => fetch(`/r/${encodeURIComponent(ticket)}/state`)
    .then((r) => (r.ok ? r.json() : null))
    .then((state) => state && take(state))
    .catch(() => {});

  poll();

  let source;
  try {
    source = new EventSource(`/r/${encodeURIComponent(ticket)}/events`);
    source.addEventListener('state', (event) => take(JSON.parse(event.data)));
  } catch (_err) {
    source = null;
  }
  // Polling is the floor: if the stream never connects, the room still follows.
  const timer = setInterval(() => {
    if (source && source.readyState === 1) return;
    poll();
  }, 4000);

  return () => {
    if (source) source.close();
    clearInterval(timer);
  };
}

/** Watch whoever is in the room, without being told whose visit it is.
 *
 * The desktop pet opens the moment the agent connects, which is before she has
 * a ticket, so it cannot be handed one. It asks the server who is inside right
 * now instead, latches onto that visit, and drops back to the empty house when
 * she leaves -- ready for the next one in the same session.
 */
function followNow() {
  let ticket = ''; // the visit latched onto, whether or not it is still going
  let stop = null; // set while subscribed to it

  const look = () => fetch('/now/state')
    .then((r) => (r.ok ? r.json() : null))
    .then((state) => {
      if (!state || !state.ticket) return;
      if (state.ticket !== ticket) {
        if (stop) stop();
        ticket = state.ticket;
        stop = follow(ticket);
        return;
      }
      // She has gone, but the leaving still has to play: hold the subscription
      // until the queue drains, or the room would cut to an empty house.
      if (!stop || state.still_inside || !director.done || queue.length) return;
      stop();
      stop = null;
      enqueue('house');
    })
    .catch(() => {});

  enqueue('house');
  look();
  setInterval(look, 1500);
}

/* ---------------------------------------------------------------- rehearse */

function rehearse() {
  const want = params.get('scene') || 'enter';
  const lines = params.get('say');
  enqueue(sceneFor(want));
  if (lines) {
    setTimeout(() => visitor.say(lines, 'say', 'visitor'), 1200);
    setTimeout(() => teacher.say('欢迎回来，先坐一会儿吧。', 'say', 'teacher'), 2400);
  }
  if (!params.has('once')) {
    setInterval(() => {
      if (director.done && !queue.length) enqueue(sceneFor(want));
    }, 600);
  }
}

if (TICKET) follow(TICKET);
else if (FOLLOW_NOW) followNow();
else rehearse();

const seek = parseFloat(params.get('seek') || '0');
if (seek > 0) {
  const dt = 1 / 60;
  for (let t = 0; t < seek; t += dt) step(dt);
}

// `freeze` holds the seeked moment still so it can be inspected frame by frame.
if (!params.has('freeze')) requestAnimationFrame(frame);
requestAnimationFrame(() => veil.classList.add('off'));

window.__stage = { stage, visitor, teacher, director, queue, step, art, SCENES, speak };
window.__ready = true;

/* -------------------------------------------------------------- pet shape */

// In the pet window the room is cut out of the desktop, so the window's shape
// has to keep up with whatever is on screen: the room, and every bubble that
// rises above its walls. The window reads this and re-cuts itself, and it has
// to be cheap to ask, so it is a plain read of the layout.
if (params.has('pet')) {
  window.__outline = () => stage.outline();
}
