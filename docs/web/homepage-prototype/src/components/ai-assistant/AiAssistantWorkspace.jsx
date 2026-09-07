import {
  ArrowClockwise, ArrowsIn, ArrowsOut, CaretDown, CaretRight, CheckCircle, CircleNotch, Copy, DownloadSimple, FileArrowUp,
  FileText, FilmSlate, ImageSquare, PaperPlaneRight, Plus, Sparkle, Trash, WarningCircle,
} from "@phosphor-icons/react";
import { AssistantRuntimeProvider, useExternalStoreRuntime } from "@assistant-ui/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal, flushSync } from "react-dom";
import { getAiVideoAsset, getAiVideoModelGenParam, listAiVideoModels } from "../../services/aiVideoApi.js";
import { createAssistantDraft, createAssistantThread, deleteAssistantThread, getAssistantRun, getAssistantRuns, getAssistantThread, listAssistantChatModels, listAssistantThreads, mergeAssistantMessages, mergeAssistantRunSnapshot, mergeAssistantRunStepSnapshot, normalizeAssistantMessages, normalizeAssistantRuns, normalizeAssistantThreadList, sendAssistantMessage, streamAssistantChatMessage, streamAssistantChatRetry, streamAssistantRun, resumeAssistantChatStream, updateAssistantThreadTitle } from "../../services/assistantApi.js";
import { uploadAsset } from "../../features/uploads/ossPostUpload.js";
import { getSubtitleRegionDetector } from "../../features/subtitle-region/subtitleRegionDetector.js";
import { labelOf, modelDefaults, normalizeModel } from "../../features/ai-video/modelCapabilities.js";
import { CONVERSATION_MODES, TARGET_LANGUAGES, VIDEO_GENERATION_MODES, ASSISTANT_UI as UI, assistantRunAnchorMessageId, assistantRunStatusLabel, assetTypeForFile, isAssistantRunActive, validateAssistantSubmission } from "../../features/ai-assistant/assistantConfig.js";
import { useI18n } from "../../i18n/useI18n.js";

const textOf = (message) => (message?.content || []).filter((part) => part.type === "text").map((part) => part.text).join("\n");
const idOf = (value) => String(value?.id || value?.thread_id || value?.threadId || "");
const runStatus = (run) => String(run?.status || run?.state || "queued").toLowerCase();
const runTitle = (run) => ({ short_drama_narration: UI.narration, video_translation: UI.translation, video_generation: UI.generation }[run.mode] || UI.agentRun);
const optionId = (value) => String(value?.id || value?.value || value || "");
const DEFAULT_AGENT_SOURCE_SUBTITLE_REGION = Object.freeze({ x: 0, y: 0.78, width: 1, height: 0.12 });

async function detectAgentSourceSubtitleLayout(file) {
  try {
    const detected = await getSubtitleRegionDetector().detect(file);
    const region = detected?.region || DEFAULT_AGENT_SOURCE_SUBTITLE_REGION;
    return {
      status: "confirmed",
      region: { ...region },
      ...(Number.isFinite(Number(detected?.confidence)) ? { detected_confidence: Number(detected.confidence) } : {}),
    };
  } catch {
    // Agent 自动模式不能停在人工确认门；检测异常时冻结产品默认底部遮罩。
    return { status: "confirmed", region: { ...DEFAULT_AGENT_SOURCE_SUBTITLE_REGION } };
  }
}

// The assistant API returns product DTOs, not assistant-ui ThreadMessage objects.
// Always convert at the Runtime boundary so assistant-ui can supply the required
// assistant metadata/status fields instead of reading metadata from an API DTO.
function toAssistantUiMessage(message) {
  return {
    id: String(message.id),
    role: message.role === "assistant" ? "assistant" : "user",
    content: Array.isArray(message.content) ? message.content : [{ type: "text", text: String(message.content || "") }],
    createdAt: message.created_at ? new Date(message.created_at) : new Date(),
    metadata: { custom: { mode: message.mode || "chat" } },
    // assistant-ui attachments use a different schema (each entry has content
    // parts). Keep its runtime payload empty and render our API attachment DTOs
    // directly in MessageBubble below.
    ...(message.role === "assistant" ? {} : { attachments: [] }),
  };
}

function initialGeneration() {
  return { generationMode: "text_to_video", modelId: "", ratio: "", duration: "", resolution: "", audio: false, modelParams: {} };
}

function MarkdownContent({ content }) {
  return <div className="assistant-markdown">
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children }) => /^https?:\/\//i.test(href || "") ? <a href={href} target="_blank" rel="noreferrer">{children}</a> : <>{children}</>,
        img: ({ src, alt }) => /^https?:\/\//i.test(src || "") ? <img src={src} alt={alt || ""} loading="lazy" /> : null,
        table: ({ children }) => <div className="assistant-markdown__table-scroll"><table>{children}</table></div>,
      }}
    >
      {String(content || "")}
    </ReactMarkdown>
  </div>;
}

function attachmentPreviewType(attachment, mode) {
  if (attachment.asset_type || attachment.type) return attachment.asset_type || attachment.type;
  if (mode === "short_drama_narration" || mode === "video_translation") return "video";
  if (mode === "chat") return "image";
  const url = String(attachment.url || attachment.cdn_url || "").toLowerCase();
  if (/\.(png|jpe?g|webp)(?:[?#]|$)/.test(url)) return "image";
  if (/\.(mp4|mov|avi|webm)(?:[?#]|$)/.test(url)) return "video";
  if (/\.(mp3|wav|m4a|aac|ogg)(?:[?#]|$)/.test(url)) return "audio";
  return "file";
}

function MessageAttachmentPreview({ attachment, mode, onPreview }) {
  const assetId = typeof attachment.asset_id === "string" ? attachment.asset_id : "";
  const [url, setUrl] = useState(() => attachment.url || attachment.cdn_url || "");
  const type = attachmentPreviewType({ ...attachment, url }, mode);
  useEffect(() => {
    if (url || !assetId) return undefined;
    let active = true;
    getAiVideoAsset(assetId).then((asset) => {
      const nextUrl = asset?.cdn_url || asset?.url || "";
      if (active && nextUrl) setUrl(nextUrl);
    }).catch(() => {});
    return () => { active = false; };
  }, [assetId, url]);
  const href = typeof url === "string" && /^https?:\/\//i.test(url) ? url : "";
  if (!href) return <span className="assistant-message__attachment-preview is-loading" aria-label={UI.loading}><CircleNotch className="is-spinning" /></span>;
  return <button className="assistant-message__attachment-preview" type="button" onClick={() => onPreview({ url: href, type })} aria-label={UI.openAttachment}>
    {type === "image" ? <img src={href} alt="" /> : type === "video" ? <video src={href} muted playsInline preload="metadata" aria-label={UI.videoFile} /> : type === "audio" ? <span><FileArrowUp /></span> : <span><FileArrowUp /></span>}
  </button>;
}

function MessageAttachments({ attachments, mode }) {
  const [preview, setPreview] = useState(null);
  useEffect(() => {
    if (!preview) return undefined;
    const onKeyDown = (event) => { if (event.key === "Escape") setPreview(null); };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [preview]);
  if (!attachments.length) return null;
  return <><div className="assistant-message__attachments" aria-label={UI.messageAttachments}>{attachments.map((attachment, index) => <MessageAttachmentPreview attachment={attachment} mode={mode} key={attachment.asset_id || index} onPreview={setPreview} />)}</div>{preview && <div className="assistant-media-preview" role="dialog" aria-modal="true" aria-label={UI.previewAttachment} onMouseDown={(event) => { if (event.target === event.currentTarget) setPreview(null); }}><div className="assistant-media-preview__content"><button type="button" className="assistant-media-preview__close" onClick={() => setPreview(null)} aria-label={UI.closePreview}>×</button>{preview.type === "image" ? <img src={preview.url} alt="" /> : preview.type === "video" ? <video src={preview.url} controls autoPlay playsInline /> : preview.type === "audio" ? <audio src={preview.url} controls autoPlay /> : <a href={preview.url} download>{UI.downloadAttachment}</a>}</div></div>}</>;
}

function MessageBubble({ message, onCopy, onRegenerate }) {
  const isAssistant = message.role === "assistant";
  const text = textOf(message);
  const attachments = Array.isArray(message.attachments) ? message.attachments : [];
  if (!text && !attachments.length) return null;
  const isCompletedChatReply = isAssistant && message.mode === "chat" && message.stream_status !== "running" && text !== UI.chatReplyPending && text !== UI.chatReplyFailed;
  return <article className={`assistant-message assistant-message--${isAssistant ? "assistant" : "user"}`}>
    <div className="assistant-message__avatar" aria-hidden="true">{isAssistant ? <Sparkle weight="fill" /> : UI.me}</div>
    <div className="assistant-message__body">{text && (isAssistant ? <MarkdownContent content={text} /> : <p>{text}</p>)}<MessageAttachments attachments={attachments} mode={message.mode} />{isCompletedChatReply && <div className="assistant-message__actions"><button type="button" onClick={() => onCopy(text)} aria-label={UI.copy}><Copy /></button><button type="button" onClick={() => onRegenerate(message.id)} aria-label={UI.regenerate}><ArrowClockwise /></button></div>}</div>
  </article>;
}

function projectResultHref(run, projectId) {
  if (!projectId) return null;
  if (run.mode === "short_drama_narration") return `/projects/${encodeURIComponent(projectId)}/result`;
  if (run.mode === "video_translation") return `/dashboard/video-translation/export?projectId=${encodeURIComponent(projectId)}`;
  // 视频生成没有短剧项目结果页；完成后只展示本 Run 的视频结果链接。
  return null;
}

function RunCard({ run, onRefresh }) {
  const status = runStatus(run); const progress = Math.max(0, Math.min(100, Number(run.progress ?? run.progress_percent ?? 0)));
  const videoUrl = run.video_url || run.videoUrl || run.output_url;
  const projectId = run.project_id || run.projectId;
  const resultHref = projectResultHref(run, projectId);
  const errorMessage = run.error_message || run.errorMessage || run.error_code || run.errorCode;
  return <article className={`assistant-run-card is-${status}`}>
    <div className="assistant-run-card__head"><span className="assistant-run-card__icon">{status === "completed" || status === "succeeded" ? <CheckCircle weight="fill" /> : status === "failed" || status === "cancelled" ? <WarningCircle weight="fill" /> : <CircleNotch className="is-spinning" />}</span><div><strong>{runTitle(run)}</strong><small>{assistantRunStatusLabel(run, status)}</small></div><button type="button" onClick={onRefresh} aria-label={UI.refreshRun}><ArrowClockwise /></button></div>
    {status !== "completed" && status !== "succeeded" && status !== "failed" && <div className="assistant-run-card__progress"><i style={{ width: `${progress || 8}%` }} /><span>{progress ? `${progress}%` : UI.processing}</span></div>}
    {run.display_config && <dl className="assistant-run-card__config">{Object.entries(run.display_config).slice(0, 5).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{String(value)}</dd></div>)}</dl>}
    {status === "failed" && errorMessage && <p className="assistant-run-card__error">{String(errorMessage)}</p>}
    {videoUrl && <div className="assistant-run-card__result"><video controls preload="metadata" src={videoUrl} /><a href={videoUrl} target="_blank" rel="noreferrer">{UI.openVideo}</a></div>}
    {resultHref && <a className="assistant-run-card__project" href={resultHref}>{UI.openProject} <CaretRight /></a>}
  </article>;
}

const stepStatus = (step) => String(step?.status || "queued").toLowerCase();

function AgentFileOutput({ output }) {
  const [previewOpen, setPreviewOpen] = useState(false);
  const url = typeof output.url === "string" && /^https?:\/\//i.test(output.url) ? output.url : "";
  const preview = typeof output.preview_text === "string" ? output.preview_text : "";
  return <div className="assistant-agent-file">
    <div className="assistant-agent-file__icon"><FileText weight="duotone" /></div>
    <div className="assistant-agent-file__meta">
      <strong>{output.filename || UI.file}</strong>
      <small>{output.kind === "subtitle" ? UI.subtitleFile : output.content_type || UI.agentResultFile}</small>
    </div>
    <div className="assistant-agent-file__actions">
      {preview && <button type="button" aria-expanded={previewOpen} onClick={() => setPreviewOpen((value) => !value)}>{previewOpen ? UI.closeFilePreview : UI.previewFile}</button>}
      {url && <a href={url} target="_blank" rel="noreferrer" download aria-label={UI.downloadAttachment}><DownloadSimple /></a>}
    </div>
    {previewOpen && <div className="assistant-agent-file__preview"><pre>{preview}</pre>{output.preview_truncated && <small>{UI.previewTruncated}</small>}</div>}
  </div>;
}

function AgentMarkdownOutput({ content, draft = false }) {
  const [open, setOpen] = useState(true);
  return <div className={`assistant-agent-text-output ${draft ? "is-streaming" : ""}`}>
    <button type="button" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
      <span>{draft ? UI.streamingStepResult : open ? UI.collapseStepResult : UI.expandStepResult}</span>
      <CaretDown className={open ? "is-open" : ""} />
    </button>
    {open && <div className="assistant-agent-text-output__content"><MarkdownContent content={content} />{draft && <i aria-hidden="true" />}</div>}
  </div>;
}

function AgentStepMessage({ step, run, onRefresh }) {
  const status = stepStatus(step);
  const active = ["running", "processing", "analyzing", "rendering", "submitting", "submitted"].includes(status);
  const completed = ["completed", "succeeded"].includes(status);
  const failed = ["failed", "cancelled"].includes(status);
  const outputs = Array.isArray(step.outputs) ? step.outputs : [];
  const resultHref = step.id === "video_render" ? projectResultHref(run, run.project_id || run.projectId) : null;
  return <article className={`assistant-message assistant-message--assistant assistant-agent-step is-${status}`}>
    <div className="assistant-message__avatar" aria-hidden="true"><Sparkle weight="fill" /></div>
    <div className="assistant-message__body">
      <div className="assistant-agent-step__head">
        <span className="assistant-agent-step__state" aria-hidden="true">{completed ? <CheckCircle weight="fill" /> : failed ? <WarningCircle weight="fill" /> : <CircleNotch className={active ? "is-spinning" : ""} />}</span>
        <div><strong>{step.title}</strong><small>{completed ? UI.completed : failed ? (status === "cancelled" ? UI.cancelled : UI.failed) : active ? (step.stream_label || UI.agentStepRunning) : UI.queued}</small></div>
        {active && <button type="button" onClick={onRefresh} aria-label={UI.refreshRun}><ArrowClockwise /></button>}
      </div>
      {outputs.map((output, index) => output.type === "markdown"
        ? <AgentMarkdownOutput content={output.content || ""} draft={Boolean(output.draft)} key={`${step.id}-markdown-${index}`} />
        : output.type === "video"
          ? <div className="assistant-agent-video" key={`${step.id}-video-${output.artifact_id || index}`}><video controls playsInline preload="metadata" src={output.url} /><div><a href={output.url} target="_blank" rel="noreferrer">{UI.openVideo}</a>{resultHref && <a href={resultHref}>{UI.openProject} <CaretRight /></a>}</div></div>
          : <AgentFileOutput output={output} key={`${step.id}-file-${output.artifact_id || index}`} />)}
      {failed && (step.error_code || run.error_message || run.errorMessage) && <p className="assistant-agent-step__error">{step.error_code || run.error_message || run.errorMessage}</p>}
      {completed && step.id === "video_render" && !outputs.some((output) => output.type === "video") && resultHref && <a className="assistant-agent-step__project" href={resultHref}>{UI.openProject} <CaretRight /></a>}
    </div>
  </article>;
}

function NarrationRunTimeline({ run, onRefresh }) {
  const steps = Array.isArray(run.steps) ? run.steps : [];
  const queuedStates = new Set(["queued", "pending", "not_started"]);
  const activeStates = new Set(["running", "processing", "analyzing", "rendering", "submitting", "submitted"]);
  const hasActiveStep = steps.some((step) => activeStates.has(stepStatus(step)));
  const nextQueuedStep = !hasActiveStep && isAssistantRunActive(runStatus(run)) ? steps.find((step) => queuedStates.has(stepStatus(step))) : null;
  const visibleSteps = steps.filter((step) => !queuedStates.has(stepStatus(step)) || step === nextQueuedStep);
  const fallback = {
    id: "narration_run",
    title: UI.narration,
    status: runStatus(run),
    outputs: run.video_url ? [{ type: "video", url: run.video_url }] : [],
    error_code: run.error_code,
  };
  const rendered = visibleSteps.length ? visibleSteps : [steps[0] || fallback];
  return <>{rendered.filter(Boolean).map((step) => <AgentStepMessage step={step} run={run} onRefresh={onRefresh} key={`run-${run.id || run.run_id}-step-${step.id}`} />)}</>;
}

function ModeSelector({ mode, onChange }) {
  const [open, setOpen] = useState(false); const ref = useRef(null); const current = CONVERSATION_MODES[mode];
  useEffect(() => { if (!open) return undefined; const close = (event) => { if (!ref.current?.contains(event.target)) setOpen(false); }; document.addEventListener("pointerdown", close); return () => document.removeEventListener("pointerdown", close); }, [open]);
  return <div className="assistant-mode-selector" ref={ref}><button type="button" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen((value) => !value)}>{current.shortLabel}<CaretDown /></button>{open && <div className="assistant-mode-selector__menu" role="listbox" aria-label={UI.selectMode}>{Object.values(CONVERSATION_MODES).map((item) => <button type="button" role="option" aria-selected={item.id === mode} key={item.id} onClick={() => { onChange(item.id); setOpen(false); }}><span>{item.id === mode ? "●" : "○"}</span>{item.label}</button>)}</div>}</div>;
}

function ChatModelSelector({ models, value, loading, onChange }) {
  const [open, setOpen] = useState(false); const ref = useRef(null); const selected = models.find((model) => model.id === value);
  useEffect(() => { if (!open) return undefined; const close = (event) => { if (!ref.current?.contains(event.target)) setOpen(false); }; document.addEventListener("pointerdown", close); return () => document.removeEventListener("pointerdown", close); }, [open]);
  const label = loading ? UI.modelLoading : selected?.display_name || UI.selectChatModel;
  return <div className="assistant-chat-model-selector" ref={ref}><button type="button" aria-haspopup="listbox" aria-expanded={open} disabled={loading || !models.length} onClick={() => setOpen((state) => !state)}>{label}<CaretDown /></button>{open && <div className="assistant-chat-model-selector__menu" role="listbox" aria-label={UI.chatModel}>{models.map((model) => <button type="button" key={model.id} role="option" aria-selected={model.id === value} onClick={() => { onChange(model.id); setOpen(false); }}><span>{model.id === value ? "✓" : ""}</span>{model.display_name}</button>)}</div>}</div>;
}

function TranslationLanguageSelector({ value, onChange }) {
  const [open, setOpen] = useState(false); const ref = useRef(null); const selected = TARGET_LANGUAGES.find((item) => item.id === value);
  useEffect(() => { if (!open) return undefined; const close = (event) => { if (!ref.current?.contains(event.target)) setOpen(false); }; document.addEventListener("pointerdown", close); return () => document.removeEventListener("pointerdown", close); }, [open]);
  return <div className="assistant-translation-selector" ref={ref}><button type="button" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen((state) => !state)}>{selected?.label || UI.translateTo}<CaretDown /></button>{open && <div className="assistant-translation-selector__menu" role="listbox" aria-label={UI.translateTo}>{TARGET_LANGUAGES.map((item) => <button type="button" key={item.id} role="option" aria-selected={item.id === value} onClick={() => { onChange(item.id); setOpen(false); }}><span>{item.id === value ? "✓" : ""}</span>{item.label}</button>)}</div>}</div>;
}

function GenerationDropdown({ label, options, value, disabled, onChange }) {
  const [open, setOpen] = useState(false); const ref = useRef(null); const selected = options.find((item) => item.id === value);
  useEffect(() => { if (!open) return undefined; const close = (event) => { if (!ref.current?.contains(event.target)) setOpen(false); }; document.addEventListener("pointerdown", close); return () => document.removeEventListener("pointerdown", close); }, [open]);
  return <div className="assistant-generation-select" ref={ref}><button type="button" disabled={disabled} aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen((state) => !state)}><span>{selected?.label || label}</span><CaretDown /></button>{open && <div className="assistant-generation-select__menu" role="listbox">{options.map((item) => <button type="button" key={item.id} role="option" aria-selected={item.id === value} onClick={() => { onChange(item.id); setOpen(false); }}><span>{item.id === value ? "✓" : ""}</span>{item.label}</button>)}</div>}</div>;
}

function VideoSettingsSelector({ ratios, resolutions, durations, generation, disabled, onChange }) {
  const [open, setOpen] = useState(false); const ref = useRef(null); const durationNumber = (value) => Number.parseFloat(String(value));
  const selectedDuration = durations.find((item) => item.id === generation.duration); const [durationInput, setDurationInput] = useState(String(durationNumber(selectedDuration?.id) || ""));
  useEffect(() => { if (!open) return undefined; const close = (event) => { if (!ref.current?.contains(event.target)) setOpen(false); }; document.addEventListener("pointerdown", close); return () => document.removeEventListener("pointerdown", close); }, [open]);
  useEffect(() => { setDurationInput(String(durationNumber(selectedDuration?.id) || "")); }, [selectedDuration?.id]);
  const optionLabel = (items, value, fallback) => items.find((item) => item.id === value)?.label || fallback;
  const select = (key, value) => onChange({ ...generation, [key]: value });
  const durationLabel = optionLabel(durations, generation.duration, UI.selectDuration);
  const selectedDurationIndex = Math.max(0, durations.findIndex((item) => item.id === generation.duration));
  const commitDuration = () => { const entry = durations.find((item) => String(durationNumber(item.id)) === durationInput.trim()); if (entry) { select("duration", entry.id); return; } setDurationInput(String(durationNumber(selectedDuration?.id) || "")); };
  return <div className="assistant-video-settings" ref={ref}><button type="button" disabled={disabled} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen((state) => !state)}><span>{optionLabel(ratios, generation.ratio, UI.selectRatio)}</span><span>{optionLabel(resolutions, generation.resolution, UI.selectResolution)}</span><span>{durationLabel}</span><CaretDown /></button>{open && <div className="assistant-video-settings__menu" role="dialog" aria-label="视频生成参数"><div><p>{UI.ratio}</p><section>{ratios.map((item) => <button type="button" className={item.id === generation.ratio ? "is-selected" : ""} key={item.id} onClick={() => select("ratio", item.id)}>{item.label}</button>)}</section></div><div><p>{UI.resolution}</p><section>{resolutions.map((item) => <button type="button" className={item.id === generation.resolution ? "is-selected" : ""} key={item.id} onClick={() => select("resolution", item.id)}>{item.label}</button>)}</section></div><div className="assistant-duration-picker"><p>{UI.duration}</p><div><input type="range" min="0" max={Math.max(0, durations.length - 1)} step="1" value={selectedDurationIndex} onChange={(event) => { const entry = durations[Number(event.target.value)]; if (entry) { setDurationInput(String(durationNumber(entry.id))); select("duration", entry.id); } }} /><label><span className="sr-only">{UI.duration}</span><input type="text" inputMode="numeric" value={durationInput} onChange={(event) => setDurationInput(event.target.value)} onBlur={commitDuration} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); commitDuration(); } }} /><small>{UI.seconds}</small></label></div></div></div>}</div>;
}

function GenerationControls({ generation, models, selectedModel, loading, onChange }) {
  const defaults = selectedModel ? modelDefaults(selectedModel) : null;
  const values = (items) => (items || []).map((item) => ({ id: optionId(item), label: labelOf(item) }));
  const ratios = values(selectedModel?.aspectRatios).map((item) => String(item.label).toLowerCase() === "adaptive" ? { ...item, label: "auto" } : item); const resolutions = values(selectedModel?.resolutions); const durations = values(selectedModel?.duration?.options);
  if (!durations.length && defaults?.duration) durations.push({ id: String(defaults.duration), label: `${defaults.duration} ${UI.seconds}` });
  const set = (key, value) => onChange({ ...generation, [key]: value });
  return <div className="assistant-controls assistant-controls--generation">
    <GenerationDropdown label={UI.generationMode} options={VIDEO_GENERATION_MODES.map((item) => ({ id: item.id, label: item.label }))} value={generation.generationMode} onChange={(value) => set("generationMode", value)} />
    <GenerationDropdown label={loading ? UI.modelLoading : UI.selectModel} options={models.map((model) => ({ id: model.id, label: model.name }))} value={generation.modelId} disabled={loading || !models.length} onChange={(value) => set("modelId", value)} />
    <VideoSettingsSelector ratios={ratios} resolutions={resolutions} durations={durations} generation={generation} disabled={!selectedModel} onChange={onChange} />
    <label className="assistant-audio-switch"><input type="checkbox" checked={generation.audio} disabled={!selectedModel?.audioGeneration} onChange={(event) => set("audio", event.target.checked)} /><span>{UI.autoAudio}</span></label>
  </div>;
}

function ComposerAttachmentPreview({ attachment }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    if (!attachment.file) return undefined;
    const objectUrl = URL.createObjectURL(attachment.file);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [attachment.file]);
  if (!url) return <span className="assistant-attachment__preview is-loading"><CircleNotch className="is-spinning" /></span>;
  if (attachment.kind === "image") return <img className="assistant-attachment__preview" src={url} alt="" />;
  if (attachment.kind === "video") return <video className="assistant-attachment__preview" src={url} muted playsInline preload="metadata" aria-label={UI.videoFile} />;
  return <span className="assistant-attachment__preview"><FileArrowUp /></span>;
}

function AttachmentStrip({ attachments, onRemove }) {
  if (!attachments.length) return null;
  return <div className="assistant-attachments" aria-label={UI.selectedAttachments}>{attachments.map((attachment) => <div className={`assistant-attachment is-${attachment.status}`} key={attachment.localId} aria-label={attachment.filename}><ComposerAttachmentPreview attachment={attachment} />{attachment.status === "uploading" && <span className="assistant-attachment__loading" role="status" aria-label={UI.uploading}><CircleNotch className="is-spinning" /></span>}<button type="button" onClick={() => onRemove(attachment.localId)} aria-label={`${UI.remove} ${attachment.filename}`}><Trash /></button></div>)}</div>;
}

function ConversationThreads({ threadId, threads, onNewThread, onRenameThread, onDeleteThread, onSelectThread, notify }) {
  const [editingId, setEditingId] = useState(""); const [title, setTitle] = useState(""); const [menuId, setMenuId] = useState(""); const [menuPosition, setMenuPosition] = useState(null); const panelRef = useRef(null); const menuRef = useRef(null);
  useEffect(() => { if (!menuId) return undefined; const close = (event) => { if (!menuRef.current?.contains(event.target)) { setMenuId(""); setMenuPosition(null); } }; document.addEventListener("pointerdown", close); return () => document.removeEventListener("pointerdown", close); }, [menuId]);
  const openMenu = (event, id) => {
    event.preventDefault(); const menuWidth = 112; const menuHeight = 82; const left = Math.min(event.clientX, window.innerWidth - menuWidth - 8); const top = window.innerHeight - event.clientY < menuHeight + 8 ? Math.max(8, event.clientY - menuHeight) : event.clientY;
    setMenuId(id); setMenuPosition({ left: Math.max(8, left), top });
  };
  const beginEdit = (thread) => { setMenuId(""); setMenuPosition(null); setEditingId(idOf(thread)); setTitle(thread.title || UI.newThreadTitle); };
  const saveTitle = async () => {
    const next = title.trim();
    if (!next) { notify(UI.threadTitleInvalid); return; }
    try { await onRenameThread(editingId, next); setEditingId(""); } catch (error) { notify(error.message || UI.threadRenameFailed); }
  };
  const removeThread = async (id) => {
    setMenuId(""); setMenuPosition(null);
    if (!window.confirm(UI.deleteThreadConfirm)) return;
    try { await onDeleteThread(id); } catch (error) { notify(error.message || UI.threadDeleteFailed); }
  };
  return <aside className="assistant-thread-panel" ref={panelRef}><div className="assistant-thread-panel__title"><span>{UI.conversations}</span><button type="button" onClick={() => onNewThread()} aria-label={UI.newThread}><Plus /></button></div><div className="assistant-thread-panel__list">{threads.map((thread) => {
    const id = idOf(thread); const editing = id === editingId;
    return <div className={`assistant-thread-item ${id === threadId ? "is-active" : ""}`} key={id} onContextMenu={(event) => openMenu(event, id)}>
      {editing ? <input autoFocus value={title} maxLength={200} aria-label={UI.threadTitlePlaceholder} onChange={(event) => setTitle(event.target.value)} onBlur={() => { void saveTitle(); }} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void saveTitle(); } if (event.key === "Escape") setEditingId(""); }} /> : <button type="button" onClick={() => onSelectThread(id)} onDoubleClick={() => beginEdit(thread)} title={UI.renameThread}><Sparkle /><span>{thread.title || UI.newThreadTitle}</span></button>}
    </div>;
  })}</div>{menuId && menuPosition && createPortal(<div className="assistant-thread-menu assistant-thread-menu--floating" ref={menuRef} role="menu" style={menuPosition}><button type="button" role="menuitem" onClick={() => beginEdit(threads.find((thread) => idOf(thread) === menuId) || {})}>{UI.renameThread}</button><button type="button" role="menuitem" className="is-danger" onClick={() => { void removeThread(menuId); }}>{UI.deleteThread}</button></div>, document.body)}</aside>;
}

function AssistantConversation({ threadId, threads, messages, runs, mode, locale, hasMoreMessages, loadingOlderMessages, onLoadOlderMessages, onModeChange, onNewThread, onEnsureDraft, onPrepareSubmission, onSubmitMessage, onRetryChat, onRenameThread, onDeleteThread, onSelectThread, refreshThread, notify }) {
  const [prompt, setPrompt] = useState(""); const [attachments, setAttachments] = useState([]); const [targetLanguage, setTargetLanguage] = useState("en");
  const [generation, setGeneration] = useState(initialGeneration); const [models, setModels] = useState([]); const [modelsState, setModelsState] = useState("idle"); const [chatModels, setChatModels] = useState([]); const [chatModelId, setChatModelId] = useState(""); const [chatModelsState, setChatModelsState] = useState("idle"); const [submitting, setSubmitting] = useState(false); const [inputExpanded, setInputExpanded] = useState(false);
  const inputRef = useRef(null); const messageListRef = useRef(null); const initialScrollThreadId = useRef(""); const streamScrollFrame = useRef(0); const current = CONVERSATION_MODES[mode]; const selectedModel = models.find((model) => model.id === generation.modelId) || null;
  const attachmentAccept = mode !== "video_generation" ? current.accepted : generation.generationMode === "first_frame" || generation.generationMode === "first_last_frame" ? "image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp" : current.accepted;
  const allowsMultipleAttachments = mode === "chat" || mode === "video_generation";

  useEffect(() => { if (mode !== "video_generation") return; let active = true; setModelsState("loading"); listAiVideoModels().then(({ items, defaultModelId }) => { if (!active) return; setModels(items); const selected = items.find((model) => model.id === defaultModelId) || items[0]; if (selected) setGeneration((state) => ({ ...state, modelId: selected.id })); setModelsState("ready"); }).catch((error) => { if (active) { setModelsState("error"); notify(error.message || UI.modelLoadFailed); } }); return () => { active = false; }; }, [mode, notify]);
  useEffect(() => { if (mode !== "chat") return; let active = true; setChatModelsState("loading"); listAssistantChatModels().then((items) => { if (!active) return; setChatModels(items || []); if (items?.length) setChatModelId((current) => current || items[0].id); setChatModelsState("ready"); }).catch((error) => { if (active) { setChatModelsState("error"); notify(error.message || UI.modelLoadFailed); } }); return () => { active = false; }; }, [mode, notify]);
  useEffect(() => { if (!selectedModel?.id) return; let active = true; getAiVideoModelGenParam(selectedModel.id).then((detail) => { if (!active) return; const hydrated = normalizeModel({ ...selectedModel.raw, ...detail }); setModels((list) => list.map((item) => item.id === hydrated.id ? hydrated : item)); const defaults = modelDefaults(hydrated); setGeneration((state) => ({ ...state, ratio: state.ratio || defaults.aspectRatio, duration: state.duration || String(defaults.duration), resolution: state.resolution || defaults.resolution, generationMode: state.generationMode || defaults.playMode })); }).catch(() => {}); return () => { active = false; }; }, [selectedModel?.id]);
  useEffect(() => { setPrompt(""); setAttachments([]); inputRef.current?.focus(); }, [mode]);
  useEffect(() => {
    if (!threadId || !messages.length || initialScrollThreadId.current === threadId) return;
    messageListRef.current?.scrollTo({ top: messageListRef.current.scrollHeight });
    initialScrollThreadId.current = threadId;
  }, [messages.length, threadId]);
  useEffect(() => {
    if (!submitting) return undefined;
    // Streaming mutates the content of the last message without changing the
    // message count. Observe the rendered DOM as well as React state so every
    // delta keeps the scroller pinned to the newest content.
    const scroller = messageListRef.current;
    if (!scroller) return undefined;
    const scrollToLatest = () => {
      window.cancelAnimationFrame(streamScrollFrame.current);
      streamScrollFrame.current = window.requestAnimationFrame(() => {
        scroller.scrollTop = scroller.scrollHeight;
      });
    };
    const observer = new MutationObserver(scrollToLatest);
    observer.observe(scroller, { childList: true, characterData: true, subtree: true });
    scrollToLatest();
    return () => {
      observer.disconnect();
      window.cancelAnimationFrame(streamScrollFrame.current);
    };
  }, [submitting]);
  const clearComposer = () => {
    // The composer must visibly clear before the long-running SSE promise
    // settles. flushSync prevents React from deferring this event update.
    flushSync(() => {
      setPrompt(""); setAttachments([]);
    });
    if (inputRef.current) inputRef.current.value = "";
  };
  const loadOlderOnScroll = async (event) => {
    const scroller = event.currentTarget;
    if (!hasMoreMessages || loadingOlderMessages || scroller.scrollTop > 56) return;
    const previousHeight = scroller.scrollHeight;
    await onLoadOlderMessages();
    window.requestAnimationFrame(() => { scroller.scrollTop += scroller.scrollHeight - previousHeight; });
  };

  const addFiles = async (files) => {
    const selected = Array.from(files || []); if (!selected.length) return;
    const draftProjectId = await onEnsureDraft(mode);
    const pending = selected.map((file, index) => ({
      localId: crypto.randomUUID(), filename: file.name, kind: assetTypeForFile(file), file, status: "uploading",
      role: mode === "video_generation" && generation.generationMode === "first_last_frame" ? (attachments.length + index === 0 ? "first_frame" : "last_frame") : mode === "video_generation" && generation.generationMode === "first_frame" ? "first_frame" : undefined,
    })); setAttachments((value) => [...value, ...pending]);
    await Promise.all(pending.map(async (item) => {
      try {
        const subtitleLayoutPromise = mode === "short_drama_narration" && item.kind === "video"
          ? detectAgentSourceSubtitleLayout(item.file)
          : Promise.resolve(null);
        const asset = await uploadAsset(draftProjectId, item.file, item.kind);
        let settled = asset;
        for (let attempt = 0; attempt < 30 && !["ready", "failed"].includes(String(settled?.status || "").toLowerCase()); attempt += 1) { await new Promise((resolve) => window.setTimeout(resolve, 1200)); settled = await getAiVideoAsset(asset.id).catch(() => settled); }
        if (String(settled?.status || "ready").toLowerCase() !== "ready") throw new Error(UI.assetNotReady);
        const sourceSubtitleLayout = await subtitleLayoutPromise;
        setAttachments((value) => value.map((entry) => entry.localId === item.localId ? { ...entry, status: "ready", assetId: settled.id, sourceSubtitleLayout } : entry));
      } catch (error) { setAttachments((value) => value.map((entry) => entry.localId === item.localId ? { ...entry, status: "failed", error: error.message || UI.uploadFailed } : entry)); }
    }));
  };

  const submit = async (event) => {
    event?.preventDefault(); if (submitting) return;
    const content = prompt.trim(); const submittedAttachments = attachments.map((attachment) => ({ asset_id: attachment.assetId, role: attachment.role || undefined }));
    const error = validateAssistantSubmission({ mode, prompt: content, attachments, targetLanguage, generation }); if (error) return notify(error);
    const submittedPrompt = prompt; const submittedLocalAttachments = attachments;
    let submissionAccepted = false;
    const clearAcceptedInput = () => {
      if (submissionAccepted) return;
      submissionAccepted = true;
      clearComposer();
    };
    setSubmitting(true);
    // Keep the composer responsive even when an SSE implementation delays its
    // first event. Any failure before the server accepts the request restores
    // this exact draft below; accepted tasks never put stale input back.
    clearComposer();
    try {
      const preparedPayload = await onPrepareSubmission({
        mode,
        content,
        attachments: submittedAttachments,
        input: mode === "chat" ? { locale, ...(chatModelId ? { model_id: chatModelId } : {}) } : mode === "video_translation" ? { locale, target_language: targetLanguage } : mode === "video_generation" ? {
          locale,
          generation_mode: generation.generationMode,
          model_id: generation.modelId,
          ratio: generation.ratio,
          duration_seconds: Number(generation.duration),
          resolution: generation.resolution,
          audio: generation.audio,
          model_params: generation.modelParams,
        } : {
          locale,
          source_subtitle_layouts: Object.fromEntries(
            attachments
              .filter((attachment) => attachment.kind === "video" && attachment.assetId)
              .map((attachment) => [
                attachment.assetId,
                attachment.sourceSubtitleLayout || { status: "confirmed", region: { ...DEFAULT_AGENT_SOURCE_SUBTITLE_REGION } },
              ]),
          ),
        },
      });
      await onSubmitMessage(preparedPayload, { onAccepted: clearAcceptedInput });
      // Agent requests return after their POST succeeds. Chat requests stay pending
      // until SSE completes, but clear as soon as its message_created event confirms
      // the server accepted the turn.
      if (mode !== "chat") clearAcceptedInput();
    } catch (submitError) {
      if (!submissionAccepted) {
        setPrompt(submittedPrompt); setAttachments(submittedLocalAttachments);
      }
      notify(submitError.message || UI.sendFailed);
    } finally { setSubmitting(false); }
  };

  const onModelChange = (next) => { setGeneration((state) => ({ ...state, ...next })); };
  const copyMessage = async (content) => {
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(content);
      else { const input = document.createElement("textarea"); input.value = content; document.body.append(input); input.select(); document.execCommand("copy"); input.remove(); }
      notify(UI.copied);
    } catch { notify(UI.copyFailed); }
  };
  const regenerateMessage = async (assistantMessageId) => {
    if (submitting) return;
    setSubmitting(true);
    try {
      await onRetryChat(assistantMessageId);
    } catch (error) { notify(error.message || UI.sendFailed); } finally { setSubmitting(false); }
  };
  const attachedRunIds = new Set();
  const runsByAnchorMessage = new Map();
  runs.forEach((run) => {
    // Every Agent first acknowledges the user's request in an assistant reply.
    // Its execution timeline must follow that acknowledgement, never split the
    // user turn from the first response by inserting progress steps in between.
    const anchorId = assistantRunAnchorMessageId(run);
    if (!anchorId) return;
    const entries = runsByAnchorMessage.get(anchorId) || [];
    entries.push(run);
    runsByAnchorMessage.set(anchorId, entries);
  });
  const timeline = messages.flatMap((message) => {
    const entries = [<MessageBubble message={message} key={`message-${message.id}`} onCopy={copyMessage} onRegenerate={regenerateMessage} />];
    (runsByAnchorMessage.get(message.id) || []).forEach((run) => {
      attachedRunIds.add(run.id || run.run_id);
      entries.push(run.mode === "short_drama_narration"
        ? <NarrationRunTimeline run={run} key={`run-${run.id || run.run_id}`} onRefresh={refreshThread} />
        : <RunCard run={run} key={`run-${run.id || run.run_id}`} onRefresh={refreshThread} />);
    });
    return entries;
  });
  // Runs whose source message is beyond the oldest loaded page remain visible,
  // but must preserve chronological order instead of the API's newest-first
  // list order.
  const unlinkedRuns = runs
    .filter((run) => !attachedRunIds.has(run.id || run.run_id))
    .sort((left, right) => Date.parse(left.created_at || left.createdAt || "") - Date.parse(right.created_at || right.createdAt || ""));
  return <div className="assistant-layout">
    <ConversationThreads threadId={threadId} threads={threads} onNewThread={onNewThread} onRenameThread={onRenameThread} onDeleteThread={onDeleteThread} onSelectThread={onSelectThread} notify={notify} />
    <section className="assistant-chat">
      <div className="assistant-message-list" ref={messageListRef} onScroll={(event) => { void loadOlderOnScroll(event); }} aria-live="polite">{loadingOlderMessages && <div className="assistant-message-list__loading" role="status" aria-label={UI.loading}><CircleNotch className="is-spinning" /></div>}{messages.length ? timeline : <div className="assistant-welcome" aria-hidden="true"><Sparkle weight="fill" /></div>}{unlinkedRuns.map((run) => run.mode === "short_drama_narration" ? <NarrationRunTimeline run={run} key={`run-${run.id || run.run_id}`} onRefresh={refreshThread} /> : <RunCard run={run} key={`run-${run.id || run.run_id}`} onRefresh={refreshThread} />)}</div>
      <form className="assistant-composer" onSubmit={submit}><AttachmentStrip attachments={attachments} onRemove={(localId) => setAttachments((items) => items.filter((item) => item.localId !== localId))} />
        <div className="assistant-composer__shell">
          <textarea className={inputExpanded ? "is-expanded" : ""} ref={inputRef} value={prompt} rows="2" readOnly={submitting} aria-busy={submitting} onChange={(event) => setPrompt(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (!submitting) void submit(); } }} placeholder={current.placeholder} aria-label={current.placeholder} />
          <button className="assistant-composer__resize" type="button" onClick={() => setInputExpanded((value) => !value)} aria-label={inputExpanded ? UI.shrinkInput : UI.expandInput} title={inputExpanded ? UI.shrinkInput : UI.expandInput}>{inputExpanded ? <ArrowsIn /> : <ArrowsOut />}</button>
          <div className={`assistant-composer__toolbar ${mode === "chat" ? "has-chat-model" : ""}`}>
            <label className="assistant-upload"><FileArrowUp /><input type="file" accept={attachmentAccept} multiple={allowsMultipleAttachments} onChange={(event) => { void addFiles(event.target.files); event.target.value = ""; }} /><span className="sr-only">{current.attachmentHint}</span></label>
            <ModeSelector mode={mode} onChange={onModeChange} />
            <div className="assistant-composer__parameters">
              {mode === "video_translation" && <div className="assistant-controls"><TranslationLanguageSelector value={targetLanguage} onChange={setTargetLanguage} /></div>}
              {mode === "video_generation" && <GenerationControls generation={generation} models={models} selectedModel={selectedModel} loading={modelsState === "loading"} onChange={onModelChange} />}
            </div>
            {mode === "chat" && <ChatModelSelector models={chatModels} value={chatModelId} loading={chatModelsState === "loading"} onChange={setChatModelId} />}
            <button className={`assistant-send ${submitting ? "is-loading" : ""}`} disabled={submitting} aria-busy={submitting} type="submit" aria-label={submitting ? UI.sending : UI.send} title={submitting ? UI.sending : UI.send}>{submitting ? <CircleNotch className="is-spinning" /> : <PaperPlaneRight weight="fill" />}</button>
          </div>
        </div>
      </form>
    </section>
  </div>;
}

export function AiAssistantWorkspace({ notify }) {
  const { locale } = useI18n();
  const [threads, setThreads] = useState([]); const [threadId, setThreadId] = useState(""); const [messages, setMessages] = useState([]); const [runs, setRuns] = useState([]); const [mode, setMode] = useState("chat"); const [loading, setLoading] = useState(true); const [messagePage, setMessagePage] = useState({ hasMore: false, nextBefore: null }); const [loadingOlderMessages, setLoadingOlderMessages] = useState(false);
  const draftProjects = useRef(new Map()); const chatStreamAbort = useRef(null); const chatStreamMessageId = useRef(""); const loadingOlderRef = useRef(false); const runStreamControllers = useRef(new Map()); const [runStreamRetryTick, setRunStreamRetryTick] = useState(0);
  const loadThread = useCallback(async (nextThreadId, { before, append = false, preserve = false } = {}) => {
    if (!nextThreadId) { setMessages([]); setRuns([]); setMessagePage({ hasMore: false, nextBefore: null }); return null; }
    const [thread, runResponse] = await Promise.all([getAssistantThread(nextThreadId, { before }), append ? Promise.resolve(null) : getAssistantRuns(nextThreadId)]);
    const pageMessages = normalizeAssistantMessages(thread);
    setMessages((current) => append || preserve ? mergeAssistantMessages(current, pageMessages) : pageMessages);
    if (!preserve) setMessagePage((current) => append ? { hasMore: Boolean(thread?.has_more), nextBefore: thread?.next_before || null } : { hasMore: Boolean(thread?.has_more), nextBefore: thread?.next_before || null });
    if (!append) setRuns(normalizeAssistantRuns(runResponse));
    return thread;
  }, []);
  const refreshThread = useCallback(async () => { if (!threadId) return; try { await loadThread(threadId, { preserve: true }); } catch (error) { notify(error.message || UI.refreshFailed); } }, [loadThread, notify, threadId]);
  const refreshActiveRuns = useCallback(async () => {
    const activeRuns = runs.filter((run) => isAssistantRunActive(runStatus(run)) && (run.id || run.run_id));
    if (!activeRuns.length) return;
    try {
      const refreshed = await Promise.all(activeRuns.map((run) => getAssistantRun(run.id || run.run_id)));
      const refreshedById = new Map(refreshed.map((run) => [String(run.id || run.run_id), run]));
      setRuns((current) => current.map((run) => {
        const refreshedRun = refreshedById.get(String(run.id || run.run_id));
        return refreshedRun ? mergeAssistantRunSnapshot(run, refreshedRun) : run;
      }));
    } catch (error) { notify(error.message || UI.refreshFailed); }
  }, [notify, runs]);
  const loadOlderMessages = useCallback(async () => {
    if (!threadId || !messagePage.hasMore || !messagePage.nextBefore || loadingOlderRef.current) return;
    loadingOlderRef.current = true; setLoadingOlderMessages(true);
    try { await loadThread(threadId, { before: messagePage.nextBefore, append: true }); } catch (error) { notify(error.message || UI.refreshFailed); } finally { loadingOlderRef.current = false; setLoadingOlderMessages(false); }
  }, [loadThread, messagePage.hasMore, messagePage.nextBefore, notify, threadId]);
  useEffect(() => { let active = true; listAssistantThreads().then((data) => { if (!active) return; const list = normalizeAssistantThreadList(data); setThreads(list); const first = idOf(list[0]); if (first) { setThreadId(first); return loadThread(first); } }).catch((error) => { if (active) notify(error.message || UI.threadsLoadFailed); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [loadThread, notify]);
  useEffect(() => { if (!runs.some((run) => isAssistantRunActive(runStatus(run)))) return undefined; const timer = window.setInterval(() => { void refreshActiveRuns(); }, 2000); return () => window.clearInterval(timer); }, [refreshActiveRuns, runs]);
  const activeRunKey = runs.filter((run) => isAssistantRunActive(runStatus(run)) && (run.id || run.run_id)).map((run) => String(run.id || run.run_id)).sort().join("|");
  useEffect(() => {
    const activeIds = new Set(activeRunKey ? activeRunKey.split("|") : []);
    runStreamControllers.current.forEach((controller, id) => {
      if (!activeIds.has(id)) { controller.abort(); runStreamControllers.current.delete(id); }
    });
    activeIds.forEach((id) => {
      if (runStreamControllers.current.has(id)) return;
      const controller = new AbortController();
      runStreamControllers.current.set(id, controller);
      void streamAssistantRun(id, {
        signal: controller.signal,
        onRunSnapshot: (snapshot) => setRuns((current) => current.map((run) => String(run.id || run.run_id) === id ? mergeAssistantRunSnapshot(run, snapshot) : run)),
        onStepSnapshot: (snapshot) => setRuns((current) => current.map((run) => String(run.id || run.run_id) === id ? mergeAssistantRunStepSnapshot(run, snapshot) : run)),
        onCompleted: (snapshot) => setRuns((current) => current.map((run) => String(run.id || run.run_id) === id ? mergeAssistantRunSnapshot(run, snapshot) : run)),
      }).catch((error) => {
        if (error?.name !== "AbortError") window.setTimeout(() => setRunStreamRetryTick((value) => value + 1), 1500);
      }).finally(() => {
        if (runStreamControllers.current.get(id) === controller) runStreamControllers.current.delete(id);
      });
    });
  }, [activeRunKey, runStreamRetryTick]);
  useEffect(() => () => {
    chatStreamAbort.current?.abort(); chatStreamMessageId.current = "";
    runStreamControllers.current.forEach((controller) => controller.abort());
    runStreamControllers.current.clear();
  }, []);

  const ensureThread = useCallback(async () => {
    if (threadId) return threadId;
    const created = await createAssistantThread(); const id = idOf(created);
    if (!id) throw new Error(UI.threadIdMissing);
    setThreadId(id); setThreads((items) => [{ ...created, id }, ...items]); return id;
  }, [threadId]);
  const ensureDraft = useCallback(async (requestedMode) => {
    const id = await ensureThread(); const key = `${id}:${requestedMode}`;
    if (draftProjects.current.has(key)) return draftProjects.current.get(key);
    const draft = await createAssistantDraft(id, requestedMode); const projectId = draft?.project_id || draft?.projectId;
    if (!projectId) throw new Error(UI.draftIdMissing);
    draftProjects.current.set(key, projectId); return projectId;
  }, [ensureThread]);
  const prepareSubmission = useCallback(async (payload) => {
    const id = await ensureThread();
    // Every task-mode run is bound to the mode-specific draft project that owns its uploaded assets.
    // The user-selected `input` is frozen verbatim; the model never receives authority to replace it.
    // Chat stays task-free, but an image attachment still belongs to its chat draft project.
    const needsDraftProject = payload.mode !== "chat" || payload.attachments.length > 0;
    const projectId = needsDraftProject ? await ensureDraft(payload.mode) : undefined;
    return { ...payload, threadId: id, input: projectId ? { ...payload.input, project_id: projectId } : payload.input };
  }, [ensureDraft, ensureThread]);
  const submitPreparedMessage = useCallback(async (payload, { onAccepted } = {}) => {
    if (payload.mode === "chat") {
      const controller = new AbortController(); chatStreamAbort.current = controller;
      const upsertMessages = (items) => setMessages((current) => mergeAssistantMessages(current, items));
      try {
        await streamAssistantChatMessage(payload.threadId, { mode: payload.mode, content: payload.content, attachments: payload.attachments, input: payload.input }, {
          signal: controller.signal,
          onAccepted,
          onMessageCreated: (data) => { chatStreamMessageId.current = data.assistant_message?.id || ""; upsertMessages(normalizeAssistantMessages([data.message, data.assistant_message])); setThreads((items) => items.map((item) => idOf(item) === payload.threadId ? { ...item, title: data.thread_title || item.title, updated_at: new Date().toISOString() } : item)); },
          onDelta: ({ assistant_message_id: assistantMessageId, content }) => setMessages((current) => current.map((message) => message.id === assistantMessageId ? { ...message, content: [{ type: "text", text: String(content || "") }] } : message)),
          onCompleted: ({ assistant_message_id: assistantMessageId, content }) => setMessages((current) => current.map((message) => message.id === assistantMessageId ? { ...message, stream_status: "completed", content: [{ type: "text", text: String(content || "") }] } : message)),
        });
      } catch (error) {
        if (error?.name !== "AbortError") throw error;
      } finally {
        if (chatStreamAbort.current === controller) { chatStreamAbort.current = null; chatStreamMessageId.current = ""; }
      }
      return;
    }
    const draftKey = `${payload.threadId}:${payload.mode}`;
    let response;
    try {
      response = await sendAssistantMessage(payload.threadId, { mode: payload.mode, content: payload.content, attachments: payload.attachments, input: payload.input });
    } catch (error) {
      // A previously accepted task locks its draft project. Every Agent task
      // must own a new draft, regardless of its selected product mode.
      if (![
        "AI_VIDEO_DRAFT_LOCKED",
        "ASSISTANT_TASK_DRAFT_LOCKED",
      ].includes(error?.code)) throw error;
      draftProjects.current.delete(draftKey);

      // Text-to-video has no draft-bound assets, so it can safely recover once
      // without making the user re-enter the prompt. Uploaded assets belong to
      // the original project and must be re-uploaded into a new draft instead.
      if (payload.attachments.length) throw error;
      const projectId = await ensureDraft(payload.mode);
      response = await sendAssistantMessage(payload.threadId, {
        mode: payload.mode,
        content: payload.content,
        attachments: payload.attachments,
        input: { ...payload.input, project_id: projectId },
      });
    }
    // A task-mode project has one submission lifecycle. Do not reuse it for
    // the next agent run, regardless of whether the provider later succeeds.
    draftProjects.current.delete(draftKey);
    onAccepted?.();
    const nextMessages = normalizeAssistantMessages(response); if (nextMessages.length) setMessages(nextMessages); else await loadThread(payload.threadId);
    const nextRuns = normalizeAssistantRuns(response?.runs || response?.agent_runs); if (nextRuns.length) setRuns(nextRuns); else void getAssistantRuns(payload.threadId).then((data) => setRuns(normalizeAssistantRuns(data))).catch(() => {});
    setThreads((items) => items.map((item) => idOf(item) === payload.threadId ? { ...item, title: response.thread_title || item.title, updated_at: new Date().toISOString() } : item));
  }, [ensureDraft, loadThread]);
  const retryChat = useCallback(async (assistantMessageId) => {
    if (!threadId) return;
    const controller = new AbortController(); chatStreamAbort.current = controller;
    const upsertMessages = (items) => setMessages((current) => mergeAssistantMessages(current, items));
    try {
      await streamAssistantChatRetry(threadId, assistantMessageId, {
        signal: controller.signal,
        onMessageCreated: (data) => { chatStreamMessageId.current = data.assistant_message?.id || ""; upsertMessages(normalizeAssistantMessages([data.assistant_message])); },
        onDelta: ({ assistant_message_id: id, content }) => setMessages((current) => current.map((message) => message.id === id ? { ...message, content: [{ type: "text", text: String(content || "") }] } : message)),
        onCompleted: ({ assistant_message_id: id, content }) => setMessages((current) => current.map((message) => message.id === id ? { ...message, stream_status: "completed", content: [{ type: "text", text: String(content || "") }] } : message)),
      });
    } finally {
      if (chatStreamAbort.current === controller) { chatStreamAbort.current = null; chatStreamMessageId.current = ""; }
    }
  }, [threadId]);
  const activeChatMessageId = messages.find((message) => message.role === "assistant" && message.mode === "chat" && message.stream_status === "running")?.id || "";
  useEffect(() => {
    if (!threadId || !activeChatMessageId || chatStreamMessageId.current === activeChatMessageId) return undefined;
    const controller = new AbortController(); chatStreamAbort.current = controller; chatStreamMessageId.current = activeChatMessageId;
    const update = (assistantMessageId, content) => setMessages((current) => current.map((message) => message.id === assistantMessageId ? { ...message, content: [{ type: "text", text: String(content || "") }] } : message));
    void resumeAssistantChatStream(threadId, activeChatMessageId, {
      signal: controller.signal,
      onMessageCreated: (data) => { if (data.assistant_message) setMessages((current) => mergeAssistantMessages(current, normalizeAssistantMessages([data.assistant_message]))); },
      onDelta: ({ assistant_message_id: assistantMessageId, content }) => update(assistantMessageId, content),
      onCompleted: ({ assistant_message_id: assistantMessageId, content }) => setMessages((current) => current.map((message) => message.id === assistantMessageId ? { ...message, stream_status: "completed", content: [{ type: "text", text: String(content || "") }] } : message)),
    }).catch((error) => { if (error?.name !== "AbortError") void refreshThread(); }).finally(() => {
      if (chatStreamAbort.current === controller) { chatStreamAbort.current = null; chatStreamMessageId.current = ""; }
    });
    return () => { controller.abort(); if (chatStreamAbort.current === controller) { chatStreamAbort.current = null; chatStreamMessageId.current = ""; } };
  }, [activeChatMessageId, refreshThread, threadId]);
  const renameThread = useCallback(async (targetThreadId, title) => {
    const updated = await updateAssistantThreadTitle(targetThreadId, title);
    setThreads((items) => items.map((item) => idOf(item) === targetThreadId ? { ...item, ...updated, title: updated.title || title } : item));
  }, []);
  const removeThread = useCallback(async (targetThreadId) => {
    chatStreamAbort.current?.abort(); chatStreamMessageId.current = "";
    await deleteAssistantThread(targetThreadId);
    draftProjects.current.forEach((_projectId, key) => { if (key.startsWith(`${targetThreadId}:`)) draftProjects.current.delete(key); });
    const remaining = threads.filter((item) => idOf(item) !== targetThreadId);
    setThreads(remaining);
    if (threadId !== targetThreadId) return;
    const nextThreadId = idOf(remaining[0]);
    setThreadId(nextThreadId);
    if (nextThreadId) await loadThread(nextThreadId); else { setMessages([]); setRuns([]); setMessagePage({ hasMore: false, nextBefore: null }); }
  }, [loadThread, threadId, threads]);
  const runtime = useExternalStoreRuntime({
    messages,
    isRunning: false,
    // The custom composer owns request dispatch so that it can preserve drafts
    // until the server accepts them. assistant-ui remains the message runtime.
    onNew: async () => {},
    convertMessage: toAssistantUiMessage,
  });

  const selectThread = async (nextId) => { chatStreamAbort.current?.abort(); chatStreamMessageId.current = ""; setThreadId(nextId); try { await loadThread(nextId); } catch (error) { notify(error.message || UI.threadReadFailed); } };
  const createNewThread = async () => { chatStreamAbort.current?.abort(); chatStreamMessageId.current = ""; const created = await createAssistantThread(); const id = idOf(created); if (!id) throw new Error(UI.threadIdMissing); setThreads((items) => [{ ...created, id }, ...items]); setThreadId(id); setMessages([]); setRuns([]); setMessagePage({ hasMore: false, nextBefore: null }); return id; };
  if (loading) return <div className="assistant-loading"><CircleNotch className="is-spinning" />{UI.loading}</div>;
  return <AssistantRuntimeProvider runtime={runtime}><AssistantConversation threadId={threadId} threads={threads} messages={messages} runs={runs} mode={mode} locale={locale} hasMoreMessages={messagePage.hasMore} loadingOlderMessages={loadingOlderMessages} onLoadOlderMessages={loadOlderMessages} onModeChange={setMode} onNewThread={createNewThread} onEnsureDraft={ensureDraft} onPrepareSubmission={prepareSubmission} onSubmitMessage={submitPreparedMessage} onRetryChat={retryChat} onRenameThread={renameThread} onDeleteThread={removeThread} onSelectThread={selectThread} refreshThread={refreshThread} notify={notify} /></AssistantRuntimeProvider>;
}
