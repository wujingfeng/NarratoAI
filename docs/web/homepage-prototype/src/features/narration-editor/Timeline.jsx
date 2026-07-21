import { DndContext, PointerSensor, useDraggable, useSensor, useSensors } from "@dnd-kit/core";
import { useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../../i18n/useI18n.js";
import { selectedIdsForRect, formatTime } from "./timeline-geometry.js";
import { WaveformTrack } from "./WaveformTrack.jsx";

const TRACKS = [{ id: "video", icon: "▣" }, { id: "script", icon: "▤" }, { id: "voice", icon: "♬" }, { id: "bgm", icon: "♪" }];
const RULER_STEPS = [1, 2, 5, 10, 15, 30, 60, 120];

function Clip({ clip, pps, selected, onSelect, onTrim, trimStartLabel, trimEndLabel }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: clip.id });
  const style = { left: clip.start * pps, width: Math.max(48, clip.duration * pps), transform: transform ? `translate3d(${transform.x}px,0,0)` : undefined };
  return <div ref={setNodeRef} data-clip-id={clip.id} className={`timeline-clip timeline-clip--${clip.trackId} ${selected ? "is-selected" : ""} ${isDragging ? "is-dragging" : ""}`} style={style} onClick={(event) => { event.stopPropagation(); onSelect(clip.id, event.shiftKey); }} {...attributes} {...listeners}><button aria-label={trimStartLabel} className="clip-handle clip-handle--start" type="button" onPointerDown={(event) => event.stopPropagation()} onClick={(event) => { event.stopPropagation(); onTrim(clip, "start"); }} /><span>{clip.trackId === "voice" || clip.trackId === "bgm" ? <i className="clip-wave">▁▃▅▇▅▂▆▃▇▅▂▅▇▃</i> : clip.text || clip.id.replace(/-.*/, "")}</span><button aria-label={trimEndLabel} className="clip-handle clip-handle--end" type="button" onPointerDown={(event) => event.stopPropagation()} onClick={(event) => { event.stopPropagation(); onTrim(clip, "end"); }} /></div>;
}

export function Timeline({ state, dispatch }) {
  const { t } = useI18n();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));
  const laneRef = useRef(null); const zoomOutRef = useRef(null); const zoomRef = useRef(null); const [box, setBox] = useState(null); const [anchor, setAnchor] = useState(null);
  const timelineDuration = Math.max(...state.clips.map((clip) => clip.start + clip.duration));
  const timelineWidth = Math.max(920, timelineDuration * state.pixelsPerSecond + 125);
  // Keep labelled ticks roughly 72px apart across all zoom levels.
  const tickStep = useMemo(() => RULER_STEPS.find((step) => step * state.rulerZoom >= 72) ?? 120, [state.rulerZoom]);
  const tickCount = useMemo(() => Math.ceil(timelineDuration / tickStep), [timelineDuration, tickStep]);
  useEffect(() => {
    const minus = zoomOutRef.current;
    if (minus) minus.disabled = state.rulerZoom <= state.minimumZoom;
    const slider = zoomRef.current;
    if (slider) {
      slider.min = String(state.minimumZoom);
      slider.value = String(state.rulerZoom);
    }
  }, [state.minimumZoom, state.rulerZoom]);
  const seekFromEvent = (event) => { const origin = event.currentTarget.getBoundingClientRect().left; dispatch({ type: "seek", seconds: Math.max(0, (event.clientX - origin) / state.pixelsPerSecond) }); };
  const endSelection = (event) => { if (!anchor || !laneRef.current) return; const rect = laneRef.current.getBoundingClientRect(); const finalBox = { left: Math.min(anchor.x, event.clientX - rect.left), right: Math.max(anchor.x, event.clientX - rect.left), top: Math.min(anchor.y, event.clientY - rect.top), bottom: Math.max(anchor.y, event.clientY - rect.top) }; const boxes = [...laneRef.current.querySelectorAll("[data-clip-id]")].map((node) => { const item = node.getBoundingClientRect(); return { id: node.dataset.clipId, left: item.left - rect.left, right: item.right - rect.left, top: item.top - rect.top, bottom: item.bottom - rect.top }; }); dispatch({ type: "select", ids: selectedIdsForRect(finalBox, boxes), append: event.shiftKey }); setAnchor(null); setBox(null); };
  return <section className="timeline" aria-label={t("editor.timeline.ariaLabel")}><header className="timeline-head"><span>{t("editor.timeline.noOverlap")}</span><div><button ref={zoomOutRef} type="button" aria-label={t("editor.timeline.zoomOut")} onClick={() => dispatch({ type: "setZoom", value: state.pixelsPerSecond - 8 })}>−</button><input ref={zoomRef} aria-label={t("editor.timeline.zoom")} type="range" min="22" max="100" value={state.pixelsPerSecond} onChange={(event) => dispatch({ type: "setZoom", value: Number(event.target.value) })} /><button type="button" aria-label={t("editor.timeline.zoomIn")} onClick={() => dispatch({ type: "setZoom", value: state.pixelsPerSecond + 8 })}>＋</button></div></header><div className="timeline-scroll"><div className="timeline-inner" ref={laneRef} style={{ width: timelineWidth }} onPointerDown={(event) => { if (event.target !== laneRef.current) return; const rect = laneRef.current.getBoundingClientRect(); setAnchor({ x: event.clientX - rect.left - 125, y: event.clientY - rect.top }); setBox({ left: event.clientX - rect.left, top: event.clientY - rect.top, width: 0, height: 0 }); }} onPointerMove={(event) => { if (!anchor) return; const rect = laneRef.current.getBoundingClientRect(); setBox({ left: Math.min(anchor.x + 125, event.clientX - rect.left), top: Math.min(anchor.y, event.clientY - rect.top), width: Math.abs(anchor.x + 125 - (event.clientX - rect.left)), height: Math.abs(anchor.y - (event.clientY - rect.top)) }); }} onPointerUp={endSelection}><div className="timeline-ruler" onClick={seekFromEvent}>{Array.from({ length: tickCount + 1 }, (_, index) => { const seconds = index * tickStep; return <span style={{ left: seconds * state.pixelsPerSecond }} key={seconds}>{formatTime(seconds)}</span>; })}</div><DndContext sensors={sensors} onDragEnd={({ active, delta }) => { const clip = state.clips.find((item) => item.id === active.id); if (clip) dispatch({ type: "moveClip", id: clip.id, start: clip.start + delta.x / state.pixelsPerSecond }); }}><div className="timeline-lanes">{TRACKS.map((track) => <div className="timeline-row" data-testid={`track-${track.id}`} key={track.id}><label><b>{track.icon}</b>{t(`editor.timeline.tracks.${track.id}`)}</label><div className="timeline-lane">{track.id === "voice" || track.id === "bgm" ? <WaveformTrack variant="timeline" kind={track.id} clips={state.clips.filter((clip) => clip.trackId === track.id)} state={state} dispatch={dispatch} /> : state.clips.filter((clip) => clip.trackId === track.id).map((clip) => <Clip key={clip.id} clip={clip} pps={state.pixelsPerSecond} selected={state.activeClipIds.includes(clip.id)} onSelect={(id, append) => dispatch({ type: "select", ids: [id], append })} onTrim={(clip, edge) => dispatch({ type: "trimClip", id: clip.id, edge, seconds: edge === "start" ? clip.start + .5 : clip.start + clip.duration - .5 })} trimStartLabel={t("editor.timeline.trimStart")} trimEndLabel={t("editor.timeline.trimEnd")} />)}</div></div>)}</div></DndContext><div data-testid="playhead" className="timeline-playhead" style={{ left: 250 + state.playhead * state.pixelsPerSecond }} onPointerDown={seekFromEvent} />{box && <div className="timeline-selection" style={box} />}</div></div></section>;
}
