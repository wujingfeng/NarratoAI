import { useEffect, useRef, useState } from "react";
import { ArrowsOut, Pause, Play, SpeakerHigh, X } from "@phosphor-icons/react";

export function VideoModal({ caseItem, onClose, returnFocusRef }) {
  const [playing, setPlaying] = useState(false);
  const closeButtonRef = useRef(null);

  useEffect(() => {
    if (!caseItem) return undefined;
    setPlaying(false);
    requestAnimationFrame(() => closeButtonRef.current?.focus());
    const handleKey = (event) => {
      if (event.key === "Escape") onClose();
      if (event.key === "Tab") {
        const panel = closeButtonRef.current?.closest(".video-modal__panel");
        const focusable = panel ? [...panel.querySelectorAll("button:not([disabled])")] : [];
        const first = focusable[0];
        const last = focusable.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.body.classList.add("modal-locked");
    window.addEventListener("keydown", handleKey);
    return () => {
      document.body.classList.remove("modal-locked");
      window.removeEventListener("keydown", handleKey);
      requestAnimationFrame(() => returnFocusRef?.current?.focus?.());
    };
  }, [caseItem, onClose, returnFocusRef]);

  if (!caseItem) return null;

  return (
    <div className="video-modal" role="dialog" aria-modal="true" aria-labelledby="video-modal-title">
      <button className="video-modal__backdrop" type="button" aria-label="关闭案例播放" onClick={onClose} />
      <div className="video-modal__panel">
        <div className="video-modal__header">
          <span><small>{caseItem.toolName}</small><h2 id="video-modal-title">{caseItem.title}</h2></span>
          <button ref={closeButtonRef} type="button" aria-label="关闭案例" onClick={onClose}><X size={24} /></button>
        </div>
        <div className={`video-modal__stage ${playing ? "is-playing" : ""}`}>
          <img src={caseItem.image} alt={`${caseItem.title}视频案例`} loading="eager" decoding="async" />
          <button className="video-modal__center-play" type="button" aria-label={playing ? "暂停" : "播放"} onClick={() => setPlaying(!playing)}>
            {playing ? <Pause size={30} weight="fill" /> : <Play size={30} weight="fill" />}
          </button>
          <div className="video-modal__controls">
            <button type="button" aria-label={playing ? "暂停" : "播放"} onClick={() => setPlaying(!playing)}>{playing ? <Pause size={18} weight="fill" /> : <Play size={18} weight="fill" />}</button>
            <span>{playing ? caseItem.playingElapsed : "00:00"} / {caseItem.duration}</span>
            <div className="video-modal__progress"><span style={{ width: playing ? `${caseItem.progress}%` : "4%" }} /></div>
            <SpeakerHigh size={19} />
            <ArrowsOut size={19} />
          </div>
        </div>
        <div className="video-modal__meta">{caseItem.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
      </div>
    </div>
  );
}
