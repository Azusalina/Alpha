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
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useMemo, useRef } from 'react';
import {
  BufferGeometry,
  Color,
  Euler,
  Float32BufferAttribute,
  Group,
  Matrix4,
  NormalBlending,
  Quaternion,
  Ray,
  ShaderMaterial,
  Sphere,
  Vector2,
  Vector3,
} from 'three';

import { DIAGNOSTICS_ENABLED } from '../app/diagnostics';
import { humanStore } from '../app/humanStore';
import { humanProgress, stage } from '../app/stage';
import { buildHumanCloud, nodeBrainPositions } from '../brain/humanCloud';
import { hopDistances, nearestVertex, useBrainMesh } from '../brain/brainAsset';
import { ANCHORS, BRAIN, PALETTE, devicePixelsPerUnitDepth } from '../config/composition';
import { SCENE_SEED, type QualityTier } from '../config/quality';
import { TRANSITION, phaseProgress } from '../config/timing';
import { GRAPH } from '../fixtures/graph';
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
  // brightness of the travelling discharge at this many hops from the impact
  float discharge(float hop) {
    if (uSigT < 0.0) return 0.0;
    float front = uSigT * uHopRate;
    float band = exp(-pow((hop - front) / 1.1, 2.0));
    // a short afterglow behind the front, all of it fading with distance
    float wake = step(hop, front) * exp(-(front - hop) * 0.9) * 0.35;
    return max(band, wake) * exp(-hop / uReach);
  }
  float held(float region) {
    return uSigRegion < 0.0 ? 0.0 : step(abs(region - uSigRegion), 0.5) * uHold;
  }
`;

const signalUniforms = () => ({
  uSigT: { value: -1 },
  uHopRate: { value: SIGNAL.HOP_RATE },
  uReach: { value: SIGNAL.REACH },
  uSigRegion: { value: -1 },
  uHold: { value: 0 },
});


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
  const source = useHandGeometry('left');
  const rig = handRig('left');
  const camera = useThree((s) => s.camera);
  const size = useThree((s) => s.size);
  const dpr = useThree((s) => s.viewport.dpr);
  const domElement = useThree((s) => s.gl.domElement);

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

  const nodeLocal = useMemo(() => nodeBrainPositions(brain, GRAPH.nodes), [brain]);

  /** Graph edges inside the brain: arcs bowed outward, ordered root → leaves for growth. */
  const edges = useMemo(() => {
    const SEG = 14;
    const pos: number[] = [];
    const order: number[] = [];
    const kind: number[] = [];
    const depth = new Map(GRAPH.nodes.map((n) => [n.id, n.depth]));
    const a = new Vector3();
    const b = new Vector3();
    const mid = new Vector3();
    const q = new Vector3();
    const prev = new Vector3();
    for (const e of GRAPH.edges) {
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
    GRAPH.nodes.forEach((n, i) => {
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
          ${SIGNAL_GLSL}
          void main() {
            vHop = aHop;
            vHover = step(abs(aRegion - uHoverRegion), 0.5) * uFocus;
            vHeld = held(aRegion);
            vec4 mv = modelViewMatrix * vec4(position, 1.0);
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
          ${SIGNAL_GLSL}
          void main() {
            // the hop varies along the edge, so the discharge runs down it
            float w = discharge(vHop);
            float lit = max(max(w, vHeld * 0.8), vHover * 0.6);
            float a = uShow * mix(0.06, 0.34, vFront) * (1.0 + 2.2 * lit) * uAlpha;
            if (a <= 0.002) discard;
            vec3 col = mix(uColor, uAccent, clamp(vHeld * 0.9 + w * 0.45, 0.0, 1.0));
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

          varying float vAlpha;
          varying float vLit;
          varying float vHeld;
          ${SIGNAL_GLSL}

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

            vec3 target = (uBrain * vec4(aBrain, 1.0)).xyz;
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
            float w = discharge(aHop) * uSettle;
            float hold = held(aRegion) * uSettle;
            pos += nrm * w * 0.02;
            // Hovered region, while drilled in.
            float hover = step(abs(aRegion - uHoverRegion), 0.5) * uFocus * 0.65;
            vLit = max(max(w, hold), hover);
            vHeld = clamp(hold * 0.9 + w * 0.45, 0.0, 1.0);

            // Arrived, the net (D52): every vertex one clean dot, the side
            // facing the viewer full, the far side a faint echo.
            vec3 toEye = normalize(cameraPosition - target);
            float front = smoothstep(-0.3, 0.4, dot(nrm, toEye));
            vec4 mv = modelViewMatrix * vec4(pos, 1.0);
            gl_Position = projectionMatrix * mv;
            float node = mix(1.0, 1.7 * mix(0.7, 1.0, front), m);
            float size = mix(aSize, node, m);
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
          void main() {
            vec2 c = gl_PointCoord - 0.5;
            float r = dot(c, c);
            if (r > 0.25) discard;
            float a = vAlpha * (1.0 - smoothstep(mix(0.16, 0.0, uGlow), 0.25, r));
            if (a <= 0.004) discard;
            gl_FragColor = vec4(mix(uColor, uAccent, vHeld), min(1.0, a) * uAlpha);
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
          uColor: { value: new Color(PALETTE.inkSoft) },
          uAlpha: { value: 1 },
        },
        vertexShader: /* glsl */ `
          attribute float aOrder;
          attribute float aKind;
          varying float vOrder;
          varying float vKind;
          void main() {
            vOrder = aOrder;
            vKind = aKind;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
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
          uColor: { value: new Color(PALETTE.ink) },
          uAlpha: { value: 1 },
        },
        vertexShader: /* glsl */ `
          attribute float aDepth;
          attribute float aIndex;
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
            vec4 mv = modelViewMatrix * vec4(position, 1.0);
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

  useThemeBinding(
    (p) => {
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
    [particleMaterial, edgeMaterial, nodeMaterial, linkMaterial, cometMaterial],
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

  /** Write the hop distances from `start` into the dots and the lines. */
  const writeHops = (start: number) => {
    const hop = hopDistances(brain, start);
    const pa = geometry.getAttribute('aHop');
    for (let k = 0; k < cloud.count; k++) pa.array[k] = hop[cloud.vertex[k]];
    pa.needsUpdate = true;
    const la = links.getAttribute('aHop');
    for (let k = 0; k < brain.edges.length; k++) la.array[k] = hop[brain.edges[k]];
    la.needsUpdate = true;
  };

  const runSignal = (delta: number, settle: number) => {
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
    if (s.kind === 'input' && s.fromCss && s.t < flight + SIGNAL.TRAIL * SIGNAL.TRAIL_DT) {
      const r = domElement.getBoundingClientRect();
      vertexWorld(s.vertex, tmp.b);
      const depth = tmp.proj.copy(tmp.b).project(camera).z;
      tmp.a
        .set(((s.fromCss[0] - r.left) / r.width) * 2 - 1, -((s.fromCss[1] - r.top) / r.height) * 2 + 1, depth)
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
    }

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

    edgeMaterial.uniforms.uGrow.value = humanStore.growP * 4;
    nodeMaterial.uniforms.uGrow.value = humanStore.growP * 4;

    if (pointsRef.current) pointsRef.current.visible = hp > 0;
    if (linksRef.current) linksRef.current.visible = settle > 0;

    // hover: nodes first, then regions (only while drilled in and settled)
    const ui = humanStore.get();
    let hovered: string | null = null;
    let region = -1;
    const ndc = pointerNdc.current;
    if (ui.focused && humanStore.growP > 0.5 && ndc && g) {
      let best = NODE_PICK_PX;
      GRAPH.nodes.forEach((n) => {
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
    nodeMaterial.uniforms.uHover.value = hovered ? GRAPH.nodes.findIndex((n) => n.id === hovered) : -1;
    nodeMaterial.uniforms.uSelected.value = ui.selected ? GRAPH.nodes.findIndex((n) => n.id === ui.selected) : -1;
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
        <lineSegments ref={linksRef} geometry={links} material={linkMaterial} renderOrder={5} frustumCulled={false} visible={false} />
        <lineSegments geometry={edges} material={edgeMaterial} renderOrder={20} frustumCulled={false} />
        <points geometry={nodes} material={nodeMaterial} renderOrder={21} frustumCulled={false} />
      </group>
    </>
  );
}
