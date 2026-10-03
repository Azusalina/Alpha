/**
 * The page transition between the particle brain and the ball (D69). A 2D
 * canvas over the page flies one picture into the other. Both pictures are
 * sets of short segments in CSS px (a dot is a very short segment), so one
 * machinery serves both directions.
 *
 *  - 'morph'  every segment drifts on a curling path to its place in the other
 *             picture, dots stretching into lines, lines gathering into dots;
 *  - 'ruin'   the first picture comes apart and falls under gravity, bounces,
 *             lies in a heap along the bottom; then, one piece at a time, from
 *             the bottom up, the heap lifts and assembles the second picture.
 *
 * A fixed 1/120 s step drives the falling, so the result does not depend on
 * the frame rate. The canvas does not know what the pictures are; the page
 * hands it two `FxShape`s and gets a callback when the last piece has landed.
 */

export interface FxShape {
  /** x0 y0 x1 y1 per segment, CSS px. */
  segs: Float32Array;
  /** 0..1 per segment. */
  alpha: Float32Array;
  /** 1 = drawn in the accent (gold) colour, 0 = in ink. */
  gold: Uint8Array;
}

export type FxKind = 'morph' | 'ruin';

export interface FxColors {
  ink: string;
  gold: string;
}

const MAX = 6500;
const STEP = 1 / 120;
const GRAVITY = 2600;
const LEVELS = 8;

/** Seconds of each stage of a 'ruin'. */
const RUIN = { fall: 2.1, pause: 0.3, build: 1.7, piece: 0.85 };
/** A 'morph' takes this long in all. */
const MORPH = { total: 2.6, piece: 1.5 };

const ease = (u: number) => (u <= 0 ? 0 : u >= 1 ? 1 : u * u * (3 - 2 * u));

function hash(i: number, k: number): number {
  let x = (Math.imul(i + 1, 0x9e3779b1) ^ Math.imul(k + 7, 0x85ebca6b)) >>> 0;
  x = Math.imul(x ^ (x >>> 15), 0x2c1b3c6d) >>> 0;
  x = Math.imul(x ^ (x >>> 12), 0x297a2d39) >>> 0;
  return ((x ^ (x >>> 15)) >>> 0) / 4294967296;
}

/** An even sub-sample, so a huge picture still flies at full frame rate. */
export function thinShape(s: FxShape, max = MAX): FxShape {
  const n = s.alpha.length;
  if (n <= max) return s;
  const segs = new Float32Array(max * 4);
  const alpha = new Float32Array(max);
  const gold = new Uint8Array(max);
  for (let i = 0; i < max; i++) {
    const j = Math.floor((i * n) / max);
    segs.set(s.segs.subarray(j * 4, j * 4 + 4), i * 4);
    alpha[i] = s.alpha[j];
    gold[i] = s.gold[j];
  }
  return { segs, alpha, gold };
}

/** Segment i of a shape as centre, half-length and angle (mod π). */
function decompose(s: FxShape, i: number): [number, number, number, number] {
  const x0 = s.segs[i * 4];
  const y0 = s.segs[i * 4 + 1];
  const x1 = s.segs[i * 4 + 2];
  const y1 = s.segs[i * 4 + 3];
  const dx = x1 - x0;
  const dy = y1 - y0;
  return [(x0 + x1) / 2, (y0 + y1) / 2, Math.max(0.6, Math.hypot(dx, dy) / 2), Math.atan2(dy, dx)];
}

/** Shortest turn from a to b for an undirected segment. */
function turn(a: number, b: number): number {
  let d = (b - a) % Math.PI;
  if (d > Math.PI / 2) d -= Math.PI;
  if (d < -Math.PI / 2) d += Math.PI;
  return d;
}

export class TransitionFx {
  private ctx: CanvasRenderingContext2D;
  private raf = 0;
  private w = 1;
  private h = 1;

  // per element (N of them)
  private n = 0;
  private x = new Float32Array(0);
  private y = new Float32Array(0);
  private th = new Float32Array(0);
  private len = new Float32Array(0);
  private vx = new Float32Array(0);
  private vy = new Float32Array(0);
  private om = new Float32Array(0);
  private delay = new Float32Array(0);
  private floor = new Float32Array(0);
  private rested = new Uint8Array(0);
  private a0 = new Float32Array(0);
  private g0 = new Uint8Array(0);
  // where each element goes: the pose it starts from, the pose it ends in
  private rx = new Float32Array(0);
  private ry = new Float32Array(0);
  private rth = new Float32Array(0);
  private rlen = new Float32Array(0);
  private tx = new Float32Array(0);
  private ty = new Float32Array(0);
  private tth = new Float32Array(0);
  private tlen = new Float32Array(0);
  private a1 = new Float32Array(0);
  private g1 = new Uint8Array(0);
  private start = new Float32Array(0);
  private curl = new Float32Array(0);

  private kind: FxKind = 'ruin';
  private target: FxShape | null = null;
  private clock = 0;
  private acc = 0;
  private last = 0;
  private built = false;
  private colors: FxColors = { ink: '#fff', gold: '#e3b04b' };
  private done: (() => void) | null = null;
  private buckets = Array.from({ length: LEVELS * 2 }, () => new Float32Array(0));
  private counts = new Int32Array(LEVELS * 2);

  constructor(private canvas: HTMLCanvasElement) {
    this.ctx = canvas.getContext('2d')!;
  }

  /** Is a run in progress? */
  get running(): boolean {
    return this.raf !== 0;
  }

  /**
   * Fly `from` into `to`. `refresh`, when given, is asked for a fresh target
   * at the moment the second picture starts to assemble (the first one may
   * have moved on while the pieces fell).
   */
  run(kind: FxKind, from: FxShape, to: FxShape, colors: FxColors, onDone: () => void, refresh?: () => FxShape | null): void {
    this.stop();
    TransitionFx.active = this;
    this.hold = false;
    this.kind = kind;
    this.colors = colors;
    this.done = onDone;
    this.refresh = refresh ?? null;
    this.resize();
    const src = thinShape(from);
    this.target = thinShape(to);
    const N = Math.max(src.alpha.length, this.target.alpha.length, 1);
    this.alloc(N);
    for (let i = 0; i < N; i++) {
      const j = src.alpha.length ? i % src.alpha.length : 0;
      if (!src.alpha.length) {
        this.a0[i] = 0;
        this.x[i] = this.w / 2;
        this.y[i] = this.h / 2;
        this.len[i] = 0.6;
        continue;
      }
      const [cx, cy, L, a] = decompose(src, j);
      this.x[i] = cx;
      this.y[i] = cy;
      this.len[i] = L;
      this.th[i] = a;
      this.a0[i] = src.alpha[j];
      this.g0[i] = src.gold[j];
      // the fall
      this.delay[i] = hash(i, 1) * 0.85 + (cy / this.h) * 0.15;
      this.vx[i] = (hash(i, 2) - 0.5) * 120;
      this.vy[i] = -hash(i, 3) * 90;
      this.om[i] = (hash(i, 4) - 0.5) * 7;
      this.floor[i] = this.h - 10 - Math.pow(hash(i, 5), 2.2) * Math.min(90, this.h * 0.1);
    }
    this.clock = 0;
    this.acc = 0;
    this.built = false;
    if (kind === 'morph') this.assemble();
    this.last = performance.now();
    this.raf = requestAnimationFrame(this.frame);
  }

  private refresh: (() => FxShape | null) | null = null;

  /** The run in progress, for the test inspector. */
  static active: TransitionFx | null = null;
  private hold = false;

  /**
   * Test hook: stop following the clock and jump to `t` seconds into the
   * flight (forward only). The run still ends, and calls back, once `t` is past
   * its end.
   */
  seek(t: number): void {
    this.hold = true;
    while (this.clock + STEP <= t) {
      this.clock += STEP;
      if (this.kind === 'ruin') this.fall();
    }
    this.tick();
  }

  stop(): void {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
    this.done = null;
    if (TransitionFx.active === this) TransitionFx.active = null;
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
  }

  private resize(): void {
    this.w = window.innerWidth;
    this.h = window.innerHeight;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = Math.floor(this.w * dpr);
    this.canvas.height = Math.floor(this.h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  private alloc(N: number): void {
    this.n = N;
    const f = () => new Float32Array(N);
    this.x = f();
    this.y = f();
    this.th = f();
    this.len = f();
    this.vx = f();
    this.vy = f();
    this.om = f();
    this.delay = f();
    this.floor = f();
    this.rested = new Uint8Array(N);
    this.a0 = f();
    this.g0 = new Uint8Array(N);
    this.rx = f();
    this.ry = f();
    this.rth = f();
    this.rlen = f();
    this.tx = f();
    this.ty = f();
    this.tth = f();
    this.tlen = f();
    this.a1 = f();
    this.g1 = new Uint8Array(N);
    this.start = f();
    this.curl = f();
    this.buckets = this.buckets.map(() => new Float32Array(N * 4));
  }

  /**
   * Pair every element with a place in the target and fix when it leaves.
   * Elements and places are both ordered along x (a 'ruin' heap) or around the
   * picture's middle (a 'morph'), so neighbours stay neighbours.
   */
  private assemble(): void {
    const fresh = this.refresh?.();
    if (fresh) this.target = thinShape(fresh);
    const T = this.target!;
    const N = this.n;
    const nt = T.alpha.length;
    const place: number[] = Array.from({ length: N }, (_, i) => i % Math.max(1, nt));
    const els = Array.from({ length: N }, (_, i) => i);

    const midOf = (xs: (i: number) => number, ys: (i: number) => number, ids: number[]): [number, number] => {
      let sx = 0;
      let sy = 0;
      for (const i of ids) {
        sx += xs(i);
        sy += ys(i);
      }
      return [sx / Math.max(1, ids.length), sy / Math.max(1, ids.length)];
    };
    const tcx = (p: number) => (T.segs[p * 4] + T.segs[p * 4 + 2]) / 2;
    const tcy = (p: number) => (T.segs[p * 4 + 1] + T.segs[p * 4 + 3]) / 2;

    let keyE: (i: number) => number;
    let keyP: (p: number) => number;
    if (this.kind === 'ruin') {
      keyE = (i) => this.x[i];
      keyP = (p) => tcx(p);
    } else {
      const [mx, my] = midOf((i) => this.x[i], (i) => this.y[i], els);
      const [px, py] = midOf(tcx, tcy, place);
      keyE = (i) => Math.atan2(this.y[i] - my, this.x[i] - mx);
      keyP = (p) => Math.atan2(tcy(p) - py, tcx(p) - px);
    }
    els.sort((a, b) => keyE(a) - keyE(b));
    place.sort((a, b) => keyP(a) - keyP(b));

    let minY = Infinity;
    let maxY = -Infinity;
    for (let p = 0; p < nt; p++) {
      minY = Math.min(minY, tcy(p));
      maxY = Math.max(maxY, tcy(p));
    }
    const span = Math.max(1, maxY - minY);

    for (let k = 0; k < N; k++) {
      const i = els[k];
      const p = nt ? place[k] : -1;
      this.rx[i] = this.x[i];
      this.ry[i] = this.y[i];
      this.rth[i] = this.th[i];
      this.rlen[i] = this.len[i];
      if (p < 0) {
        this.tx[i] = this.x[i];
        this.ty[i] = this.y[i];
        this.tth[i] = this.th[i];
        this.tlen[i] = this.len[i];
        this.a1[i] = 0;
        this.start[i] = 0;
        continue;
      }
      const [cx, cy, L, a] = decompose(T, p);
      this.tx[i] = cx;
      this.ty[i] = cy;
      this.tth[i] = this.th[i] + turn(this.th[i], a);
      this.tlen[i] = L;
      this.a1[i] = T.alpha[p];
      this.g1[i] = T.gold[p];
      this.curl[i] = (hash(i, 9) - 0.5) * 2;
      if (this.kind === 'ruin') {
        // bottom of the picture first; the order along the way is a little ragged
        const rank = (maxY - cy) / span;
        this.start[i] = Math.min(1, Math.max(0, rank * 0.93 + hash(i, 6) * 0.07)) * RUIN.build;
      } else {
        this.start[i] = hash(i, 6) * (MORPH.total - MORPH.piece - 0.1);
      }
    }
    this.built = true;
  }

  // ---- the frame ------------------------------------------------------------------

  private frame = (now: number): void => {
    this.raf = requestAnimationFrame(this.frame);
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    if (this.hold) return;
    this.acc += dt;
    while (this.acc >= STEP) {
      this.acc -= STEP;
      this.clock += STEP;
      if (this.kind === 'ruin') this.fall();
    }
    this.tick();
  };

  /** Draw the current moment; finish the run if it is over. */
  private tick(): void {
    if (this.kind === 'ruin' && !this.built && this.clock >= RUIN.fall + RUIN.pause) this.assemble();
    this.draw();
    const total = this.kind === 'ruin' ? RUIN.fall + RUIN.pause + RUIN.build + RUIN.piece : MORPH.total;
    if (this.clock >= total && this.raf) {
      const cb = this.done;
      cancelAnimationFrame(this.raf);
      this.raf = 0;
      this.done = null;
      TransitionFx.active = null;
      cb?.();
    }
  }

  /** One physics step while the pieces fall. */
  private fall(): void {
    if (this.clock > RUIN.fall + RUIN.pause) return;
    for (let i = 0; i < this.n; i++) {
      if (this.rested[i] || this.clock < this.delay[i]) continue;
      this.vy[i] += GRAVITY * STEP;
      this.x[i] += this.vx[i] * STEP;
      this.y[i] += this.vy[i] * STEP;
      this.th[i] += this.om[i] * STEP;
      if (this.y[i] >= this.floor[i]) {
        this.y[i] = this.floor[i];
        if (Math.abs(this.vy[i]) < 110) {
          this.rested[i] = 1;
          this.vx[i] = this.vy[i] = this.om[i] = 0;
        } else {
          this.vy[i] *= -0.3;
          this.vx[i] *= 0.55;
          this.om[i] *= 0.5;
        }
      }
      // lying pieces settle flat
      if (this.y[i] >= this.floor[i] - 0.5) this.th[i] += turn(this.th[i], 0) * 0.12;
    }
  }

  private draw(): void {
    const { ctx } = this;
    ctx.clearRect(0, 0, this.w, this.h);
    this.counts.fill(0);
    const ruin = this.kind === 'ruin';
    const t0 = ruin ? RUIN.fall + RUIN.pause : 0;
    const piece = ruin ? RUIN.piece : MORPH.piece;
    for (let i = 0; i < this.n; i++) {
      let x = this.x[i];
      let y = this.y[i];
      let th = this.th[i];
      let L = this.len[i];
      let alpha = this.a0[i];
      let gold = this.g0[i];
      if (this.built) {
        const u = ease((this.clock - t0 - this.start[i]) / piece);
        if (u > 0) {
          // from the pose the piece lay in (or the picture it was in) to its place, arching up on the way
          const lift = Math.sin(u * Math.PI);
          const dx = this.tx[i] - this.rx[i];
          const dy = this.ty[i] - this.ry[i];
          const d = Math.hypot(dx, dy) || 1;
          const arc = lift * (ruin ? Math.min(70, d * 0.18) : d * 0.22 * this.curl[i]);
          x = this.rx[i] + dx * u + (-dy / d) * arc * (ruin ? 0 : 1);
          y = this.ry[i] + dy * u + (ruin ? -arc : (dx / d) * arc);
          th = this.rth[i] + (this.tth[i] - this.rth[i]) * u;
          L = this.rlen[i] + (this.tlen[i] - this.rlen[i]) * u;
          alpha = this.a0[i] + (this.a1[i] - this.a0[i]) * u;
          gold = u < 0.5 ? this.g0[i] : this.g1[i];
        } else if (!ruin) {
          x = this.rx[i];
          y = this.ry[i];
        }
      }
      const q = Math.min(LEVELS - 1, Math.max(0, Math.floor(alpha * LEVELS)));
      if (alpha <= 0.01) continue;
      const b = gold * LEVELS + q;
      const buf = this.buckets[b];
      const o = this.counts[b]++ * 4;
      const c = Math.cos(th) * L;
      const s = Math.sin(th) * L;
      buf[o] = x - c;
      buf[o + 1] = y - s;
      buf[o + 2] = x + c;
      buf[o + 3] = y + s;
    }
    ctx.lineCap = 'round';
    ctx.lineWidth = 1;
    for (let b = 0; b < LEVELS * 2; b++) {
      const cnt = this.counts[b];
      if (!cnt) continue;
      ctx.strokeStyle = b >= LEVELS ? this.colors.gold : this.colors.ink;
      ctx.globalAlpha = Math.min(1, ((b % LEVELS) + 0.5) / LEVELS);
      ctx.beginPath();
      const buf = this.buckets[b];
      for (let k = 0; k < cnt; k++) {
        const o = k * 4;
        ctx.moveTo(buf[o], buf[o + 1]);
        ctx.lineTo(buf[o + 2], buf[o + 3]);
      }
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }
}

export const FX_KINDS: readonly FxKind[] = ['morph', 'ruin'];
