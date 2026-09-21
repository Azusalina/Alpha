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
import { useMemo, useRef, type RefObject } from 'react';
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

import { stage } from '../app/stage';
import { PALETTE } from '../config/composition';
import { QUALITY, SCENE_SEED, type QualityTier } from '../config/quality';
import { IDLE, REDUCED_MOTION, STARTUP, phaseProgress } from '../config/timing';
import { useHandGeometry } from '../hand/assets';
import { handRig } from '../hand/pose';
import { dissipationDirection, sampleParticleHand, scatterOrigin } from '../hand/sampling';
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


export function ParticleHand({ tier, pointer, reducedMotion }: Props) {
  const viewport = useThree((s) => s.viewport);
  const camera = useThree((s) => s.camera);
  const dpr = useThree((s) => s.viewport.dpr);

  const source = useHandGeometry('right');
  const rig = handRig('right');
  const viewMode = useViewMode();

  const geometry = useMemo(() => {
    const cloud = sampleParticleHand(source, rig, QUALITY[tier].particleCount, SCENE_SEED);
    const toward = dissipationDirection(rig);

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
    g.computeBoundingSphere();
    return g;
  }, [source, rig, tier]);

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
          uColor: { value: new Color(PALETTE.ink) },
        },
        vertexShader: /* glsl */ `
          attribute vec3 aScatter;
          attribute float aSize;
          attribute float aTone;
          attribute float aId;
          attribute float aDissolve;
          attribute float aRim;

          uniform float uGather;
          uniform float uTime;
          uniform float uBreath;
          uniform vec3 uPointer;
          uniform float uPointerInfluence;
          uniform float uPointerRadius;
          uniform float uPointerStrength;
          uniform float uSizeScale;

          varying float vAlpha;

          // Hashed per-particle constants: recomputed from the id, never stored,
          // so a reverse transition can reproduce them exactly.
          float hash(float n) { return fract(sin(n * 127.1) * 43758.5453); }

          void main() {
            float h1 = hash(aId);
            float h2 = hash(aId + 19.7);
            float h3 = hash(aId + 51.3);

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

            vec4 mv = modelViewMatrix * vec4(pos, 1.0);
            gl_Position = projectionMatrix * mv;
            gl_PointSize = aSize * uSizeScale / max(0.25, -mv.z);

            // Larger points are lighter (aTone), the tail reads lighter still, and
            // everything fades up as it gathers.
            vAlpha = aTone * (1.0 - 0.45 * aDissolve) * clamp(g * 1.6, 0.0, 1.0);
          }
        `,
        fragmentShader: /* glsl */ `
          uniform vec3 uColor;
          varying float vAlpha;

          void main() {
            vec2 c = gl_PointCoord - 0.5;
            float r = dot(c, c);
            if (r > 0.25) discard;

            // Soft-edged dot: small points stay crisp, large ones read as deposits.
            float edge = 1.0 - smoothstep(0.16, 0.25, r);
            float a = vAlpha * edge;
            if (a <= 0.004) discard;
            gl_FragColor = vec4(uColor, a);
          }
        `,
      }),
    [],
  );

  const smoothed = useRef(new Vector3());
  /** False until the pointer is first seen, so acquisition snaps instead of lerping. */
  const acquired = useRef(false);

  useFrame((_, delta) => {
    const p = stage.state === 'intro' ? stage.progress : stage.state === 'loading' ? 0 : 1;
    material.uniforms.uGather.value = phaseProgress(p, STARTUP.phases.particleGather);

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

    stage.pointerInfluence = influence.value;
    stage.pointerSmoothed = acquired.current
      ? [smoothed.current.x, smoothed.current.y, smoothed.current.z]
      : null;

    // Point size in device pixels. `viewport.factor` is CSS pixels per world
    // unit on the z = 0 plane; scaling by DPR and the camera distance turns
    // `aSize` into a stable on-screen diameter that still shrinks with depth.
    const perWorldUnit = viewport.factor * dpr;
    material.uniforms.uSizeScale.value = perWorldUnit * camera.position.z * POINT_SIZE;
  });

  if (viewMode !== 'full') {
    return <mesh geometry={source} material={viewMode === 'silhouette' ? silhouetteMaterial : solidMaterial} />;
  }
  return <points geometry={geometry} material={material} frustumCulled={false} />;
}
