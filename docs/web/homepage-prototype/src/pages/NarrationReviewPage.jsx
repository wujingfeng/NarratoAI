import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  CheckCircle,
  FloppyDisk,
  Plus,
  Trash,
  WarningCircle,
} from "@phosphor-icons/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { LanguageSwitcher } from "../components/i18n/LanguageSwitcher.jsx";
import { useI18n } from "../i18n/useI18n.js";
import { ApiError } from "../services/httpClient.js";
import { createEditorDraft, readEditorDraft } from "../features/narration-editor/editor-data.js";
import { createTransitionGuard } from "../features/narration-editor/transition-guard.js";
import {
  collectReviewAssets,
  createReviewModel,
  deleteReviewRow,
  formatTimecode,
  insertReviewRow,
  materializeReviewModel,
  moveReviewRow,
  parseTimecode,
  updateReviewRow,
  validateReviewModel,
} from "../features/narration-review/review-model.js";
import {
  createDebouncedEditorSaver,
  getEditorDraft,
  getProjectStage,
  submitRender,
} from "../features/projects/projectApi.js";
import {
  normalizeStageSnapshot,
  stageIndex,
  stagePath,
} from "../features/projects/narrationStage.js";

function SourceSegment({ row, label, unavailable }) {
  const videoRef = useRef(null);

  const seekToStart = () => {
    const video = videoRef.current;
    if (!video || !Number.isFinite(row.sourceStart)) return;
    const target = Number.isFinite(video.duration)
      ? Math.min(Math.max(0, row.sourceStart), video.duration)
      : Math.max(0, row.sourceStart);
    try { video.currentTime = target; } catch {}
  };

  useEffect(() => {
    const video = videoRef.current;
    if (video?.readyState >= 1) seekToStart();
  }, [row.assetUrl, row.sourceStart]);

  if (!row.assetUrl) return <div className="review-source-empty">{unavailable}</div>;
  return (
    <video
      ref={videoRef}
      src={row.assetUrl}
      controls
      playsInline
      preload="metadata"
      aria-label={label}
      onLoadedMetadata={seekToStart}
      onPlay={(event) => {
        const time = event.currentTarget.currentTime;
        if (time < row.sourceStart || time >= row.sourceEnd) seekToStart();
      }}
      onTimeUpdate={(event) => {
        if (!Number.isFinite(row.sourceEnd) || event.currentTarget.currentTime < row.sourceEnd - 0.02) return;
        event.currentTarget.pause();
        seekToStart();
      }}
    />
  );
}

function errorKey(code) {
  return code ? `review.validation.${code}` : null;
}

export function NarrationReviewPage() {
  const { state: locationState } = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { formatNumber, t } = useI18n();
  const projectId = searchParams.get("projectId") || locationState?.projectId || "";
  const [model, setModel] = useState(null);
  const [assets, setAssets] = useState([]);
  const [projectTitle, setProjectTitle] = useState("");
  const [locked, setLocked] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saveState, setSaveState] = useState("loading");
  const [fatalError, setFatalError] = useState("");
  const [actionError, setActionError] = useState("");
  const [transition, setTransition] = useState("");
  const [showErrors, setShowErrors] = useState(false);
  const [timeInputs, setTimeInputs] = useState({});
  const saverRef = useRef(null);
  const initializedRef = useRef(false);
  const mountedRef = useRef(true);
  const transitionGuardRef = useRef(null);
  if (!transitionGuardRef.current) {
    transitionGuardRef.current = createTransitionGuard(setTransition);
  }

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (!projectId) return undefined;
    saverRef.current = createDebouncedEditorSaver(projectId);
    return () => saverRef.current?.cancel();
  }, [projectId]);

  useEffect(() => {
    let active = true;
    async function load() {
      if (!projectId) {
        setFatalError(t("review.messages.missingProject"));
        setLoading(false);
        return;
      }
      initializedRef.current = false;
      setLoading(true);
      setFatalError("");
      try {
        const [stagePayload, draftResponse] = await Promise.all([
          getProjectStage(projectId),
          getEditorDraft(projectId),
        ]);
        if (!active) return;
        const snapshot = normalizeStageSnapshot(stagePayload);
        if (stageIndex(snapshot.currentStage) < stageIndex("edit")) {
          navigate(stagePath(snapshot.currentStage, projectId), { replace: true });
          return;
        }
        const saved = readEditorDraft(draftResponse.content);
        if (!saved) throw new Error(t("review.messages.invalidDraft"));
        setAssets(snapshot.videoAssets);
        setProjectTitle(snapshot.projectTitle || projectId);
        setModel(createReviewModel(saved));
        const readOnly = Boolean(draftResponse.locked || stageIndex(snapshot.currentStage) > stageIndex("edit"));
        setLocked(readOnly);
        setSaveState(readOnly ? "locked" : "saved");
      } catch (requestError) {
        if (!active) return;
        const message = requestError instanceof ApiError && requestError.status === 404
          ? t("review.messages.draftUnavailable")
          : requestError.message || t("review.messages.readFailed");
        setFatalError(message);
      } finally {
        if (active) {
          initializedRef.current = true;
          setLoading(false);
        }
      }
    }
    load();
    return () => { active = false; };
  }, [navigate, projectId]);

  const availableAssets = useMemo(
    () => collectReviewAssets(assets, model?.rows || []),
    [assets, model?.rows],
  );
  const validation = useMemo(
    () => model ? validateReviewModel(model, availableAssets) : null,
    [availableAssets, model],
  );
  const materialized = useMemo(
    () => model ? materializeReviewModel(model) : null,
    [model],
  );
  const draft = useMemo(() => {
    if (!materialized) return null;
    return createEditorDraft({
      clips: materialized.clips,
      cues: materialized.cues,
      voiceRole: materialized.settings.voiceRole,
      volume: materialized.settings.volume,
      rate: materialized.settings.rate,
      subtitleStyle: materialized.settings.subtitleStyle,
      videoRatio: materialized.settings.videoRatio,
      backgroundMusic: materialized.settings.backgroundMusic,
    });
  }, [materialized]);
  const invalidTimeInputCount = useMemo(() => Object.values(timeInputs)
    .filter((value) => !Number.isFinite(parseTimecode(value))).length, [timeInputs]);
  const canPersist = Boolean(validation?.safeToSave && invalidTimeInputCount === 0);
  const canGenerate = Boolean(validation?.isValid && invalidTimeInputCount === 0);
  const issueCount = (validation?.errorCount || 0) + invalidTimeInputCount;
  const transitionBusy = Boolean(transition);
  const interactionLocked = locked || transitionBusy;

  useEffect(() => {
    if (!initializedRef.current || loading || locked || !draft || !canPersist || !saverRef.current) return;
    setSaveState("saving");
    saverRef.current(draft).then(() => {
      if (!mountedRef.current) return;
      setSaveState("saved");
      setActionError("");
    }).catch((requestError) => {
      if (!mountedRef.current) return;
      setSaveState("failed");
      setActionError(requestError.message || t("review.messages.saveFailed"));
    });
  }, [canPersist, draft, loading, locked]);

  const mutate = (transform) => {
    if (locked || transitionGuardRef.current.busy) return;
    setActionError("");
    setModel((current) => transform(current));
  };

  const setRow = (rowId, patch) => mutate((current) => updateReviewRow(current, rowId, patch, availableAssets));

  const timeInputKey = (rowId, field) => `${rowId}:${field}`;
  const displayedTime = (row, field) => {
    const key = timeInputKey(row.id, field);
    return Object.hasOwn(timeInputs, key) ? timeInputs[key] : formatTimecode(row[field]);
  };
  const changeTime = (row, field, value) => {
    const key = timeInputKey(row.id, field);
    setTimeInputs((current) => ({ ...current, [key]: value }));
    const parsed = parseTimecode(value);
    if (Number.isFinite(parsed)) setRow(row.id, { [field]: parsed });
  };
  const settleTime = (row, field) => {
    const key = timeInputKey(row.id, field);
    const value = timeInputs[key];
    if (value === undefined || !Number.isFinite(parseTimecode(value))) return;
    setTimeInputs((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
  };
  const clearRowTimes = (rowId) => setTimeInputs((current) => {
    const next = { ...current };
    delete next[timeInputKey(rowId, "sourceStart")];
    delete next[timeInputKey(rowId, "sourceEnd")];
    return next;
  });
  const fieldError = (row, field) => {
    const value = timeInputs[timeInputKey(row.id, field)];
    if (value !== undefined && !Number.isFinite(parseTimecode(value))) return "timecode";
    return validation?.rowErrors[row.id]?.[field] || null;
  };

  const queueAndFlush = async () => {
    if (locked) return;
    if (!canPersist || !draft || !saverRef.current) {
      setShowErrors(true);
      throw new Error(t("review.messages.fixBeforeSave"));
    }
    setSaveState("saving");
    setActionError("");
    saverRef.current(draft).catch(() => {});
    await saverRef.current.flush();
    if (mountedRef.current) setSaveState("saved");
  };

  const saveNow = async () => {
    const action = "save";
    if (locked || !transitionGuardRef.current.begin(action)) return;
    try {
      await queueAndFlush();
    } catch (requestError) {
      setSaveState("failed");
      setActionError(requestError.message || t("review.messages.saveFailed"));
    } finally {
      transitionGuardRef.current.end(action);
    }
  };

  const openEditor = async () => {
    const action = "switch";
    if (!transitionGuardRef.current.begin(action)) return;
    try {
      if (locked) {
        navigate(`/dashboard/narration/editor?projectId=${encodeURIComponent(projectId)}`);
        return;
      }
      await queueAndFlush();
      saverRef.current?.cancel();
      navigate(`/dashboard/narration/editor?projectId=${encodeURIComponent(projectId)}`);
    } catch (requestError) {
      setSaveState("failed");
      setActionError(requestError.message || t("review.messages.switchFailed"));
    } finally {
      transitionGuardRef.current.end(action);
    }
  };

  const generate = async () => {
    const action = "generate";
    if (locked || !transitionGuardRef.current.begin(action)) return;
    if (!canGenerate) {
      setShowErrors(true);
      setActionError(t("review.messages.fixBeforeGenerate"));
      transitionGuardRef.current.end(action);
      return;
    }
    try {
      await queueAndFlush();
      saverRef.current?.cancel();
      await submitRender(projectId);
      navigate(stagePath("render", projectId), { replace: true });
    } catch (requestError) {
      setSaveState("failed");
      setActionError(requestError.message || t("review.messages.generateFailed"));
    } finally {
      transitionGuardRef.current.end(action);
    }
  };

  if (loading) return <main className="narration-review-shell"><p className="review-page-state">{t("review.messages.loading")}</p></main>;
  if (fatalError || !model) return <main className="narration-review-shell"><p className="review-page-state" role="alert">{fatalError || t("review.messages.invalidDraft")}</p></main>;

  const statusText = locked
    ? t("review.status.locked")
    : saveState === "saving"
      ? t("review.status.saving")
      : saveState === "failed"
        ? t("review.status.failed")
        : t("review.status.saved");

  return (
    <main className="narration-review-shell" data-page="narration-review" data-testid="narration-review">
      <h1 className="sr-only" data-route-heading tabIndex="-1">{t("review.routeHeading")}</h1>
      <header className="review-topbar">
        <div className="review-topbar__identity">
          <button type="button" className="review-mode" onClick={openEditor} disabled={transitionBusy} data-testid="review-editor-mode">
            <ArrowLeft aria-hidden="true" />{transition === "switch" ? t("review.actions.switching") : t("review.actions.editorMode")}
          </button>
          <i aria-hidden="true" />
          <div>
            <strong>{projectTitle || projectId}</strong>
            <small>{t("review.heading")}</small>
          </div>
        </div>
        <div className="review-topbar__actions">
          <span className={`review-save-state is-${saveState}`} role="status">
            {saveState === "failed" ? <WarningCircle weight="fill" /> : <CheckCircle weight="fill" />}{statusText}
          </span>
          <LanguageSwitcher compact />
          <button type="button" className="review-save" onClick={saveNow} disabled={interactionLocked || !canPersist} data-testid="review-save">
            <FloppyDisk aria-hidden="true" />{t("review.actions.save")}
          </button>
          <button type="button" className="review-generate" onClick={generate} disabled={interactionLocked || !canGenerate} data-testid="review-generate">
            {transition === "generate" ? t("review.actions.generating") : t("review.actions.generate")}
          </button>
        </div>
      </header>

      <section className="review-intro" aria-labelledby="review-visible-heading">
        <div>
          <p>{t("review.eyebrow")}</p>
          <h2 id="review-visible-heading">{t("review.heading")}</h2>
          <span>{t("review.description")}</span>
        </div>
        <div className={`review-validation-summary ${canGenerate ? "is-ready" : "is-pending"}`} role="status" data-testid="review-validation">
          {canGenerate ? <CheckCircle weight="fill" /> : <WarningCircle weight="fill" />}
          <span>{canGenerate
            ? t("review.validation.ready", { count: formatNumber(model.rows.length) })
            : t("review.validation.pending", { count: formatNumber(issueCount) })}</span>
        </div>
      </section>

      {locked && <p className="review-notice">{t("review.messages.readOnly")}</p>}
      {actionError && <p className="review-action-error" role="alert">{actionError}</p>}
      {showErrors && validation.generalError && <p className="review-action-error" role="alert">{t(errorKey(validation.generalError))}</p>}

      <section className="review-content" aria-label={t("review.contentLabel")}>
        <div className="review-column-head" aria-hidden="true">
          <span>{t("review.columns.sequence")}</span>
          <span>{t("review.columns.source")}</span>
          <span>{t("review.columns.timecode")}</span>
          <span>{t("review.columns.picture")}</span>
          <span>{t("review.columns.script")}</span>
          <span>{t("review.columns.originalSound")}</span>
          <span>{t("review.columns.actions")}</span>
        </div>

        <div className="review-row-list">
          {model.rows.map((row, index) => {
            const number = index + 1;
            const startError = fieldError(row, "sourceStart");
            const endError = fieldError(row, "sourceEnd");
            const assetError = validation.rowErrors[row.id]?.asset;
            const scriptError = validation.rowErrors[row.id]?.text;
            const rowError = validation.rowErrors[row.id]?.row;
            return (
              <article className="review-row" key={row.id} data-testid={`review-row-${number}`} aria-label={t("review.rowLabel", { number: formatNumber(number) })}>
                <div className="review-cell review-sequence" data-label={t("review.columns.sequence")}><strong>{formatNumber(number)}</strong></div>

                <div className="review-cell review-source" data-label={t("review.columns.source")}>
                  <SourceSegment
                    row={row}
                    label={t("review.sourcePreview", { number: formatNumber(number) })}
                    unavailable={t("review.messages.previewUnavailable")}
                  />
                  <label>
                    <span className="sr-only">{t("review.assetSelect", { number: formatNumber(number) })}</span>
                    <select
                      value={row.assetId}
                      disabled={interactionLocked}
                      aria-invalid={Boolean(assetError)}
                      onChange={(event) => {
                        clearRowTimes(row.id);
                        setRow(row.id, { assetId: event.target.value });
                      }}
                      data-testid={`review-asset-${number}`}
                    >
                      {!availableAssets.length && <option value="">{t("review.messages.noAssets")}</option>}
                      {availableAssets.map((asset) => <option key={asset.id} value={asset.id}>{asset.filename}</option>)}
                    </select>
                  </label>
                  {(showErrors || assetError) && assetError && <small className="review-field-error">{t(errorKey(assetError))}</small>}
                </div>

                <div className="review-cell review-timecode" data-label={t("review.columns.timecode")}>
                  <label>
                    <span>{t("review.fields.start")}</span>
                    <input
                      type="text"
                      inputMode="decimal"
                      value={displayedTime(row, "sourceStart")}
                      disabled={interactionLocked}
                      aria-invalid={Boolean(startError)}
                      aria-label={t("review.timeInput", { field: t("review.fields.start"), number: formatNumber(number) })}
                      onChange={(event) => changeTime(row, "sourceStart", event.target.value)}
                      onBlur={() => settleTime(row, "sourceStart")}
                      data-testid={`review-start-${number}`}
                    />
                    {startError && <small className="review-field-error">{t(errorKey(startError))}</small>}
                  </label>
                  <label>
                    <span>{t("review.fields.end")}</span>
                    <input
                      type="text"
                      inputMode="decimal"
                      value={displayedTime(row, "sourceEnd")}
                      disabled={interactionLocked}
                      aria-invalid={Boolean(endError)}
                      aria-label={t("review.timeInput", { field: t("review.fields.end"), number: formatNumber(number) })}
                      onChange={(event) => changeTime(row, "sourceEnd", event.target.value)}
                      onBlur={() => settleTime(row, "sourceEnd")}
                      data-testid={`review-end-${number}`}
                    />
                    {endError && <small className="review-field-error">{t(errorKey(endError))}</small>}
                  </label>
                </div>

                <div className="review-cell review-picture" data-label={t("review.columns.picture")}>
                  <textarea
                    value={row.picture}
                    disabled={interactionLocked}
                    aria-label={t("review.pictureInput", { number: formatNumber(number) })}
                    placeholder={t("review.placeholders.picture")}
                    onChange={(event) => setRow(row.id, { picture: event.target.value })}
                    data-testid={`review-picture-${number}`}
                  />
                </div>

                <div className="review-cell review-script" data-label={t("review.columns.script")}>
                  <textarea
                    value={row.text}
                    disabled={interactionLocked}
                    aria-invalid={Boolean(scriptError)}
                    aria-label={t("review.scriptInput", { number: formatNumber(number) })}
                    placeholder={t("review.placeholders.script")}
                    onChange={(event) => setRow(row.id, { text: event.target.value })}
                    data-testid={`review-script-${number}`}
                  />
                  {scriptError && <small className="review-field-error">{t(errorKey(scriptError))}</small>}
                  {rowError && <small className="review-field-error">{t(errorKey(rowError))}</small>}
                </div>

                <div className="review-cell review-original" data-label={t("review.columns.originalSound")}>
                  <label className="review-switch">
                    <input
                      type="checkbox"
                      checked={row.originalSound}
                      disabled={interactionLocked}
                      onChange={(event) => setRow(row.id, { originalSound: event.target.checked })}
                      aria-label={t("review.originalSoundInput", { number: formatNumber(number) })}
                      data-testid={`review-original-${number}`}
                    />
                    <span aria-hidden="true"><i /></span>
                    <b>{row.originalSound ? t("review.values.yes") : t("review.values.no")}</b>
                  </label>
                </div>

                <div className="review-cell review-operations" data-label={t("review.columns.actions")}>
                  <button type="button" className="is-danger" disabled={interactionLocked || model.rows.length === 1} aria-label={t("review.actions.deleteRow", { number: formatNumber(number) })} onClick={() => {
                    clearRowTimes(row.id);
                    mutate((current) => deleteReviewRow(current, row.id));
                  }}>
                    <Trash aria-hidden="true" />{t("review.actions.delete")}
                  </button>
                  <button type="button" disabled={interactionLocked || index === 0} aria-label={t("review.actions.moveUpRow", { number: formatNumber(number) })} onClick={() => mutate((current) => moveReviewRow(current, row.id, -1))}>
                    <ArrowUp aria-hidden="true" />{t("review.actions.moveUp")}
                  </button>
                  <button type="button" disabled={interactionLocked || index === model.rows.length - 1} aria-label={t("review.actions.moveDownRow", { number: formatNumber(number) })} onClick={() => mutate((current) => moveReviewRow(current, row.id, 1))}>
                    <ArrowDown aria-hidden="true" />{t("review.actions.moveDown")}
                  </button>
                  <button type="button" disabled={interactionLocked} aria-label={t("review.actions.insertAfterRow", { number: formatNumber(number) })} onClick={() => mutate((current) => insertReviewRow(current, row.id, availableAssets))}>
                    <Plus aria-hidden="true" />{t("review.actions.insertAfter")}
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </main>
  );
}
