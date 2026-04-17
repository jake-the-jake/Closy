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
  orbitSensitivity: 1,
  zoomSensitivity: 1,
  damping: 0.2,
  minRadius: 1.45,
  maxRadius: 8,
  targetYOffset: 0,
  enablePan: false,
  polarMin: 0.12,
  polarMax: 1.52,
  yawSpeedMultiplier: 1,
  enableRoll: false,
  orbitPitchRadPerPx: 0.0062,
  orbitYawRadPerPx: 0.0065,
};

export function mergeAvatarViewportNav(
  partial?: Partial<AvatarViewportNavSettings> | null,
): AvatarViewportNavSettings {
  return { ...DEFAULT_AVATAR_VIEWPORT_NAV, ...partial };
}
