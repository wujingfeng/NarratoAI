import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.esm.js";
import { useEffect, useRef } from "react";
import { useI18n } from "../../i18n/useI18n.js";
import { EDITOR_MEDIA } from "./editor-data.js";

export function WaveformTrack({ kind, clips, state, dispatch, variant = "inspector" }) {
  const { t } = useI18n();
  const containerRef = useRef(null);
  // `select` only changes editor UI state. Do not tear down and rebuild the
  // decoding/rendering instance for a selection-only render.
  const regionSignature = clips.map((clip) => `${clip.id}:${clip.start}:${clip.duration}:${clip.sourceStart ?? ""}`).join("|");
  useEffect(() => {
    const regions = RegionsPlugin.create();
    const wave = WaveSurfer.create({ container: containerRef.current, url: EDITOR_MEDIA.audio, height: 34, normalize: true, waveColor: kind === "voice" ? "#42d7e4" : "#ff991d", progressColor: kind === "voice" ? "#a16aff" : "#ffca64", cursorColor: "#fafcff", cursorWidth: 1, barWidth: 2, barGap: 1, plugins: [regions] });
    const register = () => clips.forEach((clip) => { const region = regions.addRegion({ id: clip.id, start: clip.sourceStart ?? clip.start, end: (clip.sourceStart ?? clip.start) + clip.duration, color: kind === "voice" ? "rgba(43, 203, 220, .13)" : "rgba(255, 143, 27, .12)", drag: true, resize: true }); region.element.dataset.regionId = clip.id; });
    wave.on("ready", register); wave.on("interaction", (seconds) => dispatch({ type: "seek", seconds })); wave.on("region-updated", (region) => dispatch({ type: "moveClip", id: region.id, start: region.start }));
    return () => wave.destroy();
  }, [kind, regionSignature, dispatch]);
  return <div className={`waveform-track waveform-track--${variant}`}><span>{variant === "inspector" ? (kind === "voice" ? t("editor.waveform.voicePreview") : t("editor.waveform.bgmWaveform")) : null}</span><div data-testid={`waveform-${kind}`} ref={containerRef} /></div>;
}
