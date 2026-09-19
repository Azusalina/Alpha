/**
 * Graphics budget for the target machine: Arch Linux / KDE Wayland, Intel Xe
 * integrated graphics (spec 9). Particle counts start conservative and are
 * verified against real frame timings rather than assumed from the hardware.
 */

export type QualityTier = 'low' | 'medium';

export interface QualitySettings {
  tier: QualityTier;
  /** Visible particles in the right hand, including the dissipation tail. */
  particleCount: number;
  /** Upper bound on device pixel ratio, so KDE scaling cannot blow up the buffer. */
  maxPixelRatio: number;
  /** Multisampling on the default framebuffer. */
  antialias: boolean;
}

export const QUALITY: Record<QualityTier, QualitySettings> = {
  low: { tier: 'low', particleCount: 6000, maxPixelRatio: 1, antialias: false },
  medium: { tier: 'medium', particleCount: 12000, maxPixelRatio: 1.5, antialias: true },
};

/** Spec 9 starting budget. Changing tier must not change the composition. */
export const DEFAULT_TIER: QualityTier = 'medium';

/**
 * Optional ambience: the auxiliary hand scattering into border particles at a
 * destination. The user marked this "暂定，假设没有效果", so it is off by default
 * and is explicitly not part of v1.0.0 (spec 3).
 */
export const ambientBorderParticles = false;

/** Deterministic seed for every sampled distribution in the scene. */
export const SCENE_SEED = 20260919;
