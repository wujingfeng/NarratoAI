import { ArrowsOutSimple, CaretLeft, CaretRight, CheckCircle, Crosshair, FileText, Sparkle, Star, UserCircle } from "@phosphor-icons/react";
import { useI18n } from "../../i18n/useI18n.js";

const icons = { caption: FileText, book: Sparkle, target: Crosshair, star: Star, script: FileText };
const ORBIT_CIRCUMFERENCE = 911;
const particleAngles = [4, 31, 58, 86, 113, 142, 169, 197, 226, 255, 283, 312, 341];

function formatProgress(progress) {
  return progress === 0 || progress === 100 ? String(progress) : progress.toFixed(2);
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  const whole = Math.round(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const remainder = whole % 60;
  return hours > 0
    ? `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

export function NarrationAnalysisBoard({
  videos,
  stages,
  insights = {},
  logs,
  progress,
  isInProgress,
  isHolding,
  selectedIndex,
  onSelect,
  onOpen,
  onScroll,
  railRef,
}) {
  const { formatNumber, t } = useI18n();
  const progressLabel = formatProgress(progress);
  const hasVideos = videos.length > 0;
  const totalDuration = videos.every((video) => Number.isFinite(video.durationSeconds))
    ? formatDuration(videos.reduce((total, video) => total + video.durationSeconds, 0))
    : "—";
  const metric = (value) => Number.isFinite(value) ? formatNumber(value) : "—";

  return <div className="analysis-layout">
    <section className="analysis-card analysis-card--main" aria-labelledby="analysis-title">
      <h2 id="analysis-title">{t("analysis.title")}</h2>
      <div className="analysis-workflow">
        {stages.map((stage) => {
          const Icon = icons[stage.icon] || FileText;
          return <div className={`analysis-stage is-${stage.state}`} key={stage.id}>
            <span className="analysis-stage__icon"><Icon /></span>
            <div><strong>{t(stage.titleKey)}</strong><small>{t(stage.statusKey)}</small></div>
            <span className="analysis-stage__state">{stage.state === "done" ? <CheckCircle weight="fill" /> : stage.state === "active" ? <i /> : null}</span>
          </div>;
        })}
      </div>
      <div className={`analysis-orbit${isInProgress ? " is-processing" : ""}`} aria-label={t("analysis.progress", { progress: progressLabel })}>
        <svg viewBox="0 0 320 320" aria-hidden="true">
          <circle className="analysis-orbit__track" cx="160" cy="160" r="145" />
          <circle className="analysis-orbit__pulse" cx="160" cy="160" r="120" />
          <circle className="analysis-orbit__progress" cx="160" cy="160" r="145" transform="rotate(-90 160 160)" style={{ strokeDasharray: ORBIT_CIRCUMFERENCE, strokeDashoffset: ORBIT_CIRCUMFERENCE - (ORBIT_CIRCUMFERENCE * progress) / 100 }} />
        </svg>
        {isInProgress && <span className="analysis-orbit__particles" aria-hidden="true">{particleAngles.map((angle, index) => <i key={angle} style={{ "--particle-angle": `${angle}deg`, "--particle-distance": `${145 + (index % 4) * 18}px`, "--particle-delay": `${-(index * 0.21)}s` }} />)}</span>}
        <span className="analysis-orbit__halo" aria-hidden="true" />
        <div className="analysis-orbit__gem">✦</div>
        <strong>{progressLabel}%</strong>
      </div>
      <p className="analysis-estimate">{t("analysis.estimate")}</p>
      <div className={`analysis-total ${isHolding ? "is-holding" : ""}`}>
        <span>{t("analysis.overall")}</span><div><i style={{ width: `${progress}%` }} /></div><b>{progressLabel}%</b>{isHolding && <small>· {t("analysis.holding")}</small>}
      </div>
    </section>
    <aside className="analysis-aside">
      <section className="analysis-card analysis-materials">
        <header><h2>{t("analysis.materials.title")}</h2><p>{t("analysis.materials.summary", { count: formatNumber(videos.length) })} <span>{t("analysis.materials.totalDuration")} <strong>{totalDuration}</strong></span></p></header>
        <div className="analysis-video-rail" aria-label={t("analysis.materials.list")}>
          <button type="button" aria-label={t("analysis.materials.scrollLeft")} onClick={() => onScroll(-1)} disabled={!hasVideos}><CaretLeft /></button>
          <div className={`analysis-video-scroll ${hasVideos ? "" : "is-empty"}`} ref={railRef}>
            {hasVideos ? videos.map((video, index) => <button className={`analysis-video ${index === selectedIndex ? "is-selected" : ""}`} key={video.id} type="button" onClick={() => onSelect(index)} aria-pressed={index === selectedIndex}>
              <video className="analysis-thumb" src={video.url} muted playsInline preload="metadata" tabIndex="-1" aria-hidden="true" />
              <b title={video.label}>{video.label}</b><small>{video.duration}</small>
              {index === selectedIndex && <span className="analysis-video__expand" role="button" tabIndex="0" aria-label={t("analysis.materials.fullscreen", { episode: video.label })} onClick={(event) => { event.stopPropagation(); onOpen(); }} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.stopPropagation(); onOpen(); } }}><ArrowsOutSimple weight="bold" /></span>}
            </button>) : <p className="analysis-materials__empty">{t("analysis.materials.empty")}</p>}
          </div>
          <button type="button" aria-label={t("analysis.materials.scrollRight")} onClick={() => onScroll(1)} disabled={!hasVideos}><CaretRight /></button>
        </div>
      </section>
      <section className="analysis-card analysis-discover">
        <h2>{t("analysis.discovered.title")}</h2>
        <div><p><UserCircle /><span>{t("analysis.discovered.characters")}</span><strong>{metric(insights.characters)}</strong></p><p><Sparkle /><span>{t("analysis.discovered.turns")}</span><strong>{metric(insights.turns)}</strong></p><p><Star /><span>{t("analysis.discovered.highlights")}</span><strong>{metric(insights.highlights)}</strong></p></div>
      </section>
      <section className="analysis-card analysis-log">
        <h2>{t("analysis.taskLog")}</h2>
        {logs.map(({ id, time, message, messageKey, state }) => <p className={state === "active" ? "is-active" : ""} key={id || `${time}-${message}`}><time>{time}</time><i /> <span>{message || (messageKey ? t(messageKey) : "")}</span>{state === "done" ? <CheckCircle weight="fill" /> : state === "active" ? <em /> : null}</p>)}
      </section>
    </aside>
  </div>;
}
