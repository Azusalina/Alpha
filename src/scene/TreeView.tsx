/**
 * The technology tree's lines and interaction at the system destination
 * (spec 3 前往右下, 7.3; round 3 part 2).
 *
 * The nodes themselves are the right hand's particles (ParticleHand, via
 * tree/mapping.ts); this component draws what the particles cannot: the tree
 * edges, drawn out along their length from the root once the layout has
 * mostly formed (p ≈ 0.62 → 0.95), cross-links last and lighter, and a thin
 * construction circle round each node — the scaffolding of the structure,
 * in the same ink as the human hand's construction drawing.
 *
 * Hover names a node; click opens its detail (treeStore). Nothing here
 * exists for the pointer outside the system state.
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useMemo, useRef } from 'react';
import { BufferGeometry, Color, Float32BufferAttribute, NormalBlending, ShaderMaterial, Vector2, Vector3 } from 'three';

import { DIAGNOSTICS_ENABLED } from '../app/diagnostics';
import { stage, systemProgress } from '../app/stage';
import { treeStore } from '../app/treeStore';
import { PALETTE } from '../config/composition';
import { SYSTEM_PHASES, phaseProgress } from '../config/timing';
import { GRAPH } from '../fixtures/graph';
import { treeLayout } from '../tree/layoutCache';

const RING_SEGMENTS = 40;
/** Minimum pick radius in CSS pixels. */
const PICK_PX = 16;

export function TreeView() {
  const camera = useThree((s) => s.camera);
  const size = useThree((s) => s.size);
  const domElement = useThree((s) => s.gl.domElement);
  const layout = treeLayout();

  const geometry = useMemo(() => {
    const pos: number[] = [];
    const order: number[] = [];
    const kind: number[] = [];
    const depth = new Map(GRAPH.nodes.map((n) => [n.id, n.depth]));
    const a = new Vector3();
    const b = new Vector3();
    const d = new Vector3();
    const SEG = 10;

    for (const e of GRAPH.edges) {
      a.fromArray(layout.pos.get(e.from)!);
      b.fromArray(layout.pos.get(e.to)!);
      d.subVectors(b, a).normalize();
      // start and end on the node circles, not inside the clusters
      const ra = layout.radius.get(e.from)! * 1.35;
      const rb = layout.radius.get(e.to)! * 1.35;
      const p0 = a.clone().addScaledVector(d, ra);
      const p1 = b.clone().addScaledVector(d, -rb);
      const link = e.kind === 'link';
      const d0 = depth.get(e.from) ?? 0;
      for (let s = 0; s < SEG; s++) {
        const t0 = s / SEG;
        const t1 = (s + 1) / SEG;
        // cross-links are dashed: every other segment
        if (link && s % 2 === 1) continue;
        const q0 = p0.clone().lerp(p1, t0);
        const q1 = p0.clone().lerp(p1, t1);
        if (link) {
          // bow the links away from the tree so they read as associations
          const bow = (t: number) => Math.sin(Math.PI * t) * 0.12;
          q0.y += bow(t0);
          q1.y += bow(t1);
        }
        pos.push(q0.x, q0.y, q0.z, q1.x, q1.y, q1.z);
        const o0 = link ? 3 + t0 : d0 + t0;
        const o1 = link ? 3 + t1 : d0 + t1;
        order.push(o0, o1);
        kind.push(link ? 1 : 0, link ? 1 : 0);
      }
    }

    // construction circles, appearing as the edge reaches each node
    GRAPH.nodes.forEach((n) => {
      const c = layout.pos.get(n.id)!;
      const r = layout.radius.get(n.id)! * 1.35;
      for (let s = 0; s < RING_SEGMENTS; s++) {
        const t0 = (s / RING_SEGMENTS) * Math.PI * 2;
        const t1 = ((s + 1) / RING_SEGMENTS) * Math.PI * 2;
        pos.push(c[0] + Math.cos(t0) * r, c[1] + Math.sin(t0) * r, c[2]);
        pos.push(c[0] + Math.cos(t1) * r, c[1] + Math.sin(t1) * r, c[2]);
        const o = n.depth + 0.02 + (s / RING_SEGMENTS) * 0.25;
        order.push(o, o);
        kind.push(2, 2);
      }
    });

    const g = new BufferGeometry();
    g.setAttribute('position', new Float32BufferAttribute(pos, 3));
    g.setAttribute('aOrder', new Float32BufferAttribute(order, 1));
    g.setAttribute('aKind', new Float32BufferAttribute(kind, 1));
    return g;
  }, [layout]);

  const material = useMemo(
    () =>
      new ShaderMaterial({
        transparent: true,
        depthWrite: false,
        depthTest: false,
        blending: NormalBlending,
        uniforms: {
          uGrow: { value: 0 },
          uColor: { value: new Color(PALETTE.construction) },
          uInk: { value: new Color(PALETTE.inkSoft) },
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
          uniform vec3 uInk;
          varying float vOrder;
          varying float vKind;
          void main() {
            float drawn = step(vOrder, uGrow);
            // the freshly drawn head is darker, like the construction drawing
            float head = 1.0 - smoothstep(0.0, 0.3, uGrow - vOrder);
            float weight = vKind < 0.5 ? 0.8 : (vKind < 1.5 ? 0.4 : 0.5);
            float a = drawn * weight * (0.85 + 0.5 * head);
            if (a <= 0.003) discard;
            gl_FragColor = vec4(mix(uColor, uInk, vKind < 0.5 ? 0.6 : 0.0), min(1.0, a));
          }
        `,
      }),
    [],
  );

  // ---- pointer ----------------------------------------------------------------
  const pointer = useRef<Vector2 | null>(null);
  const down = useRef<{ x: number; y: number } | null>(null);
  const proj = useMemo(() => new Vector3(), []);

  /** The node under a CSS-pixel point, or null. */
  const pick = (ndc: Vector2): string | null => {
    let best: string | null = null;
    let bestD = Infinity;
    for (const n of GRAPH.nodes) {
      const c = layout.pos.get(n.id)!;
      proj.set(c[0], c[1], c[2]).project(camera);
      const dx = ((proj.x - ndc.x) / 2) * size.width;
      const dy = ((proj.y - ndc.y) / 2) * size.height;
      const d = Math.hypot(dx, dy);
      // the node's own on-screen radius, at least PICK_PX
      const rPx = Math.max(PICK_PX, (layout.radius.get(n.id)! * 1.35 * size.height) / 2);
      if (d < rPx && d < bestD) {
        bestD = d;
        best = n.id;
      }
    }
    return best;
  };

  useEffect(() => {
    const toNdc = (ev: PointerEvent) => {
      const r = domElement.getBoundingClientRect();
      return new Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    };
    const onMove = (ev: PointerEvent) => {
      pointer.current = toNdc(ev);
    };
    const onLeave = () => {
      pointer.current = null;
    };
    const onDown = (ev: PointerEvent) => {
      down.current = { x: ev.clientX, y: ev.clientY };
    };
    const onUp = (ev: PointerEvent) => {
      const d = down.current;
      down.current = null;
      if (stage.state !== 'system' || !d || Math.hypot(ev.clientX - d.x, ev.clientY - d.y) > 4) return;
      if (ev.target !== domElement) return;
      treeStore.set({ selected: pick(toNdc(ev)) });
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
    // pick reads the camera and layout, which are stable for the component's life
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [domElement, camera, size]);

  const linesRef = useRef<import('three').LineSegments>(null);

  useFrame(() => {
    const sp = systemProgress();
    material.uniforms.uGrow.value = phaseProgress(sp, SYSTEM_PHASES.edges) * 4.2;
    if (linesRef.current) linesRef.current.visible = sp > 0;

    const hovered = stage.state === 'system' && pointer.current ? pick(pointer.current) : null;
    treeStore.set({ hovered });
    if (stage.state === 'system') domElement.style.cursor = hovered ? 'pointer' : '';
  });

  useEffect(() => {
    if (!DIAGNOSTICS_ENABLED) return;
    const w = window as unknown as { __alpha?: Record<string, unknown> };
    if (w.__alpha) {
      w.__alpha.tree = {
        /** CSS-pixel position of a node at the system destination. */
        screenOf(id: string) {
          const c = layout.pos.get(id);
          if (!c) return null;
          const p = new Vector3(...c).project(camera);
          return [((p.x + 1) / 2) * size.width, ((1 - p.y) / 2) * size.height];
        },
      };
    }
  }, [layout, camera, size]);

  return <lineSegments ref={linesRef} geometry={geometry} material={material} renderOrder={15} frustumCulled={false} visible={false} />;
}
