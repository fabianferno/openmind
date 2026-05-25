"use client";

import dynamic from "next/dynamic";
import type { ParticlesHologramProps } from "./types";

// WebGPU renderer + GLTF sampling must never run on the server.
const ParticlesHologram = dynamic(() => import("./ParticlesHologram"), {
  ssr: false,
});

export default function HologramScene(props: ParticlesHologramProps) {
  return <ParticlesHologram {...props} />;
}
