/**
 * The left, human hand: a soft plaster-like solid plus the geometric
 * construction drawing that produced it.
 *
 * Startup reads as a drawing being made (spec 2, 启动): the scaffolding and
 * contour are drawn in order along their own arc length, then the sculptural
 * surface resolves out from the wrist toward the fingertips. Both are driven by
 * the one startup progress value, and both are shader uniforms, so no React
 * state changes per frame.
 */

import { useFrame } from '@react-three/fiber';
import { useMemo, useRef } from 'react';
import {
  Color,
  DoubleSide,
  Group,
  MeshStandardMaterial,
  NormalBlending,
  ShaderMaterial,
} from 'three';

import { PALETTE } from '../config/composition';
import { STARTUP, phaseProgress } from '../config/timing';
import { buildConstructionGeometry } from '../hand/constructionLines';
import { buildHandSurface } from '../hand/mesh';
import { buildLeftHandRig } from '../hand/skeleton';
import { stage } from '../app/stage';

/** How far the hand starts outside its final position, in world units. */
const APPROACH_OFFSET: [number, number, number] = [-0.55, 0.42, -0.15];

/** Cubic ease-out; the hands arrive slowing down rather than snapping. */
const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);

export function HumanHand() {
  const rig = useMemo(() => buildLeftHandRig(), []);
  const surface = useMemo(() => buildHandSurface(rig), [rig]);
  const lines = useMemo(() => buildConstructionGeometry(rig), [rig]);

  const groupRef = useRef<Group>(null);

  /**
   * Plaster surface. Standard lighting is kept (the spec wants form read from
   * anatomy and shading) and `onBeforeCompile` only adds the reveal cut, so the
   * material stays a normal lit surface rather than a custom unlit hack.
   */
  const surfaceMaterial = useMemo(() => {
    const m = new MeshStandardMaterial({
      color: new Color(PALETTE.sculptureLight),
      roughness: 0.94,
      metalness: 0,
      flatShading: false,
      side: DoubleSide,
      transparent: true,
      blending: NormalBlending,
    });
    m.userData.uniforms = { uReveal: { value: 0 }, uOpacity: { value: 0 } };
    m.onBeforeCompile = (shader) => {
      shader.uniforms.uReveal = m.userData.uniforms.uReveal;
      shader.uniforms.uOpacity = m.userData.uniforms.uOpacity;
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\nattribute float aReveal;\nvarying float vReveal;')
        .replace('#include <begin_vertex>', '#include <begin_vertex>\nvReveal = aReveal;');
      shader.fragmentShader = shader.fragmentShader
        .replace(
          '#include <common>',
          '#include <common>\nuniform float uReveal;\nuniform float uOpacity;\nvarying float vReveal;',
        )
        .replace(
          '#include <dithering_fragment>',
          [
            '#include <dithering_fragment>',
            // soft leading edge, so the solid grows rather than popping in
            'float edge = smoothstep(uReveal, uReveal - 0.16, vReveal);',
            'if (edge <= 0.001) discard;',
            'gl_FragColor.a *= edge * uOpacity;',
          ].join('\n'),
        );
    };
    return m;
  }, []);

  /** Construction lines: revealed along their own ordered arc length. */
  const lineMaterial = useMemo(
    () =>
      new ShaderMaterial({
        transparent: true,
        depthWrite: false,
        // The construction drawing sits on top of the form, the way it does in
        // the reference. Inside the volume it would simply be occluded.
        depthTest: false,
        blending: NormalBlending,
        uniforms: {
          uDraw: { value: 0 },
          uSettle: { value: 0 },
          uColor: { value: new Color(PALETTE.construction) },
        },
        vertexShader: /* glsl */ `
          attribute float aOrder;
          attribute float aWeight;
          varying float vOrder;
          varying float vWeight;
          void main() {
            vOrder = aOrder;
            vWeight = aWeight;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
          }
        `,
        fragmentShader: /* glsl */ `
          uniform float uDraw;
          uniform float uSettle;
          uniform vec3 uColor;
          varying float vOrder;
          varying float vWeight;
          void main() {
            // nothing beyond the drawing head is visible yet
            float drawn = step(vOrder, uDraw);
            // the freshly drawn head is darker, then eases back to resting weight
            float freshness = 1.0 - smoothstep(0.0, 0.12, uDraw - vOrder);
            float alpha = drawn * vWeight * mix(1.0, 0.78, uSettle) * (0.9 + 0.5 * freshness);
            if (alpha <= 0.002) discard;
            gl_FragColor = vec4(uColor, alpha);
          }
        `,
      }),
    [],
  );

  useFrame(() => {
    const p = stage.state === 'intro' ? stage.progress : stage.state === 'loading' ? 0 : 1;

    const approach = easeOut(phaseProgress(p, STARTUP.phases.approach));
    const draw = phaseProgress(p, STARTUP.phases.constructionDraw);
    const reveal = phaseProgress(p, STARTUP.phases.surfaceReveal);
    const settle = phaseProgress(p, STARTUP.phases.settle);

    if (groupRef.current) {
      groupRef.current.position.set(
        APPROACH_OFFSET[0] * (1 - approach),
        APPROACH_OFFSET[1] * (1 - approach),
        APPROACH_OFFSET[2] * (1 - approach),
      );
    }
    lineMaterial.uniforms.uDraw.value = draw;
    lineMaterial.uniforms.uSettle.value = settle;
    // reveal runs past 1 so the soft edge clears the fingertips entirely
    surfaceMaterial.userData.uniforms.uReveal.value = reveal * 1.18;
    surfaceMaterial.userData.uniforms.uOpacity.value = Math.min(1, reveal * 1.4);
  });

  return (
    <group ref={groupRef}>
      <mesh geometry={surface} material={surfaceMaterial} />
      <lineSegments geometry={lines} material={lineMaterial} renderOrder={10} />
    </group>
  );
}
