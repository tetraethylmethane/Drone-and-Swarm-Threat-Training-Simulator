/** Two-dimensional plan view (SVG). Accessible alternative and fallback when WebGL is unavailable. */
import type { Track } from "./trackPicture";
import { AREA_RADIUS_M, colorFor } from "./visual";

interface Props {
  tracks: Track[];
  selected: Set<string>;
  onSelect: (id: string, additive: boolean) => void;
  dark?: boolean;
}

const R = AREA_RADIUS_M;

export function PlanView({ tracks, selected, onSelect, dark = false }: Props) {
  const ring = dark ? "#56636B" : "#C6C2B8";
  const text = dark ? "#C9D3CD" : "#5B605C";
  return (
    <svg
      viewBox={`${-R * 1.05} ${-R * 1.05} ${R * 2.1} ${R * 2.1}`}
      className="h-full w-full"
      role="img"
      aria-label="Plan view of synthetic tracks. North is up; rings every 1 km."
      style={{ background: dark ? "#20262A" : "#F1F0EB" }}
    >
      {[1000, 2000, 3000, 4000].map((r) => (
        <g key={r}>
          <circle r={r} fill="none" stroke={ring} strokeWidth={10} />
          <text x={30} y={-r + 250} fontSize={220} fill={text}>
            {r / 1000} km
          </text>
        </g>
      ))}
      <line x1={0} y1={-R} x2={0} y2={R} stroke={ring} strokeWidth={6} strokeDasharray="40 60" />
      <line x1={-R} y1={0} x2={R} y2={0} stroke={ring} strokeWidth={6} strokeDasharray="40 60" />
      <text x={-R + 40} y={-R + 200} fontSize={220} fill={text}>
        North up
      </text>
      <rect x={-60} y={-60} width={120} height={120} fill={dark ? "#C9D3CD" : "#1F4D3A"} />
      {tracks.map((t) => {
        if (!t.position) return null;
        const color = colorFor(t.classification?.value);
        const x = t.position.x;
        const y = -t.position.y;
        const isSel = selected.has(t.id);
        const trail = t.trail.map((p) => `${p.x},${-p.y}`).join(" ");
        return (
          <g key={t.id} opacity={t.lost ? 0.4 : 1}>
            {t.trail.length > 1 ? (
              <polyline points={trail} fill="none" stroke={color} strokeWidth={22} opacity={0.5} />
            ) : null}
            <circle
              cx={x}
              cy={y}
              r={isSel ? 120 : 85}
              fill={color}
              stroke={isSel ? (dark ? "#FFFFFF" : "#1B1F1D") : "none"}
              strokeWidth={18}
              onClick={(e) => onSelect(t.id, e.shiftKey || e.ctrlKey || e.metaKey)}
              style={{ cursor: "pointer" }}
            >
              <title>{t.id}</title>
            </circle>
            <text x={x + 130} y={y + 80} fontSize={240} fill={text}>
              {t.id.replace("TRK-", "")}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
