/**
 * The right, system hand: a point cloud that is recognisably a hand near the
 * fingertips and thins out toward the lower right.
 *
 * All per-particle motion happens in the vertex shader from a handful of
 * uniforms (spec 9): gather progress for startup, a breathing envelope for idle,
 * and a pointer position for local disturbance. Nothing is written per particle
 * on the CPU per frame, and nothing is re-randomised — a particle's disturbance
 * is a function of its id, so the home state is always recoverable exactly.
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useMemo, useRef, type RefObject } from 'react';
import {
  BufferGeometry,
  Color,
  Float32BufferAttribute,
  FrontSide,
  MeshBasicMaterial,
  MeshStandardMaterial,
  NormalBlending,
  ShaderMaterial,
  Vector3,
} from 'three';

import { DIAGNOSTICS_ENABLED } from '../app/diagnostics';
import { digestCloud, inspection } from '../app/inspection';
import { humanProgress, stage, systemProgress } from '../app/stage';
import { treeStore } from '../app/treeStore';
import { PALETTE, devicePixelsPerUnitDepth } from '../config/composition';
import { QUALITY, SCENE_SEED, type QualityTier } from '../config/quality';
import { IDLE, REDUCED_MOTION, STARTUP, SYSTEM_PHASES, TRANSITION, phaseProgress } from '../config/timing';
import { GRAPH } from '../fixtures/graph';
import { treeLayout } from '../tree/layoutCache';
import { mapToTree } from '../tree/mapping';
import { useHandContour, useHandGeometry } from '../hand/assets';
import { handRig } from '../hand/pose';
import { dissipationDirection, sampleParticleHand, scatterOrigin } from '../hand/sampling';
import { applyInk, useThemeBinding } from './useThemeBinding';
import { useViewMode } from './useViewMode';

interface Props {
  tier: QualityTier;
  /** Pointer position on the composition plane, or null when off-canvas. */
  pointer: RefObject<Vector3 | null>;
  reducedMotion: boolean;
}

/**
 * Base point diameter as a fraction of one world unit at the home camera
 * distance. Tuned so a mean-weight particle lands near 2.5 device pixels —
 * small enough to read as deposited ink, large enough not to alias away.
 */
const POINT_SIZE = 0.0042;

/**
 * The sampling seed. Dev/test builds accept `?seed=<integer>` to sample the cloud
 * with another seed (the D10 noise measurements); the product always uses
 * SCENE_SEED.
 */
function particleSeed(): number {
  if (!DIAGNOSTICS_ENABLED) return SCENE_SEED;
  const s = new URLSearchParams(window.location.search).get('seed');
  return s !== null && /^\d+$/.test(s) ? Number(s) : SCENE_SEED;
}


export function ParticleHand({ tier, pointer, reducedMotion }: Props) {
  const size = useThree((s) => s.size);
  const dpr = useThree((s) => s.viewport.dpr);

  const source = useHandGeometry('right');
  const contour = useHandContour('right');
  const rig = handRig('right');
  const viewMode = useViewMode();

  const toward = useMemo(() => dissipationDirection(rig), [rig]);

  const geometry = useMemo(() => {
    const count = QUALITY[tier].particleCount;
    const nails = contour.nails ?? [];
    const cloud = sampleParticleHand(source, rig, count, particleSeed(), nails);
    if (DIAGNOSTICS_ENABLED) {
      inspection.particles = digestCloud(cloud);
      inspection.resample = (seed) => digestCloud(sampleParticleHand(source, rig, count, seed, nails));
    }

    const scatter = new Float32Array(cloud.count * 3);
    const tmp = new Vector3();
    for (let i = 0; i < cloud.count; i++) {
      scatterOrigin(cloud, toward, i, tmp);
      scatter[i * 3] = tmp.x;
      scatter[i * 3 + 1] = tmp.y;
      scatter[i * 3 + 2] = tmp.z;
    }

    const g = new BufferGeometry();
    g.setAttribute('position', new Float32BufferAttribute(cloud.home, 3));
    g.setAttribute('aScatter', new Float32BufferAttribute(scatter, 3));
    g.setAttribute('aSize', new Float32BufferAttribute(cloud.size, 1));
    g.setAttribute('aTone', new Float32BufferAttribute(cloud.tone, 1));
    g.setAttribute('aId', new Float32BufferAttribute(cloud.id, 1));
    g.setAttribute('aDissolve', new Float32BufferAttribute(cloud.dissolve, 1));
    g.setAttribute('aRim', new Float32BufferAttribute(cloud.rim, 1));
    g.setAttribute('aHash', new Float32BufferAttribute(cloud.hash, 3));

    // the technology tree this hand becomes at the system destination
    const tree = mapToTree(cloud.home, cloud.dissolve, cloud.count, GRAPH, treeLayout());
    g.setAttribute('aTarget', new Float32BufferAttribute(tree.target, 3));
    g.setAttribute('aRole', new Float32BufferAttribute(tree.role, 1));
    g.setAttribute('aNode', new Float32BufferAttribute(tree.node, 1));
    g.computeBoundingSphere();
    return g;
  }, [source, contour, rig, tier, toward]);

  useEffect(() => {
    if (DIAGNOSTICS_ENABLED) inspection.meshes.right = source;
  }, [source]);

  /** Dev view modes (docs/CONTRACTS.md §9) show the mesh the particles are sampled from. */
  const solidMaterial = useMemo(
    () =>
      new MeshStandardMaterial({
        color: new Color(PALETTE.sculptureLight),
        roughness: 0.92,
        metalness: 0,
        side: FrontSide,
      }),
    [],
  );
  const silhouetteMaterial = useMemo(
    () => new MeshBasicMaterial({ color: new Color(0, 0, 1), toneMapped: false, side: FrontSide }),
    [],
  );

  const material = useMemo(
    () =>
      new ShaderMaterial({
        transparent: true,
        depthWrite: false,
        blending: NormalBlending,
        uniforms: {
          uGather: { value: 0 },
          uTime: { value: 0 },
          uBreath: { value: IDLE.breathAmplitude },
          uPointer: { value: new Vector3() },
          uPointerInfluence: { value: 0 },
          uPointerRadius: { value: IDLE.pointerRadius },
          uPointerStrength: { value: IDLE.pointerStrength },
          uSizeScale: { value: 1 },
          uExit: { value: 0 },
          uToward: { value: new Vector3() },
          uMorph: { value: 0 },
          uSettle: { value: 0 },
          uDestTime: { value: 0 },
          uHoverNode: { value: -1 },
          uSelectedNode: { value: -1 },
          uColor: { value: new Color(PALETTE.ink) },
          uAlpha: { value: 1 },
          uGlow: { value: 0 },
        },
        vertexShader: /* glsl */ `
          attribute vec3 aScatter;
          attribute float aSize;
          attribute float aTone;
          attribute float aId;
          attribute float aDissolve;
          attribute float aRim;
          attribute vec3 aHash;
          attribute vec3 aTarget;
          attribute float aRole;
          attribute float aNode;

          uniform float uGather;
          uniform float uTime;
          uniform float uBreath;
          uniform vec3 uPointer;
          uniform float uPointerInfluence;
          uniform float uPointerRadius;
          uniform float uPointerStrength;
          uniform float uSizeScale;
          uniform float uExit;
          uniform vec3 uToward;
          uniform float uMorph;
          uniform float uSettle;
          uniform float uDestTime;
          uniform float uHoverNode;
          uniform float uSelectedNode;

          varying float vAlpha;

          void main() {
            // Per-particle constants, integer-hashed from the id on the CPU
            // (sampling.ts): the same on every GPU, and recomputable from the id,
            // so a reverse transition reproduces them exactly (D29).
            float h1 = aHash.x;
            float h2 = aHash.y;
            float h3 = aHash.z;

            // Startup: each particle gathers on its own slightly delayed clock,
            // so the cloud condenses instead of sliding in as one block.
            float lead = mix(0.0, 0.35, h1 * (0.35 + aDissolve));
            float g = clamp((uGather - lead) / max(0.0001, 1.0 - lead), 0.0, 1.0);
            g = g * g * (3.0 - 2.0 * g);
            vec3 pos = mix(aScatter, position, g);

            // Idle breathing, enveloped by gather so it is silent while scattered.
            // Particles that define the outline (on the rim, not yet dissolving)
            // move least, so the hand keeps its shape while it breathes (review B3).
            float phase = uTime * 6.2831853 + h2 * 6.2831853;
            vec3 drift = vec3(sin(phase), cos(phase * 0.87), sin(phase * 0.63)) * uBreath;
            float hold = 1.0 - 0.7 * aRim * (1.0 - aDissolve);
            pos += drift * g * (0.4 + 0.9 * aDissolve) * hold;

            // Local pointer disturbance: neighbours only, pushed outward.
            vec3 away = pos - uPointer;
            float d = length(away);
            float influence = 1.0 - smoothstep(0.0, uPointerRadius, d);
            pos += normalize(away + vec3(0.0001)) * influence * influence
                 * uPointerStrength * uPointerInfluence * (0.6 + h3);

            // Auxiliary exit (a destination on the other side): the hand scatters
            // along its own dissipation direction out of view and fades
            // (ambientBorderParticles = false). Zero at home, so home is exact.
            float x = clamp((uExit - h1 * 0.3) / 0.7, 0.0, 1.0);
            x = x * x * (3.0 - 2.0 * x);
            vec3 jitter = (aHash - 0.5) * vec3(0.9, 0.9, 0.6);
            pos += (uToward * (0.8 + 1.6 * h3) + jitter) * x;

            // System destination (spec 3 前往右下): the hand becomes the tree.
            // Each particle leaves on its own clock (fingertips and knuckles
            // first, the forearm last), flies with a mid-course swirl whose
            // envelope is zero at both ends, and settles into a node cluster or
            // onto an edge; the tail scatters out of view instead. At uMorph = 0
            // nothing here moves anything, so home is exact.
            float leave = aDissolve * 0.45 + h1 * 0.2;
            float mm = clamp((uMorph - leave) / 0.35, 0.0, 1.0);
            mm = mm * mm * mm * (mm * (mm * 6.0 - 15.0) + 10.0);
            float lit = 0.0;
            if (aRole < 1.5) {
              vec3 axis = normalize(aTarget - pos + vec3(1e-4));
              vec3 side = normalize(cross(axis, vec3(0.0, 0.0, 1.0)) + vec3(1e-4));
              vec3 up = cross(axis, side);
              float ang = 6.2831853 * (h2 + mm * (0.4 + h3));
              vec3 swirl = (side * cos(ang) + up * sin(ang)) * sin(3.14159265 * mm) * (0.08 + 0.16 * h3);
              // a faint shimmer once the tree has settled
              float ph = uDestTime * 0.9 + h2 * 6.2831853;
              vec3 shimmer = vec3(sin(ph), cos(ph * 0.8), 0.0) * 0.0035 * uSettle;
              pos = mix(pos, aTarget, mm) + swirl + shimmer;
              float isHover = step(abs(aNode - uHoverNode), 0.5);
              float isSel = step(abs(aNode - uSelectedNode), 0.5);
              lit = max(isHover * 0.8, isSel) * uSettle;
            } else {
              pos += (uToward * (0.9 + 1.8 * h3) + (aHash - 0.5) * 0.8) * mm;
            }
            float fade = aRole < 1.5 ? (aRole > 0.5 ? mix(1.0, 0.6, mm) : 1.0) : 1.0 - mm;

            vec4 mv = modelViewMatrix * vec4(pos, 1.0);
            gl_Position = projectionMatrix * mv;
            gl_PointSize = aSize * (1.0 + 0.7 * lit) * uSizeScale / max(0.25, -mv.z);

            // Larger points are lighter (aTone), the tail reads lighter still, and
            // everything fades up as it gathers. On the tree the tail's lightness
            // no longer applies: a node is solid ink.
            float tailLight = mix(1.0 - 0.45 * aDissolve, 1.0, mm * step(aRole, 1.5));
            vAlpha = aTone * tailLight * clamp(g * 1.6, 0.0, 1.0) * (1.0 - x) * fade * (1.0 + 0.3 * lit);
          }
        `,
        fragmentShader: /* glsl */ `
          uniform vec3 uColor;
          uniform float uAlpha;
          uniform float uGlow;
          varying float vAlpha;

          void main() {
            vec2 c = gl_PointCoord - 0.5;
            float r = dot(c, c);
            if (r > 0.25) discard;

            // Soft-edged dot: small points stay crisp, large ones read as deposits.
            // In the dark theme the edge softens into a glow (uGlow = 1).
            float edge = 1.0 - smoothstep(mix(0.16, 0.0, uGlow), 0.25, r);
            float a = vAlpha * edge * uAlpha;
            if (a <= 0.004) discard;
            gl_FragColor = vec4(uColor, a);
          }
        `,
      }),
    [],
  );

  useThemeBinding(
    (p) => {
      material.uniforms.uColor.value.set(p.ink);
      applyInk(material, p);
      solidMaterial.color.set(p.sculptureLight);
    },
    [material, solidMaterial],
  );

  const smoothed = useRef(new Vector3());
  /** False until the pointer is first seen, so acquisition snaps instead of lerping. */
  const acquired = useRef(false);

  useFrame((_, delta) => {
    const p = stage.state === 'intro' ? stage.progress : stage.state === 'loading' ? 0 : 1;
    material.uniforms.uGather.value = phaseProgress(p, STARTUP.phases.particleGather);
    material.uniforms.uExit.value = phaseProgress(humanProgress(), TRANSITION.phases.auxiliaryExit);
    material.uniforms.uToward.value.copy(toward);
    const sp = systemProgress();
    material.uniforms.uMorph.value = phaseProgress(sp, SYSTEM_PHASES.morph);
    material.uniforms.uSettle.value = phaseProgress(sp, SYSTEM_PHASES.settle);
    if (stage.state === 'system') stage.destTime += delta * stage.timeScale;
    material.uniforms.uDestTime.value = stage.destTime;
    const tree = treeStore.get();
    material.uniforms.uHoverNode.value = tree.hovered ? GRAPH.nodes.findIndex((n) => n.id === tree.hovered) : -1;
    material.uniforms.uSelectedNode.value = tree.selected ? GRAPH.nodes.findIndex((n) => n.id === tree.selected) : -1;

    if (stage.state === 'home') stage.idleTime += delta * stage.timeScale;
    material.uniforms.uTime.value = stage.idleTime / IDLE.breathPeriod;
    material.uniforms.uBreath.value = reducedMotion
      ? REDUCED_MOTION.breathAmplitude
      : IDLE.breathAmplitude;
    material.uniforms.uPointerStrength.value = reducedMotion
      ? REDUCED_MOTION.pointerStrength
      : IDLE.pointerStrength;

    // Pointer response is two separate things: *where* the disturbance is, and
    // *how strong* it is. Keeping them apart is what lets the cloud relax back
    // smoothly when the cursor leaves, without the position having to travel
    // anywhere. An earlier version lerped the position toward a far-away
    // "no pointer" sentinel, which never converged and killed the effect.
    //
    // Deliberately on raw delta, not `timeScale`: freezing the idle clock for a
    // reproducible screenshot must still leave pointer response working, or the
    // disturbance cannot be isolated from the breathing drift.
    const rate = Math.min(1, (delta * 3) / IDLE.pointerRecovery);
    const target = pointer.current;
    if (target) {
      // snap on first acquisition; ease afterwards so a fast mouse cannot jolt it
      if (acquired.current) smoothed.current.lerp(target, rate);
      else {
        smoothed.current.copy(target);
        acquired.current = true;
      }
    }
    material.uniforms.uPointer.value.copy(smoothed.current);

    const influence = material.uniforms.uPointerInfluence;
    influence.value += ((target ? 1 : 0) - influence.value) * rate;
    // Finish the relaxation: below this the push is ~5e-5 world units (invisible),
    // and snapping to exactly 0 lets a returned home frame match the original
    // pixel for pixel (V12) instead of approaching it forever.
    if (!target && influence.value < 1e-3) influence.value = 0;

    stage.pointerInfluence = influence.value;
    stage.pointerSmoothed = acquired.current
      ? [smoothed.current.x, smoothed.current.y, smoothed.current.z]
      : null;

    // Point size in device pixels: `aSize` becomes a stable on-screen diameter
    // that still shrinks with depth (the shader divides by view depth).
    material.uniforms.uSizeScale.value = devicePixelsPerUnitDepth(size.height, dpr) * POINT_SIZE;
  });

  if (viewMode !== 'full') {
    return <mesh geometry={source} material={viewMode === 'silhouette' ? silhouetteMaterial : solidMaterial} />;
  }
  return <points geometry={geometry} material={material} frustumCulled={false} />;
}
