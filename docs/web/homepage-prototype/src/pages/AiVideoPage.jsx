import {
  CaretDown, Check, Clock, FilmSlate, FolderSimplePlus, GridFour, ImageSquare, Info,
  Lightning, ListBullets, MagnifyingGlass, Plus, SpinnerGap, VideoCamera, X,
} from "@phosphor-icons/react";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { DashboardHeader } from "../components/dashboard/DashboardHeader.jsx";
import { DashboardMobileNav } from "../components/dashboard/DashboardMobileNav.jsx";
import { DashboardSidebar } from "../components/dashboard/DashboardSidebar.jsx";
import { DashboardToast } from "../components/dashboard/DashboardToast.jsx";
import { dashboardNavItems } from "../data/dashboardData.js";
import { useAuth } from "../features/auth/AuthProvider.jsx";
import { labelOf, modelDefaults, modelForPlayMode, normalizeModel, playModesForModel } from "../features/ai-video/modelCapabilities.js";
import { uploadAsset } from "../features/uploads/ossPostUpload.js";
import { createAiVideoDraft, getAiVideoAsset, getAiVideoModelGenParam, listAiVideoModels, listAiVideoTasks, quoteAiVideoTask, retryAiVideoTask, submitAiVideoTask, uploadAiVideoImage } from "../services/aiVideoApi.js";
import "../styles/ai-video.css";

const initialFilters = { type: "all", startDate: "", endDate: "", view: "list" };
const TASK_PAGE_SIZE = 30;
const taskState = (task) => String(task.status || task.state || "queued").toLowerCase();
const taskKind = (task) => String(task.type || task.output_type || task.outputType || "video").toLowerCase();
const taskDate = (task) => task.created_at || task.createdAt || "";
const taskImage = (task) => task.thumbnail_url || task.thumbnailUrl || task.output?.thumbnail_url || task.output?.thumbnailUrl || task.preview_url || task.previewUrl || task.output?.preview_url || task.output?.url || task.output_url || "";
const taskTitle = (task) => task.title || task.model_name || task.modelName || task.model_id || "AI 视频任务";
const taskPrompt = (task) => task.prompt || task.input?.prompt || "";
const taskId = (task) => task.id || task.task_id || crypto.randomUUID();
const isTaskGenerating = (task) => ["submitting", "queued", "processing", "rendering", "finalizing"].includes(taskState(task));

function taskIdentity(task) { return task.id || task.task_id || ""; }
function appendUniqueTasks(current, incoming) {
  const seen = new Set();
  return [...current, ...incoming].filter((task) => {
    const id = taskIdentity(task);
    if (!id || seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}
function mergeLatestTasks(latest, current) {
  const latestIds = new Set(latest.map(taskIdentity).filter(Boolean));
  return appendUniqueTasks(latest, current.filter((task) => !latestIds.has(taskIdentity(task))));
}

function dateLabel(date) {
  if (!date) return "";
  const value = new Date(date);
  return Number.isNaN(value.getTime()) ? String(date) : value.toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" });
}

function optionValue(option) { return String(option?.id || option?.value || option); }
function promptMarker(assetId) { return `{{asset:${assetId}}}`; }
function referenceLabel(kind, index) { return `${kind === "image" ? "图" : kind === "video" ? "视频" : "音频"} ${index + 1}`; }
function referenceAssetsFor(assets, model) {
  return ["image", "video", "audio"].flatMap((kind) => (assets[kind] || []).map((asset, index) => ({
    ...asset,
    kind,
    referenceLabel: referenceLabel(kind, index),
    promptToken: promptMarker(asset.id),
    supportsMention: Boolean(model?.[kind]?.supportsMention),
  }))).filter((asset) => asset.supportsMention);
}

export function AiVideoPage() {
  const { user } = useAuth();
  const [models, setModels] = useState([]); const [modelsState, setModelsState] = useState("loading");
  const [modelParamsState, setModelParamsState] = useState("idle");
  const [selectedId, setSelectedId] = useState(""); const [showModels, setShowModels] = useState(false); const [showPlayModes, setShowPlayModes] = useState(false); const [search, setSearch] = useState(""); const [category, setCategory] = useState("全部");
  const [filters, setFilters] = useState(initialFilters); const [showDateFilter, setShowDateFilter] = useState(false); const [tasks, setTasks] = useState([]); const [tasksState, setTasksState] = useState("loading");
  const [taskPage, setTaskPage] = useState({ page: 0, hasNext: false, total: 0 }); const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [form, setForm] = useState({ prompt: "", ...modelDefaults({ resolutions: [], aspectRatios: [], duration: { options: [], min: "" } }) });
  const [assets, setAssets] = useState({ image: [], video: [], audio: [] }); const [references, setReferences] = useState([]); const [projectId, setProjectId] = useState(""); const [draftState, setDraftState] = useState("idle"); const [submitting, setSubmitting] = useState(false);
  const [quote, setQuote] = useState(null); const [quoteDuration, setQuoteDuration] = useState("");
  const [mention, setMention] = useState(null); const [mentionIndex, setMentionIndex] = useState(0);
  const [promptScroll, setPromptScroll] = useState({ left: 0, top: 0 }); const [mentionPreview, setMentionPreview] = useState(null);
  const [toast, setToast] = useState({ id: 0, message: "" });
  const taskQueryVersionRef = useRef(0); const loadMoreRef = useRef(null); const promptRef = useRef(null);
  const selected = models.find((model) => model.id === selectedId) || null;
  const playModes = useMemo(() => playModesForModel(selected), [selected]);
  const activePlayMode = playModes.find((mode) => optionValue(mode) === form.playMode) || playModes[0] || null;
  const activeModel = useMemo(() => modelForPlayMode(selected, activePlayMode?.id || form.playMode), [activePlayMode, form.playMode, selected]);
  const hasUnreadyAssets = Object.values(assets).flat().some((asset) => String(asset.status).toLowerCase() !== "ready");
  const referenceAssets = useMemo(() => referenceAssetsFor(assets, activeModel), [activeModel, assets]);
  const mentionAssets = useMemo(() => {
    const query = mention?.query.trim().toLocaleLowerCase() || "";
    return referenceAssets.filter((asset) => String(asset.status).toLowerCase() === "ready" && (!query || `${asset.referenceLabel} ${asset.filename || asset.name || ""}`.toLocaleLowerCase().includes(query)));
  }, [mention?.query, referenceAssets]);
  const notify = useCallback((message) => setToast(({ id }) => ({ id: id + 1, message })), []);

  const updateMention = useCallback((nextMention) => {
    setMention(nextMention);
    setMentionIndex(0);
  }, []);

  const chooseMention = useCallback((asset) => {
    if (!mention) return;
    const nextPrompt = promptRef.current?.insertMention(asset);
    if (!nextPrompt) return;
    setForm((current) => ({ ...current, prompt: nextPrompt }));
    setReferences((current) => current.includes(asset.id) ? current : [...current, asset.id]);
    setMention(null);
  }, [mention]);

  const loadModelGenParams = useCallback(async (model) => {
    if (!model?.id) return null;
    setSelectedId(model.id);
    setModelParamsState("loading");
    try {
      const params = await getAiVideoModelGenParam(model.id);
      const hydrated = normalizeModel({ ...model.raw, ...params });
      setModels((current) => current.map((item) => item.id === hydrated.id ? hydrated : item));
      const defaults = modelDefaults(hydrated);
      setForm((current) => ({ ...current, ...defaults }));
      setQuoteDuration(defaults.duration);
      setModelParamsState("ready");
      return hydrated;
    } catch (error) {
      setModelParamsState("error");
      notify(error.message || "模型玩法和参数加载失败，请重新选择模型。");
      return null;
    }
  }, [notify]);

  const refreshTasks = useCallback(async ({ background = false } = {}) => {
    if (!background) {
      taskQueryVersionRef.current += 1;
      setIsLoadingMore(false);
    }
    const queryVersion = taskQueryVersionRef.current;
    if (!background) setTasksState("loading");
    try {
      const data = await listAiVideoTasks({ ...filters, page: 1, pageSize: TASK_PAGE_SIZE });
      if (queryVersion !== taskQueryVersionRef.current) return;
      const items = Array.isArray(data) ? data : data?.tasks || data?.items || [];
      if (background) {
        setTasks((current) => mergeLatestTasks(items, current));
        setTaskPage((current) => ({
          ...current,
          total: Number(data?.total ?? current.total),
          hasNext: current.page <= 1 ? Boolean(data?.has_next ?? data?.hasNext) : current.hasNext,
        }));
      } else {
        setTasks(items);
        setTaskPage({
          page: Number(data?.page) || 1,
          hasNext: Boolean(data?.has_next ?? data?.hasNext),
          total: Number(data?.total) || 0,
        });
      }
      setTasksState("ready");
    } catch (error) {
      if (background) {
        if (import.meta.env.DEV) console.warn("AI video task list refresh failed", { error });
        return;
      }
      setTasksState("error");
      notify(error.message || "作品记录加载失败，请重试。");
    }
  }, [filters, notify]);

  const loadMoreTasks = useCallback(async () => {
    if (isLoadingMore || !taskPage.hasNext || tasksState !== "ready") return;
    const queryVersion = taskQueryVersionRef.current;
    const nextPage = taskPage.page + 1;
    setIsLoadingMore(true);
    try {
      const data = await listAiVideoTasks({ ...filters, page: nextPage, pageSize: TASK_PAGE_SIZE });
      if (queryVersion !== taskQueryVersionRef.current) return;
      const items = Array.isArray(data) ? data : data?.tasks || data?.items || [];
      setTasks((current) => appendUniqueTasks(current, items));
      setTaskPage({
        page: Number(data?.page) || nextPage,
        hasNext: Boolean(data?.has_next ?? data?.hasNext),
        total: Number(data?.total) || 0,
      });
    } catch (error) {
      if (import.meta.env.DEV) console.warn("AI video task page load failed", { error, page: nextPage });
      notify(error.message || "加载更多作品失败，请稍后重试。");
    } finally {
      if (queryVersion === taskQueryVersionRef.current) setIsLoadingMore(false);
    }
  }, [filters, isLoadingMore, notify, taskPage, tasksState]);

  useEffect(() => {
    let active = true;
    listAiVideoModels().then(({ items, defaultModelId }) => {
      if (!active) return;
      setModels(items); setModelsState("ready");
      const initial = items.find((item) => item.id === defaultModelId) || items[0];
      if (initial) void loadModelGenParams(initial);
    }).catch((error) => { if (active) { setModelsState("error"); notify(error.message || "模型配置加载失败，请稍后重试。"); } });
    return () => { active = false; };
  }, [loadModelGenParams, notify]);
  useEffect(() => { refreshTasks(); }, [refreshTasks]);
  useEffect(() => {
    const target = loadMoreRef.current;
    if (!target || !taskPage.hasNext || isLoadingMore || tasksState !== "ready") return undefined;
    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      observer.unobserve(target);
      void loadMoreTasks();
    }, { rootMargin: "180px 0px" });
    observer.observe(target);
    return () => observer.disconnect();
  }, [isLoadingMore, loadMoreTasks, taskPage.hasNext, tasksState]);
  // 供应商状态由 Business API 的后台任务同步；页面仅低频读取本地任务记录。
  useEffect(() => {
    const hasActiveTasks = tasks.some((task) => ["submitting", "queued", "processing", "rendering"].includes(taskState(task)) && task.id);
    if (!hasActiveTasks) return undefined;
    let cancelled = false;
    let timer;
    const poll = async () => {
      await refreshTasks({ background: true });
      if (!cancelled) timer = window.setTimeout(poll, 20_000);
    };
    timer = window.setTimeout(poll, 20_000);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [refreshTasks, tasks]);
  useEffect(() => {
    const pending = Object.values(assets).flat().filter((asset) => ["validating", "pending", "uploading"].includes(String(asset.status || "").toLowerCase()));
    if (!pending.length) return undefined;
    let cancelled = false; let timer;
    const poll = async () => {
      const updates = await Promise.all(pending.map(async (asset) => {
        try { return await getAiVideoAsset(asset.id); } catch { return asset; }
      }));
      if (cancelled) return;
      const map = new Map(updates.map((asset) => [asset.id, asset]));
      setAssets((current) => Object.fromEntries(Object.entries(current).map(([kind, values]) => [kind, values.map((asset) => map.get(asset.id) ? { ...asset, ...map.get(asset.id) } : asset)])));
      timer = window.setTimeout(poll, 1500);
    };
    timer = window.setTimeout(poll, 900);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [assets]);
  useEffect(() => {
    if (!selected || modelParamsState !== "ready") { setQuote(null); return undefined; }
    let active = true; setQuote(null);
    quoteAiVideoTask({ modelId: selected.id, playModeId: form.playMode, resolution: form.resolution, durationSeconds: Number(quoteDuration) || undefined }).then((next) => { if (active) setQuote(next); }).catch(() => { if (active) setQuote({ credits: activeModel?.creditCost ?? selected.creditCost }); });
    return () => { active = false; };
  }, [activeModel?.creditCost, form.playMode, form.resolution, modelParamsState, quoteDuration, selected]);

  const categories = useMemo(() => ["全部", ...new Set(models.map((model) => model.category).filter(Boolean))], [models]);
  const visibleModels = useMemo(() => models.filter((model) => (category === "全部" || model.category === category) && `${model.name} ${model.provider}`.toLowerCase().includes(search.trim().toLowerCase())), [category, models, search]);
  const setValue = (name, value) => setForm((current) => ({ ...current, [name]: value }));
  const retryTask = async (taskId) => { try { await retryAiVideoTask(taskId); notify("任务已重新提交。"); refreshTasks(); } catch (error) { notify(error.message || "重试失败，请稍后再试。"); } };

  const chooseModel = (model) => {
    setAssets({ image: [], video: [], audio: [] }); setReferences([]); setProjectId(""); setDraftState("idle"); setShowModels(false); setShowPlayModes(false); void loadModelGenParams(model);
  };
  const choosePlayMode = (mode) => {
    const modeModel = modelForPlayMode(selected, optionValue(mode));
    const defaults = modelDefaults(modeModel);
    setForm((current) => ({ ...current, ...defaults, prompt: current.prompt }));
    setQuoteDuration(defaults.duration);
    // 避免切换到不支持当前素材的玩法后，隐形携带旧素材提交。
    setAssets({ image: [], video: [], audio: [] }); setReferences([]); setShowPlayModes(false);
  };
  const ensureDraft = async () => {
    if (projectId) return projectId;
    if (!selected) throw new Error("请先选择模型");
    setDraftState("loading");
    try {
      const draft = await createAiVideoDraft(); const id = draft?.project_id || draft?.projectId;
      if (!id) throw new Error("草稿接口未返回 project_id，暂不能上传素材");
      setProjectId(id); setDraftState("ready"); return id;
    } catch (error) { setDraftState("error"); throw error; }
  };
  const upload = async (kind, fileList) => {
    if (!selected || !activeModel || modelParamsState !== "ready" || !fileList?.length) return;
    const limit = activeModel[kind]?.maxCount || 0; const pending = [...fileList].slice(0, Math.max(0, limit - assets[kind].length));
    if (!pending.length) return notify(`该模型最多支持 ${limit} 个${kind === "image" ? "图片" : kind === "video" ? "视频" : "音频"}素材`);
    try {
      const id = await ensureDraft();
      const uploaded = await Promise.all(pending.map((file) => kind === "image" ? uploadAiVideoImage(id, file) : uploadAsset(id, file, kind)));
      setAssets((current) => ({ ...current, [kind]: [...current[kind], ...uploaded.map((asset, index) => ({ ...asset, filename: asset.filename || pending[index]?.name, status: kind === "image" ? "ready" : asset.status || "validating" }))] }));
    } catch (error) { notify(error.message || "素材上传失败，请重试。"); }
  };
  const submit = async () => {
    if (!selected || modelParamsState !== "ready") return notify("请等待模型玩法和参数加载完成");
    if (!form.prompt.trim()) return notify("请填写画面或镜头描述");
    if (Object.values(assets).flat().some((asset) => String(asset.status).toLowerCase() !== "ready")) return notify("请等待所有素材校验完成后再提交");
    const submittedAssets = Object.values(assets).flat();
    setSubmitting(true);
    try {
      const id = await ensureDraft();
      await submitAiVideoTask({ project_id: id, model_id: selected.id, play_mode_id: form.playMode || undefined, prompt: form.prompt.trim(), image_asset_ids: assets.image.map((asset) => asset.id), video_asset_ids: assets.video.map((asset) => asset.id), audio_asset_ids: assets.audio.map((asset) => asset.id), resolution: form.resolution || undefined, ratio: form.aspectRatio || undefined, duration_seconds: Number(form.duration) || undefined, audio_enabled: activeModel?.audioGeneration ? form.audioEnabled : false, multi_subject_references: activeModel?.multiSubject ? references : [] });
      notify("任务已提交，正在作品区等待处理。"); setAssets({ image: [], video: [], audio: [] }); setReferences([]); setForm((current) => ({ ...current, prompt: "" })); setProjectId(""); setDraftState("idle"); refreshTasks();
    } catch (error) { notify(error.message || "提交任务失败，请重试。"); } finally { setSubmitting(false); }
  };

  return <div className="dashboard-shell ai-video-shell" data-page="ai-video">
    <DashboardSidebar items={dashboardNavItems} onUnavailable={notify} />
    <div className="dashboard-workspace"><DashboardHeader credits={{ balance: user?.credit_balance ?? null }} onUnavailable={notify} />
      <main className="ai-video-main"><section className="ai-video-composer" aria-label="AI 视频参数配置">
        <header className="ai-video-composer__header"><div><p>AI VIDEO STUDIO</p><h1>视频生成</h1></div><button type="button" onClick={() => { const defaults = modelDefaults(activeModel || selected || { resolutions: [], aspectRatios: [], duration: { options: [], min: "" } }); setForm({ prompt: "", ...defaults }); setQuoteDuration(defaults.duration); setAssets({ image: [], video: [], audio: [] }); setReferences([]); setProjectId(""); }}><Clock />重置</button></header>
        <button type="button" className="ai-video-model-trigger" onClick={() => setShowModels(true)} disabled={modelsState !== "ready"}>{selected?.coverUrl && <span className="ai-video-model-trigger__blur" aria-hidden="true" style={{ backgroundImage: `url("${selected.coverUrl}")` }} />}<span className="ai-video-model-trigger__shade" aria-hidden="true" />{selected ? <><ModelCover model={selected} /><span className="ai-video-model-trigger__copy"><strong>{selected.name}</strong><Info aria-hidden="true" title={selected.provider || "模型信息"} /></span></> : <span className="ai-video-model-trigger__copy"><strong>{modelsState === "loading" ? "正在加载可用模型…" : "选择视频模型"}</strong></span>}<CaretDown aria-hidden="true" /></button>
        {selected && modelParamsState === "loading" && <p className="ai-video-model-params-state">正在加载玩法与生成参数…</p>}
        {selected && modelParamsState === "error" && <p className="ai-video-model-params-state is-error">玩法和参数加载失败，请重新选择模型。</p>}
        {selected && modelParamsState === "ready" && activeModel && <><PlayModeSelector modes={playModes} activeMode={activePlayMode} open={showPlayModes} onToggle={() => setShowPlayModes((value) => !value)} onSelect={choosePlayMode} />
          {[["图片列表", "image"], ["视频列表", "video"], ["音频列表", "audio"]].map(([title, kind]) => <AssetField key={kind} title={title} kind={kind} capability={activeModel[kind]} assets={assets[kind]} allowReferences={activeModel[kind]?.supportsMention} referencedIds={references} onReference={(asset) => {
            const marker = promptMarker(asset.id);
            setReferences((current) => current.includes(asset.id) ? current : [...current, asset.id]);
            setForm((current) => ({ ...current, prompt: current.prompt.includes(marker) ? current.prompt : `${current.prompt}${current.prompt ? " " : ""}${marker}` }));
          }} onUpload={upload} onRemove={(index) => {
            const removed = assets[kind][index];
            setAssets((current) => ({ ...current, [kind]: current[kind].filter((_, itemIndex) => itemIndex !== index) }));
            setReferences((current) => current.filter((id) => id !== removed?.id));
            setForm((current) => ({ ...current, prompt: current.prompt.split(promptMarker(removed?.id || "")).join("") }));
          }} />)}
          <div className="ai-video-prompt"><div className="ai-video-prompt__label"><span>提示词{activeModel.multiSubject && <small>输入 @ 引用素材；系统会自动补充素材用途说明</small>}</span><MentionPrompt ref={promptRef} value={form.prompt} assets={referenceAssets} enabled={referenceAssets.length > 0} onChange={(value) => setValue("prompt", value)} onMentionChange={updateMention} onPreview={setMentionPreview} onKeyDown={(event) => { if (!mentionAssets.length || !mention) return; if (event.key === "ArrowDown") { event.preventDefault(); setMentionIndex((current) => (current + 1) % mentionAssets.length); } else if (event.key === "ArrowUp") { event.preventDefault(); setMentionIndex((current) => (current - 1 + mentionAssets.length) % mentionAssets.length); } else if (event.key === "Enter") { event.preventDefault(); chooseMention(mentionAssets[mentionIndex] || mentionAssets[0]); } else if (event.key === "Escape") { event.preventDefault(); setMention(null); } }} onBlur={() => window.setTimeout(() => setMention(null), 120)} placeholder={activeModel.multiSubject ? "描述画面或镜头；输入 @ 可引用素材" : "输入画面或镜头描述文本"} /></div>{mention && <div className="ai-video-mention-menu" style={mention.position} role="listbox" aria-label="选择引用素材"><strong>选择素材</strong>{mentionAssets.length ? mentionAssets.map((asset, index) => { const previewUrl = asset.cdn_url || asset.cdnUrl || asset.url; return <button type="button" role="option" aria-selected={index === mentionIndex} className={index === mentionIndex ? "is-active" : ""} key={asset.id} onMouseDown={(event) => event.preventDefault()} onClick={() => chooseMention(asset)}>{previewUrl ? <img src={previewUrl} alt="" /> : <ImageSquare />}<span>{asset.referenceLabel} · {asset.filename || asset.name || "素材"}</span></button>; }) : <p>没有匹配的已上传素材</p>}</div>}{mentionPreview && <MentionPreview preview={mentionPreview} onClose={() => setMentionPreview(null)} />}</div>
          <CapabilityParameters model={activeModel} form={form} setValue={setValue} onDurationCommit={setQuoteDuration} />
        </>}
        <button type="button" className="ai-video-submit" onClick={submit} disabled={!selected || modelParamsState !== "ready" || submitting || modelsState !== "ready" || !quote || hasUnreadyAssets || String(form.duration) !== String(quoteDuration)}><span>{submitting ? <SpinnerGap className="ai-video-spin" /> : <Lightning weight="fill" />}{submitting ? "正在提交" : hasUnreadyAssets ? "素材校验中" : String(form.duration) !== String(quoteDuration) ? "计算费用中" : "提交任务"}</span><strong>{quote?.credits ?? "—"} 积分</strong></button>
        {draftState === "error" && <p className="ai-video-draft-hint">素材空间创建失败；请重新选择模型或稍后重试。</p>}
      </section>
      <section className="ai-video-gallery" aria-label="作品记录展示区"><header className="ai-video-gallery__header"><div><p>作品记录</p><small>按创建时间筛选你的图片与视频任务</small></div><div className="ai-video-gallery__filters"><button type="button" onClick={() => setShowDateFilter((value) => !value)}><Clock />时间<CaretDown /></button><FilterSelect label="生成类型" value={filters.type} options={[{ id: "all", label: "全部" }, { id: "image", label: "图片" }, { id: "video", label: "视频" }]} onChange={(value) => setFilters((current) => ({ ...current, type: value }))} /><button type="button" onClick={() => setFilters((current) => ({ ...current, view: current.view === "list" ? "grid" : "list" }))}>{filters.view === "list" ? <GridFour /> : <ListBullets />}{filters.view === "list" ? "纯图模式" : "任务列表"}</button></div></header>
        {showDateFilter && <DateFilter filters={filters} onChange={(next) => setFilters((current) => ({ ...current, ...next }))} onClose={() => setShowDateFilter(false)} />}
        <TaskGallery tasks={tasks} state={tasksState} view={filters.view} onRefresh={refreshTasks} onRetry={retryTask} />
        {tasksState === "ready" && tasks.length > 0 && <div ref={loadMoreRef} className="ai-video-load-more" aria-live="polite">{isLoadingMore ? <><SpinnerGap className="ai-video-spin" />正在加载更多…</> : taskPage.hasNext ? "下滑加载更多" : "没有更多数据啦"}</div>}
        {showModels && <ModelPicker models={visibleModels} allCategories={categories} category={category} search={search} onCategory={setCategory} onSearch={setSearch} onChoose={chooseModel} selectedId={selectedId} onClose={() => setShowModels(false)} />}
      </section></main>
    </div><DashboardMobileNav items={dashboardNavItems} onUnavailable={notify} />{toast.message && <DashboardToast key={toast.id} message={toast.message} onClose={() => setToast(({ id }) => ({ id, message: "" }))} />}
  </div>;
}

function ModelCover({ model }) { return model.coverUrl ? <img src={model.coverUrl} alt="" /> : <span className="ai-video-model-cover" aria-hidden="true"><FilmSlate /></span>; }
function PlayModeSelector({ modes, activeMode, open, onToggle, onSelect }) { return <section className="ai-video-play-mode"><button type="button" className="ai-video-play-mode__trigger" onClick={onToggle} aria-expanded={open}><span><strong>{labelOf(activeMode)}</strong>{activeMode.hot && <em>Hot</em>}</span><span>更多玩法 <CaretDown aria-hidden="true" /></span></button>{open && <div className="ai-video-play-mode__menu" role="listbox" aria-label="玩法选择">{modes.map((mode) => { const active = optionValue(mode) === optionValue(activeMode); return <button type="button" role="option" aria-selected={active} className={active ? "is-active" : ""} key={optionValue(mode)} onClick={() => onSelect(mode)}><span><strong>{labelOf(mode)}</strong>{mode.hot && <em>Hot</em>}<small>{mode.description || "根据当前模型能力自动配置生成参数。"}</small></span>{active && <Check weight="bold" aria-hidden="true" />}</button>; })}</div>}</section>; }
function Field({ title, children }) { return <label className="ai-video-field"><span>{title}</span>{children}</label>; }
function mentionFilename(asset) { return String(asset?.referenceLabel || asset?.filename || asset?.name || "素材"); }
function truncateMentionFilename(value, limit = 12) {
  let width = 0; let output = "";
  for (const character of Array.from(String(value))) {
    const nextWidth = character.codePointAt(0) > 0xff ? 2 : 1;
    if (width + nextWidth > limit) return `${output}...`;
    output += character; width += nextWidth;
  }
  return output;
}
function editorText(node) {
  return Array.from(node.childNodes).map((child) => {
    if (child.nodeType === Node.TEXT_NODE) return child.data;
    if (child.nodeType === Node.ELEMENT_NODE && child.dataset.mentionToken) return child.dataset.mentionToken;
    if (child.nodeName === "BR") return "\n";
    return editorText(child);
  }).join("");
}
function createMentionChip(asset) {
  const chip = document.createElement("span");
  chip.className = "ai-video-prompt__mention";
  chip.contentEditable = "false";
  chip.dataset.mentionToken = asset.promptToken || promptMarker(asset.id || "");
  chip.dataset.assetId = asset.id || "";
  chip.title = mentionFilename(asset);
  const name = document.createElement("span");
  name.className = "ai-video-prompt__mention-name";
  name.textContent = `@${truncateMentionFilename(mentionFilename(asset))}`;
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "ai-video-prompt__mention-remove";
  remove.dataset.mentionRemove = "true";
  remove.setAttribute("aria-label", `移除引用 ${mentionFilename(asset)}`);
  remove.textContent = "×";
  chip.append(name, remove);
  return chip;
}
function renderPromptEditor(editor, value, assets) {
  const byToken = new Map(assets.filter((asset) => asset.id && asset.promptToken).map((asset) => [asset.promptToken, asset]));
  const tokens = [...byToken.keys()].sort((left, right) => right.length - left.length);
  editor.replaceChildren();
  if (!tokens.length || !value) { if (value) editor.append(document.createTextNode(value)); return; }
  const expression = new RegExp(tokens.map((token) => token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "g");
  let cursor = 0; let match;
  while ((match = expression.exec(value))) {
    if (match.index > cursor) editor.append(document.createTextNode(value.slice(cursor, match.index)));
    editor.append(createMentionChip(byToken.get(match[0])));
    cursor = match.index + match[0].length;
  }
  if (cursor < value.length) editor.append(document.createTextNode(value.slice(cursor)));
}
function selectionPreviousNode(range, editor) {
  if (range.startContainer.nodeType === Node.TEXT_NODE && range.startOffset === 0) return range.startContainer.previousSibling;
  if (range.startContainer === editor && range.startOffset > 0) return editor.childNodes[range.startOffset - 1];
  return null;
}
function selectionNextNode(range, editor) {
  if (range.startContainer.nodeType === Node.TEXT_NODE && range.startOffset === range.startContainer.data.length) return range.startContainer.nextSibling;
  if (range.startContainer === editor) return editor.childNodes[range.startOffset];
  return null;
}
const MentionPrompt = forwardRef(function MentionPrompt({ value, assets, enabled, onChange, onMentionChange, onPreview, onKeyDown, onBlur, placeholder }, ref) {
  const editorRef = useRef(null); const lastValueRef = useRef(""); const mentionRangeRef = useRef(null);
  const sync = useCallback(() => {
    const editor = editorRef.current; if (!editor) return "";
    const next = editorText(editor); lastValueRef.current = next; onChange(next); return next;
  }, [onChange]);
  const emitMention = useCallback(() => {
    const editor = editorRef.current; const selection = window.getSelection();
    if (!enabled || !editor || !selection?.rangeCount) { onMentionChange(null); return; }
    const range = selection.getRangeAt(0); const node = range.endContainer;
    if (!range.collapsed || node.nodeType !== Node.TEXT_NODE) { onMentionChange(null); return; }
    const before = node.data.slice(0, range.endOffset); const match = /@([^\s@]*)$/.exec(before);
    if (!match) { onMentionChange(null); return; }
    const tokenRange = range.cloneRange(); tokenRange.setStart(node, range.endOffset - match[0].length); mentionRangeRef.current = tokenRange;
    const anchor = tokenRange.getBoundingClientRect(); const host = editor.closest(".ai-video-prompt").getBoundingClientRect();
    onMentionChange({ start: 0, end: 0, query: match[1], position: { left: Math.max(0, anchor.left - host.left), top: anchor.bottom - host.top + 6 } });
  }, [enabled, onMentionChange]);
  useImperativeHandle(ref, () => ({
    insertMention(asset) {
      const editor = editorRef.current; const range = mentionRangeRef.current;
      if (!editor || !range) return "";
      range.deleteContents(); const chip = createMentionChip(asset); const spacer = document.createTextNode(" ");
      range.insertNode(spacer); range.insertNode(chip); const selection = window.getSelection(); const nextRange = document.createRange();
      nextRange.setStartAfter(spacer); nextRange.collapse(true); selection.removeAllRanges(); selection.addRange(nextRange); editor.focus(); mentionRangeRef.current = null;
      return sync();
    },
    focus() { editorRef.current?.focus(); },
  }), [sync]);
  useEffect(() => { const editor = editorRef.current; if (!editor || value === lastValueRef.current) return; renderPromptEditor(editor, value, assets); lastValueRef.current = value; }, [assets, value]);
  const previewFor = (chip) => {
    const asset = assets.find((item) => String(item.id) === chip.dataset.assetId); if (!asset) return;
    const anchor = chip.getBoundingClientRect(); const host = chip.closest(".ai-video-prompt").getBoundingClientRect();
    const top = anchor.top - host.top > 13 * 16 ? anchor.top - host.top - 13 * 16 : anchor.bottom - host.top + 8;
    onPreview({ asset, position: { left: Math.max(0, anchor.left - host.left), top } });
  };
  const restoreAfterClick = () => {
    // 单纯定位光标不应改变受控的 @ 素材节点；遇到浏览器 contenteditable 的 DOM 归一化时立即还原。
    requestAnimationFrame(() => {
      const editor = editorRef.current;
      if (editor && editorText(editor) !== value) renderPromptEditor(editor, value, assets);
    });
  };
  return <div ref={editorRef} className="ai-video-prompt__editor" contentEditable suppressContentEditableWarning role="textbox" aria-multiline="true" data-placeholder={placeholder} onInput={() => { sync(); emitMention(); }} onMouseDown={(event) => { if (event.target.closest(".ai-video-prompt__mention")) event.preventDefault(); }} onClick={(event) => { const remove = event.target instanceof HTMLElement && event.target.matches("button.ai-video-prompt__mention-remove[data-mention-remove='true']") ? event.target : null; if (remove) { event.preventDefault(); remove.closest(".ai-video-prompt__mention")?.remove(); sync(); onMentionChange(null); return; } if (event.target.closest(".ai-video-prompt__mention")) return; emitMention(); restoreAfterClick(); }} onKeyDown={(event) => { const selection = window.getSelection(); const range = selection?.rangeCount ? selection.getRangeAt(0) : null; if (range?.collapsed && (event.key === "Backspace" || event.key === "Delete")) { const node = event.key === "Backspace" ? selectionPreviousNode(range, editorRef.current) : selectionNextNode(range, editorRef.current); if (node?.dataset?.mentionToken) { event.preventDefault(); node.remove(); sync(); onMentionChange(null); return; } } onKeyDown(event); }} onKeyUp={(event) => { if (!["ArrowDown", "ArrowUp", "Enter", "Escape"].includes(event.key)) emitMention(); }} onMouseOver={(event) => { const chip = event.target.closest(".ai-video-prompt__mention"); if (chip) previewFor(chip); }} onMouseOut={(event) => { if (event.target.closest(".ai-video-prompt__mention")) onPreview(null); }} onBlur={onBlur} />;
});
function MentionPreview({ preview, onClose }) {
  const asset = preview.asset; const previewUrl = asset.cdn_url || asset.cdnUrl || asset.url;
  if (!previewUrl) return null;
  return <div className="ai-video-prompt__preview" style={preview.position} onMouseLeave={onClose}><img src={previewUrl} alt={mentionFilename(asset)} /></div>;
}

function Select({ value, onChange, options }) { return <select value={value} onChange={(event) => onChange(event.target.value)}>{options.map((item) => <option value={optionValue(item)} key={optionValue(item)}>{labelOf(item)}</option>)}</select>; }
function AssetField({ title, kind, capability, assets, onUpload, onRemove, allowReferences = false, referencedIds = [], onReference }) {
  if (!capability?.enabled) return null;
  const noun = kind === "image" ? "图片" : kind === "video" ? "视频" : "音频";
  const accepts = { image: "image/jpeg,image/png,image/webp", video: "video/mp4,video/quicktime,video/x-msvideo", audio: "audio/mpeg,audio/wav,audio/mp4,audio/aac,audio/ogg" };
  return <section className="ai-video-assets"><header><strong>{title}</strong><small>最多 {capability.maxCount} 个</small></header><div className="ai-video-assets__list">{assets.map((asset, index) => {
    const previewUrl = kind === "image" || kind === "video" ? asset.cdn_url || asset.cdnUrl || asset.url : null;
    const status = String(asset.status).toLowerCase();
    return <span className={`ai-video-assets__item${previewUrl ? " has-preview" : ""}`} key={asset.id || index} onMouseEnter={(event) => { const player = event.currentTarget.querySelector("video"); player?.play().catch(() => {}); }} onMouseLeave={(event) => { const player = event.currentTarget.querySelector("video"); if (player) { player.pause(); player.currentTime = 0; } }}>
      {previewUrl && (kind === "video" ? <video src={previewUrl} muted playsInline preload="metadata" aria-label={asset.filename || asset.name || "已上传视频"} onError={(event) => { event.currentTarget.hidden = true; }} /> : <img src={previewUrl} alt={asset.filename || asset.name || "已上传图片"} onError={(event) => { event.currentTarget.hidden = true; }} />)}
      <span className="ai-video-assets__meta"><b>{asset.filename || asset.name || noun}</b><small>{status === "ready" ? "已就绪" : status === "invalid" ? "校验失败" : "校验中"}</small></span>
      {allowReferences && status === "ready" && <button className="ai-video-assets__reference" type="button" onClick={() => onReference(asset)}>{referencedIds.includes(asset.id) ? "已引用" : "@ 引用"}</button>}
      <button type="button" onClick={() => onRemove(index)} aria-label={`移除${noun}`}><X /></button>
    </span>;
  })}{assets.length < capability.maxCount && <label className={assets.length ? "" : "is-empty"} aria-label={`上传参考${noun}`} title={`上传参考${noun}`}><Plus />{!assets.length && <span>上传参考{noun}</span>}<input type="file" multiple={capability.maxCount - assets.length > 1} accept={accepts[kind]} onChange={(event) => { onUpload(kind, event.target.files); event.target.value = ""; }} /></label>}</div></section>;
}
function SegmentedOptions({ value, onChange, options, label }) {
  return <div className={`ai-video-segmented-options ${options.length <= 3 ? "is-compact" : ""}`} role="radiogroup" aria-label={label}>{options.map((option) => {
    const optionId = optionValue(option); const active = optionId === String(value);
    return <button type="button" role="radio" aria-checked={active} className={active ? "is-active" : ""} key={optionId} onClick={() => onChange(optionId)}>{labelOf(option)}</button>;
  })}</div>;
}
function DurationSlider({ duration, value, onChange, onCommit }) {
  const discreteValues = duration.options.map(optionValue).filter((item) => Number.isFinite(Number(item)));
  const discrete = discreteValues.length > 0;
  const currentIndex = Math.max(0, discreteValues.indexOf(String(value)));
  const minimum = discrete ? 0 : Number(duration.min);
  const maximum = discrete ? discreteValues.length - 1 : Number(duration.max);
  const sliderValue = discrete ? currentIndex : Number(value || minimum);
  const selectedValue = discrete ? discreteValues[sliderValue] : sliderValue;
  const progress = maximum > minimum ? ((sliderValue - minimum) / (maximum - minimum)) * 100 : 100;
  const valueFromSlider = (rawValue) => {
    const next = Number(rawValue);
    return discrete ? discreteValues[next] : String(next);
  };
  const commit = (event) => onCommit(valueFromSlider(event.currentTarget.value));
  return <div className="ai-video-duration"><output>{selectedValue}s</output><input type="range" min={minimum} max={maximum} step={discrete ? 1 : duration.step || 1} value={sliderValue} style={{ "--duration-progress": `${progress}%` }} onChange={(event) => onChange(valueFromSlider(event.target.value))} onPointerUp={commit} onKeyUp={commit} onBlur={commit} />{duration.adaptive && <small>支持 adaptive 时长</small>}</div>;
}
function CapabilityParameters({ model, form, setValue, onDurationCommit }) { const duration = model.duration; return <section className="ai-video-parameters"><h2>生成参数</h2>{model.resolutions.length > 0 && <Field title="分辨率"><SegmentedOptions label="分辨率" value={form.resolution} onChange={(value) => setValue("resolution", value)} options={model.resolutions} /></Field>}{model.aspectRatios.length > 0 && <Field title="比例"><SegmentedOptions label="比例" value={form.aspectRatio} onChange={(value) => setValue("aspectRatio", value)} options={model.aspectRatios} /></Field>}{(duration.options.length > 0 || duration.min || duration.max) && <Field title="时长"><DurationSlider duration={duration} value={form.duration} onChange={(value) => setValue("duration", value)} onCommit={onDurationCommit} /></Field>}{model.audioGeneration && <label className="ai-video-switch"><span><strong>音频开关</strong><small>生成视频时同步生成音频</small></span><input type="checkbox" checked={form.audioEnabled} onChange={(event) => setValue("audioEnabled", event.target.checked)} /><i /></label>}</section>; }
function FilterSelect({ label, value, options, onChange }) { return <label className="ai-video-filter-select"><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)}>{options.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label>; }
function DateFilter({ filters, onChange, onClose }) { return <div className="ai-video-date-filter"><div><label>开始日期<input type="date" value={filters.startDate} onChange={(event) => onChange({ startDate: event.target.value })} /></label><b>—</b><label>结束日期<input type="date" value={filters.endDate} onChange={(event) => onChange({ endDate: event.target.value })} /></label></div>{[["", "全部"], [7, "最近一周"], [30, "最近一个月"], [90, "最近三个月"]].map(([days, text]) => <button type="button" key={text} onClick={() => { const end = new Date(); const start = days ? new Date(Date.now() - Number(days) * 86400000) : null; onChange({ startDate: start ? start.toISOString().slice(0, 10) : "", endDate: days ? end.toISOString().slice(0, 10) : "" }); onClose(); }}>{text}</button>)}</div>; }
function TaskGallery({ tasks, state, view, onRefresh, onRetry }) {
  if (state === "loading") return <div className="ai-video-gallery-state"><SpinnerGap className="ai-video-spin" />正在加载作品记录…</div>;
  if (state === "error") return <div className="ai-video-gallery-state"><p>作品记录暂时加载失败。</p><button type="button" onClick={onRefresh}>重新加载</button></div>;
  if (!tasks.length) return <div className="ai-video-gallery-state ai-video-gallery-state--empty"><FilmSlate /><strong>开始你的第一次创作</strong><p>提交任务后，生成进度与成品会显示在这里。</p></div>;
  return <div className={`ai-video-task-grid is-${view}`}>{tasks.map((task) => {
    const generating = isTaskGenerating(task);
    const taskStatus = taskState(task);
    return <article key={taskId(task)} className={`ai-video-task${generating ? " is-generating" : ""}`}>
      <div className={`ai-video-task__cover${generating ? " is-generating" : ""}`}>
        {taskImage(task) ? <img src={taskImage(task)} alt="" /> : <FilmSlate />}
        {generating && <div className="ai-video-task__loading" aria-label="AI 正在生成"><SpinnerGap className="ai-video-spin" /><small>AI 正在生成</small></div>}
        <span className={`ai-video-task__status is-${taskStatus}`}>{taskStatus === "completed" || taskStatus === "succeeded" ? "已完成" : taskStatus === "succeeded_with_partial_output" ? "部分完成" : taskStatus === "failed" ? "失败" : "处理中"}</span>
      </div>
      <div className="ai-video-task__copy"><strong>{taskTitle(task)}</strong><small>{taskKind(task) === "image" ? "图片" : "视频"} · {dateLabel(taskDate(task))}</small>{view === "list" && taskPrompt(task) && <p>{taskPrompt(task)}</p>}{taskStatus === "failed" && <button type="button" onClick={() => onRetry(taskId(task))}>重新提交</button>}</div>
    </article>;
  })}</div>;
}
function ModelPicker({ models, allCategories, category, search, onCategory, onSearch, onChoose, selectedId, onClose }) { return <section className="ai-video-model-picker" role="dialog" aria-modal="true" aria-label="选择视频模型"><header><div><strong>视频模型</strong><small>选择后将展示该模型支持的参数</small></div><button type="button" onClick={onClose} aria-label="关闭模型列表"><X /></button></header><div className="ai-video-model-picker__tools"><nav>{allCategories.map((item) => <button type="button" className={item === category ? "is-active" : ""} onClick={() => onCategory(item)} key={item}>{item}</button>)}</nav><label><MagnifyingGlass /><input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="搜索模型" /></label></div>{models.length ? <div className="ai-video-model-grid">{models.map((model) => <button type="button" className={model.id === selectedId ? "is-selected" : ""} key={model.id} onClick={() => onChoose(model)}>{model.badge && <em className="ai-video-model-card__badge">{model.badge}</em>}{model.id === selectedId && <span className="ai-video-model-card__active">使用中</span>}<ModelCover model={model} /></button>)}</div> : <p className="ai-video-model-empty">没有符合当前筛选条件的模型。</p>}</section>; }
