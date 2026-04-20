/**
 * Dev viewport orbit / zoom preferences (live Avatar preview workstation).
 * Consumed by `AvatarViewportLive`; persisted in `useAvatarSceneStore`.
 */

export type AvatarViewportNavSettings = {
  invertOrbitX: boolean;
  invertOrbitY: boolean;
  /** Multiplier on drag→yaw / pitch deltas (0.5–2). */
  orbitSensitivity: number;
  /** Multiplier on pinch→radius (0.6–1.6). Higher = zoom changes faster. */
  zoomSensitivity: number;
  /**
   * Exponential smoothing per second-ish scale (frame-rate compensated in camera).
   * ~0.1 = heavy damping, ~0.32 = light.
   */
  damping: number;
  minRadius: number;
  maxRadius: number;
  /** Added to default orbit target Y (meters in scene space). */
  targetYOffset: number;
  /** Two-finger drag moves orbit target in XZ (experimental). */
  enablePan: boolean;
  /** Polar angle clamp (radians from +Y), min. */
  polarMin: number;
  /** Polar angle clamp (radians from +Y), max. */
  polarMax: number;
  /** Extra multiplier on yaw only. */
  yawSpeedMultiplier: number;
  /** Reserved; keep false for avatar viewer (no Dutch angle). */
  enableRoll: boolean;
  /** Radians of pitch change per pixel of vertical drag. */
  orbitPitchRadPerPx: number;
  /** Radians of yaw change per pixel of horizontal drag. */
  orbitYawRadPerPx: number;
};

export const DEFAULT_AVATAR_VIEWPORT_NAV: AvatarViewportNavSettings = {
  invertOrbitX: false,
  invertOrbitY: false,
  orbitSensitivity: 0.62,
  zoomSensitivity: 0.82,
  /** Lower = snappier orbit response (still smoothed when gesture idle). */
  damping: 0.095,
  minRadius: 1.28,
  maxRadius: 7.2,
  targetYOffset: 0,
  enablePan: false,
  polarMin: 0.22,
  polarMax: 1.42,
  yawSpeedMultiplier: 0.78,
  enableRoll: false,
  orbitPitchRadPerPx: 0.0028,
  orbitYawRadPerPx: 0.003,
};

export function mergeAvatarViewportNav(
  partial?: Partial<AvatarViewportNavSettings> | null,
): AvatarViewportNavSettings {
  const m = { ...DEFAULT_AVATAR_VIEWPORT_NAV, ...partial };
  const minR = Number.isFinite(m.minRadius) ? m.minRadius : DEFAULT_AVATAR_VIEWPORT_NAV.minRadius;
  const maxR = Number.isFinite(m.maxRadius) ? m.maxRadius : DEFAULT_AVATAR_VIEWPORT_NAV.maxRadius;
  const polarMin = Number.isFinite(m.polarMin) ? m.polarMin : DEFAULT_AVATAR_VIEWPORT_NAV.polarMin;
  const polarMax = Number.isFinite(m.polarMax) ? m.polarMax : DEFAULT_AVATAR_VIEWPORT_NAV.polarMax;
  const saneMin = Math.min(6, Math.max(0.85, minR));
  const saneMax = Math.max(saneMin + 0.05, Math.min(14, Math.max(1.6, maxR)));
  const sanePolarMin = Math.min(1.2, Math.max(0.04, polarMin));
  const sanePolarMax = Math.max(sanePolarMin + 0.02, Math.min(1.58, polarMax));
  return {
    ...m,
    orbitSensitivity: Math.min(2.5, Math.max(0.35, m.orbitSensitivity || 1)),
    zoomSensitivity: Math.min(2.2, Math.max(0.4, m.zoomSensitivity || 1)),
    damping: Math.min(0.65, Math.max(0.05, m.damping || DEFAULT_AVATAR_VIEWPORT_NAV.damping)),
    targetYOffset: Math.min(0.6, Math.max(-0.6, m.targetYOffset || 0)),
    yawSpeedMultiplier: Math.min(2.4, Math.max(0.35, m.yawSpeedMultiplier || 1)),
    orbitPitchRadPerPx: Math.min(0.02, Math.max(0.001, m.orbitPitchRadPerPx || 0.0062)),
    orbitYawRadPerPx: Math.min(0.02, Math.max(0.001, m.orbitYawRadPerPx || 0.0065)),
    minRadius: saneMin,
    maxRadius: saneMax,
    polarMin: sanePolarMin,
    polarMax: sanePolarMax,
    enablePan: !!m.enablePan,
    enableRoll: !!m.enableRoll,
    invertOrbitX: !!m.invertOrbitX,
    invertOrbitY: !!m.invertOrbitY,
  };
}
