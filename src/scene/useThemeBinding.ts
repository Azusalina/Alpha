/**
 * Re-apply the current palette to materials when the theme changes (D38–D40).
 *
 * Point and line shaders carry `uAlpha` (opacity multiplier) and `uGlow` (0 =
 * crisp ink dot, 1 = soft glowing dot); in the dark theme they blend
 * additively, so overlapping particles build up light instead of ink. With the
 * light palette every value is the one the shaders had before theming, so the
 * light frame is unchanged bit for bit.
 */

import { useEffect } from 'react';
import { AdditiveBlending, NormalBlending, type Material, type ShaderMaterial } from 'three';

import { usePalette, type Palette } from '../config/theme';

export function useThemeBinding(bind: (p: Palette) => void, materials: Material[]): void {
  const palette = usePalette();
  useEffect(() => {
    bind(palette);
    for (const m of materials) m.needsUpdate = true;
    // `bind` closes over stable memoised materials
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [palette, ...materials]);
}

/**
 * The common part for ink shaders: blending, alpha and glow. `glowScale`
 * adjusts one material's brightness in the glowing (dark) theme only; the
 * light theme always gets exactly 1.
 */
export function applyInk(m: ShaderMaterial, p: Palette, glowScale = 1): void {
  m.blending = p.glow ? AdditiveBlending : NormalBlending;
  if (m.uniforms.uAlpha) m.uniforms.uAlpha.value = p.glow ? p.inkAlpha * glowScale : 1;
  if (m.uniforms.uGlow) m.uniforms.uGlow.value = p.glow ? 1 : 0;
}
