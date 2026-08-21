const array = (value) => Array.isArray(value) ? value : [];

function enabled(value, fallback = false) {
  if (typeof value === "boolean") return value;
  if (value && typeof value === "object") return value.enabled !== false && value.supported !== false;
  return fallback;
}

function assetCapability(capabilities, kind) {
  const input = capabilities.input_assets || capabilities.inputAssets || capabilities.assets || {};
  const direct = input[kind] || capabilities[`${kind}_upload`] || capabilities[`supports_${kind}_upload`];
  const legacy = capabilities[`max_${kind}_count`] ?? capabilities[`${kind}_max_count`];
  const max = Number(direct?.max_count ?? direct?.maxCount ?? direct?.limit ?? legacy ?? 0);
  return { enabled: enabled(direct, max > 0), maxCount: max || 1, supportsMention: Boolean(direct?.supports_mention ?? direct?.supportsMention) };
}

function optionList(value) {
  return array(value).map((option) => typeof option === "object" ? option : { id: String(option), label: String(option) });
}

const generatedPlayModes = (model) => {
  const imageLimit = Number(model?.image?.maxCount || 0);
  const modes = [
    { id: "text_to_video", label: "文生视频", description: "只需输入文字脚本，AI 即能输出完整视频。" },
  ];
  if (imageLimit > 0) {
    modes.push({ id: "image_to_video", label: "图生视频", description: "上传一张静态图片，让画面自然动起来。" });
    modes.push({ id: "reference_to_video", label: "参考生视频", description: "上传参考图片，AI 将围绕参考内容生成视频。", hot: true, recommended: imageLimit > 1 });
  }
  if (imageLimit > 1) {
    modes.push({ id: "multi_image_reference_to_video", label: "多图参考", description: "上传多张图片，AI 会综合所有参考信息。" });
  }
  if (model?.video?.enabled) {
    modes.push({ id: "video_extension", label: "视频延长", description: "上传原视频，AI 自动向后延续生成内容。" });
  }
  return modes;
};

export function playModesForModel(model) {
  const configured = optionList(model?.playModes);
  return configured.length ? configured : generatedPlayModes(model);
}

function capabilitiesForPlayMode(mode) {
  const inputs = array(mode?.inputs);
  const outputs = array(mode?.output_options || mode?.outputOptions);
  const input = (type) => inputs.find((item) => item.type === type);
  const upload = (type) => {
    const rule = input(type);
    return { enabled: Boolean(rule?.supported), max_count: Number(rule?.max_count ?? rule?.maxCount ?? 0), supports_mention: Boolean(rule?.supports_mention ?? rule?.supportsMention) };
  };
  const valuesFor = (type) => outputs.filter((item) => item.type === type).flatMap((item) => item.values || (item.value == null ? [] : [item.value]));
  const durationValues = valuesFor("duration");
  return {
    image_upload: upload("image"),
    video_upload: upload("video"),
    audio_upload: upload("audio"),
    multi_subject_reference: inputs.some((item) => item.supports_mention || item.supportsMention),
    audio_switch: Boolean(mode?.supports_generate_audio ?? mode?.supportsGenerateAudio),
    resolutions: valuesFor("resolution").filter(Boolean),
    ratios: valuesFor("ratio").filter(Boolean),
    duration: {
      options: durationValues,
      adaptive: durationValues.includes("adaptive"),
    },
  };
}

export function normalizeModel(model) {
  const capabilities = model.capabilities || model.capability || model.config || {};
  const duration = capabilities.duration || capabilities.durations || {};
  const durationOptions = optionList(duration.options || duration.values || capabilities.duration_seconds || capabilities.durations);
  const resolutions = optionList(capabilities.resolutions || capabilities.resolution_options);
  const aspectRatios = optionList(capabilities.aspect_ratios || capabilities.aspectRatios || capabilities.ratios);
  return {
    id: String(model.id ?? model.model_id ?? model.code ?? ""),
    name: model.name || model.display_name || model.title || "未命名模型",
    provider: model.provider || model.provider_code || model.vendor || "",
    category: model.category || model.brand || model.provider || "全部",
    outputType: model.output_type || model.outputType || "video",
    coverUrl: model.cover_url || model.thumbnail_url || model.image_url || "",
    description: model.description || model.summary || "",
    badge: model.badge || model.tag || "",
    status: model.status || "available",
    creditCost: Number(model.credit_cost ?? model.credits ?? model.pricing?.credits ?? model.price?.credits ?? 0),
    image: assetCapability(capabilities, "image"),
    video: assetCapability(capabilities, "video"),
    audio: assetCapability(capabilities, "audio"),
    multiSubject: enabled(capabilities.multi_subject_reference ?? capabilities.multiSubjectReference ?? capabilities.multi_subject, false),
    audioGeneration: enabled(capabilities.audio_switch ?? capabilities.audio_generation ?? capabilities.audioGeneration ?? capabilities.generate_audio, false),
    playModes: optionList(model.play_modes || model.playModes || capabilities.play_modes || capabilities.playModes),
    defaultPlayModeId: model.default_play_mode_id || model.defaultPlayModeId || "",
    resolutions,
    aspectRatios,
    duration: {
      mode: duration.mode || (durationOptions.length ? "options" : capabilities.duration_mode || ""),
      min: Number(duration.min ?? duration.min_seconds ?? capabilities.min_duration ?? 0),
      max: Number(duration.max ?? duration.max_seconds ?? capabilities.max_duration ?? 0),
      step: Number(duration.step ?? duration.step_seconds ?? capabilities.duration_step ?? 1),
      options: durationOptions,
      adaptive: enabled(duration.adaptive ?? capabilities.adaptive_duration, false),
    },
    raw: model,
  };
}

export function normalizeModels(payload) {
  const entries = array(payload?.models || payload?.items || payload?.data || payload);
  return entries.map(normalizeModel).filter((model) => model.id);
}

/** 将已下发的模型详情切换为指定玩法对应的输入、输出和收费展示。 */
export function modelForPlayMode(model, playModeId) {
  const mode = playModesForModel(model).find((item) => String(item.id) === String(playModeId));
  // 兼容尚未升级详情接口的旧数据；旧数据只能展示模型级默认能力。
  if (!mode || !Array.isArray(mode.inputs)) return model;
  const normalized = normalizeModel({
    ...model.raw,
    capabilities: capabilitiesForPlayMode(mode),
    play_modes: model.raw?.play_modes || model.playModes,
    default_play_mode_id: mode.id,
    price: { credits: mode.default_credits ?? mode.defaultCredits ?? model.creditCost },
  });
  return { ...normalized, playModes: model.playModes, activePlayMode: mode };
}

export function modelDefaults(model) {
  const playModes = playModesForModel(model);
  const defaultPlayMode = playModes.find((mode) => String(mode.id) === String(model.defaultPlayModeId))?.id || playModes.find((mode) => mode.recommended)?.id || playModes[0]?.id || "";
  return {
    playMode: defaultPlayMode,
    resolution: model.resolutions[0]?.id || model.resolutions[0]?.value || "",
    aspectRatio: model.aspectRatios[0]?.id || model.aspectRatios[0]?.value || "",
    duration: model.duration.options[0]?.id || model.duration.options[0]?.value || model.duration.min || "",
    audioEnabled: false,
  };
}

export function labelOf(option) {
  return String(option?.display_name || option?.displayName || option?.label || option?.name || option?.value || option?.id || option || "");
}
