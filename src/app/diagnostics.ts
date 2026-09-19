/**
 * Real-machine frame diagnostics (spec 9 and 12 "开发检查能力"; review D).
 *
 * The question this answers is "what does the target machine actually do?" —
 * Arch / KDE Plasma Wayland / Intel Xe, in Tauri's WebKitGTK and in a system
 * browser. It reports the renderer the page really got, the pixel budget it is
 * really drawing, and frame intervals measured in that same page. The numbers
 * are only ever valid for the renderer named in the result: a software
 * rasteriser (SwiftShader, llvmpipe) says nothing about the Intel Xe target.
 *
 * What is measured, precisely:
 *   - frame intervals are deltas between successive requestAnimationFrame
 *     timestamps, i.e. how often the page gets to present a frame. They are
 *     not GPU times; a GPU-bound frame shows up as a longer interval.
 *   - firstFrameAfterLoad_ms is navigation start (performance.timeOrigin) to
 *     the end of the first frame in which three.js rendered the scene. three
 *     compiles and links each material's program on the first draw that needs
 *     it, so this is a proxy for first shader compile plus scene construction.
 *
 * Gate: enabled only in `vite` dev or when built with VITE_ALPHA_DIAGNOSTICS=1.
 * The gate is written with import.meta.env so a normal production build folds
 * it to `false` and drops this module, the panel and the window hook entirely.
 */

import { _roots, addAfterEffect } from '@react-three/fiber';
import type { WebGLRenderer, Scene } from 'three';

import type { QualitySettings } from '../config/quality';

export const DIAGNOSTICS_ENABLED: boolean =
  import.meta.env.DEV || import.meta.env.VITE_ALPHA_DIAGNOSTICS === '1';

export interface FrameDiagnostics {
  /** ISO time the measurement finished. */
  measuredAt: string;
  /** Vite mode the bundle was built in ('development' or 'production'). */
  buildMode: string;
  /** Unmasked via WEBGL_debug_renderer_info when the browser exposes it. */
  renderer: string;
  vendor: string;
  /**
   * False when the strings above are not the real GPU: either the debug
   * extension is missing, or the browser is WebKit, which returns a fixed
   * "Apple GPU" even through the extension.
   */
  rendererUnmasked: boolean;
  webglVersion: string;
  /** Whether the context actually got multisampling. */
  antialias: boolean | null;
  userAgent: string;
  isTauri: boolean;
  /** Tauri runtime version, when the shell answers (null in a browser). */
  tauriVersion: string | null;
  /** Window inner size in CSS px. */
  viewport: { width: number; height: number };
  /** The canvas' CSS size (should equal the viewport). */
  canvasCss: { width: number; height: number };
  /** Screen size in CSS px; under KDE scaling this is the logical size. */
  screen: { width: number; height: number };
  devicePixelRatio: number;
  /** Pixels actually rendered per frame. */
  drawingBuffer: { width: number; height: number };
  /** Points actually in the scene graph (falls back to the configured count). */
  particleCount: number | null;
  /** Particle count the quality tier asks for. */
  configuredParticleCount: number | null;
  qualityTier: string | null;
  /** Upper bound the tier puts on the renderer's pixel ratio. */
  maxPixelRatio: number | null;
  /** Scene state name during the measurement (e.g. 'home'). */
  sceneState: string | null;
  /** three.js statistics for the last rendered frame. */
  render: {
    calls: number;
    triangles: number;
    points: number;
    lines: number;
    programs: number;
    geometries: number;
    textures: number;
  } | null;
  /** Number of frame intervals in the percentiles below. */
  frames: number;
  mean_ms: number;
  p50_ms: number;
  p95_ms: number;
  max_ms: number;
  /** 1000 / p50. */
  implied_fps: number;
  /** Intervals longer than twice p50: a missed presentation at any refresh rate. */
  longFrames: number;
  /** navigation start → end of the first frame three.js rendered (see header). */
  firstFrameAfterLoad_ms: number | null;
  /** Longest frame interval in the first 5 s after that first frame. */
  startupWorstFrame_ms: number | null;
  /** True if sampling stopped early (window hidden / minimised mid-run). */
  interrupted: boolean;
  /** Page visibility when sampling ended. */
  visibility: DocumentVisibilityState;
}

/** Filled in by installDevInspector: what only the app shell knows. */
interface DiagnosticsContext {
  quality?: QualitySettings;
  sceneState?: () => string;
}

let context: DiagnosticsContext = {};

export function configureDiagnostics(next: DiagnosticsContext): void {
  context = { ...context, ...next };
}

// ---------------------------------------------------------------------------
// First rendered frame. Registered at module evaluation — before React mounts
// the Canvas — so the very first frame cannot be missed.

const STARTUP_WINDOW_MS = 5000;
let firstFrameAt: number | null = null;
let startupWorst: number | null = null;

function firstRoot(): { gl: WebGLRenderer; scene: Scene } | null {
  for (const root of _roots.values()) {
    const s = root.store.getState();
    if (s.gl) return { gl: s.gl, scene: s.scene };
  }
  return null;
}

if (DIAGNOSTICS_ENABLED) {
  let last = 0;
  const off = addAfterEffect(() => {
    const now = performance.now();
    if (firstFrameAt === null) {
      // the loop can tick before the root is configured; wait for a real draw
      const root = firstRoot();
      if (!root || root.gl.info.render.frame === 0) return;
      firstFrameAt = now;
      last = now;
      return;
    }
    const dt = now - last;
    last = now;
    if (document.visibilityState === 'visible') {
      startupWorst = Math.max(startupWorst ?? 0, dt);
    }
    if (now - firstFrameAt > STARTUP_WINDOW_MS) off();
  });
}

// ---------------------------------------------------------------------------

const round = (v: number) => Math.round(v * 100) / 100;

function percentile(sorted: number[], q: number): number {
  // nearest-rank
  if (sorted.length === 0) return NaN;
  const i = Math.min(sorted.length - 1, Math.max(0, Math.ceil(q * sorted.length) - 1));
  return sorted[i];
}

function glInfo(gl: WebGL2RenderingContext | WebGLRenderingContext | null) {
  if (!gl) {
    return {
      renderer: 'unavailable',
      vendor: 'unavailable',
      rendererUnmasked: false,
      webglVersion: 'unavailable',
      antialias: null,
    };
  }
  const dbg = gl.getExtension('WEBGL_debug_renderer_info');
  const renderer = String(gl.getParameter(dbg ? dbg.UNMASKED_RENDERER_WEBGL : gl.RENDERER));
  return {
    renderer,
    vendor: String(gl.getParameter(dbg ? dbg.UNMASKED_VENDOR_WEBGL : gl.VENDOR)),
    // WebKit (Safari and WebKitGTK, so Tauri on Linux) answers the "unmasked"
    // query with a fixed "Apple GPU" / "Apple Inc." on every platform: seen
    // in Tauri 2.11 on WebKitGTK 2.52. The real renderer then has to come
    // from webkit://gpu — see docs/DESKTOP_CHECK.md.
    rendererUnmasked: Boolean(dbg) && renderer !== 'Apple GPU',
    webglVersion: String(gl.getParameter(gl.VERSION)),
    antialias: gl.getContextAttributes()?.antialias ?? null,
  };
}

function countPoints(scene: Scene): number {
  let n = 0;
  scene.traverse((o) => {
    const p = o as unknown as {
      isPoints?: boolean;
      visible: boolean;
      geometry?: { drawRange: { count: number }; attributes: { position?: { count: number } } };
    };
    if (!p.isPoints || !p.visible || !p.geometry) return;
    const total = p.geometry.attributes.position?.count ?? 0;
    n += Math.min(total, p.geometry.drawRange.count);
  });
  return n;
}

function isTauri(): boolean {
  const w = window as unknown as { isTauri?: boolean; __TAURI_INTERNALS__?: unknown };
  return w.isTauri === true || w.__TAURI_INTERNALS__ !== undefined;
}

/** Ask the shell for its version without depending on @tauri-apps/api. */
async function tauriVersion(): Promise<string | null> {
  const internals = (window as unknown as {
    __TAURI_INTERNALS__?: { invoke?: (cmd: string) => Promise<unknown> };
  }).__TAURI_INTERNALS__;
  if (!internals?.invoke) return null;
  try {
    const v = await Promise.race([
      internals.invoke('plugin:app|tauri_version'),
      new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 1000)),
    ]);
    return typeof v === 'string' ? v : null;
  } catch {
    return null;
  }
}

/**
 * Collect `sampleCount` frame intervals from requestAnimationFrame. The first
 * interval after the call is discarded (it contains whatever triggered the
 * measurement, e.g. the panel's own React commit). Sampling stops early —
 * `interrupted: true` — if frames stop arriving, which is what a minimised or
 * hidden window does.
 */
function sampleIntervals(sampleCount: number): Promise<{ intervals: number[]; interrupted: boolean }> {
  return new Promise((resolve) => {
    const intervals: number[] = [];
    let prev: number | null = null;
    let skipped = false;
    let done = false;
    let watchdog = 0;

    const finish = (interrupted: boolean) => {
      if (done) return;
      done = true;
      window.clearTimeout(watchdog);
      resolve({ intervals, interrupted });
    };
    const arm = () => {
      window.clearTimeout(watchdog);
      watchdog = window.setTimeout(() => finish(true), 2000);
    };

    const tick = (t: number) => {
      if (done) return;
      arm();
      if (prev !== null) {
        if (skipped) intervals.push(t - prev);
        else skipped = true;
      }
      prev = t;
      if (intervals.length >= sampleCount) finish(false);
      else requestAnimationFrame(tick);
    };
    arm();
    requestAnimationFrame(tick);
  });
}

export async function measureFrames(sampleCount = 240): Promise<FrameDiagnostics> {
  const n = Math.max(10, Math.floor(Number(sampleCount) || 240));
  const { intervals, interrupted } = await sampleIntervals(n);

  const root = firstRoot();
  const canvas =
    (root?.gl.domElement as HTMLCanvasElement | undefined) ??
    document.querySelector<HTMLCanvasElement>('canvas');
  const gl = root
    ? root.gl.getContext()
    : (canvas?.getContext('webgl2') ?? canvas?.getContext('webgl') ?? null);

  const sorted = [...intervals].sort((a, b) => a - b);
  const p50 = percentile(sorted, 0.5);
  const mean = intervals.reduce((a, b) => a + b, 0) / Math.max(1, intervals.length);
  const q = context.quality;
  const scenePoints = root ? countPoints(root.scene) : null;
  const info = root?.gl.info;

  return {
    measuredAt: new Date().toISOString(),
    buildMode: import.meta.env.MODE,
    ...glInfo(gl),
    userAgent: navigator.userAgent,
    isTauri: isTauri(),
    tauriVersion: await tauriVersion(),
    viewport: { width: window.innerWidth, height: window.innerHeight },
    canvasCss: { width: canvas?.clientWidth ?? 0, height: canvas?.clientHeight ?? 0 },
    screen: { width: window.screen.width, height: window.screen.height },
    devicePixelRatio: window.devicePixelRatio,
    drawingBuffer: { width: gl?.drawingBufferWidth ?? 0, height: gl?.drawingBufferHeight ?? 0 },
    particleCount: scenePoints ?? q?.particleCount ?? null,
    configuredParticleCount: q?.particleCount ?? null,
    qualityTier: q?.tier ?? null,
    maxPixelRatio: q?.maxPixelRatio ?? null,
    sceneState: context.sceneState?.() ?? null,
    render: info
      ? {
          calls: info.render.calls,
          triangles: info.render.triangles,
          points: info.render.points,
          lines: info.render.lines,
          programs: info.programs?.length ?? 0,
          geometries: info.memory.geometries,
          textures: info.memory.textures,
        }
      : null,
    frames: intervals.length,
    mean_ms: round(mean),
    p50_ms: round(p50),
    p95_ms: round(percentile(sorted, 0.95)),
    max_ms: round(sorted[sorted.length - 1] ?? NaN),
    implied_fps: round(1000 / p50),
    longFrames: intervals.filter((d) => d > 2 * p50).length,
    firstFrameAfterLoad_ms: firstFrameAt === null ? null : round(firstFrameAt),
    startupWorstFrame_ms: startupWorst === null ? null : round(startupWorst),
    interrupted,
    visibility: document.visibilityState,
  };
}
