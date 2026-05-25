"use client";

import HologramScene from "./HologramScene";

/**
 * BD-1 hologram preset, ported from fabianferno/hologram-particles.
 * The values below are the playground's Leva defaults merged with its "dark"
 * preset (preset wins) — i.e. exactly the cyan/blue look on the ink-black stage.
 * Fills its parent: give the wrapping element an explicit width and height.
 */
export default function Bd1Hologram({
  particleCount = 60_000,
}: {
  /** Lower this on weaker GPUs (e.g. 30_000) to trade fidelity for frame rate. */
  particleCount?: number;
}) {
  return (
    <HologramScene
      url="/glb/bd1.glb"
      particleCount={particleCount}
      autoRotateSpeed={2.53}
      // ── Material (neutral pale figure, lit lime) ──
      color="#dfe7d3"
      ambient={0.1}
      wrap={0.31}
      volumeStrength={0.98}
      sphereSize={0.014}
      floatAmp={0.01}
      // ── Position ──
      modelX={0}
      modelY={-1.2}
      modelZ={0}
      // ── Lights (electric-lime key + deep olive fill) ──
      light1X={0}
      light1Y={5}
      light1Z={2}
      light1Color="#c6f24a"
      light1Intensity={1.9}
      light2X={0}
      light2Y={-5}
      light2Z={-2}
      light2Color="#3f5a1c"
      light2Intensity={1.1}
      // ── Wave ──
      noiseAmp={0.72}
      noiseScale={3.0}
      noiseSpeed={1}
      noiseGain={0.65}
      maskScale={0.95}
      maskSpeed={0.5}
      maskContrast={3.8}
      // ── Interaction ──
      mouseRadius={2.15}
      mouseStrength={4.9}
      pushStrength={2.5}
      springStiffness={40}
      springDamping={20}
      mouseScatter={1}
      mouseGlowColor="#d8ff5e"
      mouseGlowPassive={3}
      mouseGlowActive={6}
      mouseGlowDecay={0.3}
      mouseGlowPow={6.0}
      mouseLerp={1.5}
      // ── Post-processing ──
      bloomStrength={0.65}
      bloomRadius={0.65}
      bloomThreshold={0.34}
      chromaticStr={0.05}
      // ── Transition / entrance ──
      transitionDeformDur={0.4}
      transitionMorphDur={2.05}
      transitionReformDur={0.45}
      transitionMaskContrast={1.65}
      transitionGlowScale={1.0}
      entranceMorphDur={1.8}
      entranceReformDur={1.1}
      // ── Cylinder ──
      cylVisible
      cylColor="#c6f24a"
      cylRadius={1.95}
      cylHeight={5.3}
      cylNoiseScale={0.2}
      cylLineWidth={0.22}
      cylFresnelPow={1.6}
      cylBaseOpacity={0.0}
      cylLineOpacity={1}
      cylNoiseSpeed={0.15}
      cylPulseSpeed={2.5}
      cylPulseAmp={0.68}
      cylPulseEasing={2.5}
      cylWaveFreq={2.0}
      cylTexRepeat={8.5}
      cylY={-0.85}
      // ── Dot grid: off — the full-plane field is what reads as a square frame ──
      gridVisible={false}
      gridColor="#5c7a2e"
      gridBaseOpacity={0.06}
      gridWaveAmp={0.73}
      gridNoiseScale={0.44}
      gridWaveSpeed={0.62}
      gridDensity={2.15}
      gridDotSize={0.04}
      // ── Halo ring (lime) ──
      ringVisible
      ringColor="#c6f24a"
      ringRadius={1.95}
      ringThickness={0.035}
      ringGap={20}
      ringOpacity={0.5}
      ringBrightness={4.8}
      // ── Camera parallax ──
      camIntensity={1}
      camStiffness={3.0}
      camDamping={4.0}
      // ── Background: transparent so the ink page shows through (no frame) ──
      bgTransparent
    />
  );
}
