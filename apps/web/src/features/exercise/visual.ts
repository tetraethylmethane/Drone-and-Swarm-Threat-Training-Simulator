/** Shared visual encoding for the 3D and plan views. Colour follows the trainee's own classification. */
export const CLASS_COLORS: Record<string, string> = {
  unclassified: "#7C817D",
  unknown: "#5B605C",
  small_multirotor: "#B4562B",
  fixed_wing_uas: "#2D4F73",
  coordinated_swarm: "#7A2E5C",
  bird_or_clutter: "#5D7A3A",
};

export function colorFor(classification: string | null | undefined): string {
  return CLASS_COLORS[classification ?? "unclassified"] ?? CLASS_COLORS.unclassified!;
}

/** Flat (unlit) terrain tones for the tactical 3D view. */
export const TERRAIN_GROUND: Record<string, string> = {
  rural: "#DCE2D3",
  urban: "#DEDCD6",
  coastal: "#E2DDCB",
  industrial: "#DDD9CF",
};
export const SEA = { day: "#C9D6DC", night: "#22313A" };

export const SKY: Record<string, { background: string; ambient: number; sun: number; sunColor: string }> = {
  day: { background: "#EEF0EE", ambient: 0.75, sun: 0.9, sunColor: "#FFFFFF" },
  dusk: { background: "#E2DDD3", ambient: 0.5, sun: 0.55, sunColor: "#F2D2A9" },
  night: { background: "#20262A", ambient: 0.28, sun: 0.15, sunColor: "#9FB0C8" },
};

/** Area radius used by the simulation core (metres). */
export const AREA_RADIUS_M = 4000;
/** World units per metre in the 3D view. */
export const SCALE = 0.1;
