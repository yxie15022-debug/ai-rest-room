/* The rest room stage: a 2D paper-puppet room that follows a visit live.
 *
 * Everything is laid out in room coordinates (the cut-out room's own pixels)
 * and the whole room is scaled to fit its container, so positions here read
 * the same as the numbers measured off the art.
 */

const ROOM = { w: 925, h: 902 };

// The room is an isometric cutaway, so its floor is a quadrilateral seen
// corner-on, not a band that only gets nearer. Walking is therefore across a
// surface: a position is (u, v), the two floor axes, and the corners below --
// measured off the art where the walls meet the floor -- turn that back into
// a point on screen. `u` runs along the right-hand wall (window, desk, bed),
// `v` along the left-hand one (door, sofa); both are 0 at the far corner.
//
// Heights are how tall a standing sprite reads at the far corner and at the
// near one, judged against the doorway, which the art draws about two of our
// chibi characters high.
const FLOOR = {
  back: [462, 325],
  right: [921, 555],
  left: [3, 555],
  front: [462, 882],
  backH: 175,
  frontH: 275,
};

// Where people stand, as (u, v) on the floor. The sofa and the door take the
// left wall, the desk and the bed the right one, so the open floor people can
// actually use is the middle and the near half -- and the teacher needs a spot
// per scene that neither stands in the furniture nor in front of the visitor.
const SPOT = {
  doorstep: [0.06, 0.8],
  inside: [0.2, 0.72],
  rug: [0.46, 0.4],
  // Both furniture spots are solved to land right in front of the seat, so the
  // walk ends where the pin begins: a spot across the room from the cushion
  // reads as a teleport at the moment she sits down.
  sofa: [0.19, 0.55],
  // u 0.80 v 0.33 is the floor point in front of the mattress (about
  // x=678 y=611), which is where she has to stop before lying on it.
  bed: [0.8, 0.33],
  desk: [0.41, 0.19],
  front: [0.5, 0.5],
  teacher: [0.28, 0.72],
  teacherDesk: [0.26, 0.44],
  teacherSofa: [0.62, 0.58],
  teacherAside: [0.22, 0.7],
};

// Seats and beds are anchors, not floor positions: the sprite is pinned by a
// point on its own body instead of by its feet.
const ANCHOR = {
  // Measured off the art rather than by eye: the cushion's front lip runs
  // across y≈420-434 with its centre near x=297, so a kneeling figure pinned
  // there puts her knees on the seat and her body on the cushion's middle
  // instead of over the left armrest.
  sofa: { x: 298, y: 436, h: 215 },
  // The bed's top surface is a shallow diamond centred on (664, 514); a lying
  // sprite is pinned by the bottom-centre of her box, so this sits her length
  // across the mattress instead of her feet at the foot of the bed.
  bed: { x: 680, y: 550, h: 245 },
};

const WALK_SPEED = 185; // room px per second across the floor
const STRIDE = 95; // room px per half stride
// Room above the room for speech to live in, in room pixels. Bubbles are drawn
// at a readable screen size rather than scaled with the room, so this has to
// be enough of both: a couple of lines of text plus the gap that keeps them
// clear of the roof. The window is made taller by the same amount.
const SPEECH = 380;
// Screen pixels kept clear at the very top of the window. A bubble draws its
// rounded corners and drop shadow outside the box it is measured by, so the
// window's clip -- which follows that measurement plus a bleed -- would shave
// the top line flat if speech were allowed to reach the very edge.
const TOP_PAD = 16;

const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const lerp = (a, b, t) => a + (b - a) * t;
const ease = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t));
const easeOut = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : 1 - Math.pow(1 - t, 3));

/** Where (u, v) lands on screen, and how tall someone standing there reads. */
function floorAt(u, v, floor = FLOOR) {
  const { back, right, left, front } = floor;
  const place = (i) => (
    back[i]
    + u * (right[i] - back[i])
    + v * (left[i] - back[i])
    + u * v * (front[i] - right[i] - left[i] + back[i])
  );
  return {
    x: place(0),
    y: place(1),
    h: lerp(floor.backH, floor.frontH, clamp((u + v) / 2, 0, 1.2)),
  };
}

/* ------------------------------------------------------------------ puppet */

/** One character: a standing sprite cut into three bands that move. */
class Puppet {
  constructor(model, art, host, opts = {}) {
    this.model = model;
    this.art = art;
    this.rig = art.rig;
    this.flip = opts.flip ?? 1;
    this.scaleBias = opts.scaleBias ?? 1;
    this.floor = opts.floor ?? FLOOR;

    const [sw, sh] = this.rig.size;
    this.sprite = { w: sw, h: sh };

    const root = document.createElement('div');
    root.className = 'puppet';
    root.dataset.model = model;

    const shadow = document.createElement('div');
    shadow.className = 'shadow';
    shadow.style.width = `${sw * 0.46}px`;
    shadow.style.height = `${sw * 0.14}px`;
    shadow.style.top = `${sh}px`;

    const body = document.createElement('div');
    body.className = 'body';
    body.style.width = `${sw}px`;
    body.style.height = `${sh}px`;

    const { hem, split } = this.rig;
    // The leg bands reach well above the hem so the skirt always covers where
    // they join, however far they swing.
    const overlap = 0.1;
    const bands = {
      legL: `inset(${(hem - overlap) * 100}% ${(1 - split) * 100}% 0% 0%)`,
      legR: `inset(${(hem - overlap) * 100}% 0% 0% ${split * 100}%)`,
      upper: `inset(0% 0% ${(1 - hem) * 100}% 0%)`,
    };
    // Legs sit behind the upper body so the skirt hides where they join.
    this.part = {};
    for (const key of ['legL', 'legR', 'upper']) {
      const img = document.createElement('img');
      img.className = `part ${key}`;
      img.src = art.poses.stand.url;
      img.draggable = false;
      img.style.clipPath = bands[key];
      img.style.transformOrigin = `${split * sw}px ${hem * sh}px`;
      body.append(img);
      this.part[key] = img;
    }

    this.poseImg = document.createElement('img');
    this.poseImg.className = 'part pose';
    this.poseImg.draggable = false;

    // Transparent VP9 video: the character actually animates, the room shows
    // through behind her. Only for standing still -- walking is the rig's job,
    // because the clips are all filmed on the spot.
    this.clipVid = document.createElement('video');
    this.clipVid.className = 'part clip';
    this.clipVid.loop = true;
    this.clipVid.muted = true;
    this.clipVid.autoplay = true;
    this.clipVid.playsInline = true;
    body.append(this.poseImg, this.clipVid);

    this.stage = opts.stage ?? null;
    // Shown on every bubble this puppet says. The visitor is named by whoever
    // is inside; the teacher is the room's own voice and is always DeepSeek.
    this.label = opts.label || '';

    // Speech is not a child of the body: see `Stage.say`.
    root.append(shadow, body);
    host.append(root);
    this.root = root;
    this.bodyEl = body;
    this.shadow = shadow;

    [this.u, this.v] = SPOT.doorstep;
    this.target = null;
    this.phase = 0;
    this.facing = 1;
    this.faceTo = 1;
    this.pose = 'stand';
    this.mood = 'idle';
    this.anchor = null;
    this.visible = true;
    // The little motion a standing character is in the middle of. Picked by
    // `_fidget`, which reads it every frame.
    this.fidget = null;
    this.idleSeed = Math.random() * 10;
  }

  setVisible(on) {
    this.visible = on;
    this.root.style.opacity = on ? '1' : '0';
  }

  /** The name this puppet's bubbles are signed with. */
  setLabel(name) {
    this.label = name || '';
  }

  /** What the puppet is doing. The layer that shows it is picked per frame. */
  setPose(name) {
    if (name !== 'stand' && !this.art.poses[name] && !this.art.clips?.[name]) return;
    this.pose = name;
  }

  /** Lay a still or a clip in the standing sprite's box, feet on the same line.
   *
   * Art of every kind is trimmed to the character, so sizes differ; each one is
   * centred and sat on the floor line rather than stretched to fill the box.
   *
   * `scale` is how tall she should read next to her own standing sprite. Stills
   * carry it in their pixel height already -- the build resizes them against the
   * standing art -- but footage keeps its native resolution, so a clip says how
   * tall it means to be and gets scaled here instead of re-encoded larger.
   */
  _fitPart(el, [pw, ph], scale) {
    const h = scale ? this.sprite.h * scale : ph;
    const w = pw * (h / ph);
    Object.assign(el.style, {
      width: `${w}px`,
      height: `${h}px`,
      left: `${(this.sprite.w - w) / 2}px`,
      top: `${this.sprite.h - h}px`,
    });
  }

  /** Show exactly one of: the rig, a drawn pose, a video clip. */
  _show(layer) {
    if (this.layer === layer) return;
    this.layer = layer;
    const [kind, name] = layer.split(':');
    // Spell out 'block': clearing the inline display would hand the element
    // back to the stylesheet, which hides the pose and clip layers by default.
    const show = (el, on) => { el.style.display = on ? 'block' : 'none'; };
    for (const key of ['legL', 'legR', 'upper']) show(this.part[key], kind === 'rig');
    show(this.poseImg, kind === 'pose');
    show(this.clipVid, kind === 'clip');
    if (kind === 'pose') {
      const art = this.art.poses[name];
      this._fitPart(this.poseImg, art.size);
      this.poseImg.src = art.url;
    } else if (kind === 'clip') {
      const clip = this.art.clips[name];
      this._fitPart(this.clipVid, clip.size, clip.scale);
      this.clipVid.src = clip.url;
      // Autoplay can still be refused; nothing to do about it but try.
      this.clipVid.play().catch(() => {});
    } else {
      this.clipVid.removeAttribute('src');
      this.clipVid.load();
    }
  }

  /** Which layer should be showing right now.
   *
   * A pose is where the body is, a mood is what it is doing there: standing
   * still, the mood names the clip ('idle' / 'talk' / 'work'); sitting or
   * asleep, the pose does. Walking is always the rig -- every clip is filmed
   * on the spot, so none of them can carry her across the room.
   */
  _layerFor(walking) {
    if (walking) return 'rig';
    const want = this.pose === 'stand' ? this.mood : this.pose;
    if (this.art.clips?.[want]) return `clip:${want}`;
    if (this.pose !== 'stand' && this.art.poses[this.pose]) return `pose:${this.pose}`;
    return 'rig';
  }

  place(u, v) {
    this.u = u;
    this.v = v;
    this.target = null;
    this.anchor = null;
  }

  placeAt(spot) {
    this.place(SPOT[spot][0], SPOT[spot][1]);
  }

  /** Pin the sprite by a body point instead of by its feet (sitting, lying). */
  pin(anchor) {
    this.anchor = anchor;
    this.target = null;
  }

  walkTo(u, v) {
    this.target = { u, v };
    this.anchor = null;
  }

  walkToSpot(spot) {
    this.walkTo(SPOT[spot][0], SPOT[spot][1]);
  }

  /** A step away from a spot, along the floor rather than across the screen. */
  walkNear(spot, du, dv) {
    this.walkTo(SPOT[spot][0] + du, SPOT[spot][1] + dv);
  }

  get arrived() {
    return this.target === null;
  }

  /** Is this puppet already standing at that spot (within a step)? */
  nearest(spot, within = 0.08) {
    const [u, v] = SPOT[spot] || [NaN, NaN];
    if (Number.isNaN(u)) return false;
    return Math.hypot(this.u - u, this.v - v) <= within;
  }

  face(dir) {
    this.faceTo = dir;
  }

  /** 'idle' | 'talk' | 'work' -- what the body does while standing still. */
  feel(mood) {
    this.mood = mood;
  }

  say(text, kind = 'say', who = '') {
    // Speech belongs to the room, not to the sprite: one column above the
    // walls holds every line, signed by its speaker. Two speakers, two
    // bubbles over two heads, in a window this small, is two panels trying to
    // occupy the same few hundred pixels -- and whichever loses is cut by the
    // window or buried under the other.
    if (this.stage) this.stage.say(this, text, kind, who);
  }

  /** Pick the next little thing to do, and how long to do it for. */
  _nextFidget(t) {
    // Standing still is the default state of the whole pet, so it cannot be
    // one loop of breathing: a character that only breathes reads as a picture
    // with a pulse. These are the cheap motions a paper puppet can actually
    // make -- a tilt, a glance, a rise on the toes, a shift of weight -- and
    // they are picked at random so two people never tick in time.
    const beats = ['breathe', 'breathe', 'glance', 'tilt', 'shift', 'bounce', 'lean'];
    this.fidget = {
      kind: beats[Math.floor(Math.random() * beats.length)],
      at: t,
      for: 1.1 + Math.random() * 1.8,
      // A glance has to go somewhere; a tilt and a shift pick a side.
      dir: Math.random() < 0.5 ? -1 : 1,
    };
  }

  /** The extra motion the current fidget adds, at time `t`. */
  _fidget(t) {
    if (!this.fidget || t - this.fidget.at > this.fidget.for + 0.9) {
      this._nextFidget(t + Math.random() * 1.4);
      return { bob: 0, lean: 0, squash: 0, turn: 0 };
    }
    const f = this.fidget;
    const since = t - f.at;
    if (since < 0) return { bob: 0, lean: 0, squash: 0, turn: 0 };
    // One clear movement, eased in and out, then a pause before the next.
    const phase = clamp(since / f.for, 0, 1);
    const wave = Math.sin(phase * Math.PI) ** 1.4;
    switch (f.kind) {
      case 'tilt':
        return { bob: 0, lean: 5.5 * f.dir * wave, squash: 0, turn: 0 };
      case 'glance':
        return { bob: -1.5 * wave, lean: 1.2 * f.dir * wave, squash: 0, turn: 0.12 * f.dir * wave };
      case 'shift':
        return { bob: 1.6 * wave, lean: -2.2 * f.dir * wave, squash: -0.008 * wave, turn: 0 };
      case 'bounce':
        return { bob: -4.5 * wave, lean: 0, squash: 0.012 * wave, turn: 0 };
      case 'lean':
        return { bob: -1.8 * wave, lean: 0, squash: 0, turn: 0.05 * f.dir * wave };
      default:
        return { bob: 0, lean: 0, squash: 0, turn: 0 };
    }
  }

  update(t, dt) {
    let walking = false;
    let here = floorAt(this.u, this.v, this.floor);
    if (this.target) {
      // Pace by how far the step carries her across the screen, not by how far
      // it moves her along the floor axes: a stride near the camera covers more
      // of the room than the same stride at the far corner.
      const there = floorAt(this.target.u, this.target.v, this.floor);
      const span = Math.hypot(there.x - here.x, there.y - here.y);
      const step = WALK_SPEED * dt;
      if (span <= step || span < 1) {
        this.u = this.target.u;
        this.v = this.target.v;
        this.target = null;
      } else {
        const k = step / span;
        this.u += (this.target.u - this.u) * k;
        this.v += (this.target.v - this.v) * k;
        this.phase += (step / STRIDE) * Math.PI;
        if (Math.abs(there.x - here.x) > 2) this.faceTo = there.x > here.x ? 1 : -1;
        walking = true;
      }
      here = floorAt(this.u, this.v, this.floor);
    }

    this.facing += (this.faceTo - this.facing) * (1 - Math.exp(-dt * 11));

    let x = here.x;
    let bottom = here.y;
    let height = here.h;
    if (this.anchor) {
      x = this.anchor.x;
      bottom = this.anchor.y;
      height = this.anchor.h;
    }
    height *= this.scaleBias;

    const k = height / this.sprite.h;
    this.root.style.transform =
      `translate(${x - (this.sprite.w * k) / 2}px, ${bottom - this.sprite.h * k}px) scale(${k})`;
    this.root.style.zIndex = String(100 + Math.round(bottom));
    // Contact shadow: keep it on the floor, so it must not take the body's bob.
    const shade = walking ? 0.84 : 1;
    this.shadow.style.transform = `translate(-50%, -50%) scale(${shade}, ${shade * 0.9})`;

    this._show(this._layerFor(walking));
    if (this.layer !== 'rig') {
      // A still or a clip is a whole body already posed, so the rig's parts
      // must not move -- but the layer still has to breathe, or a seated
      // character is a photograph. A slow vertical scale about the hips is
      // enough at this size, and it cannot pull her off the cushion.
      //
      // Sitting and lying both mean "asleep to the world", so both take the
      // slow breath: a lying figure bobbing at the standing rate reads as
      // twitching, not resting.
      const resting = this.mood === 'rest' || this.pose === 'sleep';
      const air = Math.sin(t * (resting ? 0.9 : 1.7) + this.idleSeed);
      this.bodyEl.style.transform =
        `scaleX(${this.flip * this.facing}) `
        + `translateY(${air * (resting ? 1.1 : 1.8)}px) `
        + `scaleY(${1 + air * (resting ? 0.006 : 0.004)})`;
      return;
    }

    const swing = walking ? Math.sin(this.phase) : 0;
    const lift = walking ? Math.abs(swing) : 0;
    const breath = Math.sin(t * 1.7 + this.idleSeed);

    // A front-facing sprite cannot swing a leg forward, so a step reads as the
    // foot lifting off the floor, one leg at a time, with only a hint of splay.
    // The body rises with whichever leg is up and leans into the walk, and
    // lands a little on each footfall rather than gliding.
    const stepL = Math.max(0, swing);
    const stepR = Math.max(0, -swing);
    const footfall = walking ? Math.abs(Math.cos(this.phase)) : 0;
    let bob = walking ? -lift * 7 + footfall * 1.6 : breath * 2.2;
    let lean = walking ? swing * 1.4 : breath * 0.5;
    let squash = walking ? 1 - lift * 0.01 - footfall * 0.004 : 1 + breath * 0.006;

    // Standing still still has something to do: talking nods, working leans in.
    let turn = 0;
    if (!walking && this.mood === 'talk') {
      const beat = Math.sin(t * 5.2 + this.idleSeed);
      bob += beat * 4;
      lean += Math.sin(t * 2.6 + this.idleSeed) * 1.6;
      squash -= Math.abs(beat) * 0.006;
    } else if (!walking && this.mood === 'work') {
      bob += 5 + Math.sin(t * 6.4 + this.idleSeed) * 1.4;
      lean += 4.2 * this.facing;
      squash -= 0.012;
    } else if (this.mood === 'rest') {
      // Sitting: slower and shallower than standing, because the whole point
      // of the scene is that nothing is happening. A long breath, and every so
      // often a small settle of the weight, so she does not read as a still.
      const slow = Math.sin(t * 0.9 + this.idleSeed);
      const settlePhase = (t * 0.32 + this.idleSeed) % (Math.PI * 2);
      const settle = Math.sin(settlePhase) ** 6; // a brief dip, then rest
      bob += slow * 1.6 + settle * 1.8;
      lean += Math.sin(t * 0.5 + this.idleSeed) * 0.9;
      squash += slow * 0.004 - settle * 0.006;
    } else if (!walking) {
      // Idle: the fidgets above, on top of the breath already in `bob`.
      const extra = this._fidget(t);
      bob += extra.bob;
      lean += extra.lean;
      squash += extra.squash;
      turn = extra.turn;
    }

    this.part.legL.style.transform = `translateY(${-stepL * 34}px) rotate(${swing * 4}deg)`;
    this.part.legR.style.transform = `translateY(${-stepR * 34}px) rotate(${swing * 4}deg)`;
    this.part.upper.style.transform =
      `translateY(${bob}px) rotate(${lean}deg) scaleY(${squash})`;
    // A front-facing sprite narrows a little when it heads sideways, and a
    // glance turns it a little further without stepping anywhere.
    this.bodyEl.style.transform =
      `scaleX(${this.flip * this.facing * (walking ? 0.95 : 1 - Math.abs(turn))})`;
  }
}

/* ------------------------------------------------------------------- stage */

class Stage {
  constructor(host, art) {
    this.host = host;
    this.art = art;
    // The art is cut to the room's own outline, so its size is the room's.
    const [w, h] = art.room.size || [ROOM.w, ROOM.h];
    this.size = { w, h };

    const room = document.createElement('div');
    room.className = 'room';
    room.style.width = `${w}px`;
    room.style.height = `${h}px`;

    const bg = document.createElement('img');
    bg.className = 'bg';
    bg.src = art.room.bg;
    bg.draggable = false;

    const cast = document.createElement('div');
    cast.className = 'cast';

    const tint = document.createElement('div');
    tint.className = 'tint';
    // Dusk has to stop at the walls: the room is a cut-out box with nothing
    // around it, and a tinted rectangle would give its bounding box away.
    tint.style.maskImage = `url(${art.room.bg})`;
    tint.style.webkitMaskImage = `url(${art.room.bg})`;

    room.append(bg, cast, tint);
    host.append(room);

    // One column of speech for the whole room, sitting in the open air above
    // the walls. It is a child of the stage rather than of a puppet, so it is
    // never scaled with a body, never moved by a walk, and never covers one.
    const speech = document.createElement('div');
    speech.className = 'speech';
    host.append(speech);

    this.room = room;
    this.castEl = cast;
    this.tint = tint;
    this.speech = speech;

    this.fit();
    addEventListener('resize', () => this.fit());
  }

  fit() {
    // The room is fitted inside a box that leaves `SPEECH` room pixels of open
    // air above it, so a bubble has somewhere to go that is still inside the
    // window. Without it the room would fill the window and every bubble would
    // have to be squeezed back down onto the head that said it.
    const boxH = this.size.h + SPEECH;
    const k = Math.min(this.host.clientWidth / this.size.w, this.host.clientHeight / boxH);
    this.scale = k;
    // Centre the box in the window, then sit the room at the bottom of it: the
    // space made for speech is taken out of the top.
    const box = this.host.clientHeight - boxH * k;
    const dy = (box / 2 + SPEECH * k + (this.size.h * k) / 2) - this.host.clientHeight / 2;
    this.room.style.transform = `translate(-50%, -50%) translateY(${dy}px) scale(${k})`;
    // The speech column hangs off the room's top edge. The air available to it
    // is everything from the top of the window down to that edge: `sky` is the
    // edge's distance from the top, and the column's `bottom` is measured from
    // the stage's own bottom, so it is the whole window less that.
    const sky = box / 2 + SPEECH * k;
    this.speech.style.bottom = `${this.host.clientHeight - sky}px`;
    // The air itself, less the margin the clip needs at the very top: a
    // bubble's rounded corners and shadow draw outside the box it is measured
    // by, and a clip laid on that box would slice the top bubble flat.
    this.sky = Math.max(0, sky - TOP_PAD);
    this.speech.style.setProperty('--sky', `${this.sky}px`);
    this.fitSpeech();
  }

  /** The window's shape right now: the room, plus whatever speech is showing.
   *
   * The pet window is clipped to what this returns, which is the one thing
   * that decides both what is drawn and what lets clicks through. It has to be
   * recomputed as bubbles come and go: a clip held at the room's outline would
   * cut the top off the speech column above the walls.
   *
   * `room` is where the room art was laid down and `boxes` are the bubbles on
   * top of it. Both are in the window's own pixels. They are reported apart
   * because they are cut apart: the window traces the room's silhouette from
   * the art, and only ever adds plain boxes for speech.
   */
  outline() {
    const rect = this.room.getBoundingClientRect();
    const host = this.host.getBoundingClientRect();
    const boxes = [];
    for (const bubble of this.speech.children) {
      const said = bubble.getBoundingClientRect();
      if (!said.width || !said.height) continue;
      boxes.push({
        x: said.left - host.left,
        y: said.top - host.top,
        w: said.width,
        h: said.height,
      });
    }
    return {
      room: {
        x: rect.left - host.left,
        y: rect.top - host.top,
        w: rect.width,
        h: rect.height,
      },
      boxes,
    };
  }

  /** Afternoon or night. A switch, not a tween: the room is scenery. */
  setNight(on) {
    this.night = on ? 1 : 0;
    this.tint.style.opacity = String(this.night);
  }

  /** Say something. The room keeps one column of speech above its walls.
   *
   * Speech is signed with the speaker's name and tinted per role, which is what
   * says who is talking. A bubble per head does not work here: two chibi
   * characters stand a few hundred pixels apart and each bubble is wider than
   * that gap, so at the same height they cover each other -- and either one
   * raised out of the way is a bubble floating in the air with nothing under
   * it. One column avoids both, and never covers a face.
   */
  say(speaker, text, kind = 'say', who = '') {
    if (!text) return;
    const bubble = document.createElement('div');
    bubble.className = `bubble ${kind}`;
    if (who) bubble.dataset.who = who;
    const tag = document.createElement('span');
    tag.className = 'who';
    tag.textContent = speaker.label || '访客';
    bubble.append(tag, document.createTextNode(text));

    this.speech.append(bubble);
    requestAnimationFrame(() => bubble.classList.add('in'));
    this.fitSpeech();
    while (this.speech.childElementCount > 3) this.speech.firstElementChild.remove();
    // Long enough to actually read: this is what the agent really said.
    const life = clamp(4200 + text.length * 190, 5600, 18000);
    setTimeout(() => {
      bubble.classList.remove('in');
      setTimeout(() => {
        bubble.remove();
        this.fitSpeech();
      }, 500);
    }, life);
  }

  /** Keep the speech column inside the sky above the room.
   *
   * It grows upwards, so three long lines can run off the top of the window.
   * The oldest go first: the newest line is the one being spoken.
   */
  fitSpeech() {
    // `this.sky` is the air above the room, already less the margin the clip
    // needs at the very top. The column is bottom-aligned in it, so this only
    // has to give up whatever no longer fits.
    const sky = this.sky || 0;
    for (let tries = 0; tries < 4; tries += 1) {
      if (this.speech.scrollHeight <= sky + 1) return;
      if (this.speech.childElementCount <= 1) {
        // One bubble and still too tall: trim it from the top rather than push
        // it out of the window. Its last lines are what is being said.
        this.speech.style.setProperty('--clip', `${Math.round(this.speech.scrollHeight - sky)}px`);
        return;
      }
      this.speech.firstElementChild.remove();
    }
  }

  puppet(model, role) {
    this.people = this.people || {};
    const have = this.people[role];
    if (have && have.model === model) return have;
    if (have) have.root.remove();
    const made = new Puppet(model, this.art.cast[model], this.castEl, {
      stage: this,
      // The teacher is the room's own voice and is always DeepSeek; the
      // visitor is whoever came in, and says so by name on every bubble.
      label: role === 'teacher' ? 'DeepSeek' : (this.art.labels?.[model] || model),
    });
    made.root.classList.add(role);
    this.people[role] = made;
    return made;
  }
}

export { Stage, Puppet, SPOT, ANCHOR, ROOM, FLOOR, floorAt, clamp, lerp, ease, easeOut };
