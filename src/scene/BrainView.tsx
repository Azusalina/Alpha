/**
 * The particle brain at the human destination (IDEA §3, spec 3 前往左上).
 *
 * Ported from the 3dbrain reference (github.com/victors1681/3dbrain, MIT;
 * decision D33): its brain point model, its per-particle delayed
 * `mix(start, end, ease(p))` fly-in, its region grouping and its auto-rotation.
 * Its glow shell, additive blue and post-processing are deliberately not
 * ported — here the brain is ink on paper, like the particle hand (IDEA §5).
 *
 * The brain is *made of the left hand*: every particle is sampled on the left
 * hand's surface (brain/humanCloud.ts) and appears exactly where the plaster
 * withdraws, then migrates to its brain point. All of it is a function of the
 * one transition progress p (spec 7.2), so the return path is the same path
 * run backwards and lands on the same points.
 *
 * At the destination the brain rests in the lower left of the view; a click
 * drills in (decision D34): it moves to the centre and grows, a ripple runs
 * through it from the clicked point, and the placeholder GraphData grows as a
 * tree inside it (root at the centre, one branch per placeholder region).
 * Drag turns it; hovering names a region or a node; clicking a node opens its
 * detail. Escape or the back button leaves the drill-in.
 *
 * The brain answers an input with a performance (D57, humanStore.perform): bolts
 * that run along the net's edges in the state's own colours, and for the crazy
 * state (D62) the whole brain, dots, net and tree, collapsing into one
 * singularity at its centre and unfolding again to the very same points, with a
 * light at the point. Everything for it is prebuilt and bounded: one
 * quad-strip mesh per bank (two banks, so a new performance can take over while
 * the old one fades), written once per performance, animated in the shader on
 * the scene clock; the underglow on the dots and lines reuses the D53 hop
 * waves. With no performance running nothing of it is drawn or changed.
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useMemo, useRef } from 'react';
import {
  AdditiveBlending,
  BufferGeometry,
  Color,
  DoubleSide,
  Euler,
  Float32BufferAttribute,
  Group,
  Matrix4,
  NormalBlending,
  PlaneGeometry,
  Quaternion,
  Ray,
  ShaderMaterial,
  Sphere,
  Uint16BufferAttribute,
  Vector2,
  Vector3,
  type Mesh,
} from 'three';

import { DIAGNOSTICS_ENABLED } from '../app/diagnostics';
import { humanStore, type Signal } from '../app/humanStore';
import { humanProgress, stage } from '../app/stage';
import { buildHumanCloud, nodeBrainPositions } from '../brain/humanCloud';
import { hopDistances, nearestVertex, useBrainMesh } from '../brain/brainAsset';
import { FLIGHT, MAX_EDGES, MODES, coreBloom, hopField, performEnvelope, planBolts, type BoltPlan } from '../brain/bolts';
import { ANCHORS, BRAIN, PALETTE, devicePixelsPerUnitDepth } from '../config/composition';
import { SCENE_SEED, type QualityTier } from '../config/quality';
import { STATE_PALETTE, themeStore } from '../config/theme';
import { TRANSITION, phaseProgress } from '../config/timing';
import { useGraph } from '../graph/graphStore';
import { useHandGeometry } from '../hand/assets';
import { handRig } from '../hand/pose';
import { focusBrain } from '../app/navigation';
import { applyInk, useThemeBinding } from './useThemeBinding';

/** Same on-screen dot scale as the particle hand (ParticleHand POINT_SIZE). */
const POINT_SIZE = 0.0042;
/**
 * The low-poly net (decision D52): this many particles leave the hand for each
 * mesh vertex and land on it together (≈ 900 vertices → 2 700 particles).
 */
const PER_VERTEX = 3;

/**
 * The brain's answer to a signal (decision D53), seconds and hops:
 * the input signal flies for FLIGHT, then runs along the edges at HOP_RATE
 * hops per second, fading with distance; the input's region stays lit for
 * HOLD after a RISE and fades over FADE.
 */
const SIGNAL = {
  FLIGHT: 0.75,
  HOP_RATE: 11,
  REACH: 9,
  RISE: 0.25,
  HOLD: 3.0,
  FADE: 1.2,
  /** Comet trail: points and their spacing in seconds. */
  TRAIL: 48,
  TRAIL_DT: 0.006,
} as const;

/** How long a signal lives after impact (seconds). */
const SIGNAL_LIFE = SIGNAL.RISE + SIGNAL.HOLD + SIGNAL.FADE;

/** Shared by the dots and the lines: the signal's run along the net and the lit region (D53). */
const SIGNAL_GLSL = /* glsl */ `
  uniform float uSigT;       // seconds since impact, < 0 = no signal
  uniform float uHopRate;
  uniform float uReach;
  uniform float uSigRegion;  // region held lit, -1 = none
  uniform float uHold;       // 0..1 envelope of the held region
  uniform float uPerfMode;   // D57: 0 = none (D53), 1 rational, 2 emotional, 3 crazy
  uniform float uSigGain;    // brightness of the discharge; 1 for D53
  uniform float uCoreR;      // crazy: radius of the lit front, brain-local
  uniform float uCoreVis;    // crazy: 0..1 visibility of the lit net
  // brightness of the travelling discharge at this many hops from the impact
  float discharge(float hop) {
    if (uSigT < 0.0) return 0.0;
    if (uPerfMode > 2.5) {
      // crazy: hop is the vertex's distance from the light on the SCREEN, in brain radii (the net
      // is a shell, so a distance from the centre would light all of it at once). Inside the
      // swelling (then collapsing) front the net is lit, and the front itself is the brightest line.
      float inside = 1.0 - smoothstep(uCoreR - 0.16, uCoreR + 0.03, hop);
      float rim = exp(-pow((hop - uCoreR) / 0.075, 2.0));
      return clamp(inside * 0.5 + rim * 0.95, 0.0, 1.0) * uCoreVis * uSigGain;
    }
    float front = uSigT * uHopRate;
    float band = exp(-pow((hop - front) / 1.1, 2.0));
    // a short afterglow behind the front, all of it fading with distance
    float wake = step(hop, front) * exp(-(front - hop) * 0.9) * 0.35;
    return max(band, wake) * exp(-hop / uReach) * uSigGain;
  }
  float held(float region) {
    return uSigRegion < 0.0 ? 0.0 : step(abs(region - uSigRegion), 0.5) * uHold;
  }
`;

/** The state palettes (D57), shared by the dots, the lines and the bolts. */
const PALETTE_GLSL = /* glsl */ `
  uniform vec3 uPal[6];      // 0-4 the emotional colours, 5 the rational one
  uniform float uSat;        // saturation and value of the crazy hue wheel
  uniform float uVal;
  vec3 perfHsv(float h) {
    vec3 k = clamp(abs(mod(h * 6.0 + vec3(0.0, 4.0, 2.0), 6.0) - 3.0) - 1.0, 0.0, 1.0);
    return uVal * mix(vec3(1.0), k, uSat);
  }
  vec3 perfRamp(float h) {
    float x = fract(h) * 5.0;
    int i = int(floor(x));
    return mix(uPal[i], uPal[(i + 1) % 5], smoothstep(0.0, 1.0, fract(x)));
  }
`;

/** The underglow's colour at a brain-local point p, `hop` hops from its origin. */
const PERF_COLOR_GLSL = /* glsl */ `
  uniform float uPerfT;
  uniform float uPerfSeed;
  uniform float uJit;        // vertex jitter, brain-local (unused: crazy no longer shakes the vertices)
  uniform vec3 uCoreCol;     // the crazy state's single light: white on black, ink on white
  vec3 perfColor(vec3 p, float hop) {
    if (uPerfMode < 1.5) return uPal[5];
    if (uPerfMode < 2.5) return perfRamp(dot(p, vec3(0.5, 0.32, 0.25)) * 0.8 + hop * 0.03 + uPerfSeed);
    return uCoreCol;
  }
  // the whole-brain shudder of the crazy state: a jitter of the vertices, brain-local
  vec3 perfJitter(vec3 p) {
    float jh = fract(dot(p, vec3(12.9898, 78.233, 37.719)));
    float tick = floor(uPerfT * 14.0);
    return (fract(sin(vec3(jh * 91.7 + tick * 1.3, jh * 47.1 + tick * 2.9, jh * 13.3 + tick * 4.1)) * 43758.5453) - 0.5) * uJit * 2.0;
  }
`;

/**
 * The crazy state's collapse (D62), shared by the dots, the net lines and the tree.
 * `uCollapse` 0 returns the point untouched (the resting frame is unchanged bit for
 * bit); 1 puts every point at the centre. Each point's own progress is staggered by a
 * hash of its REST position (quantised, so the dot, the line end and the tree end at
 * one vertex move together) and by its radius (the rim starts first), yet ends at 1
 * exactly when `uCollapse` does. On the way each point also turns about the vertical
 * axis, so the brain is wound into the point rather than shrunk. Because the whole
 * path is a function of the one `uCollapse`, running it backwards unfolds the brain
 * to exactly the points it left.
 */
const COLLAPSE_GLSL = /* glsl */ `
  uniform float uCollapse;   // D62: 0 = at rest, 1 = the singularity
  float collapseP(vec3 p) {
    vec3 q = floor(p * 512.0 + 0.5);
    float h = fract(sin(dot(q, vec3(12.9898, 78.233, 37.719))) * 43758.5453);
    float r = clamp(length(p), 0.0, 1.0);
    float s = 0.38 * (0.55 * h + 0.45 * (1.0 - r));
    float x = clamp((uCollapse - s) / (1.0 - 0.38), 0.0, 1.0);
    return x * x * (3.0 - 2.0 * x);
  }
  vec3 collapsePos(vec3 p) {
    if (uCollapse <= 0.0) return p;
    float c = collapseP(p);
    float a = sin(3.14159265 * c) * 1.3;
    float cs = cos(a);
    float sn = sin(a);
    return vec3(cs * p.x + sn * p.z, p.y, -sn * p.x + cs * p.z) * (1.0 - c);
  }
`;

const signalUniforms = () => ({
  uSigT: { value: -1 },
  uHopRate: { value: SIGNAL.HOP_RATE },
  uReach: { value: SIGNAL.REACH },
  uSigRegion: { value: -1 },
  uHold: { value: 0 },
});

/**
 * Bolts (D57). Each path edge is 2 sub-segments x 3 colour channels x a quad, all
 * of it written once per performance into these fixed buffers (no allocation
 * per frame), bent, grown and lit in the vertex shader. An unused channel or an
 * edge the head has not reached collapses to nothing.
 */
const SUB = 2;
const CHAN = 3;
const QUADS_PER_EDGE = SUB * CHAN;
const VERTS_PER_EDGE = QUADS_PER_EDGE * 4;
const FADE_OUT = 0.25;

function makeBoltGeometry(): BufferGeometry {
  const V = MAX_EDGES * VERTS_PER_EDGE;
  const g = new BufferGeometry();
  const cn = new Float32Array(V * 4);
  const index = new Uint16Array(MAX_EDGES * QUADS_PER_EDGE * 6);
  for (let e = 0; e < MAX_EDGES; e++) {
    for (let q = 0; q < QUADS_PER_EDGE; q++) {
      const sub = Math.floor(q / CHAN);
      const chan = q % CHAN;
      const base = e * VERTS_PER_EDGE + q * 4;
      for (let c = 0; c < 4; c++) {
        cn[(base + c) * 4] = sub;
        cn[(base + c) * 4 + 1] = chan;
        cn[(base + c) * 4 + 2] = c;
        cn[(base + c) * 4 + 3] = 1;
      }
      index.set([base, base + 1, base + 2, base + 2, base + 1, base + 3], (e * QUADS_PER_EDGE + q) * 6);
    }
  }
  // `position` is the edge's start; aP1 its end; aTm: head reaches the start / the end, colour, brightness
  g.setAttribute('position', new Float32BufferAttribute(new Float32Array(V * 3), 3));
  g.setAttribute('aP1', new Float32BufferAttribute(new Float32Array(V * 3), 3));
  g.setAttribute('aTm', new Float32BufferAttribute(new Float32Array(V * 4), 4));
  g.setAttribute('aCn', new Float32BufferAttribute(cn, 4));
  g.setIndex(new Uint16BufferAttribute(index, 1));
  g.setDrawRange(0, 0);
  return g;
}

const BOLT_VERT = /* glsl */ `
  attribute vec3 aP1;
  attribute vec4 aTm;   // head reaches the start, the end, colour parameter, brightness
  attribute vec4 aCn;   // sub-segment, colour channel, corner, width factor
  uniform float uPT;    // seconds since the bolts started
  uniform float uMode;
  uniform float uFade;  // 0..1: brightness of the whole bank (fade in and out)
  uniform float uWidth;
  uniform float uJitter;
  uniform float uFlickHz;
  uniform float uFlash;
  uniform float uTau;
  uniform float uSplit;
  uniform float uSeed;
  uniform vec2 uRes;
  ${PALETTE_GLSL}
  varying vec3 vCol;
  varying float vI;
  varying float vSide;
  float hash1(float x) { return fract(sin(x * 127.1 + 311.7) * 43758.5453); }
  void main() {
    float sub = aCn.x;
    float chan = aCn.y;
    float corner = aCn.z;
    float atEnd = step(1.5, corner);
    vSide = mod(corner, 2.0) * 2.0 - 1.0;

    // the edge, bent at its midpoint; the bend is redrawn uFlickHz times a second
    vec3 a = position;
    vec3 b = aP1;
    float len = length(b - a);
    vec3 d = (b - a) / max(len, 1e-5);
    float seed = dot(a + b, vec3(12.9898, 78.233, 37.719)) + uSeed;
    float tick = uFlickHz > 0.0 ? floor(uPT * uFlickHz) : 0.0;
    vec3 r = vec3(hash1(seed + tick * 1.7), hash1(seed + 5.3 + tick * 2.3), hash1(seed + 9.1 + tick * 3.1)) - 0.5;
    r -= d * dot(r, d);
    vec3 m = 0.5 * (a + b) + r * len * uJitter * 2.0;
    vec3 s0 = sub < 0.5 ? a : m;
    vec3 s1 = sub < 0.5 ? m : b;

    // the head grows the edge; behind it the light fades
    float f = clamp((uPT - aTm.x) / max(aTm.y - aTm.x, 1e-4), 0.0, 1.0);
    float fs = clamp(f * 2.0 - sub, 0.0, 1.0);
    float since = max(uPT - aTm.y, 0.0);
    float chanOn = (chan < 0.5 || uSplit > 0.0) ? 1.0 : 0.0;
    float live = step(0.0001, fs) * step(0.001, aTm.w) * step(0.001, uFade) * chanOn;

    mat4 mvp = projectionMatrix * modelViewMatrix;
    vec4 c0 = mvp * vec4(s0 * 1.012, 1.0);
    vec4 c1 = mvp * vec4(mix(s0, s1, fs) * 1.012, 1.0);
    vec2 n0 = c0.xy / c0.w;
    vec2 n1 = c1.xy / c1.w;
    vec2 dpx = (n1 - n0) * uRes * 0.5;
    float dl = length(dpx);
    vec2 dn = dl > 1e-3 ? dpx / dl : vec2(1.0, 0.0);
    vec2 perp = vec2(-dn.y, dn.x);
    float wpx = uWidth * aCn.w;
    vec4 c = atEnd > 0.5 ? c1 : c0;
    // a quad is as wide as the bolt and overhangs by half of it, so the joints close
    vec2 off = (perp * vSide + dn * (atEnd * 2.0 - 1.0)) * wpx / uRes;
    // colour-channel split (crazy): each channel is nudged its own way, in bursts
    float ang = hash1(aTm.z * 91.7 + uSeed) * 6.2831853;
    float glitch = 0.3 + 0.7 * step(0.5, hash1(floor(uPT * 5.0) + aTm.z * 17.0));
    vec2 sp = vec2(cos(ang), sin(ang)) * (chan - 1.0) * uSplit * glitch * 2.0 / uRes;
    c.xy += (off + sp) * c.w;
    gl_Position = live > 0.5 ? c : vec4(2.0, 2.0, 2.0, 1.0);

    // the side of the net facing the viewer carries the bolt; the far side is an echo (as the lines)
    vec4 mvA = modelViewMatrix * vec4(a, 1.0);
    float front = smoothstep(-0.3, 0.4, dot(normalize(normalMatrix * normalize(a)), normalize(-mvA.xyz)));
    float flick = 1.0 - (uFlickHz > 0.0 ? 0.18 * (0.5 + 0.5 * sin(uPT * 15.0 + aTm.z * 40.0)) : 0.0);
    float glow = exp(-since / uTau);
    float flash = 1.0 + uFlash * exp(-since * 9.0);
    vI = aTm.w * uFade * glow * flash * flick * mix(0.28, 1.0, front);

    float h = aTm.z;
    if (uMode < 1.5) vCol = uPal[5];
    else if (uMode < 2.5) vCol = perfRamp(h + aTm.x * 0.5);
    else vCol = perfHsv(fract(h + chan / 3.0 + uPT * 0.6 + aTm.x * 0.3));
  }
`;

const BOLT_FRAG = /* glsl */ `
  uniform float uAlpha;
  uniform float uDark;
  uniform float uMode;
  varying vec3 vCol;
  varying float vI;
  varying float vSide;
  void main() {
    float e = abs(vSide);
    float soft = 1.0 - smoothstep(0.55, 1.0, e);
    float core = 1.0 - smoothstep(0.0, 0.5, e);
    // a hot core: paler on black, deeper on white
    // (calm rational bolts keep their hue: only a touch of white; the state palettes are already
    // the darker saturated variants on white, so the light theme adds nothing to the core)
    float white = uMode < 1.5 ? 0.3 : 0.6;
    vec3 col = uDark > 0.5 ? mix(vCol, vec3(1.0), white * core * min(1.0, vI)) : vCol;
    float a = vI * soft * uAlpha;
    if (a < 0.003) discard;
    gl_FragColor = vec4(col, min(1.0, a));
  }
`;


/** Fastest release spin, radians per second (D42). */
const MAX_FLING = 3;

/** A click within this many CSS pixels of a node picks it. */
const NODE_PICK_PX = 14;

const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

interface Props {
  tier: QualityTier;
  reducedMotion: boolean;
}

export function BrainView({ tier, reducedMotion }: Props) {
  const brain = useBrainMesh();
  const graph = useGraph();
  /** How many levels the tree inside the brain grows through (the growth clock runs 0 .. levels). */
  const levels = useMemo(() => Math.max(...graph.nodes.map((n) => n.depth)) + 1, [graph]);
  const source = useHandGeometry('left');
  const rig = handRig('left');
  const camera = useThree((s) => s.camera);
  const size = useThree((s) => s.size);
  const dpr = useThree((s) => s.viewport.dpr);
  const domElement = useThree((s) => s.gl.domElement);
  const gl = useThree((s) => s.gl);
  const scene = useThree((s) => s.scene);

  const cloud = useMemo(
    () =>
      // one net for every tier: the count is the mesh's, not the tier's (D52)
      buildHumanCloud(source, rig, brain, PER_VERTEX, SCENE_SEED + 1),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [source, rig, brain, tier],
  );

  const geometry = useMemo(() => {
    const g = new BufferGeometry();
    g.setAttribute('position', new Float32BufferAttribute(cloud.hand, 3));
    g.setAttribute('aBrain', new Float32BufferAttribute(cloud.brain, 3));
    g.setAttribute('aRegion', new Float32BufferAttribute(cloud.region, 1));
    g.setAttribute('aReveal', new Float32BufferAttribute(cloud.reveal, 1));
    g.setAttribute('aHash', new Float32BufferAttribute(cloud.hash, 3));
    g.setAttribute('aSize', new Float32BufferAttribute(cloud.size, 1));
    g.setAttribute('aTone', new Float32BufferAttribute(cloud.tone, 1));
    g.setAttribute('aNormal', new Float32BufferAttribute(cloud.normal, 3));
    // hops from the last signal's vertex, rewritten on each impact (D53)
    g.setAttribute('aHop', new Float32BufferAttribute(new Float32Array(cloud.count).fill(1e4), 1));
    return g;
  }, [cloud]);

  const nodeLocal = useMemo(() => nodeBrainPositions(brain, graph.nodes), [brain, graph]);

  /** Graph edges inside the brain: arcs bowed outward, ordered root → leaves for growth. */
  const edges = useMemo(() => {
    const SEG = 14;
    const pos: number[] = [];
    const order: number[] = [];
    const kind: number[] = [];
    const depth = new Map(graph.nodes.map((n) => [n.id, n.depth]));
    const a = new Vector3();
    const b = new Vector3();
    const mid = new Vector3();
    const q = new Vector3();
    const prev = new Vector3();
    for (const e of graph.edges) {
      a.fromArray(nodeLocal.get(e.from)!);
      b.fromArray(nodeLocal.get(e.to)!);
      mid.addVectors(a, b).multiplyScalar(0.5);
      mid.multiplyScalar(e.kind === 'link' ? 1.35 : 1.12);
      const d0 = depth.get(e.from) ?? 0;
      for (let s = 0; s <= SEG; s++) {
        const t = s / SEG;
        // quadratic Bézier a → mid → b (the reference app's bezierAnimation)
        q.copy(a).multiplyScalar((1 - t) * (1 - t))
          .addScaledVector(mid, 2 * (1 - t) * t)
          .addScaledVector(b, t * t);
        if (s > 0) {
          pos.push(prev.x, prev.y, prev.z, q.x, q.y, q.z);
          // links draw last; tree edges draw by depth, along their length
          const o = e.kind === 'link' ? 3 + t : d0 + t;
          order.push(o, o);
          kind.push(e.kind === 'link' ? 1 : 0, e.kind === 'link' ? 1 : 0);
        }
        prev.copy(q);
      }
    }
    const g = new BufferGeometry();
    g.setAttribute('position', new Float32BufferAttribute(pos, 3));
    g.setAttribute('aOrder', new Float32BufferAttribute(order, 1));
    g.setAttribute('aKind', new Float32BufferAttribute(kind, 1));
    return g;
  }, [nodeLocal]);

  const nodes = useMemo(() => {
    const pos: number[] = [];
    const depth: number[] = [];
    const index: number[] = [];
    graph.nodes.forEach((n, i) => {
      pos.push(...nodeLocal.get(n.id)!);
      depth.push(n.depth);
      index.push(i);
    });
    const g = new BufferGeometry();
    g.setAttribute('position', new Float32BufferAttribute(pos, 3));
    g.setAttribute('aDepth', new Float32BufferAttribute(depth, 1));
    g.setAttribute('aIndex', new Float32BufferAttribute(index, 1));
    return g;
  }, [nodeLocal]);

  /** The net's edges (D52), brain-local, drawn inside the brain group. */
  const links = useMemo(() => {
    const E = brain.edges;
    const pos = new Float32Array(E.length * 3);
    const nrm = new Float32Array(E.length * 3);
    const reg = new Float32Array(E.length);
    for (let k = 0; k < E.length; k++) {
      const v = E[k];
      for (let c = 0; c < 3; c++) {
        pos[k * 3 + c] = brain.position[v * 3 + c];
        nrm[k * 3 + c] = brain.normal[v * 3 + c];
      }
      reg[k] = brain.region[v];
    }
    const g = new BufferGeometry();
    g.setAttribute('position', new Float32BufferAttribute(pos, 3));
    g.setAttribute('aNormal', new Float32BufferAttribute(nrm, 3));
    g.setAttribute('aRegion', new Float32BufferAttribute(reg, 1));
    g.setAttribute('aHop', new Float32BufferAttribute(new Float32Array(E.length).fill(1e4), 1));
    return g;
  }, [brain]);

  /** The input signal's comet (D53): a head and a fading trail, world space. */
  const comet = useMemo(() => {
    const g = new BufferGeometry();
    g.setAttribute('position', new Float32BufferAttribute(new Float32Array(SIGNAL.TRAIL * 3), 3));
    const fall = new Float32Array(SIGNAL.TRAIL);
    for (let i = 0; i < SIGNAL.TRAIL; i++) fall[i] = i / (SIGNAL.TRAIL - 1);
    g.setAttribute('aFall', new Float32BufferAttribute(fall, 1));
    return g;
  }, []);

  /**
   * What the dots, the lines and the bolts share while a performance runs
   * (D57): one set of uniform objects, so one write reaches all of them. At
   * rest every value is the one the shaders had before (mode 0, gain 1, bulge
   * 0.02, no jitter), so the resting frame is unchanged bit for bit.
   */
  const perfU = useMemo(
    () => ({
      uPerfMode: { value: 0 },
      uSigGain: { value: 1 },
      uPerfT: { value: 0 },
      uPerfSeed: { value: 0 },
      uBulge: { value: 0.02 },
      uJit: { value: 0 },
      uCoreR: { value: 0 },
      uCoreVis: { value: 0 },
      uCollapse: { value: 0 },
      uCoreCol: { value: new Color() },
      uPal: { value: Array.from({ length: 6 }, () => new Color()) },
      uSat: { value: 0.9 },
      uVal: { value: 0.8 },
    }),
    [],
  );

  const linkMaterial = useMemo(
    () =>
      new ShaderMaterial({
        transparent: true,
        depthWrite: false,
        blending: NormalBlending,
        uniforms: {
          uShow: { value: 0 },
          uHoverRegion: { value: -1 },
          uFocus: { value: 0 },
          ...signalUniforms(),
          ...perfU,
          uColor: { value: new Color(PALETTE.inkSoft) },
          uAccent: { value: new Color(PALETTE.inkSoft) },
          uAlpha: { value: 1 },
        },
        vertexShader: /* glsl */ `
          attribute float aRegion;
          attribute float aHop;
          attribute vec3 aNormal;
          uniform float uHoverRegion;
          uniform float uFocus;
          varying float vHop;
          varying float vHover;
          varying float vHeld;
          varying float vFront;
          varying vec3 vLocal;
          ${SIGNAL_GLSL}
          ${PALETTE_GLSL}
          ${PERF_COLOR_GLSL}
          ${COLLAPSE_GLSL}
          void main() {
            vHover = step(abs(aRegion - uHoverRegion), 0.5) * uFocus;
            vHeld = held(aRegion);
            vLocal = position;
            vec3 lp = collapsePos(position);
            if (uJit > 0.0) lp += perfJitter(position);
            vec4 mv = modelViewMatrix * vec4(lp, 1.0);
            vHop = aHop;
            if (uPerfMode > 2.5) {
              // crazy: distance from the light on the screen, in brain radii (it varies along the edge)
              vec4 mvc = modelViewMatrix * vec4(0.0, 0.0, 0.0, 1.0);
              vHop = length(mv.xy - mvc.xy) / length(modelViewMatrix[0].xyz);
            }
            // the side of the net facing the viewer carries the lines; the far
            // side stays a faint echo, so the polyhedron reads in depth (D52)
            vec3 n = normalize(normalMatrix * aNormal);
            vFront = smoothstep(-0.3, 0.4, dot(n, normalize(-mv.xyz)));
            gl_Position = projectionMatrix * mv;
          }
        `,
        fragmentShader: /* glsl */ `
          uniform float uShow;
          uniform vec3 uColor;
          uniform vec3 uAccent;
          uniform float uAlpha;
          varying float vHop;
          varying float vHover;
          varying float vHeld;
          varying float vFront;
          varying vec3 vLocal;
          ${SIGNAL_GLSL}
          ${PALETTE_GLSL}
          ${PERF_COLOR_GLSL}
          void main() {
            // the hop varies along the edge, so the discharge runs down it
            float w = discharge(vHop);
            float lit = max(max(w, vHeld * 0.8), vHover * 0.6);
            float a = uShow * mix(0.06, 0.34, vFront) * (1.0 + 2.2 * lit) * uAlpha;
            if (a <= 0.002) discard;
            vec3 col = mix(uColor, uAccent, clamp(vHeld * 0.9 + w * 0.45, 0.0, 1.0));
            // a performance (D57) tints the lines its wave has reached with the state's colour
            if (uPerfMode > 0.5) col = mix(col, perfColor(vLocal, vHop), clamp(w * 2.4, 0.0, 1.0));
            gl_FragColor = vec4(col, min(1.0, a));
          }
        `,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const particleMaterial = useMemo(
    () =>
      new ShaderMaterial({
        transparent: true,
        depthWrite: false,
        blending: NormalBlending,
        uniforms: {
          uDissolve: { value: 0 },
          uMigrate: { value: 0 },
          uSettle: { value: 0 },
          uBrain: { value: new Matrix4() },
          uTime: { value: 0 },
          uFocus: { value: 0 },
          uHoverRegion: { value: -1 },
          ...signalUniforms(),
          ...perfU,
          uSwirl: { value: 1 },
          uSizeScale: { value: 1 },
          uColor: { value: new Color(PALETTE.ink) },
          uAccent: { value: new Color(PALETTE.inkSoft) },
          uAlpha: { value: 1 },
          uGlow: { value: 0 },
        },
        vertexShader: /* glsl */ `
          attribute vec3 aBrain;
          attribute vec3 aNormal;
          attribute float aHop;
          attribute float aRegion;
          attribute float aReveal;
          attribute vec3 aHash;
          attribute float aSize;
          attribute float aTone;

          uniform float uDissolve;
          uniform float uMigrate;
          uniform float uSettle;
          uniform mat4 uBrain;
          uniform float uTime;
          uniform float uFocus;
          uniform float uHoverRegion;
          uniform float uSwirl;
          uniform float uSizeScale;

          uniform float uBulge;

          varying float vAlpha;
          varying float vLit;
          varying float vHeld;
          varying float vTint;
          varying vec3 vTintCol;
          ${SIGNAL_GLSL}
          ${PALETTE_GLSL}
          ${PERF_COLOR_GLSL}
          ${COLLAPSE_GLSL}

          void main() {
            // Appear where the solid has withdrawn: the plaster is visible where
            // reveal < 1.18 * (1 - dissolve) (HumanHand.tsx). The window is
            // compressed by 0.88 so it completes by dissolve = 1: uncompressed,
            // wrist particles (which become the back of the brain) stopped at 7 %
            // and the back of the brain stayed faint (D43).
            float gone = (1.0 - aReveal / 1.18) * 0.88;
            float appear = smoothstep(gone - 0.04, gone + 0.1, uDissolve);

            // Migrate on a delayed clock: fingertips leave first, then the hand
            // unravels toward the wrist (the reference's aDelayDuration).
            float lead = (1.0 - aReveal) * 0.34 + aHash.x * 0.16;
            float m = clamp((uMigrate - lead) / 0.5, 0.0, 1.0);
            m = m * m * m * (m * (m * 6.0 - 15.0) + 10.0);

            vec3 target = (uBrain * vec4(collapsePos(aBrain), 1.0)).xyz;
            // the shudder of the crazy state (D57): the vertices jitter, brain-local
            if (uJit > 0.0) target += (uBrain * vec4(perfJitter(aBrain), 0.0)).xyz;
            vec3 pos = mix(position, target, m);

            // Mid-flight the particles spiral about the travel axis (the
            // reference's loading-ring swirl); the envelope is zero at both
            // ends, so both endpoints are exact.
            vec3 axis = normalize(target - position + vec3(1e-4));
            vec3 side = normalize(cross(axis, vec3(0.0, 0.0, 1.0)) + vec3(1e-4));
            vec3 up = cross(axis, side);
            float ang = 6.2831853 * (aHash.y + m * (0.6 + aHash.z));
            float env = sin(3.14159265 * m) * uSwirl;
            pos += (side * cos(ang) + up * sin(ang)) * env * (0.12 + 0.22 * aHash.z);

            // Breathing at the destination, silent while travelling.
            // The phase is the vertex's, not the particle's: the PER_VERTEX dots
            // of one vertex breathe together and stay one dot (D52).
            float ph = uTime * 0.8 + fract(dot(aBrain, vec3(12.9898, 78.233, 37.719))) * 6.2831853;
            pos += vec3(sin(ph), cos(ph * 0.9), sin(ph * 0.7)) * 0.006 * uSettle;

            // The signal (D53): a discharge running out along the net from
            // the impact vertex, and the input's region held lit.
            vec3 nrm = normalize(mat3(uBrain) * aNormal);
            float dh = aHop;
            if (uPerfMode > 2.5) {
              // crazy: distance from the light, seen from the camera, in brain radii
              vec4 mvp = modelViewMatrix * vec4(pos, 1.0);
              vec4 mvc = modelViewMatrix * (uBrain * vec4(0.0, 0.0, 0.0, 1.0));
              dh = length(mvp.xy - mvc.xy) / length(uBrain[0].xyz);
            }
            float w = discharge(dh) * uSettle;
            float hold = held(aRegion) * uSettle;
            pos += nrm * w * uBulge;
            // Hovered region, while drilled in.
            float hover = step(abs(aRegion - uHoverRegion), 0.5) * uFocus * 0.65;
            vLit = max(max(w, hold), hover);
            vHeld = clamp(hold * 0.9 + w * 0.45, 0.0, 1.0);
            // a performance (D57) tints the dots its wave has reached with the state's colour
            vTint = 0.0;
            vTintCol = vec3(0.0);
            if (uPerfMode > 0.5) {
              vTint = clamp(w * 2.4, 0.0, 1.0);
              vTintCol = perfColor(aBrain, aHop);
            }

            // Arrived, the net (D52): every vertex one clean dot, the side
            // facing the viewer full, the far side a faint echo.
            vec3 toEye = normalize(cameraPosition - target);
            float front = smoothstep(-0.3, 0.4, dot(nrm, toEye));
            vec4 mv = modelViewMatrix * vec4(pos, 1.0);
            gl_Position = projectionMatrix * mv;
            float node = mix(1.0, 1.7 * mix(0.7, 1.0, front), m);
            float size = mix(aSize, node, m);
            // D62: the dots shrink a little as they are compressed, so the point stays a point
            if (uCollapse > 0.0) size *= 1.0 - 0.35 * collapseP(aBrain);
            gl_PointSize = size * (1.0 + 0.9 * vLit) * uSizeScale / max(0.25, -mv.z);
            // PER_VERTEX dots overlap on one vertex: the far side is kept low
            // enough that the stack still reads faint
            float arrived = mix(0.1, 0.62, front) * (1.0 + 0.8 * vLit);
            vAlpha = appear * mix(aTone, arrived, m);
          }
        `,
        fragmentShader: /* glsl */ `
          uniform vec3 uColor;
          uniform vec3 uAccent;
          uniform float uAlpha;
          uniform float uGlow;
          varying float vAlpha;
          varying float vLit;
          varying float vHeld;
          varying float vTint;
          varying vec3 vTintCol;
          void main() {
            vec2 c = gl_PointCoord - 0.5;
            float r = dot(c, c);
            if (r > 0.25) discard;
            float a = vAlpha * (1.0 - smoothstep(mix(0.16, 0.0, uGlow), 0.25, r));
            if (a <= 0.004) discard;
            vec3 col = mix(uColor, uAccent, vHeld);
            if (vTint > 0.0) col = mix(col, vTintCol, vTint);
            gl_FragColor = vec4(col, min(1.0, a) * uAlpha);
          }
        `,
      }),
    [],
  );

  const edgeMaterial = useMemo(
    () =>
      new ShaderMaterial({
        transparent: true,
        depthWrite: false,
        depthTest: false,
        blending: NormalBlending,
        uniforms: {
          uGrow: { value: 0 },
          uCollapse: perfU.uCollapse,
          uColor: { value: new Color(PALETTE.inkSoft) },
          uAlpha: { value: 1 },
        },
        vertexShader: /* glsl */ `
          attribute float aOrder;
          attribute float aKind;
          varying float vOrder;
          varying float vKind;
          ${COLLAPSE_GLSL}
          void main() {
            vOrder = aOrder;
            vKind = aKind;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(collapsePos(position), 1.0);
          }
        `,
        fragmentShader: /* glsl */ `
          uniform float uGrow;
          uniform vec3 uColor;
          uniform float uAlpha;
          varying float vOrder;
          varying float vKind;
          void main() {
            // uGrow runs 0 → 4: depth 0 edges, then 1, 2, then the cross-links
            float drawn = step(vOrder, uGrow);
            float head = 1.0 - smoothstep(0.0, 0.25, uGrow - vOrder);
            float a = drawn * mix(0.7, 0.32, vKind) * (0.85 + 0.6 * head);
            if (a <= 0.003) discard;
            gl_FragColor = vec4(uColor, min(1.0, a) * uAlpha);
          }
        `,
      }),
    [],
  );

  const nodeMaterial = useMemo(
    () =>
      new ShaderMaterial({
        transparent: true,
        depthWrite: false,
        depthTest: false,
        blending: NormalBlending,
        uniforms: {
          uGrow: { value: 0 },
          uHover: { value: -1 },
          uSelected: { value: -1 },
          uSizeScale: { value: 1 },
          uCollapse: perfU.uCollapse,
          uColor: { value: new Color(PALETTE.ink) },
          uAlpha: { value: 1 },
        },
        vertexShader: /* glsl */ `
          attribute float aDepth;
          attribute float aIndex;
          ${COLLAPSE_GLSL}
          uniform float uGrow;
          uniform float uHover;
          uniform float uSelected;
          uniform float uSizeScale;
          varying float vAlpha;
          varying float vRing;
          void main() {
            float shown = smoothstep(aDepth - 0.05, aDepth + 0.35, uGrow);
            float hot = max(step(abs(aIndex - uHover), 0.5), step(abs(aIndex - uSelected), 0.5));
            vRing = step(abs(aIndex - uSelected), 0.5);
            vAlpha = shown;
            vec4 mv = modelViewMatrix * vec4(collapsePos(position), 1.0);
            gl_Position = projectionMatrix * mv;
            gl_PointSize = (aDepth < 0.5 ? 5.5 : 4.2 - 0.5 * aDepth) * (1.0 + 0.6 * hot) * shown
                         * uSizeScale / max(0.25, -mv.z);
          }
        `,
        fragmentShader: /* glsl */ `
          uniform vec3 uColor;
          uniform float uAlpha;
          varying float vAlpha;
          varying float vRing;
          void main() {
            vec2 c = gl_PointCoord - 0.5;
            float r = length(c);
            if (r > 0.5) discard;
            // a filled dot with a pale core; the selected node becomes a ring
            float fill = 1.0 - smoothstep(0.42, 0.5, r);
            float core = mix(0.0, 1.0 - smoothstep(0.16, 0.24, r), vRing);
            float a = vAlpha * fill * (1.0 - 0.85 * core);
            if (a <= 0.004) discard;
            gl_FragColor = vec4(uColor, a * uAlpha);
          }
        `,
      }),
    [],
  );

  const cometMaterial = useMemo(
    () =>
      new ShaderMaterial({
        transparent: true,
        depthWrite: false,
        depthTest: false,
        blending: NormalBlending,
        uniforms: {
          uShow: { value: 0 },
          uSizeScale: { value: 1 },
          uColor: { value: new Color(PALETTE.ink) },
          uAccent: { value: new Color(PALETTE.inkSoft) },
          uAlpha: { value: 1 },
          uGlow: { value: 0 },
        },
        vertexShader: /* glsl */ `
          attribute float aFall; // 0 at the head, 1 at the tail's end
          uniform float uSizeScale;
          varying float vFall;
          void main() {
            vFall = aFall;
            vec4 mv = modelViewMatrix * vec4(position, 1.0);
            gl_Position = projectionMatrix * mv;
            gl_PointSize = mix(3.4, 0.8, aFall) * uSizeScale / max(0.25, -mv.z);
          }
        `,
        fragmentShader: /* glsl */ `
          uniform float uShow;
          uniform vec3 uColor;
          uniform vec3 uAccent;
          uniform float uAlpha;
          uniform float uGlow;
          varying float vFall;
          void main() {
            vec2 c = gl_PointCoord - 0.5;
            float r = dot(c, c);
            if (r > 0.25) discard;
            float a = uShow * pow(1.0 - vFall, 1.6) * (1.0 - smoothstep(mix(0.12, 0.0, uGlow), 0.25, r));
            if (a <= 0.004) discard;
            // the head in ink, the trail turning to the accent
            gl_FragColor = vec4(mix(uColor, uAccent, smoothstep(0.0, 0.5, vFall)), min(1.0, a) * uAlpha);
          }
        `,
      }),
    [],
  );

  /**
   * The crazy state's light source (D57, revised): one camera-facing quad at the brain's centre,
   * sized in brain-local units (so it tracks the brain's scale and the lit front), a hot point
   * and a soft ball around it. Additive white on black; on white a soft ink "negative light".
   */
  const coreMaterial = useMemo(
    () =>
      new ShaderMaterial({
        transparent: true,
        depthWrite: false,
        depthTest: false,
        blending: AdditiveBlending,
        uniforms: {
          uRad: { value: 0.2 },
          uCoreSize: { value: 0.05 },
          uCore: { value: 0 },
          uHalo: { value: 0 },
          uHaloMax: { value: 0.5 },
          uColor: { value: new Color(1, 1, 1) },
          uAlpha: { value: 1 },
        },
        vertexShader: /* glsl */ `
          uniform float uRad;
          varying vec2 vUv;
          void main() {
            vUv = position.xy;
            vec4 mv = modelViewMatrix * vec4(0.0, 0.0, 0.0, 1.0);
            // the group's scale carries the brain's size; the quad faces the camera
            mv.xy += position.xy * uRad * length(modelViewMatrix[0].xyz);
            gl_Position = projectionMatrix * mv;
          }
        `,
        fragmentShader: /* glsl */ `
          uniform float uRad;
          uniform float uCoreSize;
          uniform float uCore;
          uniform float uHalo;
          uniform float uHaloMax;
          uniform vec3 uColor;
          uniform float uAlpha;
          varying vec2 vUv;
          void main() {
            float d = length(vUv);
            if (d > 1.0) discard;
            float r = d * uRad;
            float hot = exp(-r * r / (uCoreSize * uCoreSize));
            float ball = 1.0 - smoothstep(0.0, 1.0, d);
            ball *= ball;
            float a = (hot * uCore + ball * uHalo * uHaloMax) * uAlpha;
            if (a < 0.003) discard;
            gl_FragColor = vec4(uColor, min(1.0, a));
          }
        `,
      }),
    [],
  );
  const coreGeometry = useMemo(() => new PlaneGeometry(2, 2), []);
  const coreRef = useRef<Mesh | null>(null);

  /** The bolts (D57): two banks, so a new performance can start while the old one fades out. */
  const banks = useMemo(
    () =>
      [0, 1].map(() => ({
        geometry: makeBoltGeometry(),
        material: new ShaderMaterial({
          transparent: true,
          depthWrite: false,
          side: DoubleSide,
          blending: NormalBlending,
          uniforms: {
            ...perfU,
            uPT: { value: 0 },
            uMode: { value: 1 },
            uFade: { value: 0 },
            uWidth: { value: 2.4 },
            uJitter: { value: 0.1 },
            uFlickHz: { value: 0 },
            uFlash: { value: 0.5 },
            uTau: { value: 0.5 },
            uSplit: { value: 0 },
            uSeed: { value: 0 },
            uRes: { value: new Vector2(1, 1) },
            uAlpha: { value: 1 },
            uDark: { value: 0 },
          },
          vertexShader: BOLT_VERT,
          fragmentShader: BOLT_FRAG,
        }),
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // The bolt meshes are hidden until the first performance, so their shader would be compiled
  // (and linked) in the middle of that first frame. renderer.compile walks the whole scene,
  // hidden meshes included, so the first lightning finds its program ready.
  useEffect(() => {
    try {
      gl.compile(scene, camera);
    } catch {
      // a pre-warm only: the first performance compiles on demand as before
    }
  }, [gl, scene, camera, banks]);

  useThemeBinding(
    (p) => {
      // the state palettes (D57)
      const sp = STATE_PALETTE[p.glow ? 'dark' : 'light'];
      // These shaders write their colour straight to the canvas (no output colour-space step), so a
      // hex set the usual way (sRGB -> linear) came out darker than its name: the light theme's
      // slate-teal #2a6a78 drew as (6,37,48), nearly the ink. The palette is set as display values.
      sp.emotional.forEach((c, i) => perfU.uPal.value[i].set(c).convertLinearToSRGB());
      perfU.uPal.value[5].set(sp.rational).convertLinearToSRGB();
      perfU.uSat.value = sp.crazy.s;
      perfU.uVal.value = sp.crazy.v;
      // the crazy state's one light: the ink colour of the theme, additive on black, ordinary on white
      perfU.uCoreCol.value.set(p.ink);
      coreMaterial.uniforms.uColor.value.set(p.glow ? '#ffffff' : p.ink);
      coreMaterial.uniforms.uHaloMax.value = p.glow ? 0.7 : 0.3;
      coreMaterial.blending = p.glow ? AdditiveBlending : NormalBlending;
      coreMaterial.needsUpdate = true;
      for (const b of banks) {
        b.material.uniforms.uDark.value = p.glow ? 1 : 0;
        applyInk(b.material, p, 1.4);
      }
      particleMaterial.uniforms.uColor.value.set(p.ink);
      particleMaterial.uniforms.uAccent.value.set(p.accent);
      applyInk(particleMaterial, p, 1.25);
      edgeMaterial.uniforms.uColor.value.set(p.inkSoft);
      applyInk(edgeMaterial, p, 1.2);
      nodeMaterial.uniforms.uColor.value.set(p.ink);
      applyInk(nodeMaterial, p);
      // the net's lines in full ink, so the polyhedron reads (D52)
      linkMaterial.uniforms.uColor.value.set(p.ink);
      linkMaterial.uniforms.uAccent.value.set(p.accent);
      applyInk(linkMaterial, p, 1.5);
      cometMaterial.uniforms.uColor.value.set(p.ink);
      cometMaterial.uniforms.uAccent.value.set(p.accent);
      applyInk(cometMaterial, p, 1.4);
    },
    [particleMaterial, edgeMaterial, nodeMaterial, linkMaterial, cometMaterial, banks[0].material, banks[1].material],
  );

  const groupRef = useRef<Group>(null);
  const pointsRef = useRef<import('three').Points>(null);
  const linksRef = useRef<import('three').LineSegments>(null);
  const cometRef = useRef<import('three').Points>(null);

  // ---- brain transform ---------------------------------------------------------
  const tmp = useMemo(
    () => ({
      q: new Quaternion(),
      qSpin: new Quaternion(),
      e: new Euler(),
      v: new Vector3(),
      m: new Matrix4(),
      ray: new Ray(),
      sphere: new Sphere(),
      ndc: new Vector2(),
      proj: new Vector3(),
      a: new Vector3(),
      b: new Vector3(),
      c: new Vector3(),
      n: new Vector3(),
      eye: new Vector3(),
    }),
    [],
  );

  /** Where the brain is, how big, and which way it faces, for this frame. */
  const brainTransform = (settle: number) => {
    const f = easeInOut(humanStore.focusP);
    const off = BRAIN.offset.map((o, i) => o + (BRAIN.focusOffset[i] - o) * f);
    tmp.v.set(ANCHORS.HUMAN[0] + off[0], ANCHORS.HUMAN[1] + off[1], ANCHORS.HUMAN[2] + off[2]);
    const scale = BRAIN.scale + (BRAIN.focusScale - BRAIN.scale) * f;
    tmp.e.set(
      BRAIN.tilt[0] + humanStore.dragPitch * settle,
      BRAIN.tilt[1] + (humanStore.spin + humanStore.dragYaw) * settle,
      BRAIN.tilt[2],
    );
    tmp.q.setFromEuler(tmp.e);
    return scale;
  };

  // ---- pointer: click to drill in, drag to turn, hover to name -----------------
  const pointerNdc = useRef<Vector2 | null>(null);
  const drag = useRef<{ x: number; y: number; t: number; moved: boolean } | null>(null);

  useEffect(() => {
    const toNdc = (ev: PointerEvent) => {
      const r = domElement.getBoundingClientRect();
      return new Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    };
    const onMove = (ev: PointerEvent) => {
      pointerNdc.current = toNdc(ev);
      const d = drag.current;
      // drag turns the brain, resting or drilled in (D42)
      if (d && stage.state === 'human') {
        const dx = ev.clientX - d.x;
        const dy = ev.clientY - d.y;
        if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true;
        if (d.moved) {
          humanStore.dragYaw += dx * 0.008;
          humanStore.dragPitch = Math.max(-1.1, Math.min(1.1, humanStore.dragPitch + dy * 0.008));
          // velocity for the release, radians per second (smoothed)
          const dt = Math.max(1, ev.timeStamp - d.t) / 1000;
          const clamp = (v: number) => Math.max(-MAX_FLING, Math.min(MAX_FLING, v));
          humanStore.spinVel = { yaw: clamp((dx * 0.008) / dt), pitch: clamp((dy * 0.008) / dt) };
          d.x = ev.clientX;
          d.y = ev.clientY;
          d.t = ev.timeStamp;
        }
      }
    };
    const onLeave = () => {
      pointerNdc.current = null;
    };
    const onDown = (ev: PointerEvent) => {
      if (stage.state !== 'human') return;
      drag.current = { x: ev.clientX, y: ev.clientY, t: ev.timeStamp, moved: false };
      humanStore.dragging = true;
      humanStore.spinVel = { yaw: 0, pitch: 0 };
    };
    const onUp = (ev: PointerEvent) => {
      const d = drag.current;
      drag.current = null;
      humanStore.dragging = false;
      // a pause before release means no fling
      if (d && ev.timeStamp - d.t > 80) humanStore.spinVel = { yaw: 0, pitch: 0 };
      if (stage.state !== 'human' || !d || d.moved) return;
      const ui = humanStore.get();
      // a node under the pointer wins
      if (ui.focused && ui.hovered) {
        humanStore.set({ selected: ui.hovered });
        return;
      }
      const hit = hitBrain(toNdc(ev));
      if (!hit) return;
      humanStore.pulse(hit);
      if (!ui.focused) focusBrain(true, reducedMotion);
    };
    domElement.addEventListener('pointermove', onMove);
    domElement.addEventListener('pointerleave', onLeave);
    domElement.addEventListener('pointerdown', onDown);
    window.addEventListener('pointerup', onUp);
    return () => {
      domElement.removeEventListener('pointermove', onMove);
      domElement.removeEventListener('pointerleave', onLeave);
      domElement.removeEventListener('pointerdown', onDown);
      window.removeEventListener('pointerup', onUp);
    };
    // hitBrain reads refs and the store only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [domElement, reducedMotion]);

  /** Ray against the brain's bounding sphere; returns the brain-local hit point. */
  const hitBrain = (ndc: Vector2): [number, number, number] | null => {
    const g = groupRef.current;
    if (!g) return null;
    tmp.ray.origin.setFromMatrixPosition(camera.matrixWorld);
    tmp.ray.direction.set(ndc.x, ndc.y, 0.5).unproject(camera).sub(tmp.ray.origin).normalize();
    tmp.sphere.set(g.position, g.scale.x * 0.92);
    const p = tmp.ray.intersectSphere(tmp.sphere, new Vector3());
    if (!p) return null;
    g.worldToLocal(p);
    return [p.x, p.y, p.z];
  };

  // ---- the signal (D53) ------------------------------------------------------------
  /** World position of mesh vertex `v` this frame. */
  const vertexWorld = (v: number, out: Vector3) =>
    out.fromArray(brain.position, v * 3).applyMatrix4(groupRef.current!.matrixWorld);

  /** The vertex of `region` to aim at: facing the viewer, nearest the region's middle. */
  const aimVertex = (region: number): number => {
    const g = groupRef.current!;
    tmp.eye.setFromMatrixPosition(camera.matrixWorld);
    const mid = tmp.c.set(0, 0, 0);
    let n = 0;
    for (let i = 0; i < brain.count; i++) {
      if (brain.region[i] !== region) continue;
      mid.x += brain.position[i * 3];
      mid.y += brain.position[i * 3 + 1];
      mid.z += brain.position[i * 3 + 2];
      n++;
    }
    if (n === 0) return 0;
    mid.divideScalar(n);
    let best = -1;
    let bestScore = -Infinity;
    for (let i = 0; i < brain.count; i++) {
      if (brain.region[i] !== region) continue;
      vertexWorld(i, tmp.a);
      tmp.n.fromArray(brain.normal, i * 3).transformDirection(g.matrixWorld);
      const facing = tmp.n.dot(tmp.b.subVectors(tmp.eye, tmp.a).normalize());
      const d = Math.hypot(
        brain.position[i * 3] - mid.x,
        brain.position[i * 3 + 1] - mid.y,
        brain.position[i * 3 + 2] - mid.z,
      );
      const score = facing * 1.5 - d;
      if (score > bestScore) {
        bestScore = score;
        best = i;
      }
    }
    return best;
  };

  /** Write per-vertex hop distances into the dots and the lines. */
  const writeHopArray = (hop: Float32Array) => {
    const pa = geometry.getAttribute('aHop');
    for (let k = 0; k < cloud.count; k++) pa.array[k] = hop[cloud.vertex[k]];
    pa.needsUpdate = true;
    const la = links.getAttribute('aHop');
    for (let k = 0; k < brain.edges.length; k++) la.array[k] = hop[brain.edges[k]];
    la.needsUpdate = true;
  };

  /** Write the hop distances from `start` into the dots and the lines. */
  const writeHops = (start: number) => writeHopArray(hopDistances(brain, start));

  /** The comet from `s.fromCss` across the divide into vertex `s.vertex`, `flight` seconds long. */
  const flyComet = (s: Signal, flight: number) => {
    const cu = cometMaterial.uniforms;
    const r = domElement.getBoundingClientRect();
    vertexWorld(s.vertex, tmp.b);
    const depth = tmp.proj.copy(tmp.b).project(camera).z;
    tmp.a
      .set(((s.fromCss![0] - r.left) / r.width) * 2 - 1, -((s.fromCss![1] - r.top) / r.height) * 2 + 1, depth)
      .unproject(camera);
    // bow the path upward, a third of its length
    tmp.c.addVectors(tmp.a, tmp.b).multiplyScalar(0.5);
    tmp.c.y += tmp.a.distanceTo(tmp.b) * 0.33;
    const arr = comet.getAttribute('position');
    for (let i = 0; i < SIGNAL.TRAIL; i++) {
      const t = Math.min(1, Math.max(0, (s.t - i * SIGNAL.TRAIL_DT) / flight));
      const e = t * t * (3 - 2 * t);
      const k0 = (1 - e) * (1 - e);
      const k1 = 2 * (1 - e) * e;
      const k2 = e * e;
      arr.setXYZ(
        i,
        tmp.a.x * k0 + tmp.c.x * k1 + tmp.b.x * k2,
        tmp.a.y * k0 + tmp.c.y * k1 + tmp.b.y * k2,
        tmp.a.z * k0 + tmp.c.z * k1 + tmp.b.z * k2,
      );
    }
    arr.needsUpdate = true;
    // fade in over the first tenth, out as the tail lands
    cu.uShow.value = Math.min(1, s.t / 0.08) * Math.min(1, Math.max(0, (flight + SIGNAL.TRAIL * SIGNAL.TRAIL_DT - s.t) / 0.25));
  };

  const runD53Signal = (delta: number, settle: number) => {
    const s = humanStore.signal;
    const g = groupRef.current;
    const pu = particleMaterial.uniforms;
    const lu = linkMaterial.uniforms;
    const cu = cometMaterial.uniforms;
    cu.uShow.value = 0;
    humanStore.label = null;
    if (!s || !g || settle <= 0) {
      pu.uSigT.value = lu.uSigT.value = -1;
      pu.uHold.value = lu.uHold.value = 0;
      return;
    }
    if (s.vertex < 0) s.vertex = s.kind === 'input' ? aimVertex(s.region) : nearestVertex(brain, s.origin);
    const flight = s.kind === 'input' ? SIGNAL.FLIGHT : 0;
    s.t += delta;
    const since = s.t - flight;
    if (since >= 0 && !s.hopped) {
      writeHops(s.vertex);
      s.hopped = true;
    }
    if (since > SIGNAL_LIFE) {
      humanStore.signal = null;
      pu.uSigT.value = lu.uSigT.value = -1;
      pu.uHold.value = lu.uHold.value = 0;
      return;
    }
    pu.uSigT.value = lu.uSigT.value = since;
    pu.uSigRegion.value = lu.uSigRegion.value = s.region;
    const hold =
      s.region < 0 || since < 0
        ? 0
        : Math.min(1, since / SIGNAL.RISE) *
          (since < SIGNAL.RISE + SIGNAL.HOLD ? 1 : 1 - (since - SIGNAL.RISE - SIGNAL.HOLD) / SIGNAL.FADE);
    pu.uHold.value = lu.uHold.value = Math.max(0, hold);

    // the comet: from the input box across the divide into the vertex
    if (s.kind === 'input' && s.fromCss && s.t < flight + SIGNAL.TRAIL * SIGNAL.TRAIL_DT) flyComet(s, flight);

    // name the lit region next to where it was struck
    if (hold > 0.02) {
      vertexWorld(s.vertex, tmp.proj).project(camera);
      humanStore.label = {
        x: ((tmp.proj.x + 1) / 2) * size.width,
        y: ((1 - tmp.proj.y) / 2) * size.height,
        alpha: hold,
        region: s.region,
      };
    }
  };

  // ---- the performance (D57) -----------------------------------------------------
  const boltRefs = useRef<(Mesh | null)[]>([null, null]);

  /** Plain fields for the frame loop; nothing here is React state and nothing is allocated per frame. */
  const perf = useMemo(
    () => ({
      /** The performance signal the current bank belongs to, and its bank (-1 = none yet). */
      sig: null as Signal | null,
      cur: -1,
      built: false,
      plan: null as BoltPlan | null,
      hop: new Float32Array(brain.count),
      /** Per bank: drawing, its own clock, its length, seconds since it was replaced (-1 = not). */
      on: [false, false],
      t: [0, 0],
      life: [0, 0],
      fade: [-1, -1],
      cometTinted: false,
    }),
    [brain],
  );

  const smooth01 = (a: number, b: number, x: number) => {
    const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
    return t * t * (3 - 2 * t);
  };

  const endBank = (i: number) => {
    perf.on[i] = false;
    perf.fade[i] = -1;
    banks[i].geometry.setDrawRange(0, 0);
    const m = boltRefs.current[i];
    if (m) m.visible = false;
  };

  /** The running performance ends or is replaced: its bolts fade out over FADE_OUT on their own clock. */
  const releaseCurrent = () => {
    if (perf.cur >= 0 && perf.on[perf.cur]) perf.fade[perf.cur] = 0;
    perf.cur = -1;
    perf.built = false;
  };

  /** The vertex facing the input: nearest `fromCss` on screen, else the brain's upper right; the visible side wins. */
  const inputVertex = (fromCss: [number, number] | null): number => {
    const g = groupRef.current!;
    tmp.eye.setFromMatrixPosition(camera.matrixWorld);
    const r = domElement.getBoundingClientRect();
    const scale = size.height * 0.3;
    let best = 0;
    let bestScore = -Infinity;
    for (let i = 0; i < brain.count; i++) {
      vertexWorld(i, tmp.a);
      tmp.n.fromArray(brain.normal, i * 3).transformDirection(g.matrixWorld);
      const facing = tmp.n.dot(tmp.b.subVectors(tmp.eye, tmp.a).normalize());
      tmp.proj.copy(tmp.a).project(camera);
      const sx = ((tmp.proj.x + 1) / 2) * size.width;
      const sy = ((1 - tmp.proj.y) / 2) * size.height;
      const toward = fromCss
        ? -Math.hypot(sx - (fromCss[0] - r.left), sy - (fromCss[1] - r.top)) / scale
        : ((sx - sy) * 0.7071) / scale;
      const score = toward + 0.9 * Math.max(facing, -0.2);
      if (score > bestScore) {
        bestScore = score;
        best = i;
      }
    }
    return best;
  };

  /** Everything the shaders read for a performance goes back to what they read at rest. */
  const restUniforms = () => {
    perfU.uPerfMode.value = 0;
    perfU.uSigGain.value = 1;
    perfU.uBulge.value = 0.02;
    perfU.uJit.value = 0;
    perfU.uCoreR.value = 0;
    perfU.uCoreVis.value = 0;
    perfU.uCollapse.value = 0;
    if (coreRef.current) coreRef.current.visible = false;
    particleMaterial.uniforms.uHopRate.value = linkMaterial.uniforms.uHopRate.value = SIGNAL.HOP_RATE;
    particleMaterial.uniforms.uReach.value = linkMaterial.uniforms.uReach.value = SIGNAL.REACH;
  };

  /** Plan the bolts, write them into a free bank, lay the underglow's hop field. */
  const buildPerformance = (s: Signal) => {
    const partition = s.partition ?? 'rational';
    const mode = MODES[partition];
    const seed = s.seed ?? 0;
    if (s.vertex < 0) s.vertex = inputVertex(s.fromCss);
    const plan = planBolts(brain, partition, s.vertex, s.intensity ?? 0.5, seed);
    perf.plan = plan;

    // a free bank, else the one that has been fading longest
    let i = !perf.on[0] ? 0 : !perf.on[1] ? 1 : perf.fade[0] >= perf.fade[1] ? 0 : 1;
    if (perf.on[i]) endBank(i);
    perf.cur = i;
    perf.on[i] = true;
    perf.t[i] = -1;
    perf.life[i] = mode.life;
    perf.fade[i] = -1;

    const g = banks[i].geometry;
    const P0 = g.getAttribute('position').array as Float32Array;
    const P1 = g.getAttribute('aP1').array as Float32Array;
    const TM = g.getAttribute('aTm').array as Float32Array;
    const CN = g.getAttribute('aCn').array as Float32Array;
    const pos = brain.position;
    for (let e = 0; e < plan.count; e++) {
      const a = plan.a[e] * 3;
      const b = plan.b[e] * 3;
      for (let v = 0; v < VERTS_PER_EDGE; v++) {
        const k = e * VERTS_PER_EDGE + v;
        P0[k * 3] = pos[a];
        P0[k * 3 + 1] = pos[a + 1];
        P0[k * 3 + 2] = pos[a + 2];
        P1[k * 3] = pos[b];
        P1[k * 3 + 1] = pos[b + 1];
        P1[k * 3 + 2] = pos[b + 2];
        TM[k * 4] = plan.t0[e];
        TM[k * 4 + 1] = plan.t1[e];
        TM[k * 4 + 2] = plan.hue[e];
        TM[k * 4 + 3] = plan.gain[e];
        CN[k * 4 + 3] = plan.level[e];
      }
    }
    for (const n of ['position', 'aP1', 'aTm', 'aCn']) g.getAttribute(n).needsUpdate = true;
    g.setDrawRange(0, plan.count * QUADS_PER_EDGE * 6);

    const bu = banks[i].material.uniforms;
    bu.uMode.value = mode.id;
    bu.uWidth.value = mode.width;
    bu.uJitter.value = reducedMotion ? 0 : mode.jitter;
    bu.uFlickHz.value = reducedMotion ? 0 : mode.flickHz;
    bu.uFlash.value = mode.flash;
    bu.uTau.value = mode.tau;
    bu.uSplit.value = reducedMotion ? 0 : mode.split;
    bu.uSeed.value = (seed % 1000) * 0.137;

    // the underglow runs out of every bolt's origin at that bolt's time
    // (crazy: the shaders measure each vertex's distance from the light on the screen instead)
    if (partition !== 'crazy') {
      const rate = reducedMotion ? 4.5 : mode.hopRate;
      hopField(brain, plan.origins, plan.delays.map((d) => d * rate), perf.hop);
      writeHopArray(perf.hop);
    }

    // the comet wears the state's colours
    const sp = STATE_PALETTE[themeStore.get()];
    const cu = cometMaterial.uniforms;
    if (partition === 'rational') {
      cu.uColor.value.set(sp.rational);
      cu.uAccent.value.set(sp.rational);
    } else if (partition === 'crazy') {
      // one light, no colours
      const ink = themeStore.palette().ink;
      cu.uColor.value.set(ink);
      cu.uAccent.value.set(ink);
    } else {
      cu.uColor.value.set(sp.emotional[seed % 5]);
      cu.uAccent.value.set(sp.emotional[(seed + 1) % 5]);
    }
    perf.cometTinted = true;
    perf.built = true;
  };

  const runPerform = (s: Signal, delta: number) => {
    const partition = s.partition ?? 'rational';
    const mode = MODES[partition];
    const intensity = s.intensity ?? 0.5;
    const flight = s.fromCss ? FLIGHT : 0;
    const pu = particleMaterial.uniforms;
    const lu = linkMaterial.uniforms;
    if (!perf.built) buildPerformance(s);
    s.t += delta;
    const T = s.t - flight;
    if (T > mode.life) {
      // over: everything is back to what it was at rest
      humanStore.signal = null;
      if (perf.cur >= 0) endBank(perf.cur);
      perf.cur = -1;
      perf.sig = null;
      perf.built = false;
      restUniforms();
      pu.uSigT.value = lu.uSigT.value = -1;
      pu.uHold.value = lu.uHold.value = 0;
      return;
    }
    perf.t[perf.cur] = T;

    // the underglow on the dots and the lines
    const env = performEnvelope(mode, T, reducedMotion);
    const k = 0.6 + 0.4 * intensity;
    perfU.uPerfMode.value = mode.id;
    perfU.uPerfT.value = T;
    perfU.uPerfSeed.value = ((s.seed ?? 0) % 1000) / 1000;
    perfU.uSigGain.value = mode.gain * k * env * (reducedMotion ? 0.7 : 1);
    perfU.uBulge.value = reducedMotion ? 0.008 : mode.bulge;
    perfU.uJit.value = reducedMotion ? 0 : mode.jit * env * k;
    pu.uHopRate.value = lu.uHopRate.value = reducedMotion ? 4.5 : mode.hopRate;
    pu.uReach.value = lu.uReach.value = reducedMotion ? 18 : mode.reach;
    if (partition === 'crazy') {
      // D62: the whole brain falls into one point, rests, and unfolds again. With reduced motion
      // nothing moves: only the light at the centre rises and falls, slowly.
      const b = coreBloom(T);
      const gain = k * (reducedMotion ? 0.7 : 1);
      perfU.uSigGain.value = mode.gain * gain;
      perfU.uBulge.value = reducedMotion ? 0.008 : 0.02;
      perfU.uJit.value = 0;
      perfU.uCoreR.value = 0;
      perfU.uCoreVis.value = 0;
      perfU.uCollapse.value = reducedMotion ? 0 : b.collapse;
      const cm = coreMaterial.uniforms;
      cm.uRad.value = b.haloRadius;
      cm.uCoreSize.value = 0.03 + 0.05 * b.core;
      cm.uCore.value = Math.min(1, b.core * gain);
      cm.uHalo.value = Math.min(1, b.halo * gain);
      if (coreRef.current) coreRef.current.visible = T >= 0;
    }
    pu.uSigT.value = lu.uSigT.value = T;
    pu.uSigRegion.value = lu.uSigRegion.value = -1;
    pu.uHold.value = lu.uHold.value = 0;

    if (s.fromCss && s.t < flight + SIGNAL.TRAIL * SIGNAL.TRAIL_DT) flyComet(s, flight);

    // the state's name beside where the bolts start
    const alpha = smooth01(0, 0.15, T) * (1 - smooth01(mode.life * 0.5, mode.life * 0.8, T));
    if (alpha > 0.02) {
      vertexWorld(s.vertex, tmp.proj).project(camera);
      humanStore.label = {
        x: ((tmp.proj.x + 1) / 2) * size.width,
        y: ((1 - tmp.proj.y) / 2) * size.height,
        alpha,
        region: -1,
        text: partition === 'rational' ? '理性' : partition === 'emotional' ? '感性' : '癫狂',
      };
    }
  };

  /** The bolts' uniforms and visibility for this frame; two banks at most, one usually. */
  const applyBanks = (delta: number, settle: number) => {
    for (let i = 0; i < 2; i++) {
      if (!perf.on[i]) continue;
      if (perf.fade[i] >= 0) {
        // replaced: run on until faded
        perf.t[i] += delta;
        perf.fade[i] += delta;
        if (perf.fade[i] >= FADE_OUT || perf.t[i] > perf.life[i]) {
          endBank(i);
          continue;
        }
      }
      const m = boltRefs.current[i];
      if (!m) continue;
      const draw = !reducedMotion && settle > 0 && perf.t[i] >= 0;
      m.visible = draw;
      if (!draw) continue;
      const bu = banks[i].material.uniforms;
      const t = perf.t[i];
      bu.uPT.value = t;
      bu.uFade.value =
        (1 - smooth01(perf.life[i] - 0.35, perf.life[i], t)) * (perf.fade[i] >= 0 ? Math.max(0, 1 - perf.fade[i] / FADE_OUT) : 1);
      bu.uRes.value.set(size.width, size.height);
    }
  };

  const runSignal = (delta: number, settle: number) => {
    const s = humanStore.signal;
    const g = groupRef.current;
    const p = s && s.kind === 'perform' ? s : null;
    // a new performance, or none: the one that was running fades out
    if (perf.sig !== p) {
      releaseCurrent();
      perf.sig = p;
    }
    if (settle <= 0) for (let i = 0; i < 2; i++) if (perf.on[i]) endBank(i);
    if (!p && perf.cometTinted) {
      const pal = themeStore.palette();
      cometMaterial.uniforms.uColor.value.set(pal.ink);
      cometMaterial.uniforms.uAccent.value.set(pal.accent);
      perf.cometTinted = false;
    }
    if (p && g && settle > 0) {
      cometMaterial.uniforms.uShow.value = 0;
      humanStore.label = null;
      runPerform(p, delta);
    } else {
      restUniforms();
      runD53Signal(delta, settle);
    }
    applyBanks(delta, settle);
  };

  // ---- frame ---------------------------------------------------------------------
  useFrame((_, delta) => {
    const hp = humanProgress();
    const ph = TRANSITION.phases;
    const settle = phaseProgress(hp, ph.settle);
    if (stage.state === 'human') {
      stage.destTime += delta * stage.timeScale;
      const dt = delta * stage.timeScale;
      if (!humanStore.dragging) {
        // release inertia, decaying; the idle spin resumes underneath it
        const v = humanStore.spinVel;
        humanStore.dragYaw += v.yaw * dt;
        humanStore.dragPitch = Math.max(-1.1, Math.min(1.1, humanStore.dragPitch + v.pitch * dt));
        const k = Math.exp(-dt * 3.2);
        humanStore.spinVel = { yaw: v.yaw * k, pitch: v.pitch * k };
        if (!reducedMotion) humanStore.spin += BRAIN.spin * dt;
      }
    }

    const g = groupRef.current;
    if (g) {
      const s = brainTransform(settle);
      g.position.copy(tmp.v);
      g.quaternion.copy(tmp.q);
      g.scale.setScalar(s);
      g.updateMatrixWorld(true);
      particleMaterial.uniforms.uBrain.value.copy(g.matrixWorld);
    }

    const u = particleMaterial.uniforms;
    u.uDissolve.value = phaseProgress(hp, ph.surfaceDissolve);
    u.uMigrate.value = phaseProgress(hp, ph.migrate);
    u.uSettle.value = settle;
    u.uTime.value = stage.destTime;
    u.uFocus.value = humanStore.focusP;
    u.uSwirl.value = reducedMotion ? 0.15 : 1;

    const sizeScale = devicePixelsPerUnitDepth(size.height, dpr) * POINT_SIZE;
    u.uSizeScale.value = sizeScale;
    nodeMaterial.uniforms.uSizeScale.value = sizeScale;
    cometMaterial.uniforms.uSizeScale.value = sizeScale;

    // links surface once the particles have arrived, and go first on the way back
    const lu = linkMaterial.uniforms;
    lu.uShow.value = settle;
    lu.uFocus.value = humanStore.focusP;

    // on the scene clock, so a frozen clock (tests, captures) holds the signal still
    runSignal(delta * stage.timeScale, settle);

    edgeMaterial.uniforms.uGrow.value = humanStore.growP * levels;
    nodeMaterial.uniforms.uGrow.value = humanStore.growP * levels;

    if (pointsRef.current) pointsRef.current.visible = hp > 0;
    if (linksRef.current) linksRef.current.visible = settle > 0;

    // hover: nodes first, then regions (only while drilled in and settled)
    const ui = humanStore.get();
    let hovered: string | null = null;
    let region = -1;
    const ndc = pointerNdc.current;
    if (ui.focused && humanStore.growP > 0.5 && ndc && g) {
      let best = NODE_PICK_PX;
      graph.nodes.forEach((n) => {
        tmp.proj.fromArray(nodeLocal.get(n.id)!).applyMatrix4(g.matrixWorld).project(camera);
        const dx = ((tmp.proj.x - ndc.x) / 2) * size.width;
        const dy = ((tmp.proj.y - ndc.y) / 2) * size.height;
        const d = Math.hypot(dx, dy);
        if (d < best) {
          best = d;
          hovered = n.id;
        }
      });
      if (!hovered) {
        // the nearest net vertex, if the pointer is on the brain
        const hit = hitBrain(ndc);
        if (hit) region = brain.region[nearestVertex(brain, hit)];
      }
    }
    humanStore.set({ hovered, hoverRegion: region });
    u.uHoverRegion.value = region;
    lu.uHoverRegion.value = region;
    nodeMaterial.uniforms.uHover.value = hovered ? graph.nodes.findIndex((n) => n.id === hovered) : -1;
    nodeMaterial.uniforms.uSelected.value = ui.selected ? graph.nodes.findIndex((n) => n.id === ui.selected) : -1;
    if (stage.state === 'human') {
      domElement.style.cursor = humanStore.dragging && drag.current?.moved
        ? 'grabbing'
        : hovered || (!ui.focused && ndc && hitBrain(ndc))
          ? 'pointer'
          : 'grab';
    }
  });

  useEffect(() => {
    if (!DIAGNOSTICS_ENABLED) return;
    const w = window as unknown as { __alpha?: Record<string, unknown> };
    if (w.__alpha) {
      w.__alpha.brain = {
        count: cloud.count,
        vertices: brain.count,
        regions: brain.regions,
        /** The running signal (D53): kind, seconds, region, vertex; null when quiet. */
        signal: () => (humanStore.signal ? { ...humanStore.signal } : null),
        /**
         * Start a performance (D57): the same call the UI makes. `fromCss` null =
         * from the brain's upper right; the same seed gives the same bolts.
         */
        perform(partition: 'rational' | 'emotional' | 'crazy', intensity = 0.7, seed?: number, fromCss: [number, number] | null = null) {
          humanStore.perform({ partition, intensity, fromCss, seed });
        },
        /** The bolts in flight: path edges planned, banks drawing; `collapse` is the crazy state's 0..1 (D62). */
        perfInfo: () => ({
          edges: perf.plan?.count ?? 0,
          banksOn: [...perf.on],
          drawn: boltRefs.current.map((m) => !!m?.visible),
          collapse: perfU.uCollapse.value,
        }),
        /** Capture hook: put the running signal at `t` seconds (with the clock frozen). */
        setSignalTime(t: number) {
          if (humanStore.signal) humanStore.signal.t = t;
        },
        /** Screen position (CSS px) of the brain's centre and of a graph node. */
        screenOf(id?: string) {
          const g = groupRef.current;
          if (!g) return null;
          const p = id ? new Vector3().fromArray(nodeLocal.get(id)!).applyMatrix4(g.matrixWorld) : g.position.clone();
          p.project(camera);
          return [((p.x + 1) / 2) * size.width, ((1 - p.y) / 2) * size.height];
        },
      };
    }
  }, [cloud, brain, nodeLocal, camera, size, particleMaterial]);

  return (
    <>
      <points ref={pointsRef} geometry={geometry} material={particleMaterial} frustumCulled={false} visible={false} />
      <points ref={cometRef} geometry={comet} material={cometMaterial} renderOrder={30} frustumCulled={false} />
      <group ref={groupRef}>
        <mesh ref={coreRef} geometry={coreGeometry} material={coreMaterial} renderOrder={9} frustumCulled={false} visible={false} />
        <mesh ref={(m) => (boltRefs.current[0] = m)} geometry={banks[0].geometry} material={banks[0].material} renderOrder={8} frustumCulled={false} visible={false} />
        <mesh ref={(m) => (boltRefs.current[1] = m)} geometry={banks[1].geometry} material={banks[1].material} renderOrder={8} frustumCulled={false} visible={false} />
        <lineSegments ref={linksRef} geometry={links} material={linkMaterial} renderOrder={5} frustumCulled={false} visible={false} />
        <lineSegments geometry={edges} material={edgeMaterial} renderOrder={20} frustumCulled={false} />
        <points geometry={nodes} material={nodeMaterial} renderOrder={21} frustumCulled={false} />
      </group>
    </>
  );
}
