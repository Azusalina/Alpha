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
  Vector4,
} from 'three';

import { DIAGNOSTICS_ENABLED } from '../app/diagnostics';
import { humanStore } from '../app/humanStore';
import { humanProgress, stage } from '../app/stage';
import { brainLinks, buildHumanCloud, nodeBrainPositions } from '../brain/humanCloud';
import { useBrainPoints } from '../brain/brainAsset';
import { ANCHORS, BRAIN, PALETTE, devicePixelsPerUnitDepth } from '../config/composition';
import { QUALITY, SCENE_SEED, type QualityTier } from '../config/quality';
import { TRANSITION, phaseProgress } from '../config/timing';
import { GRAPH } from '../fixtures/graph';
import { useHandGeometry } from '../hand/assets';
import { handRig } from '../hand/pose';
import { focusBrain } from '../app/navigation';
import { applyInk, useThemeBinding } from './useThemeBinding';

/** Same on-screen dot scale as the particle hand (ParticleHand POINT_SIZE). */
const POINT_SIZE = 0.0042;
/** Ripple speed (brain-local units per second) and lifetime (seconds). */
const PULSE_SPEED = 1.6;
const PULSE_LIFE = 1.5;
/**
 * How much the arrived brain is strengthened over the plain hand particles
 * (decision D41): more opaque and a little larger overall, and more again on
 * the silhouette (points whose surface turns away from the viewer), so the
 * resting brain in the lower left reads as a shape. Drilled in, the rim boost
 * halves so it does not crowd the interior and the tree.
 */
const VISIBILITY = {
  alpha: 0.3,
  rimAlpha: 0.7,
  size: 0.18,
  rimSize: 0.5,
  /** In the glowing dark theme the brain's dots get this much more light. */
  darkGlow: 1.25,
} as const;

/**
 * The brain's particle budget as a share of the tier's hand budget (D46): half,
 * so the brain reads clean and simple rather than as a dense haze.
 */
const BRAIN_PARTICLE_SHARE = 0.5;

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
  const brain = useBrainPoints();
  const source = useHandGeometry('left');
  const rig = handRig('left');
  const camera = useThree((s) => s.camera);
  const size = useThree((s) => s.size);
  const dpr = useThree((s) => s.viewport.dpr);
  const domElement = useThree((s) => s.gl.domElement);

  const cloud = useMemo(
    () =>
      buildHumanCloud(
        source,
        rig,
        brain,
        Math.round(QUALITY[tier].particleCount * BRAIN_PARTICLE_SHARE),
        SCENE_SEED + 1,
      ),
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

  /** Faint neighbour links (D37), brain-local, drawn inside the brain group. */
  const links = useMemo(() => {
    const l = brainLinks(cloud);
    const g = new BufferGeometry();
    g.setAttribute('position', new Float32BufferAttribute(l.position, 3));
    g.setAttribute('aRegion', new Float32BufferAttribute(l.region, 1));
    return g;
  }, [cloud]);

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
          uPulseOrigin: { value: new Vector3() },
          uPulseT: { value: -1 },
          uPulseSpeed: { value: PULSE_SPEED },
          uPulseLife: { value: PULSE_LIFE },
          uPulseRegion: { value: -1 },
          uColor: { value: new Color(PALETTE.inkSoft) },
          uAlpha: { value: 1 },
        },
        vertexShader: /* glsl */ `
          attribute float aRegion;
          uniform float uHoverRegion;
          uniform float uFocus;
          uniform vec3 uPulseOrigin;
          uniform float uPulseT;
          uniform float uPulseSpeed;
          uniform float uPulseLife;
          uniform float uPulseRegion;
          varying float vLit;
          varying float vShell;
          void main() {
            float lit = step(abs(aRegion - uHoverRegion), 0.5) * uFocus;
            if (uPulseT >= 0.0) {
              float d = distance(position, uPulseOrigin);
              float wave = exp(-pow((d - uPulseT * uPulseSpeed) * 7.0, 2.0)) * (1.0 - uPulseT / uPulseLife);
              float hit = uPulseRegion < 0.0 ? 1.0 : step(abs(aRegion - uPulseRegion), 0.5);
              lit = max(lit, wave * hit);
            }
            vLit = lit;
            // the cortex carries the web; the dense interior stays quieter
            vShell = smoothstep(0.35, 0.9, length(position));
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
          }
        `,
        fragmentShader: /* glsl */ `
          uniform float uShow;
          uniform vec3 uColor;
          uniform float uAlpha;
          varying float vLit;
          varying float vShell;
          void main() {
            // D44: about twice the opacity, same 1-px width
            float a = uShow * mix(0.11, 0.26, vShell) * (1.0 + 1.6 * vLit) * uAlpha;
            if (a <= 0.002) discard;
            gl_FragColor = vec4(uColor, min(1.0, a));
          }
        `,
      }),
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
          uPulseRegion: { value: -1 },
          uPulseOrigin: { value: new Vector3() },
          uPulseT: { value: -1 },
          uPulseSpeed: { value: PULSE_SPEED },
          uPulseLife: { value: PULSE_LIFE },
          uSwirl: { value: 1 },
          uVis: { value: new Vector4(VISIBILITY.alpha, VISIBILITY.rimAlpha, VISIBILITY.size, VISIBILITY.rimSize) },
          uSizeScale: { value: 1 },
          uColor: { value: new Color(PALETTE.ink) },
          uAccent: { value: new Color(PALETTE.inkSoft) },
          uAlpha: { value: 1 },
          uGlow: { value: 0 },
        },
        vertexShader: /* glsl */ `
          attribute vec3 aBrain;
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
          uniform float uPulseRegion;
          uniform vec3 uPulseOrigin;
          uniform float uPulseT;
          uniform float uPulseSpeed;
          uniform float uPulseLife;
          uniform float uSwirl;
          uniform vec4 uVis; // alpha, rim alpha, size, rim size (VISIBILITY)
          uniform float uSizeScale;

          varying float vAlpha;
          varying float vLit;

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
            float ph = uTime * 0.8 + aHash.y * 6.2831853;
            pos += vec3(sin(ph), cos(ph * 0.9), sin(ph * 0.7)) * 0.006 * uSettle;

            // Ripple: a shell expanding from the pulse origin through the brain.
            float lit = 0.0;
            if (uPulseT >= 0.0) {
              float d = distance(aBrain, uPulseOrigin);
              float front = uPulseT * uPulseSpeed;
              float wave = exp(-pow((d - front) * 7.0, 2.0)) * (1.0 - uPulseT / uPulseLife);
              float regionHit = uPulseRegion < 0.0 ? 1.0 : step(abs(aRegion - uPulseRegion), 0.5);
              lit = max(lit, wave * regionHit);
              pos += normalize(target - (uBrain * vec4(0.0, 0.0, 0.0, 1.0)).xyz + vec3(1e-4))
                   * wave * regionHit * 0.025 * uSettle;
            }
            // Hovered region, while drilled in.
            lit = max(lit, step(abs(aRegion - uHoverRegion), 0.5) * uFocus * 0.65);
            vLit = lit;

            // Visibility once arrived (D41): the silhouette is where the surface
            // normal (≈ direction from the brain centre) turns away from the
            // viewer; those points get the strongest boost, so the outline reads.
            float shell = smoothstep(0.35, 0.9, length(aBrain));
            vec3 centre = (uBrain * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
            vec3 nrm = normalize(target - centre + vec3(1e-4));
            vec3 toEye = normalize(cameraPosition - target);
            float rim = smoothstep(0.5, 0.95, 1.0 - abs(dot(nrm, toEye))) * shell;
            float rimK = rim * (1.0 - 0.5 * uFocus);

            vec4 mv = modelViewMatrix * vec4(pos, 1.0);
            gl_Position = projectionMatrix * mv;
            float grow = (1.0 + m * (uVis.z + uVis.w * rimK)) * (1.0 + m * 0.2 * aBrain.x);
            gl_PointSize = aSize * grow * (1.0 + 0.9 * lit) * uSizeScale / max(0.25, -mv.z);

            // The interior stays a touch lighter than the cortex, for depth.
            float body = mix(1.0, 0.9 + 0.1 * shell, m);
            float boost = 1.0 + m * (uVis.x + uVis.y * rimK);
            // Front / back balance (D43), in the brain's own frame so it turns
            // with it: the frontal pole is the sparsest part of the model and the
            // back has the cerebellum layered under the cortex.
            // Opacity is already saturated in the light theme, so the balance
            // acts on coverage: front dots a little larger, back ones smaller.
            boost *= 1.0 + m * 0.12 * aBrain.x;
            vAlpha = aTone * appear * body * boost * (0.85 + 0.15 * lit);
          }
        `,
        fragmentShader: /* glsl */ `
          uniform vec3 uColor;
          uniform vec3 uAccent;
          uniform float uAlpha;
          uniform float uGlow;
          varying float vAlpha;
          varying float vLit;
          void main() {
            vec2 c = gl_PointCoord - 0.5;
            float r = dot(c, c);
            if (r > 0.25) discard;
            float a = vAlpha * (1.0 - smoothstep(mix(0.16, 0.0, uGlow), 0.25, r));
            if (a <= 0.004) discard;
            gl_FragColor = vec4(mix(uColor, uAccent, 0.35 * vLit), min(1.0, a * (1.0 + 0.4 * vLit)) * uAlpha);
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

  useThemeBinding(
    (p) => {
      particleMaterial.uniforms.uColor.value.set(p.ink);
      particleMaterial.uniforms.uAccent.value.set(p.inkSoft);
      applyInk(particleMaterial, p, VISIBILITY.darkGlow);
      edgeMaterial.uniforms.uColor.value.set(p.inkSoft);
      applyInk(edgeMaterial, p, 1.2);
      nodeMaterial.uniforms.uColor.value.set(p.ink);
      applyInk(nodeMaterial, p);
      // links in full ink (not the softer ink) so they read brighter
      linkMaterial.uniforms.uColor.value.set(p.ink);
      applyInk(linkMaterial, p, 1.5);
    },
    [particleMaterial, edgeMaterial, nodeMaterial, linkMaterial],
  );

  const groupRef = useRef<Group>(null);
  const pointsRef = useRef<import('three').Points>(null);
  const linksRef = useRef<import('three').LineSegments>(null);

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

    // ripple clock
    if (humanStore.pulseT >= 0) {
      humanStore.pulseT += delta;
      if (humanStore.pulseT > PULSE_LIFE) humanStore.pulseT = -1;
    }
    u.uPulseT.value = humanStore.pulseT;
    u.uPulseRegion.value = humanStore.pulseRegion;
    u.uPulseOrigin.value.fromArray(humanStore.pulseOrigin);

    const sizeScale = devicePixelsPerUnitDepth(size.height, dpr) * POINT_SIZE;
    u.uSizeScale.value = sizeScale;
    nodeMaterial.uniforms.uSizeScale.value = sizeScale;

    // links surface once the particles have arrived, and go first on the way back
    const lu = linkMaterial.uniforms;
    lu.uShow.value = settle;
    lu.uFocus.value = humanStore.focusP;
    lu.uPulseT.value = humanStore.pulseT;
    lu.uPulseRegion.value = humanStore.pulseRegion;
    lu.uPulseOrigin.value.fromArray(humanStore.pulseOrigin);

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
        // nearest of a sparse subset of brain particles, if the pointer is on the brain
        const hit = hitBrain(ndc);
        if (hit) {
          let bestD = Infinity;
          for (let i = 0; i < cloud.count; i += 7) {
            const dx = cloud.brain[i * 3] - hit[0];
            const dy = cloud.brain[i * 3 + 1] - hit[1];
            const dz = cloud.brain[i * 3 + 2] - hit[2];
            const d = dx * dx + dy * dy + dz * dz;
            if (d < bestD) {
              bestD = d;
              region = cloud.region[i];
            }
          }
        }
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
        /** Tuning hook: override the VISIBILITY vector (alpha, rimAlpha, size, rimSize). */
        setVis(a: number, b: number, c: number, d: number) {
          particleMaterial.uniforms.uVis.value.set(a, b, c, d);
        },
        regions: brain.meta.regions,
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
      <group ref={groupRef}>
        <lineSegments ref={linksRef} geometry={links} material={linkMaterial} renderOrder={5} frustumCulled={false} visible={false} />
        <lineSegments geometry={edges} material={edgeMaterial} renderOrder={20} frustumCulled={false} />
        <points geometry={nodes} material={nodeMaterial} renderOrder={21} frustumCulled={false} />
      </group>
    </>
  );
}
