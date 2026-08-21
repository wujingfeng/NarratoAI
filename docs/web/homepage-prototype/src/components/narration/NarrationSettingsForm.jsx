import { CaretUp, Check, MusicNotes, Trash, UploadSimple } from "@phosphor-icons/react";
import { useEffect, useId, useRef, useState } from "react";
import { useI18n } from "../../i18n/useI18n.js";

const ACCENT_CLASSES = ["blue", "violet", "pink", "orange"];

function voiceDetails(voice, index) {
  return {
    accent: ACCENT_CLASSES[index % ACCENT_CLASSES.length],
    initial: voice.name.slice(0, 1),
    tags: [...new Set([
      voice.gender,
      ...(Array.isArray(voice.styles) ? voice.styles : []),
      ...(Array.isArray(voice.languages) ? voice.languages : []),
      voice.provider_code,
    ].filter(Boolean))].slice(0, 4),
  };
}

function VoiceGrid({ voices, value, onChange }) {
  const { t } = useI18n();
  return (
    <div className="narration-voice-grid" role="radiogroup" aria-label={t("narration.form.voiceCatalog")}>
      {voices.map((voice, index) => {
        const selected = voice.id === value;
        const details = voiceDetails(voice, index);
        return (
          <div
            className={`narration-voice-tile narration-voice-tile--${details.accent} ${selected ? "is-selected" : ""}`}
            key={voice.id}
          >
            <button className="narration-voice-tile__select" type="button" role="radio" aria-checked={selected} onClick={() => onChange(voice.id)}>
              <span className="narration-voice-tile__identity">
                <span className="narration-voice-tile__avatar">{details.initial}</span>
                <span className="narration-voice-tile__name"><b>{voice.name}</b></span>
              </span>
              <span className="narration-voice-tile__tags">{details.tags.map((tag) => <i key={tag}>{tag}</i>)}</span>
            </button>
            <span className="narration-voice-tile__demo">
              <small>{t("narration.form.voiceSample")}</small>
              {voice.sample_url
                ? <audio controls preload="none" src={voice.sample_url}>{t("narration.form.voiceSampleUnsupported")}</audio>
                : <b>{t("narration.form.voiceSampleUnavailable")}</b>}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function BackgroundMusicPicker({ music, volume, isUploading, error, disabled, onUpload, onRemove, onVolumeChange }) {
  const inputRef = useRef(null);
  const audioRef = useRef(null);
  const inputId = useId();
  const volumeId = useId();

  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = volume / 100;
  }, [volume, music?.playbackUrl]);

  const selectFile = (event) => {
    const [file] = event.target.files || [];
    if (file) onUpload(file);
    // 允许选择同一首音乐进行替换。
    event.target.value = "";
  };

  return <fieldset className="narration-fieldset narration-bgm-picker">
    <legend>背景音乐 <small>可选</small></legend>
    <p className="narration-bgm-picker__hint">上传一首音乐作为解说背景；可在此试听并调整最终混音音量。</p>
    {!music && <div className={`narration-bgm-upload ${disabled ? "is-disabled" : ""}`}>
      <MusicNotes aria-hidden="true" />
      <div><strong>添加背景音乐</strong><span>支持 MP3、WAV、M4A、AAC、OGG，单个文件不超过 100 MiB</span></div>
      <label className="narration-bgm-upload__action" htmlFor={inputId}>
        <UploadSimple aria-hidden="true" /> {isUploading ? "上传中…" : "选择音频"}
      </label>
      <input ref={inputRef} id={inputId} type="file" accept="audio/mpeg,audio/wav,audio/x-wav,audio/mp4,audio/aac,audio/ogg,.mp3,.wav,.m4a,.aac,.ogg" disabled={disabled || isUploading} onChange={selectFile} />
    </div>}
    {music && <div className="narration-bgm-player">
      <div className="narration-bgm-player__file"><span><MusicNotes aria-hidden="true" /></span><div><strong title={music.fileName}>{music.fileName}</strong><small>{music.status === "ready" ? "背景音乐已就绪" : music.status === "validating" ? "正在校验背景音乐…" : "正在上传背景音乐…"}</small></div><button type="button" onClick={() => inputRef.current?.click()} disabled={disabled || isUploading}>替换</button><button className="narration-bgm-player__remove" type="button" onClick={onRemove} disabled={isUploading} aria-label="移除背景音乐"><Trash aria-hidden="true" /></button></div>
      <input ref={inputRef} id={inputId} className="sr-only" type="file" accept="audio/mpeg,audio/wav,audio/x-wav,audio/mp4,audio/aac,audio/ogg,.mp3,.wav,.m4a,.aac,.ogg" disabled={disabled || isUploading} onChange={selectFile} />
      {music.status === "ready" && music.playbackUrl ? <audio ref={audioRef} controls preload="metadata" src={music.playbackUrl}>你的浏览器不支持音频试听。</audio> : <p className="narration-bgm-player__pending">正在校验背景音乐，校验通过后可试听。</p>}
      <label className="narration-bgm-volume" htmlFor={volumeId}><span>背景音乐音量</span><input id={volumeId} type="range" min="0" max="100" step="1" value={volume} onChange={(event) => onVolumeChange(Number(event.target.value))} disabled={isUploading} aria-valuetext={`${volume}%`} /><output htmlFor={volumeId}>{volume}%</output></label>
    </div>}
    {disabled && <p className="narration-bgm-picker__notice" role="status">请先从“创建项目”上传视频素材后，再添加背景音乐。</p>}
    {error && <p className="narration-bgm-picker__error" role="alert">{error}</p>}
  </fieldset>;
}

export function NarrationSettingsForm({
  config,
  executionMode,
  selectedStyle,
  selectedOriginalSoundRatio,
  selectedRatio,
  selectedVoice,
  selectedSubtitle,
  customStyle,
  requirements,
  backgroundMusic,
  backgroundMusicVolume,
  backgroundMusicUploading,
  backgroundMusicError,
  backgroundMusicDisabled,
  disabled = false,
  onExecutionModeChange,
  onStyleChange,
  onOriginalSoundRatioChange,
  onRatioChange,
  onVoiceChange,
  onSubtitleChange,
  onCustomStyleChange,
  onRequirementsChange,
  onBackgroundMusicUpload,
  onBackgroundMusicRemove,
  onBackgroundMusicVolumeChange,
}) {
  const { formatNumber, t } = useI18n();
  const [customStyleTouched, setCustomStyleTouched] = useState(false);
  const custom = Boolean(config.narration_styles.find((item) => item.id === selectedStyle)?.is_custom);
  const customStyleInvalid = custom && customStyleTouched && !customStyle.trim();
  return <section className={`narration-settings ${disabled ? "is-locked" : ""}`} aria-label={t("narration.form.label")} aria-disabled={disabled}>
    <fieldset className="narration-fieldset narration-mode-picker">
      <legend>{t("narration.form.mode.title")}</legend>
      <p className="narration-mode-picker__hint">{t("narration.form.mode.hint")}</p>
      <div className="narration-mode-grid" role="radiogroup" aria-label={t("narration.form.mode.title")}>
        {(["manual", "auto"]).map((mode) => {
          const selected = executionMode === mode;
          return <label className={`narration-mode-card ${selected ? "is-selected" : ""}`} key={mode}>
            <input type="radio" name="narration-execution-mode" value={mode} checked={selected} onChange={() => onExecutionModeChange(mode)} />
            <span><strong>{t(`narration.form.mode.${mode}.name`)}</strong><small>{t(`narration.form.mode.${mode}.description`)}</small></span>
            {selected && <Check weight="bold" aria-hidden="true" />}
          </label>;
        })}
      </div>
    </fieldset>
    <fieldset className="narration-fieldset narration-style-picker"><legend>{t("narration.form.style")}</legend><div className="narration-style-grid" role="radiogroup" aria-label={t("narration.form.style")}>{config.narration_styles.map((item, index) => { const selected = selectedStyle === item.id; return <label className={`narration-style-card narration-style-card--${index % 4} ${selected ? "is-selected" : ""}`} key={item.id}><input className="narration-style-card__input" type="radio" name="narration-style" value={item.id} checked={selected} onChange={() => onStyleChange(item.id)} /><span className="narration-style-card__topline"><span>{item.eyebrow}</span>{selected && <span className="narration-selected"><Check weight="bold" aria-hidden="true" /></span>}</span><strong>{item.name}</strong><small>{item.description}</small><span className="narration-style-card__tags">{item.tags.map((tag) => <i key={tag}>{tag}</i>)}</span></label>; })}</div>{custom && <label className="narration-custom-style"><span className="narration-custom-style__label">自定义解说类型 <em>必填</em></span><span className={`narration-custom-style__control ${customStyleInvalid ? "is-invalid" : ""}`}><input value={customStyle} maxLength="50" required aria-invalid={customStyleInvalid} aria-describedby={customStyleInvalid ? "narration-custom-style-hint narration-custom-style-error" : "narration-custom-style-hint"} onBlur={() => setCustomStyleTouched(true)} onChange={(event) => onCustomStyleChange(event.target.value)} placeholder="例如：职场逆袭、校园青春、科幻悬疑" /><span aria-hidden="true">{customStyle.length}/50</span></span><small id="narration-custom-style-hint">填写后将按该题材调整解说表达。</small>{customStyleInvalid && <small className="narration-custom-style__error" id="narration-custom-style-error" role="alert">请输入自定义解说类型。</small>}</label>}</fieldset>
    <fieldset className="narration-fieldset narration-original-sound-picker">
      <legend>{t("narration.form.originalSoundRatio")}</legend>
      <label>
        <select value={selectedOriginalSoundRatio} disabled={disabled} onChange={(event) => onOriginalSoundRatioChange(Number(event.target.value))}>
          {(config.original_sound_ratios || [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]).map((value) => <option value={value} key={value}>{value}%</option>)}
        </select>
        <small>{t("narration.form.originalSoundRatioHint")}</small>
      </label>
    </fieldset>
    <fieldset className="narration-fieldset narration-ratio-picker"><legend>{t("narration.form.ratio")}</legend><div className="narration-ratio-grid">{config.video_ratios.map((item) => { const selected = selectedRatio === item.id; return <label className={`narration-ratio ${selected ? "is-selected" : ""}`} data-ratio={item.id.replace(":", "-")} key={item.id}><input className="narration-ratio__input" type="radio" name="narration-video-ratio" value={item.id} checked={selected} onChange={() => onRatioChange(item.id)} /><span className="narration-ratio__visual" aria-hidden="true"><span /></span><span className="narration-ratio__label">{item.name}</span>{selected && <Check className="narration-ratio__check" weight="bold" aria-hidden="true" />}</label>; })}</div></fieldset>
    <fieldset className="narration-fieldset narration-subtitle-picker"><legend>{t("narration.form.subtitle")}</legend><div className="narration-subtitle-grid">{config.subtitle_styles.map((item, index) => { const selected = selectedSubtitle === item.id; const className = ["narration-subtitle--glow", "narration-subtitle--classic", "narration-subtitle--blue-outline"][index]; return <button className={`narration-subtitle-card ${className} ${selected ? "is-selected" : ""}`} type="button" aria-pressed={selected} onClick={() => onSubtitleChange(item.id)} key={item.id}><strong aria-hidden="true">Aa</strong><small>{item.name}</small></button>; })}</div></fieldset>
    <BackgroundMusicPicker music={backgroundMusic} volume={backgroundMusicVolume} isUploading={backgroundMusicUploading} error={backgroundMusicError} disabled={backgroundMusicDisabled || disabled} onUpload={onBackgroundMusicUpload} onRemove={onBackgroundMusicRemove} onVolumeChange={onBackgroundMusicVolumeChange} />
    <fieldset className="narration-fieldset narration-voice-picker"><legend>{t("narration.form.voice")}</legend><VoiceGrid voices={config.voices} value={selectedVoice} onChange={onVoiceChange} /></fieldset>
    <fieldset className="narration-fieldset narration-requirements"><legend>{t("narration.form.moreRequirements")} <CaretUp aria-hidden="true" /></legend><label><span className="sr-only">{t("narration.form.requirements")}</span><textarea maxLength="200" value={requirements} onChange={(event) => onRequirementsChange(event.target.value)} placeholder={t("narration.form.placeholder")} /><em>{formatNumber(requirements.length)} / 200</em></label></fieldset>
  </section>;
}
