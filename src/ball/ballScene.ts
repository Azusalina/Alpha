/**
 * The ball: how well the model fits one person (docs: design/ball-design.md, D68).
 *
 *  - the sphere is the person; its surface is a stack of tilted bands that
 *    carry ripples. One facet of the surface per model parameter: the stronger
 *    the fit there (BallFit.fit), the livelier the ripples; no evidence, a
 *    still surface;
 *  - a spike stands where the fit is concentrated in a few strong statements
 *    (BallFit.peak): its band region swells and sharpens and the spike grows
 *    out of that peak. A thin-evidence facet draws the spike hollow;
 *  - the older chord / diameter forms stay as an ambient, unexplained layer.
 *
 * Motion: the sphere itself does not spin. It breathes, floats, its waves run
 * (tide), a heartbeat pulses the amplitude, spikes resonate; the pointer and a
 * click make the surface answer; a drag tilts it and it settles back.
 *
 * Rendering is plain line segments, rewritten each frame on the CPU (a few
 * thousand segments), in orthographic pixel space. No fill, no sketch texture.
 */

import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  LineBasicMaterial,
  LineSegments,
  NormalBlending,
  OrthographicCamera,
  Scene,
  WebGLRenderer,
} from 'three';

import { facetDirections, type BallFit } from './ballFit';
import type { FxShape } from './transitionFx';

export type BallTheme = 'light' | 'dark';
export type BallLook = 1 | 2;

type V3 = [number, number, number];

const TAU = Math.PI * 2;
const MAX_SEGS = 9000;

const NB = 9; // bands
const NS = 200; // samples per band
const BAND_LAT = Array.from({ length: NB }, (_, i) => ((-60 + (118 * i) / (NB - 1)) * Math.PI) / 180);

function mulberry32(a: number) {
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const clamp01 = (x: number) => (x < 0 ? 0 : x > 1 ? 1 : x);
const smooth = (a: number, b: number, x: number) => {
  const t = clamp01((x - a) / (b - a));
  return t * t * (3 - 2 * t);
};
const norm = (v: V3): V3 => {
  const l = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / l, v[1] / l, v[2] / l];
};
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const dot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

/** Rotate v about unit axis k by angle a (Rodrigues). */
function rot(v: V3, k: V3, a: number): V3 {
  const c = Math.cos(a);
  const s = Math.sin(a);
  const kv = cross(k, v);
  const kd = dot(k, v) * (1 - c);
  return [v[0] * c + kv[0] * s + k[0] * kd, v[1] * c + kv[1] * s + k[1] * kd, v[2] * c + kv[2] * s + k[2] * kd];
}

/** Angle between two unit vectors. */
const angle = (a: V3, b: V3) => Math.acos(Math.max(-1, Math.min(1, dot(a, b))));

type Kind = 'solid' | 'barbed' | 'hollow';

interface Spike {
  dir: V3;
  e1: V3;
  e2: V3;
  kind: Kind;
  reach: number; // length beyond the surface, in radii
  rho: number; // root half-width, in radii
  bend: V3;
  bendAmp: number;
  seed: number;
}

/** One life: a spike (or a chord / diameter with two ends) with its own clock. */
interface Life {
  ends: Spike[];
  /** 'chord' / 'diameter' draw the line through the ball between the two ends. */
  through: 'none' | 'chord' | 'diameter';
  period: number;
  offset: number;
  scar: number; // how much of a spike stays when it has retracted
  /** A fit spike: always out, its length set by the data (no life cycle). */
  steady?: boolean;
  /** The facet this life stands for (fit spikes only). */
  facet?: number;
}

interface Shock {
  dir: V3;
  t0: number;
}

/** What the pointer is over: the index of a facet (BallFit order). */
export interface BallHover {
  facet: number;
}

export interface BallStyle {
  theme: BallTheme;
  look: BallLook;
}

export class BallScene {
  private renderer: WebGLRenderer;
  private scene = new Scene();
  private camera = new OrthographicCamera(-1, 1, 1, -1, -10, 10);
  private geo = new BufferGeometry();
  private pos = new Float32Array(MAX_SEGS * 6);
  private col = new Float32Array(MAX_SEGS * 8);
  private mat = new LineBasicMaterial({ vertexColors: true, transparent: true, depthTest: false, depthWrite: false });
  private lines: LineSegments;
  private n = 0;

  private w = 1;
  private h = 1;
  private lives: Life[] = [];
  /** The ambient layer (chords, the diameter); `lives` = these + the fit spikes. */
  private ambient: Life[] = [];
  private fit: BallFit = [];
  private dirs = facetDirections();
  /** Called when the pointer moves onto / off / between facets. */
  onHover: ((h: BallHover | null) => void) | null = null;
  private hoverFacet = -1;
  private shocks: Shock[] = [];
  private style: BallStyle = { theme: 'dark', look: 1 };
  private reduced: boolean;

  // pointer
  private hover = 0;
  private hoverTarget = 0;
  private hoverDir: V3 = [0, 0, 1];
  private pointerPx: [number, number] | null = null;
  private drag: { x: number; y: number; moved: number } | null = null;
  private dragYaw = 0;
  private dragPitch = 0;

  // frame transform
  private m = new Float64Array(9);
  private cx = 0;
  private cy = 0;
  private S = 1;
  private clock = 0;
  private last = 0;
  private raf = 0;
  private ro: ResizeObserver;
  private off: Array<() => void> = [];

  constructor(private canvas: HTMLCanvasElement, reducedMotion: boolean) {
    this.reduced = reducedMotion;
    this.renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
    this.renderer.setClearColor(0x000000, 0);
    this.geo.setAttribute('position', new BufferAttribute(this.pos, 3).setUsage(35048));
    this.geo.setAttribute('color', new BufferAttribute(this.col, 4).setUsage(35048));
    this.lines = new LineSegments(this.geo, this.mat);
    this.lines.frustumCulled = false;
    this.scene.add(this.lines);
    this.build();
    this.resize();
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(canvas);
    this.bindPointer();
    this.last = performance.now();
    this.raf = requestAnimationFrame(this.frame);
  }

  setStyle(s: BallStyle): void {
    this.style = s;
    const dark = s.theme === 'dark';
    this.mat.blending = dark ? AdditiveBlending : NormalBlending;
    this.mat.needsUpdate = true;
  }

  dispose(): void {
    cancelAnimationFrame(this.raf);
    this.ro.disconnect();
    this.off.forEach((f) => f());
    this.geo.dispose();
    this.mat.dispose();
    this.renderer.dispose();
  }

  // ---- construction -------------------------------------------------------------

  private makeSpike(dir: V3, kind: Kind, rnd: () => number, reach?: number): Spike {
    const d = norm(dir);
    const ref: V3 = Math.abs(d[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0];
    const e1 = norm(cross(d, ref));
    const e2 = cross(d, e1);
    const bendAxis = rot(e1, d, rnd() * TAU);
    return {
      dir: d,
      e1,
      e2,
      kind,
      reach: reach ?? 0.55 + rnd() * 0.75,
      rho: 0.04 + rnd() * 0.028,
      bend: bendAxis,
      bendAmp: (rnd() - 0.5) * 0.22,
      seed: rnd() * 100,
    };
  }

  private build(): void {
    const rnd = mulberry32(20261002);
    // the ambient layer: two chords (off-centre, deep but not through the core) and one
    // diameter (through the core). Not data; nothing on the page explains them.
    const dirs: V3[] = [];
    for (let i = 0; i < 3; i++) {
      const y = 1 - (2 * (i + 0.5)) / 3;
      const r = Math.sqrt(1 - y * y);
      const a = i * 2.399963 + 0.7 + rnd() * 0.25;
      dirs.push(norm([Math.cos(a) * r, y, Math.sin(a) * r]));
    }
    const life = (ends: Spike[], through: Life['through']): void => {
      const barbed = ends.some((e) => e.kind === 'barbed');
      this.ambient.push({
        ends,
        through,
        period: 17 + rnd() * 15,
        offset: rnd() < 0.72 ? 0.34 + rnd() * 0.34 : rnd(),
        scar: barbed ? 0.14 : 0,
      });
    };
    let k = 0;
    for (let c = 0; c < 2; c++) {
      const a = dirs[k++ % 3];
      const axis = norm(cross(a, [rnd() - 0.5, rnd() - 0.5, rnd() - 0.5]));
      const b = rot(a, axis, 1.9 + rnd() * 0.4);
      life([this.makeSpike(a, 'solid', rnd, 0.7), this.makeSpike(b, 'solid', rnd, 0.7)], 'chord');
    }
    const a = dirs[2];
    life([this.makeSpike(a, 'barbed', rnd, 0.95), this.makeSpike([-a[0], -a[1], -a[2]], 'solid', rnd, 0.95)], 'diameter');
    this.ambient[this.ambient.length - 1].offset = 0.45;
    this.lives = [...this.ambient];
  }

  /** The data: where the surface ripples and where a spike stands. */
  setFit(fit: BallFit): void {
    this.fit = fit;
    this.lives = [...this.ambient];
    fit.forEach((f, i) => {
      if (f.peak < 0.2 || !this.dirs[i]) return;
      const kind: Kind = f.thin ? 'hollow' : f.fit > 0.75 && f.peak > 0.6 ? 'barbed' : 'solid';
      const sp = this.makeSpike(this.dirs[i], kind, mulberry32(1000 + i), 0.25 + 0.7 * f.peak);
      this.lives.push({ ends: [sp], through: 'none', period: 1, offset: 0, scar: 0, steady: true, facet: i });
    });
  }

  /** The current drawing as segments in CSS px (the page transition flies them). */
  sample(): FxShape {
    const n = this.n;
    const segs = new Float32Array(n * 4);
    const alpha = new Float32Array(n);
    const gold = new Uint8Array(n);
    for (let i = 0; i < n; i++) {
      segs[i * 4] = this.pos[i * 6] + this.w / 2;
      segs[i * 4 + 1] = this.h / 2 - this.pos[i * 6 + 1];
      segs[i * 4 + 2] = this.pos[i * 6 + 3] + this.w / 2;
      segs[i * 4 + 3] = this.h / 2 - this.pos[i * 6 + 4];
      alpha[i] = (this.col[i * 8 + 3] + this.col[i * 8 + 7]) / 2;
      gold[i] = this.col[i * 8] > this.col[i * 8 + 1] * 1.25 ? 1 : 0;
    }
    return { segs, alpha, gold };
  }

  // ---- pointer ------------------------------------------------------------------

  private bindPointer(): void {
    const c = this.canvas;
    const on = <K extends keyof HTMLElementEventMap>(t: HTMLElement, k: K, f: (e: HTMLElementEventMap[K]) => void) => {
      t.addEventListener(k, f as EventListener);
      this.off.push(() => t.removeEventListener(k, f as EventListener));
    };
    const rel = (e: PointerEvent): [number, number] => {
      const r = c.getBoundingClientRect();
      return [e.clientX - r.left, e.clientY - r.top];
    };
    on(c, 'pointermove', (e) => {
      const p = rel(e);
      this.pointerPx = p;
      if (this.drag) {
        const dx = p[0] - this.drag.x;
        const dy = p[1] - this.drag.y;
        this.drag.x = p[0];
        this.drag.y = p[1];
        this.drag.moved += Math.abs(dx) + Math.abs(dy);
        this.dragYaw = Math.max(-0.9, Math.min(0.9, this.dragYaw + dx * 0.005));
        this.dragPitch = Math.max(-0.7, Math.min(0.7, this.dragPitch + dy * 0.005));
      }
    });
    on(c, 'pointerleave', () => {
      this.pointerPx = null;
    });
    on(c, 'pointerdown', (e) => {
      const p = rel(e);
      this.drag = { x: p[0], y: p[1], moved: 0 };
      c.setPointerCapture(e.pointerId);
    });
    const up = (e: PointerEvent) => {
      const d = this.drag;
      this.drag = null;
      if (c.hasPointerCapture(e.pointerId)) c.releasePointerCapture(e.pointerId);
      if (d && d.moved < 5 && this.hoverTarget > 0.01) {
        this.shocks.push({ dir: [...this.hoverDir] as V3, t0: this.clock });
        if (this.shocks.length > 4) this.shocks.shift();
      }
    };
    on(c, 'pointerup', up);
    on(c, 'pointercancel', up);
  }

  private resize(): void {
    const r = this.canvas.getBoundingClientRect();
    const w = Math.max(2, Math.floor(r.width));
    const h = Math.max(2, Math.floor(r.height));
    this.w = w;
    this.h = h;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setSize(w, h, false);
    this.camera.left = -w / 2;
    this.camera.right = w / 2;
    this.camera.top = h / 2;
    this.camera.bottom = -h / 2;
    this.camera.updateProjectionMatrix();
  }

  // ---- drawing ------------------------------------------------------------------

  /** Local → world pixels. */
  private tx(p: V3): V3 {
    const m = this.m;
    return [
      this.cx + this.S * (m[0] * p[0] + m[1] * p[1] + m[2] * p[2]),
      this.cy + this.S * (m[3] * p[0] + m[4] * p[1] + m[5] * p[2]),
      m[6] * p[0] + m[7] * p[1] + m[8] * p[2],
    ];
  }

  /**
   * One vertex colour. `flow` (0..1) is the current moving through the line in
   * look 2 (dark: gold); `a` the intended opacity; `z` the depth (facing the
   * viewer is +1) which dims the far side.
   */
  private put(i: number, p: V3, a: number, flow: number, z: number): void {
    const { theme, look } = this.style;
    const dark = theme === 'dark';
    const depth = 0.3 + 0.7 * smooth(-0.55, 0.45, z);
    let r: number;
    let g: number;
    let b: number;
    let alpha = a * depth;
    if (look === 2 && dark) {
      // black-gold: mostly dim gold, with currents of brighter gold running through it
      const f = clamp01(flow);
      r = 0.2 + 0.8 * f;
      g = 0.13 + 0.62 * f;
      b = 0.03 + 0.25 * f;
      alpha *= 0.55 + 0.45 * f;
    } else if (dark) {
      r = g = b = 0.94;
      alpha *= 0.72;
    } else if (look === 2) {
      // black outline only: no tonal play
      r = g = b = 0;
      alpha = Math.min(1, a * 1.15) * (0.55 + 0.45 * depth);
    } else {
      r = g = b = 0.1;
      alpha *= 0.92;
    }
    const o = i * 4;
    this.col[o] = r;
    this.col[o + 1] = g;
    this.col[o + 2] = b;
    this.col[o + 3] = clamp01(alpha);
    const q = i * 3;
    this.pos[q] = p[0];
    this.pos[q + 1] = p[1];
    this.pos[q + 2] = 0;
  }

  /** A segment between two local points. */
  private seg(a: V3, b: V3, alpha: number, fa = 0, fb = fa, alphaB = alpha): void {
    if (this.n >= MAX_SEGS) return;
    const A = this.tx(a);
    const B = this.tx(b);
    this.put(this.n * 2, A, alpha, fa, A[2]);
    this.put(this.n * 2 + 1, B, alphaB, fb, B[2]);
    this.n++;
  }

  private poly(pts: V3[], alpha: (i: number) => number, flow: (i: number) => number, closed = false): void {
    const L = pts.length;
    const end = closed ? L : L - 1;
    for (let i = 0; i < end; i++) {
      const j = (i + 1) % L;
      this.seg(pts[i], pts[j], alpha(i), flow(i), flow(j), alpha(j));
    }
  }

  // ---- the frame ----------------------------------------------------------------

  private frame = (now: number): void => {
    this.raf = requestAnimationFrame(this.frame);
    // a long gap (hidden tab, a stall) must not become a jump
    const dt = Math.min(0.05, Math.max(0, (now - this.last) / 1000));
    this.last = now;
    this.clock += this.reduced ? dt * 0.35 : dt;
    this.update(this.clock, dt);
    this.renderer.render(this.scene, this.camera);
  };

  /** Heartbeat envelope, period 1.9 s. */
  private pulse(t: number): number {
    const p = (t % 1.9) / 1.9;
    return Math.exp(-(((p - 0.08) / 0.05) ** 2)) + 0.5 * Math.exp(-(((p - 0.3) / 0.08) ** 2));
  }

  private lifeAt(l: Life, t: number): { wave: number; len: number } {
    if (l.steady) {
      const peak = this.fit[l.facet ?? -1]?.peak ?? 0.5;
      return { wave: 0.35 + 0.65 * peak, len: 1 };
    }
    const u = (t / l.period + l.offset) % 1;
    const wave = smooth(0.02, 0.3, u) * (1 - smooth(0.7, 0.92, u));
    const len = l.scar + (1 - l.scar) * smooth(0.2, 0.46, u) * (1 - smooth(0.72, 0.9, u));
    return { wave, len };
  }

  /** How lively the ripples are at `dir`: the fit of the facets around it (0.2 when nothing fits there). */
  private fitGain(dir: V3): number {
    let f = 0;
    for (let i = 0; i < this.fit.length; i++) {
      const d = this.dirs[i];
      const c = Math.max(-1, Math.min(1, dot(dir, d)));
      const a = Math.acos(c);
      f += this.fit[i].fit * Math.exp(-((a / 0.62) ** 2));
    }
    return 0.2 + 1.1 * Math.min(1, f);
  }

  private update(t: number, dt: number): void {
    const w = this.w;
    const h = this.h;
    // the ball takes the particle brain's place (lower left: left 4% / bottom 6%, 30% x 48% of the view)
    const R = Math.min(w * 0.3, h * 0.48) * 0.4;
    this.S = R;
    // the camera is centred on the window, y up
    this.cx = -w * 0.29;
    this.cy = -h * 0.2 + Math.sin(t * 0.5) * R * 0.012;

    // orientation: a fixed lean (the bands slant), a faint sway, the user's tilt
    const k = Math.exp(-dt * (this.drag ? 0 : 1.6));
    this.dragYaw *= k;
    this.dragPitch *= k;
    const yaw = 0.18 + this.dragYaw + Math.sin(t * 0.13) * 0.05;
    const pit = 0.2 + this.dragPitch + Math.sin(t * 0.17 + 1) * 0.03;
    const rz = 0.3;
    const [cyw, syw, cp, sp, cz, sz] = [Math.cos(yaw), Math.sin(yaw), Math.cos(pit), Math.sin(pit), Math.cos(rz), Math.sin(rz)];
    // M = Rz * Rx(pit) * Ry(yaw)
    const ry = [cyw, 0, syw, 0, 1, 0, -syw, 0, cyw];
    const rx = [1, 0, 0, 0, cp, -sp, 0, sp, cp];
    const rzm = [cz, -sz, 0, sz, cz, 0, 0, 0, 1];
    const mul = (a: number[], b: number[]) => {
      const o = new Array<number>(9).fill(0);
      for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) for (let q = 0; q < 3; q++) o[i * 3 + j] += a[i * 3 + q] * b[q * 3 + j];
      return o;
    };
    const M = mul(rzm, mul(rx, ry));
    for (let i = 0; i < 9; i++) this.m[i] = M[i];

    // pointer → direction on the front of the ball (in local coordinates)
    let target = 0;
    if (this.pointerPx) {
      const px = (this.pointerPx[0] - w / 2 - this.cx) / R;
      const py = (h / 2 - this.pointerPx[1] - this.cy) / R;
      const rr = Math.hypot(px, py);
      if (rr < 1.35) {
        const z = Math.sqrt(Math.max(0, 1 - Math.min(rr, 1) ** 2));
        const s = rr > 1 ? 1 / rr : 1;
        const world: V3 = [px * s, py * s, z];
        // inverse of M is its transpose
        this.hoverDir = norm([
          M[0] * world[0] + M[3] * world[1] + M[6] * world[2],
          M[1] * world[0] + M[4] * world[1] + M[7] * world[2],
          M[2] * world[0] + M[5] * world[1] + M[8] * world[2],
        ]);
        target = 1 - smooth(1.0, 1.35, rr) * 0.8;
      }
    }
    this.hoverTarget = target;
    {
      let best = -1;
      if (target > 0.3) {
        let ba = 0.62;
        for (let i = 0; i < this.fit.length; i++) {
          const a = angle(this.hoverDir, this.dirs[i]);
          if (a < ba) {
            ba = a;
            best = i;
          }
        }
      }
      if (best !== this.hoverFacet) {
        this.hoverFacet = best;
        this.onHover?.(best < 0 ? null : { facet: best });
      }
    }
    this.hover += (target - this.hover) * (1 - Math.exp(-dt * 6));
    this.shocks = this.shocks.filter((s) => t - s.t0 < 4);

    const breath = 1 + 0.024 * Math.sin((t / 5.2) * TAU);
    const pulse = this.pulse(t) * (this.reduced ? 0.4 : 1);

    // each life: where its spikes are now, and how strongly its region is swelling
    const states = this.lives.map((l) => this.lifeAt(l, t));
    const hov = this.hover;
    const hd = this.hoverDir;

    this.n = 0;

    // ---- bands: the waves ------------------------------------------------------
    for (let i = 0; i < NB; i++) {
      const lat = BAND_LAT[i];
      const cl = Math.cos(lat);
      const sl = Math.sin(lat);
      const tide = 0.55 + 0.45 * Math.sin(t * 0.42 - i * 0.62);
      const pts: V3[] = [];
      const al: number[] = [];
      const fl: number[] = [];
      for (let s = 0; s < NS; s++) {
        const th = (s / NS) * TAU;
        const ct = Math.cos(th);
        const st = Math.sin(th);
        const dir: V3 = [cl * ct, sl, cl * st];
        const north: V3 = [-sl * ct, cl, -sl * st];
        const reg = 0.55 + 0.45 * Math.sin(2 * th + 0.3 * t + i * 1.1);
        let wave =
          0.5 * Math.sin(5 * th + 0.9 * t + i * 1.3) +
          0.3 * Math.sin(11 * th - 1.4 * t + i * 2.1) +
          0.2 * Math.sin(23 * th + 2.3 * t + i * 0.7);
        let amp = 0.036 * reg * (0.5 + 0.7 * tide) * (1 + 0.55 * pulse) * this.fitGain(dir);
        let radial = 0;
        let lit = 0;
        // swelling before a spike, sharpening into its root
        for (let q = 0; q < this.lives.length; q++) {
          const st2 = states[q];
          if (st2.wave < 0.01) continue;
          for (const e of this.lives[q].ends) {
            const al2 = angle(dir, e.dir);
            if (al2 > 0.9) continue;
            const kk = Math.exp(-((al2 / 0.34) ** 2)) * st2.wave;
            amp *= 1 + 1.9 * kk;
            wave += kk * 0.55 * Math.sin(37 * th - 3 * t + e.seed);
            radial += 0.07 * st2.wave * Math.exp(-((al2 / 0.11) ** 2));
            lit += kk;
          }
        }
        // the pointer wakes the waves under it
        if (hov > 0.01) {
          const ah = angle(dir, hd);
          const kh = Math.exp(-((ah / 0.55) ** 2)) * hov;
          amp *= 1 + 1.3 * kh;
          lit += kh * 0.6;
        }
        // a click sends a ring over the surface
        let shock = 0;
        for (const sh of this.shocks) {
          const tau = t - sh.t0;
          const ring = 1.7 * tau;
          const ash = angle(dir, sh.dir);
          shock += Math.exp(-(((ash - ring) / 0.2) ** 2)) * 0.075 * Math.exp(-tau / 1.5) * Math.sin(ash * 26 - tau * 14);
        }
        const along = wave * amp + shock;
        const rad = breath + radial + 0.35 * along;
        pts.push([dir[0] * rad + north[0] * along, dir[1] * rad + north[1] * along, dir[2] * rad + north[2] * along]);
        al.push(Math.min(1, 0.5 + 0.28 * tide + 0.35 * lit));
        const flow = Math.pow(0.5 + 0.5 * Math.sin(3 * th - 0.85 * t + i * 1.1 + 2 * Math.sin(0.4 * t + i)), 3) * (0.5 + 0.5 * tide) + 0.35 * lit;
        fl.push(flow);
      }
      this.poly(pts, (j) => al[j], (j) => fl[j], true);
    }

    // ---- the rim: the sphere's outline, a little irregular ----------------------
    {
      const pts: V3[] = [];
      const NR = 180;
      for (let s = 0; s < NR; s++) {
        const th = (s / NR) * TAU;
        const r =
          breath * (1 + 0.012 * Math.sin(3 * th + 0.2 * t) + 0.008 * Math.sin(5 * th - 0.31 * t) + 0.004 * pulse);
        // the outline faces the viewer: build it in world axes, then undo M so tx() lands on it
        const wv: V3 = [Math.cos(th) * r, Math.sin(th) * r, 0];
        pts.push([M[0] * wv[0] + M[3] * wv[1] + M[6] * wv[2], M[1] * wv[0] + M[4] * wv[1] + M[7] * wv[2], M[2] * wv[0] + M[5] * wv[1] + M[8] * wv[2]]);
      }
      this.poly(pts, () => 0.7 + 0.2 * pulse, (j) => 0.25 + 0.75 * Math.pow(0.5 + 0.5 * Math.sin((j / NR) * TAU * 2 - t * 0.5), 4), true);
    }

    // ---- spikes -----------------------------------------------------------------
    for (let q = 0; q < this.lives.length; q++) {
      const l = this.lives[q];
      const st = states[q];
      const lifeAlpha = 1;
      for (const e of l.ends) {
        const near = hov > 0.01 ? Math.exp(-((angle(e.dir, hd) / 0.55) ** 2)) * hov : 0;
        let shockKick = 0;
        for (const sh of this.shocks) {
          const tau = t - sh.t0;
          shockKick += Math.exp(-(((angle(e.dir, sh.dir) - 1.7 * tau) / 0.25) ** 2)) * Math.exp(-tau / 1.5);
        }
        // pointer pokes a retracted spike out a little; resonance and kicks lengthen a live one
        const res = 1 + 0.05 * Math.sin(t * 5.5 + e.seed) + 0.04 * pulse + 0.18 * near + 0.25 * shockKick;
        const len = Math.max(st.len, 0.32 * near) * res;
        if (len < 0.02) continue;
        this.spike(e, len, t, st.len, lifeAlpha, near);
      }
      if (l.through !== 'none' && st.len > 0.05) {
        const [a, b] = l.ends;
        const aa = Math.min(1, st.len) * 0.55;
        const p0: V3 = [a.dir[0] * breath, a.dir[1] * breath, a.dir[2] * breath];
        const p1: V3 = [b.dir[0] * breath, b.dir[1] * breath, b.dir[2] * breath];
        const N = 24;
        for (let s = 0; s < N; s++) {
          if (s % 3 === 2) continue; // dashed: the part inside the ball
          const f0 = s / N;
          const f1 = (s + 1) / N;
          const lerp = (f: number): V3 => [p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f, p0[2] + (p1[2] - p0[2]) * f];
          const fl = Math.pow(0.5 + 0.5 * Math.sin(f0 * 8 - t * 1.6 + q), 2);
          this.seg(lerp(f0), lerp(f1), aa, fl, fl);
        }
        if (l.through === 'diameter') {
          // the core, lit while a spike goes through it
          const rc = 0.05 + 0.025 * pulse;
          const ring: V3[] = [];
          for (let s = 0; s < 28; s++) {
            const th = (s / 28) * TAU;
            const wv: V3 = [Math.cos(th) * rc, Math.sin(th) * rc, 0];
            ring.push([M[0] * wv[0] + M[3] * wv[1] + M[6] * wv[2], M[1] * wv[0] + M[4] * wv[1] + M[7] * wv[2], M[2] * wv[0] + M[5] * wv[1] + M[8] * wv[2]]);
          }
          this.poly(ring, () => Math.min(1, st.len) * 0.95, () => 1, true);
        }
      }
    }

    const geo = this.geo;
    geo.setDrawRange(0, this.n * 2);
    (geo.getAttribute('position') as BufferAttribute).needsUpdate = true;
    (geo.getAttribute('color') as BufferAttribute).needsUpdate = true;
  }

  /** One spike of length `len` (in radii beyond the surface), drawn as a thin cone. */
  private spike(e: Spike, len: number, t: number, grown: number, alpha: number, near: number): void {
    const hollow = e.kind === 'hollow';
    const barbed = e.kind === 'barbed';
    const L = e.reach * len;
    const M = 12;
    const rho0 = e.rho * (hollow ? 1.7 : 1) * (0.7 + 0.3 * Math.min(1, len));
    const tremble = 0.012 * Math.sin(t * 7.3 + e.seed) * (0.4 + near) * Math.min(1, len);
    const base = 1.0; // the surface
    const axis = (u: number): V3 => {
      const r = base + L * u;
      const b = e.bendAmp * L * u * u + tremble * u;
      return [e.dir[0] * r + e.bend[0] * b, e.dir[1] * r + e.bend[1] * b, e.dir[2] * r + e.bend[2] * b];
    };
    // flared root, fine tip
    const rho = (u: number) => rho0 * (0.5 * Math.pow(1 - u, 2.2) + 0.95 * Math.exp(-u * 11) * (1 - u)) + 0.0012;
    const frame = (u: number, a: number): V3 => {
      const c = Math.cos(a);
      const s = Math.sin(a);
      const r = rho(u);
      return [(e.e1[0] * c + e.e2[0] * s) * r, (e.e1[1] * c + e.e2[1] * s) * r, (e.e1[2] * c + e.e2[2] * s) * r];
    };
    const strands = hollow ? [0, Math.PI] : [0, Math.PI / 2, Math.PI, (Math.PI * 3) / 2];
    const aLine = alpha * (hollow ? 0.8 : 1);
    const flowAt = (u: number) => Math.pow(0.5 + 0.5 * Math.sin(u * 7 - t * 2.1 + e.seed), 2.5) * 0.8 + 0.2 * u + 0.1;

    for (const a0 of strands) {
      const pts: V3[] = [];
      for (let i = 0; i <= M; i++) {
        const u = Math.pow(i / M, 0.9);
        const ax = axis(u);
        const f = frame(u, a0 + u * 0.5);
        pts.push([ax[0] + f[0], ax[1] + f[1], ax[2] + f[2]]);
      }
      this.poly(pts, (i) => aLine * (0.55 + 0.45 * (i / M)), (i) => flowAt(i / M));
    }
    // solid: an axis, and rungs that make it read as filled
    if (!hollow) {
      const pts: V3[] = [];
      for (let i = 0; i <= M; i++) pts.push(axis(i / M));
      this.poly(pts, () => aLine, (i) => flowAt(i / M));
      for (const u of [0.12, 0.26, 0.42]) {
        const p = axis(u);
        const f = frame(u, 0.0);
        this.seg([p[0] - f[0], p[1] - f[1], p[2] - f[2]], [p[0] + f[0], p[1] + f[1], p[2] + f[2]], aLine * 0.6, flowAt(u));
      }
    } else {
      // hollow: the root stays open — a ring, and nothing inside it
      const ring: V3[] = [];
      for (let i = 0; i < 20; i++) {
        const a = (i / 20) * TAU;
        const f = frame(0.02, a);
        const p = axis(0.02);
        ring.push([p[0] + f[0], p[1] + f[1], p[2] + f[2]]);
      }
      this.poly(ring, () => aLine * 0.6, () => 0.3, true);
    }
    // barbs: back-swept hooks that make a withdrawal hard
    if (barbed) {
      const barbs = Math.max(2, Math.round(6 * Math.min(1, grown + 0.3)));
      for (let i = 0; i < barbs; i++) {
        const u = 0.34 + 0.5 * (i / Math.max(1, barbs - 1));
        const side = i % 2 === 0 ? 1 : -1;
        const f = frame(u, side > 0 ? 0 : Math.PI);
        const p = axis(u);
        const out: V3 = [p[0] + f[0], p[1] + f[1], p[2] + f[2]];
        const back = axis(Math.max(0, u - 0.17));
        const hook = 0.05 * (1 - u * 0.4) * (0.7 + 0.3 * Math.min(1, len));
        const sx = side;
        this.seg(out, [back[0] + e.e1[0] * hook * sx * 1.6 + f[0], back[1] + e.e1[1] * hook * sx * 1.6 + f[1], back[2] + e.e1[2] * hook * sx * 1.6 + f[2]], aLine * 0.9, 0.9, 0.6);
      }
    }
  }
}
