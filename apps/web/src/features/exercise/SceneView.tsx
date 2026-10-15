/**
 * 3D presentation of the trainee's track picture (React Three Fiber).
 *
 * Presentation only: no simulation state lives here. Everything drawn is derived
 * from trainee-visible events, so this view cannot reveal ground truth.
 */
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import type { Environment } from "@/lib/types";

import type { Track } from "./trackPicture";
import { AREA_RADIUS_M, colorFor, SCALE, SEA, SKY, TERRAIN_GROUND } from "./visual";

interface Props {
  tracks: Track[];
  environment: Environment;
  visibilityKm: number | null;
  selected: Set<string>;
  onSelect: (id: string, additive: boolean) => void;
}

function Controls() {
  const { camera, gl } = useThree();
  const ref = useRef<OrbitControls | null>(null);
  useEffect(() => {
    const c = new OrbitControls(camera, gl.domElement);
    c.enableDamping = true;
    c.maxPolarAngle = Math.PI * 0.47;
    c.minDistance = 60;
    c.maxDistance = 900;
    ref.current = c;
    return () => c.dispose();
  }, [camera, gl]);
  useFrame(() => ref.current?.update());
  return null;
}

function RangeRings({ dark }: { dark: boolean }) {
  const rings = useMemo(() => [1000, 2000, 3000, 4000].map((r) => r * SCALE), []);
  return (
    <group rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.2, 0]}>
      {rings.map((r) => (
        <mesh key={r}>
          <ringGeometry args={[r - 0.6, r + 0.6, 128]} />
          <meshBasicMaterial color={dark ? "#56636B" : "#7C817D"} transparent opacity={0.55} />
        </mesh>
      ))}
    </group>
  );
}

function Ground({ terrain, dark, dusk }: { terrain: string; dark: boolean; dusk: boolean }) {
  const color = new THREE.Color(TERRAIN_GROUND[terrain] ?? "#DDDAD2");
  if (dark) color.multiplyScalar(0.28);
  else if (dusk) color.multiplyScalar(0.9);
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[AREA_RADIUS_M * SCALE * 1.15, 96]} />
        <meshBasicMaterial color={color} />
      </mesh>
      {terrain === "coastal" ? (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[AREA_RADIUS_M * SCALE * 0.6, 0.05, 0]}>
          <planeGeometry args={[AREA_RADIUS_M * SCALE * 1.1, AREA_RADIUS_M * SCALE * 2.3]} />
          <meshBasicMaterial color={dark ? SEA.night : SEA.day} />
        </mesh>
      ) : null}
      {/* Protected virtual site */}
      <mesh position={[0, 4, 0]}>
        <boxGeometry args={[14, 8, 14]} />
        <meshBasicMaterial color={dark ? "#C9D3CD" : "#1F4D3A"} />
      </mesh>
    </group>
  );
}

/** Text label rendered to a canvas texture (no external font or network assets). */
function Label({
  text,
  color,
  position,
  dark,
}: {
  text: string;
  color: string;
  position: [number, number, number];
  dark: boolean;
}) {
  const sprite = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 64;
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.font = "500 34px Inter, system-ui, sans-serif";
      ctx.fillStyle = dark ? "rgba(32,38,42,0.85)" : "rgba(255,255,255,0.88)";
      const w = Math.min(250, ctx.measureText(text).width + 24);
      ctx.fillRect(0, 8, w, 48);
      ctx.fillStyle = color;
      ctx.fillRect(0, 8, 5, 48);
      ctx.fillStyle = dark ? "#E7ECE9" : "#1B1F1D";
      ctx.textBaseline = "middle";
      ctx.fillText(text, 14, 33);
    }
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true }));
    s.scale.set(104, 26, 1);
    s.center.set(0, 0.5);
    return s;
  }, [text, color, dark]);
  useEffect(
    () => () => {
      sprite.material.map?.dispose();
      sprite.material.dispose();
    },
    [sprite],
  );
  return <primitive object={sprite} position={position} renderOrder={10} />;
}

function TrackMarker({
  track,
  selected,
  onSelect,
  dark,
}: {
  track: Track;
  selected: boolean;
  onSelect: Props["onSelect"];
  dark: boolean;
}) {
  const pos = track.position;
  const color = colorFor(track.classification?.value);
  const line = useMemo(() => {
    const pts = track.trail.map(
      (p) => new THREE.Vector3(p.x * SCALE, Math.max(1, (p.alt ?? 50) * SCALE), -p.y * SCALE),
    );
    if (pts.length < 2) return null;
    const geom = new THREE.BufferGeometry().setFromPoints(pts);
    return new THREE.Line(
      geom,
      new THREE.LineBasicMaterial({ color, transparent: true, opacity: track.lost ? 0.3 : 0.75 }),
    );
  }, [track.trail, color, track.lost]);
  useEffect(
    () => () => {
      line?.geometry.dispose();
      (line?.material as THREE.Material | undefined)?.dispose();
    },
    [line],
  );
  if (!pos) return null;
  const x = pos.x * SCALE;
  const z = -pos.y * SCALE;
  const y = Math.max(2, (pos.alt ?? 50) * SCALE);
  const handle = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    onSelect(track.id, e.shiftKey || e.ctrlKey || e.metaKey);
  };
  return (
    <group>
      {line ? <primitive object={line} /> : null}
      <mesh position={[x, y, z]} onClick={handle}>
        <sphereGeometry args={[8, 20, 14]} />
        <meshBasicMaterial color={color} transparent opacity={track.lost ? 0.4 : 1} />
      </mesh>
      {selected ? (
        <mesh position={[x, 0.6, z]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[13, 16, 40]} />
          <meshBasicMaterial color={dark ? "#FFFFFF" : "#1B1F1D"} />
        </mesh>
      ) : null}
      {/* Altitude stalk helps judge height in the oblique view */}
      <mesh position={[x, y / 2, z]}>
        <cylinderGeometry args={[0.5, 0.5, y, 6]} />
        <meshBasicMaterial color={color} transparent opacity={0.45} />
      </mesh>
      <Label text={track.id} color={color} position={[x + 13, y + 10, z]} dark={dark} />
    </group>
  );
}

export function SceneView({ tracks, environment, visibilityKm, selected, onSelect }: Props) {
  const sky = SKY[environment.time_of_day] ?? SKY.day!;
  const dark = environment.time_of_day === "night";
  const vis = (visibilityKm ?? environment.visibility_km) * 1000 * SCALE;
  return (
    <Canvas
      camera={{ position: [0, 300, 360], fov: 45, near: 1, far: 5000 }}
      dpr={[1, 2]}
      aria-label="Three-dimensional view of synthetic tracks around the protected virtual site"
      role="img"
    >
      <color attach="background" args={[sky.background]} />
      {/* Mild atmospheric haze only: reduced visibility degrades the simulated sensors,
          not the trainee's own display of the reported tracks. */}
      <fog attach="fog" args={[sky.background, 700, 700 + Math.min(Math.max(vis * 6, 600), 3000)]} />
      <ambientLight intensity={sky.ambient} />
      <directionalLight position={[300, 500, 200]} intensity={sky.sun} color={sky.sunColor} />
      <Ground terrain={environment.terrain} dark={dark} dusk={environment.time_of_day === "dusk"} />
      <RangeRings dark={dark} />
      {tracks.map((t) => (
        <TrackMarker key={t.id} track={t} selected={selected.has(t.id)} onSelect={onSelect} dark={dark} />
      ))}
      <Controls />
    </Canvas>
  );
}
