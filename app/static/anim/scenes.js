/* What each scene looks like.
 *
 * A scene is a generator that yields instructions; the director advances it as
 * each one finishes, so a scene reads top to bottom like a stage direction.
 * Scene names are the MCP action names the room records.
 */

import { ANCHOR, clamp, ease } from './stage.js';

const wait = (sec) => ({ wait: sec });
const until = (fn) => ({ until: fn });
const tween = (dur, apply, curve = ease) => ({ tween: dur, apply: (t) => apply(curve(t)) });

/** Runs one generator at a time, a frame at a time. */
class Director {
  constructor() {
    this.gen = null;
    this.cur = null;
    this.t = 0;
    this.done = true;
  }

  run(gen) {
    this.gen = gen;
    this.cur = null;
    this.t = 0;
    this.done = false;
    this._advance();
  }

  _advance() {
    for (let guard = 0; guard < 500; guard += 1) {
      const next = this.gen.next();
      this.t = 0;
      if (next.done) {
        this.cur = null;
        this.done = true;
        return;
      }
      this.cur = next.value;
      // Zero-length instructions resolve immediately; keep pulling.
      if (this.cur.tween) {
        this.cur.apply(0);
        if (this.cur.tween > 0) return;
      } else if (this.cur.wait != null) {
        if (this.cur.wait > 0) return;
      } else if (this.cur.until) {
        if (!this.cur.until()) return;
      }
    }
  }

  update(dt) {
    if (this.done || !this.cur) return;
    this.t += dt;
    const c = this.cur;
    if (c.tween) {
      c.apply(clamp(this.t / c.tween, 0, 1));
      if (this.t >= c.tween) this._advance();
    } else if (c.wait != null) {
      if (this.t >= c.wait) this._advance();
    } else if (c.until) {
      if (c.until()) this._advance();
    }
  }
}

/* ------------------------------------------------------------------ scenes */

/** Put the visitor on stage.
 *
 * Only `enter` brings her in through the door. Every other scene can also be
 * the first one a viewer sees -- opening the room on a visit that is already
 * under way -- so each has to be able to start with her already here. Dropping
 * her just inside the door means she walks to wherever the scene wants her
 * instead of appearing out of nowhere.
 */
function onStage(visitor, teacher) {
  if (!visitor.visible) {
    visitor.placeAt('inside');
    visitor.setVisible(true);
  }
  if (teacher && !teacher.visible) {
    teacher.placeAt('teacher');
    teacher.setVisible(true);
  }
}

/** Nobody home, just the room.
 *
 * What the desktop pet shows between visits: it opens on the empty house as
 * soon as the agent connects, and falls back to it once she has left.
 */
function* house(ctx) {
  const { stage, visitor, teacher } = ctx;
  stage.setNight(false);
  visitor.setVisible(false);
  if (teacher) teacher.setVisible(false);
  yield wait(0.2);
}

/** The owner comes home, in through the door that already stands open. */
function* enter(ctx) {
  const { stage, visitor, teacher } = ctx;
  stage.setNight(false);
  // The teacher is not here yet; she comes once there is a rest to plan.
  if (teacher) teacher.setVisible(false);

  visitor.setPose('stand');
  visitor.placeAt('doorstep');
  visitor.setVisible(true);
  visitor.walkToSpot('inside');
  yield until(() => visitor.arrived);

  visitor.walkToSpot('rug');
  yield until(() => visitor.arrived);
  visitor.face(1);
  visitor.feel('idle');
  yield wait(0.2);
}

/** The teacher lets herself in, and the two settle how the rest will go. */
function* plan(ctx) {
  const { stage, visitor, teacher } = ctx;
  onStage(visitor, null);
  stage.setNight(false);
  visitor.setPose('stand');
  visitor.walkToSpot('rug');
  if (teacher && !teacher.visible) {
    teacher.setPose('stand');
    teacher.placeAt('doorstep');
    teacher.setVisible(true);
    teacher.walkToSpot('teacher');
  }
  yield until(() => visitor.arrived);
  // The door is on the left-hand wall, so whoever comes in stands on that side
  // and the one already in the room turns back towards it.
  visitor.face(-1);
  visitor.feel('talk');
  if (teacher) {
    yield until(() => teacher.arrived);
    teacher.face(1);
    teacher.feel('talk');
  }
  yield wait(0.1);
}

/** Sitting still on the sofa. `name` and `wake` land here too. */
function* sit(ctx) {
  const { stage, visitor, teacher } = ctx;
  onStage(visitor, teacher);
  stage.setNight(false);
  // Walk to the sofa first when she is standing somewhere else, then sit: a
  // character that teleports from the rug onto the cushion reads as a cut, and
  // sitting is the one scene with enough time to show the move.
  visitor.setPose('stand');
  if (visitor.art.poses.sit) {
    if (!visitor.nearest('sofa')) {
      visitor.walkToSpot('sofa');
      yield until(() => visitor.arrived);
    }
    visitor.setPose('sit');
    visitor.pin(ANCHOR.sofa);
  } else {
    visitor.walkToSpot('rug');
    yield until(() => visitor.arrived);
  }
  visitor.face(1);
  visitor.feel('rest');
  if (teacher) {
    // The sofa is against the left wall, so the teacher has to clear that side
    // of the room or she stands in front of whoever is sitting on it.
    teacher.walkToSpot('teacherSofa');
    yield until(() => teacher.arrived);
    teacher.face(-1);
    teacher.feel('idle');
  }
  // A breath or two of sitting before the scene lets go: a pose that appears
  // for one frame and stops looks like the animation broke.
  yield wait(1.6);
}

/** At the desk, with the teacher stepping over to look at the work. */
function* study(ctx) {
  const { stage, visitor, teacher } = ctx;
  onStage(visitor, teacher);
  stage.setNight(false);
  visitor.setPose('stand');
  visitor.walkToSpot('desk');
  if (teacher) teacher.walkToSpot('teacherDesk');
  yield until(() => visitor.arrived);
  visitor.face(1);
  visitor.feel('work');
  if (teacher) {
    yield until(() => teacher.arrived);
    teacher.face(1);
    teacher.feel('talk');
  }
  yield wait(0.1);
}

/** Facing the viewer to talk. */
function* chat(ctx) {
  const { stage, visitor, teacher } = ctx;
  onStage(visitor, teacher);
  stage.setNight(false);
  visitor.setPose('stand');
  visitor.walkToSpot('front');
  yield until(() => visitor.arrived);
  visitor.face(1);
  visitor.feel('talk');
  if (teacher) {
    teacher.walkToSpot('teacherAside');
    yield until(() => teacher.arrived);
    teacher.face(1);
    teacher.feel('idle');
  }
  yield wait(0.1);
}

/** Off to bed; the room goes quiet and the teacher steps back. */
function* sleep(ctx) {
  const { stage, visitor, teacher } = ctx;
  onStage(visitor, teacher);
  visitor.setPose('stand');
  visitor.walkToSpot('bed');
  if (teacher) teacher.walkToSpot('teacherAside');
  yield until(() => visitor.arrived);
  visitor.feel('idle');
  if (visitor.art.poses.sleep) {
    visitor.setPose('sleep');
    visitor.pin(ANCHOR.bed);
  }
  stage.setNight(true);
  if (teacher) {
    teacher.face(1);
    teacher.feel('idle');
  }
  yield wait(1.4);
}

/** Out the door, and the house is empty again. */
function* leave(ctx) {
  const { stage, visitor, teacher } = ctx;
  onStage(visitor, teacher);
  stage.setNight(false);
  visitor.setPose('stand');
  visitor.walkToSpot('inside');
  if (teacher) {
    teacher.walkNear('teacher', -0.08, 0.1);
    teacher.face(-1);
  }
  yield until(() => visitor.arrived);
  visitor.walkToSpot('doorstep');
  yield until(() => visitor.arrived);
  visitor.setVisible(false);
  yield wait(0.5);
  if (teacher) teacher.setVisible(false);
  yield wait(0.2);
}

const SCENES = { house, enter, plan, sit, study, chat, sleep, leave };

// MCP records more actions than there are staged scenes.
const ALIAS = {
  name: 'sit',
  wake: 'sit',
  listen: 'chat',
};

function sceneFor(name) {
  const key = ALIAS[name] || name;
  return SCENES[key] ? key : 'sit';
}

export { Director, SCENES, sceneFor, wait, until, tween };
