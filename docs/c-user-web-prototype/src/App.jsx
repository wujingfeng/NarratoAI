import { useEffect, useMemo, useRef, useState } from "react";

const screens = [
  ["D01", "首页：AI 视频创作工作台首页", 2560, 1440],
  ["D02", "影视解说：上传素材与模式选择", 1536, 1024],
  ["D03", "短剧解说：上传多段短剧视频", 1536, 1024],
  ["D04", "画面解说：上传视频与主题", 1536, 1024],
  ["D05", "短剧混剪：上传多段素材与混剪设置", 1536, 1024],
  ["D06", "素材库：视频", 1535, 1024],
  ["D07", "影视解说：正在生成", 1536, 1024],
  ["D08", "成片结果", 1536, 1024],
  ["D09", "自动模式：影视/短剧解说生成中", 1487, 1058],
  ["D10", "自动模式：画面解说生成中", 1487, 1058],
  ["D11", "自动模式：短剧混剪生成中", 1536, 1024],
  ["D12", "精细模式：字幕确认", 1536, 1024],
  ["D13", "精细模式：剧情理解", 1536, 1024],
  ["D14", "精细模式：解说文案", 1536, 1024],
  ["D15", "精细模式：剪辑脚本", 1536, 1024],
  ["D16", "精细模式：配音字幕", 1536, 1024],
  ["D17", "精细模式：合成导出", 1536, 1024],
  ["D27", "配置中心：模型与接口", 1487, 1058],
  ["D28", "配置中心：配音设置", 1487, 1058],
  ["D29", "配置中心：字幕设置", 1487, 1058],
  ["D30", "配置中心：背景音乐", 1487, 1058],
  ["D31", "配置中心：视频导出", 1487, 1058],
].map(([id, title, width, height]) => ({
  id,
  title,
  width,
  height,
  baseline: `/baseline/${id}.png`,
  route: `?screen=${id}`,
}));

const uploadPageData = {
  D02: {
    crumb: "首页  /  影视解说",
    title: "影视解说",
    uploadTitle: "上传素材",
    uploadLabel: "上传视频",
    uploadSub: "MP4 / MOV",
    sideTitle: "字幕文件（可选）",
    sideSub: "SRT",
    modeTop: 632,
    flow: null,
  },
  D03: {
    crumb: "首页  /  短剧解说",
    title: "短剧解说",
    uploadTitle: "上传短剧视频",
    uploadLabel: "点击上传或拖拽文件到这里",
    uploadSub: "MP4 / MOV",
    sideTitle: "字幕文件（可选）",
    sideSub: "不上传将自动识别字幕（ASR）",
    modeTop: 501,
    clips: [
      ["第01集片段.mp4", "00:18:24", "1280×720", "/assets/d03/clip-1.png"],
      ["第02集片段.mp4", "00:15:37", "1280×720", "/assets/d03/clip-2.png"],
      ["第03集片段.mp4", "00:17:12", "1280×720", "/assets/d03/clip-3.png"],
    ],
    flow: ["字幕处理", "剧情理解", "解说文案", "剪辑脚本", "配音字幕", "合成导出"],
  },
  D04: {
    crumb: "首页  /  画面解说",
    title: "画面解说",
    uploadTitle: "上传视频",
    uploadLabel: "上传视频",
    uploadSub: "MP4 / MOV",
    theme: true,
    flow: ["画面分析", "生成文案", "剪辑脚本", "配音字幕", "合成导出"],
  },
  D05: {
    crumb: "首页  /  短剧混剪",
    title: "短剧混剪",
    mix: true,
    flow: ["字幕处理", "片段分析", "生成混剪脚本", "合成导出"],
  },
};

const settingsPages = {
  D27: "模型与接口",
  D28: "配音设置",
  D29: "字幕设置",
  D30: "背景音乐",
  D31: "视频导出",
};

const productNavRoutes = {
  首页: "D01",
  我的作品: "D08",
  素材库: "D06",
  配置中心: "D27",
  帮助: "HELP",
};

const uploadGenerationRoutes = {
  D02: "D09",
  D03: "D09",
  D04: "D10",
  D05: "D11",
};

const PRODUCT_DESIGN_WIDTH = 2560;
const PRODUCT_DESIGN_HEIGHT = 1440;

function isKnownScreen(id) {
  return screens.some((screen) => screen.id === id);
}

function getHashScreen() {
  const id = window.location.hash.replace(/^#\/?/, "");
  return id && (isKnownScreen(id) || id === "HELP") ? id : null;
}

function readStorage(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeStorage(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // 原型模式下静默降级，避免阻塞视觉回归截图。
  }
}

function usePersistentState(key, fallback) {
  const [value, setValue] = useState(() => readStorage(key, fallback));
  useEffect(() => writeStorage(key, value), [key, value]);
  return [value, setValue];
}

function getProductViewportFit(width = PRODUCT_DESIGN_WIDTH, height = PRODUCT_DESIGN_HEIGHT) {
  if (typeof window === "undefined") {
    return { scale: 1, width, height };
  }
  const scale = Math.min(
    window.innerWidth / width,
    window.innerHeight / height,
  );
  return {
    scale,
    width: width * scale,
    height: height * scale,
  };
}

function toMockFile(file, fallbackName = "素材文件.mp4") {
  if (!file) return { name: fallbackName, size: "mock", type: "video/mp4" };
  const size = file.size ? `${Math.max(1, Math.round(file.size / 1024 / 1024))} MB` : "mock";
  return { name: file.name, size, type: file.type || "video/mp4" };
}

function makeMockClip(index) {
  const n = String(index).padStart(2, "0");
  return [`第${n}集新增片段.mp4`, "00:12:00", "1280×720", "/assets/d03/clip-1.png"];
}

export function App() {
  const params = new URLSearchParams(window.location.search);
  const queryScreen = params.get("screen");
  const isStageMode = params.get("qa") === "1" || isKnownScreen(queryScreen);
  const stageWrapRef = useRef(null);
  const [productFit, setProductFit] = useState(() => getProductViewportFit());
  const savedProductScreen = readStorage("narrato.product.route", "D01");
  const initial = isStageMode
    ? (isKnownScreen(queryScreen) ? queryScreen : "D01")
    : (getHashScreen() ?? (savedProductScreen === "HELP" || isKnownScreen(savedProductScreen) ? savedProductScreen : "D01"));
  const [activeId, setActiveId] = useState(initial);
  const active = useMemo(
    () => screens.find((screen) => screen.id === activeId) ?? (activeId === "HELP" ? { id: "HELP", title: "帮助中心", width: 1487, height: 1058 } : screens[0]),
    [activeId],
  );
  const navigate = (screenId) => {
    if (!screenId) return;
    if (isStageMode) {
      const next = new URLSearchParams(window.location.search);
      next.set("screen", screenId);
      if (params.get("qa") === "1") next.set("qa", "1");
      window.history.replaceState(null, "", `?${next.toString()}`);
    } else {
      window.history.pushState(null, "", `#${screenId}`);
      writeStorage("narrato.product.route", screenId);
    }
    setActiveId(screenId);
  };

  useEffect(() => {
    if (isStageMode) return undefined;
    const onHashChange = () => {
      const next = getHashScreen() ?? "D01";
      writeStorage("narrato.product.route", next);
      setActiveId(next);
    };
    window.addEventListener("hashchange", onHashChange);
    window.addEventListener("popstate", onHashChange);
    return () => {
      window.removeEventListener("hashchange", onHashChange);
      window.removeEventListener("popstate", onHashChange);
    };
  }, [isStageMode]);

  useEffect(() => {
    if (isStageMode) return undefined;
    const updateScale = () => setProductFit(getProductViewportFit(active.width, active.height));
    updateScale();
    window.addEventListener("resize", updateScale);
    return () => window.removeEventListener("resize", updateScale);
  }, [active.height, active.width, isStageMode]);

  useEffect(() => {
    if (isStageMode) return;
    window.requestAnimationFrame(() => {
      stageWrapRef.current?.scrollTo({ top: 0, left: 0 });
      window.scrollTo({ top: 0, left: 0 });
    });
  }, [activeId, isStageMode]);

  const ctx = useMemo(() => ({ navigate, isProductMode: !isStageMode }), [isStageMode]);
  const productShellStyle = {
    width: productFit.width,
    height: productFit.height,
  };
  const productStageStyle = {
    width: active.width,
    height: active.height,
    transform: `scale(${productFit.scale})`,
  };

  return (
    <main className={isStageMode ? "prototype-app qa-mode" : "prototype-app product-mode"}>
      {isStageMode && (
        <aside className="screen-picker" aria-label="页面选择">
          <strong>PNG 基准还原</strong>
          <span>当前以原型 PNG 为唯一视觉基准</span>
          <div className="screen-list">
            {screens.map((screen) => (
              <button
                className={screen.id === activeId ? "active" : ""}
                key={screen.id}
                onClick={() => navigate(screen.id)}
                type="button"
              >
                <b>{screen.id}</b>
                <small>{screen.title}</small>
              </button>
            ))}
          </div>
        </aside>
      )}

      <section className="stage-wrap" ref={stageWrapRef}>
        {isStageMode && (
          <div className="stage-meta">
            <div>
              <b>{active.id}</b>
              <span>{active.title}</span>
            </div>
            {active.baseline && (
              <a href={active.baseline} target="_blank" rel="noreferrer">
                查看 PNG 基准
              </a>
            )}
          </div>
        )}
        {isStageMode ? (
          <div
            className="screen-stage"
            data-screen={active.id}
            style={{ width: active.width, height: active.height }}
          >
            {renderScreen(active, ctx)}
          </div>
        ) : (
          <div className="responsive-stage-shell" style={productShellStyle}>
            <div className="screen-stage" data-screen={active.id} style={productStageStyle}>
              {active.id === "HELP" ? <HelpScreen navigate={navigate} /> : renderScreen(active, ctx)}
            </div>
          </div>
        )}
      </section>
    </main>
  );
}

function renderScreen(screen, ctx = {}) {
  if (screen.id === "D01") return <HomeScreen navigate={ctx.navigate} />;
  if (uploadPageData[screen.id]) return <UploadScreen id={screen.id} data={uploadPageData[screen.id]} navigate={ctx.navigate} interactive={ctx.isProductMode} />;
  if (screen.id === "D06") return <MaterialLibraryScreen navigate={ctx.navigate} interactive={ctx.isProductMode} />;
  if (["D07", "D09", "D10", "D11", "D12"].includes(screen.id)) return <GeneratingScreen id={screen.id} navigate={ctx.navigate} interactive={ctx.isProductMode} />;
  if (screen.id === "D08") return <ResultScreen navigate={ctx.navigate} />;
  if (["D13", "D14", "D15", "D16", "D17"].includes(screen.id)) return <FineStepScreen id={screen.id} navigate={ctx.navigate} />;
  if (screen.id === "D29" && !ctx.isProductMode) return <SubtitleSettingsScreen navigate={ctx.navigate} interactive={ctx.isProductMode} />;
  if (settingsPages[screen.id]) return <SettingsScreen id={screen.id} title={settingsPages[screen.id]} navigate={ctx.navigate} interactive={ctx.isProductMode} />;
  return <BaselineTodo screen={screen} />;
}

function TopNav({ active = "首页", navigate }) {
  const nav = ["首页", "我的作品", "素材库", "配置中心", "帮助"];
  return (
    <header className="top-nav">
      <img className="brand-image" src="/assets/shared/brand.png" alt="NarratoAI" />
      <nav>
        {nav.map((item) => (
          <span
            className={item === active ? "active" : ""}
            key={item}
            onClick={() => navigate?.(productNavRoutes[item])}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") navigate?.(productNavRoutes[item]);
            }}
            role="button"
            tabIndex={0}
          >
            {item}
          </span>
        ))}
      </nav>
      <img className="user-entry-image" src="/assets/shared/user-entry.png" alt="小美" />
    </header>
  );
}

function Breadcrumb({ children }) {
  return <div className="breadcrumb">⌂&nbsp;&nbsp;{children}</div>;
}

function Pill({ children, muted = false }) {
  return <span className={muted ? "pill muted" : "pill"}>{children}</span>;
}

function HomeScreen({ navigate }) {
  const cards = [
    ["影视解说", "从长视频到高完成度解说短片", "上传素材", "D02", "/assets/d01/type-film.png", "01"],
    ["短剧解说", "批量导入剧集，自动拆解剧情节奏", "多集处理", "D03", "/assets/d01/type-drama.png", "02"],
    ["画面解说", "识别画面信息，生成自然旁白", "视觉理解", "D04", "/assets/d01/type-visual.png", "03"],
    ["短剧混剪", "提炼高光片段，快速生成混剪", "高光成片", "D05", "/assets/d01/type-mix.png", "04"],
  ];
  const metrics = [
    ["脚本生成", "4×", "更快进入剪辑"],
    ["视频理解", "AI", "镜头/字幕/剧情联动"],
    ["工作流", "6步", "可自动也可精细确认"],
  ];
  const languages = ["字幕识别", "剧情理解", "解说文案", "镜头匹配", "配音字幕", "合成导出"];
  return (
    <section className="landing-home page">
      <div className="landing-bg-grid" />
      <div className="landing-aurora aurora-a" />
      <div className="landing-aurora aurora-b" />
      <div className="landing-noise" />

      <header className="landing-nav">
        <button className="landing-brand" onClick={() => navigate?.("D01")} type="button" aria-label="NarratoAI 首页">
          <span className="brand-mark">N</span>
          <b>NarratoAI</b>
        </button>
        <nav aria-label="首页导航">
          <button className="active" type="button">产品</button>
          <button onClick={() => navigate?.("D06")} type="button">素材库</button>
          <button onClick={() => navigate?.("D27")} type="button">配置中心</button>
          <button onClick={() => navigate?.("HELP")} type="button">帮助</button>
        </nav>
        <div className="landing-nav-actions">
          <button className="ghost" onClick={() => navigate?.("D08")} type="button">我的作品</button>
          <button className="nav-cta" onClick={() => navigate?.("D02")} type="button">开始创作</button>
        </div>
      </header>

      <main className="landing-main">
        <section className="landing-copy">
          <div className="rating-chip" aria-label="AI video workflow">
            <span>✦</span><b>AI Video Workflow</b><em>Auto · Fine · Export</em>
          </div>
          <h1>把长视频，变成<br />高质量解说成片</h1>
          <p>参考 BlipCut 的黑白主视觉、荧光绿 CTA、局部浅色背景与媒体工具卡片感；内容聚焦 NarratoAI 的视频理解、文案生成、剪辑脚本、配音字幕与导出流程。</p>
          <div className="hero-actions">
            <button className="hero-primary" onClick={() => navigate?.("D02")} type="button">
              <span>↥</span>开始生成
            </button>
            <button className="hero-secondary" onClick={() => navigate?.("D03")} type="button">
              <span>▶</span>查看短剧流程
            </button>
          </div>
          <div className="availability-row">
            <span>Available for</span>
            {languages.map((item) => <b key={item}>{item.slice(0, 2)}</b>)}
          </div>
        </section>

        <section className="hero-showcase" aria-label="创作工作台预览">
          <div className="hero-video video-left">
            <img src="/assets/d01/type-film.png" alt="原始素材预览" />
            <span className="play-badge">▶</span>
            <p>Raw Footage</p>
          </div>
          <div className="hero-video video-right">
            <img src="/assets/d01/sample-highlight.png" alt="解说成片预览" />
            <span className="caption-line">解说字幕 · 自动贴合画面节奏</span>
            <p>Final Story</p>
          </div>
          <div className="language-stack">
            <b>剧情</b><b>文案</b><b>镜头</b><b>配音</b>
          </div>
          <div className="curved-arrow">⌁</div>
          <div className="floating-panel script-panel">
            <small>Script Intelligence</small>
            <strong>正在生成 01:25 口播脚本</strong>
            <div><span style={{ width: "72%" }} /><span style={{ width: "48%" }} /><span style={{ width: "61%" }} /></div>
          </div>
          <div className="floating-panel export-panel">
            <small>Export Queue</small>
            <strong>1080P · SRT · Voice</strong>
            <em>98%</em>
          </div>
        </section>
      </main>

      <section className="trust-strip">
        <span>Trusted workflow for creators</span>
        <b>字幕处理</b><b>剧情理解</b><b>解说文案</b><b>剪辑脚本</b><b>配音字幕</b><b>合成导出</b>
      </section>

      <section className="landing-suite">
        <div className="suite-heading">
          <span>Our AI Creation Suite</span>
          <h2>选择你的创作入口</h2>
        </div>
        <div className="suite-grid">
          {cards.map(([title, desc, tag, target, image, index]) => (
            <article className="suite-card" key={title} onClick={() => navigate?.(target)} role="button" tabIndex={0}>
              <div className="suite-visual"><img src={image} alt="" /><span>{index}</span></div>
              <div className="suite-card-copy">
                <small>{tag}</small>
                <h3>{title}</h3>
                <p>{desc}</p>
              </div>
              <button type="button" aria-label={`进入${title}`}>→</button>
            </article>
          ))}
        </div>
      </section>

      <aside className="landing-metrics">
        {metrics.map(([label, value, sub]) => (
          <div key={label}>
            <small>{label}</small>
            <b>{value}</b>
            <span>{sub}</span>
          </div>
        ))}
      </aside>
    </section>
  );
}

function UploadScreen({ id, data, navigate, interactive }) {
  if (data.mix) return <MixUploadScreen data={data} navigate={navigate} interactive={interactive} />;
  return (
    <>
      <TopNav navigate={navigate} />
      <section className="upload-page page">
        <Breadcrumb>{data.crumb}</Breadcrumb>
        <h1>{data.title}</h1>
        {data.theme
          ? <ThemeUploadLayout id={id} data={data} navigate={navigate} />
          : <StandardUploadLayout id={id} data={data} navigate={navigate} interactive={interactive} />}
      </section>
    </>
  );
}

function UploadDropzone({ storageKey, label, sub, className = "dropzone", accept = "video/*", multiple = false }) {
  const inputRef = useRef(null);
  const [files, setFiles] = usePersistentState(storageKey, []);
  const addFiles = (fileList) => {
    const picked = Array.from(fileList ?? []);
    const next = picked.length ? picked.map((file) => toMockFile(file, label)) : [toMockFile(null, label)];
    setFiles((current) => (multiple ? [...current, ...next] : next));
  };
  const openPickerWithMock = (event) => {
    addFiles([]);
    if (event?.altKey || event?.metaKey) inputRef.current?.click();
  };
  const onDrop = (event) => {
    event.preventDefault();
    addFiles(event.dataTransfer.files);
  };
  return (
    <div
      className={`${className}${files.length ? " has-file" : ""}`}
      onClick={openPickerWithMock}
      onDragOver={(event) => event.preventDefault()}
      onDrop={onDrop}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") openPickerWithMock(event);
      }}
    >
      <input
        ref={inputRef}
        className="visually-hidden"
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={(event) => addFiles(event.target.files)}
      />
      <span className="upload-icon">↥</span>
      <b>{files[0]?.name ?? label}</b>
      <small>{files.length ? `${files.length} 个文件 · ${files[0].size}` : sub}</small>
    </div>
  );
}

function SubtitleDropzone({ storageKey, compact = false, className = "", label = "字幕文件（可选）" }) {
  const inputRef = useRef(null);
  const [files, setFiles] = usePersistentState(storageKey, []);
  const addFiles = (fileList) => {
    const picked = Array.from(fileList ?? []);
    setFiles(picked.length ? picked.map((file) => toMockFile(file, "字幕文件.srt")) : [toMockFile(null, "mock字幕文件.srt")]);
  };
  const openPickerWithMock = (event) => {
    addFiles([]);
    if (event?.altKey || event?.metaKey) inputRef.current?.click();
  };
  const content = files[0]?.name ?? (compact ? "点击上传 SRT 文件" : label);
  return (
    <div
      className={`${className || (compact ? "srt-inner interactive-drop" : "subtitle-card interactive-drop")}${files.length ? " has-file" : ""}`}
      onClick={openPickerWithMock}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        addFiles(event.dataTransfer.files);
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") openPickerWithMock(event);
      }}
    >
      <input ref={inputRef} className="visually-hidden" type="file" accept=".srt,.ass,.vtt,text/*" onChange={(event) => addFiles(event.target.files)} />
      <span className="file-icon">▱</span>
      <b>{content}</b>
      <small>{files.length ? files[0].size : "SRT"}</small>
    </div>
  );
}

function StandardUploadLayout({ id, data, navigate, interactive }) {
  const [mode, setMode] = usePersistentState(`narrato.upload.${id}.mode`, "auto");
  const [clips, setClips] = usePersistentState(`narrato.upload.${id}.clips`, data.clips ?? []);
  const [previewClip, setPreviewClip] = useState("");
  const nextTarget = mode === "auto" ? uploadGenerationRoutes[id] : "D13";
  const addClip = () => setClips((current) => [...current, makeMockClip(current.length + 1)]);
  const removeClip = (index) => setClips((current) => current.filter((_, i) => i !== index));
  const visibleClips = interactive ? clips : (data.clips ?? clips);
  return (
    <>
      <div className={id === "D03" ? "upload-layout rich" : "upload-layout"}>
        <div className="upload-left">
          <h2>{data.uploadTitle}{id === "D03" && <Pill>必填</Pill>}</h2>
          <UploadDropzone storageKey={`narrato.upload.${id}.files`} label={data.uploadLabel} sub={data.uploadSub} multiple={id === "D03"} />
          {data.clips && (
            <div className="clip-list">
              {visibleClips.map(([name, duration, size, image], index) => (
                <div className="clip-row" key={`${name}-${index}`}>
                  <img src={image} alt="" />
                  <span className="play-dot">▶</span>
                  <b>{name}</b>
                  <small>{duration}</small>
                  <small>{size}</small>
                  <button className="text-action" onClick={() => setPreviewClip(name)} type="button">{previewClip === name ? "✓ 预览中" : "⊙ 预览"}</button>
                  <button className="text-action danger" onClick={() => removeClip(index)} disabled={!interactive} type="button">⌫ 删除</button>
                </div>
              ))}
              <button className="add-file" onClick={addClip} disabled={!interactive} type="button">＋ 继续添加视频</button>
            </div>
          )}
        </div>
        <div className="upload-side">
          {id === "D03" ? (
            <div className="subtitle-card d03-subtitle">
              <h2>字幕文件 <Pill muted>可选</Pill></h2>
              <SubtitleDropzone storageKey={`narrato.upload.${id}.subtitle`} compact />
              <p>{data.sideSub}</p>
            </div>
          ) : (
            <SubtitleDropzone storageKey={`narrato.upload.${id}.subtitle`} />
          )}
          {id === "D03" && <ModePanel compact mode={mode} onModeChange={setMode} />}
        </div>
      </div>
      {id !== "D03" && <ModePanel mode={mode} onModeChange={setMode} />}
      {data.flow && <FlowCard title={`${data.title}流程`} steps={data.flow} cardFlow={id === "D03"} />}
      <BottomActions onBack={() => navigate?.("D01")} onNext={() => navigate?.(nextTarget)} />
    </>
  );
}

function ThemeUploadLayout({ id, data, navigate }) {
  const [theme, setTheme] = usePersistentState("narrato.upload.D04.theme", "城市夜景记录");
  const [note, setNote] = usePersistentState("narrato.upload.D04.note", "");
  const [mode, setMode] = usePersistentState("narrato.upload.D04.mode", "auto");
  return (
    <>
      <div className="theme-grid">
        <section className="field-card">
          <h2>上传视频 <Pill>必填</Pill></h2>
          <UploadDropzone storageKey="narrato.upload.D04.files" label="上传视频" sub="MP4 / MOV" />
        </section>
        <section className="field-card">
          <h2>视频主题 <Pill>必填</Pill></h2>
          <input value={theme} onChange={(event) => setTheme(event.target.value)} />
          <h2 className="sub-label">补充要求 <Pill muted>可选</Pill></h2>
          <textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="例如：节奏轻快、突出城市氛围" />
        </section>
      </div>
      <div className="option-row">
        <section className="option-card">
          <h2>画面分析</h2>
          <div className="segmented"><button className="selected">标准</button><button>精细</button></div>
        </section>
        <section className="option-card">
          <h2>生成模式</h2>
          <div className="segmented"><button className={mode === "auto" ? "selected" : ""} onClick={() => setMode("auto")}>自动模式</button><button className={mode === "fine" ? "selected" : ""} onClick={() => setMode("fine")}>精细模式</button></div>
        </section>
      </div>
      <FlowCard title="画面解说流程" steps={data.flow} numbered />
      <BottomActions onBack={() => navigate?.("D01")} onNext={() => navigate?.(mode === "auto" ? uploadGenerationRoutes[id] : "D13")} />
    </>
  );
}

function MixUploadScreen({ data, navigate }) {
  const [mode, setMode] = usePersistentState("narrato.upload.D05.mode", "auto");
  const [clips, setClips] = usePersistentState("narrato.upload.D05.clips", [
    ["短剧片段01.mp4", "00:00:25", "/assets/d05-thumb-1.png"],
    ["短剧片段02.mp4", "00:00:31", "/assets/d05-thumb-2.png"],
    ["短剧片段03.mp4", "00:00:28", "/assets/d05-thumb-3.png"],
  ]);
  return (
    <>
      <TopNav navigate={navigate} />
      <section className="upload-page page mix-page">
        <Breadcrumb>{data.crumb}</Breadcrumb>
        <h1>{data.title}</h1>
        <div className="mix-grid">
          <section className="mix-material card">
            <h2>上传短剧素材 <Pill>必填</Pill></h2>
            <div className="mix-list">
              {clips.map(([name, time, image], index) => (
                <div className="mix-row" key={name}>
                  <img src={image} alt="" />
                  <b>{name}</b>
                  <small>{time}</small>
                  <em onClick={() => setClips(clips.filter((_, i) => i !== index))}>⌫</em>
                </div>
              ))}
            </div>
            <button
              className="add-file"
              type="button"
              onClick={() => setClips([...clips, [`短剧片段${String(clips.length + 1).padStart(2, "0")}.mp4`, "00:00:29", "/assets/d05-thumb-1.png"]])}
            >
              ⊕ 添加视频
            </button>
          </section>
          <aside className="mix-side">
            <section className="card srt-card">
              <h2>字幕文件 <Pill muted>可选</Pill></h2>
              <SubtitleDropzone storageKey="narrato.upload.D05.subtitle" className="srt-drop interactive-drop" label="上传 SRT" />
            </section>
            <section className="card mix-setting">
              <h2>混剪设置</h2>
              <label><span>混剪数量</span><Stepper /></label>
              <label><span>片段时长</span><div className="mini-seg"><b>短</b><b className="selected">中</b><b>长</b></div></label>
            </section>
            <section className="card mix-mode">
              <h2>生成模式</h2>
              <div><button className={mode === "auto" ? "selected" : ""} onClick={() => setMode("auto")}>自动模式</button><button className={mode === "fine" ? "selected" : ""} onClick={() => setMode("fine")}>精细模式</button></div>
            </section>
          </aside>
        </div>
        <FlowCard title="短剧混剪流程" steps={data.flow} icon />
        <BottomActions onBack={() => navigate?.("D01")} onNext={() => navigate?.(mode === "auto" ? "D11" : "D13")} />
      </section>
    </>
  );
}

function ModePanel({ compact = false, mode = "auto", onModeChange }) {
  return (
    <section className={compact ? "mode-panel compact" : "mode-panel"}>
      <h2>选择生成模式</h2>
      <div className="mode-cards">
        <article className={mode === "auto" ? "mode-card selected" : "mode-card"} onClick={() => onModeChange?.("auto")} role="button" tabIndex={0}>
          <i>⚡</i>
          <b>自动模式</b>
          <Pill>自动完成</Pill>
          <span>{mode === "auto" ? "✓" : ""}</span>
        </article>
        <article className={mode === "fine" ? "mode-card selected" : "mode-card"} onClick={() => onModeChange?.("fine")} role="button" tabIndex={0}>
          <i>☷</i>
          <b>精细模式</b>
          <Pill muted>逐步确认</Pill>
          <span>{mode === "fine" ? "✓" : ""}</span>
        </article>
      </div>
    </section>
  );
}

function Stepper() {
  const [count, setCount] = usePersistentState("narrato.upload.D05.mixCount", 12);
  return <div className="stepper"><button onClick={() => setCount(Math.max(1, count - 1))}>−</button><b>{count}</b><button onClick={() => setCount(count + 1)}>＋</button></div>;
}

function FlowCard({ title, steps, numbered = false, icon = false, cardFlow = false }) {
  const cardIcons = ["T", "◌", "▤", "✂", "🎙", "▣"];
  return (
    <section className="flow-card">
      <h2>{title}</h2>
      <div className={cardFlow ? "flow-line cards" : icon ? "flow-line icon" : "flow-line"}>
        {steps.map((step, index) => (
          <div className="flow-step" key={step}>
            <span>{cardFlow ? cardIcons[index] : numbered ? index + 1 : icon ? ["▤", "□", "▣", "↥"][index] : index + 1}</span>
            <b>{step}</b>
          </div>
        ))}
      </div>
    </section>
  );
}

function BottomActions({ onBack, onNext, nextText = "下一步" }) {
  return (
    <footer className="bottom-actions">
      <button className="secondary" onClick={onBack} type="button">返回</button>
      <button className="primary" onClick={onNext} type="button">{nextText}</button>
    </footer>
  );
}

function MaterialLibraryScreen({ navigate, interactive }) {
  const materialInputRef = useRef(null);
  const defaultMaterials = [
    ["都市夜景航拍.mp4", "MP4 · 1280×720", "2024-07-03 14:25", "01:32", "/assets/d06/city.png"],
    ["情感对话片段.mp4", "MP4 · 1080×1920", "2024-07-03 11:10", "02:18", "/assets/d06/romance.png"],
    ["自然风光延时.mp4", "MP4 · 1920×1080", "2024-07-03 09:48", "01:07", "/assets/d06/nature.png"],
    ["古装剧情片段.mp4", "MP4 · 1080×1920", "2024-07-02 20:33", "02:45", "/assets/d06/costume.png"],
    ["悬疑片段.mp4", "MP4 · 1080×1920", "2024-07-02 16:18", "01:49", "/assets/d06/suspense.png"],
    ["生活日常片段.mp4", "MP4 · 1080×1920", "2024-07-01 18:07", "00:58", "/assets/d06/coffee.png"],
    ["海边日落素材.mp4", "MP4 · 1280×720", "2024-07-01 15:42", "01:20", "/assets/d06/beach.png"],
    ["古镇夜景漫步.mp4", "MP4 · 1080×1920", "2024-06-30 21:36", "01:15", "/assets/d06/street.png"],
  ];
  const [materials, setMaterials] = usePersistentState("narrato.materials", defaultMaterials);
  const [query, setQuery] = usePersistentState("narrato.materials.query", "");
  const [view, setView] = usePersistentState("narrato.materials.view", "grid");
  const [renaming, setRenaming] = useState(null);
  const [toast, setToast] = useState("");
  const source = interactive ? materials : defaultMaterials;
  const displayQuery = interactive ? query : "";
  const displayView = interactive ? view : "grid";
  const visibleMaterials = source
    .map((item, originalIndex) => ({ item, originalIndex }))
    .filter(({ item: [name] }) => !displayQuery || name.includes(displayQuery));
  const notify = (message) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 1800);
  };
  const addMaterialFiles = (fileList) => {
    const picked = Array.from(fileList ?? []);
    const stamp = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    const nextMaterials = picked.length
      ? picked.map((file) => [
        file.name,
        `${file.type?.split("/")?.[1]?.toUpperCase() || "MP4"} · ${Math.max(1, Math.round(file.size / 1024 / 1024 || 1))}MB`,
        `刚刚 ${stamp}`,
        "00:30",
        "/assets/d06/city.png",
      ])
      : [[`mock上传素材-${materials.length + 1}.mp4`, "MP4 · mock", `刚刚 ${stamp}`, "00:30", "/assets/d06/city.png"]];
    setMaterials((current) => [...current, ...nextMaterials]);
    notify(picked.length ? `已添加 ${picked.length} 个真实文件` : "已生成 mock 上传素材");
  };
  const openMaterialPickerWithMock = (event) => {
    addMaterialFiles([]);
    if (event?.altKey || event?.metaKey) materialInputRef.current?.click();
  };
  return (
    <>
      <TopNav active="素材库" navigate={navigate} />
      <section className="material-page page">
        <h1>素材库</h1>
        <button className="upload-material" onClick={openMaterialPickerWithMock} type="button">↥ 上传素材</button>
        <div className="material-tabs"><button className="active">▣ 视频</button><button>▣ 字幕</button><button>♫ 背景音乐</button></div>
        <div className="material-filter">
          <input value={interactive ? query : "⌕  搜索素材名称"} onChange={(event) => setQuery(event.target.value)} readOnly={!interactive} placeholder="⌕  搜索素材名称" />
          <button onClick={() => notify("已按最近上传排序")}>最近上传⌄</button>
          <span className={interactive && displayView === "grid" ? "active" : ""} onClick={() => setView("grid")}>▦</span>
          <span className={interactive && displayView === "list" ? "active" : ""} onClick={() => setView("list")}>☷</span>
        </div>
        <div
          className="material-drop"
          onClick={openMaterialPickerWithMock}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            addMaterialFiles(event.dataTransfer.files);
          }}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") openMaterialPickerWithMock(event);
          }}
        >
          <input
            ref={materialInputRef}
            className="visually-hidden"
            type="file"
            accept="video/*,audio/*,.srt,.ass,.vtt"
            multiple
            onChange={(event) => addMaterialFiles(event.target.files)}
          />
          ☁&nbsp;&nbsp;拖拽文件到这里，或点击 <b>上传素材</b>
        </div>
        <div className={displayView === "list" ? "material-grid list" : "material-grid"}>
          {visibleMaterials.map(({ item: [name, meta, time, duration, image], originalIndex }) => (
            <article className="material-card" key={`${name}-${originalIndex}`}>
              <div className="thumb"><img src={image} alt="" /><span>{duration}</span></div>
              <div>
                {renaming === originalIndex ? (
                  <input
                    className="rename-input"
                    value={name}
                    autoFocus
                    onChange={(event) => {
                      const next = [...materials];
                      next[originalIndex] = [event.target.value, meta, time, duration, image];
                      setMaterials(next);
                    }}
                    onBlur={() => {
                      setRenaming(null);
                      notify("素材名称已更新");
                    }}
                  />
                ) : <h2>{name}</h2>}
                <p>{meta}</p><p>{time}</p>
                <footer>
                  <b onClick={() => {
                    notify(`已选择素材：${name}`);
                    navigate?.("D02");
                  }}>使用</b>
                  <button onClick={() => setRenaming(originalIndex)}>重命名</button>
                  <button onClick={() => {
                    setMaterials(materials.filter((_, i) => i !== originalIndex));
                    notify("素材已删除");
                  }}>删除</button>
                </footer>
              </div>
            </article>
          ))}
        </div>
        {toast && <div className="product-toast">{toast}</div>}
        <div className="pagination"><span>共 {visibleMaterials.length} 条</span><button>‹</button><b>1</b><button>›</button><button>20 条/页⌄</button></div>
      </section>
    </>
  );
}

function GeneratingScreen({ id, navigate, interactive }) {
  const compactHero = id === "D09" || id === "D10";
  const framed = id === "D07";
  const title = id === "D10" ? "城市夜景记录" : "都市情感解说-07月03日";
  const type = id === "D10" ? "画面解说" : id === "D11" ? "短剧混剪" : "影视解说";
  const steps = id === "D11"
    ? ["字幕处理", "片段分析", "生成脚本", "合成视频"]
    : ["字幕处理", id === "D10" ? "画面分析" : "剧情理解", "生成剧本", "生成配音", "合成视频"];
  const [progress, setProgress] = usePersistentState(`narrato.generate.${id}.progress`, 32);
  useEffect(() => {
    if (!interactive || progress >= 100) return undefined;
    const timer = window.setInterval(() => setProgress((value) => Math.min(100, value + 8)), 900);
    return () => window.clearInterval(timer);
  }, [interactive, progress, setProgress]);
  const displayProgress = interactive ? progress : 32;
  const currentStep = interactive ? Math.min(steps.length - 1, Math.floor((progress / 100) * steps.length)) : 1;
  return (
    <>
      <TopNav active="我的作品" navigate={navigate} />
      <section className={`generate-page page${compactHero ? " compact" : ""}${framed ? " framed" : ""}`}>
        <Breadcrumb>我的作品&nbsp;&nbsp;/&nbsp;&nbsp;{title}</Breadcrumb>
        <div className="generate-hero">
          {!compactHero && <img className="generate-icon-image" src="/assets/shared/generating-icon.png" alt="" />}
          <div>
            <h1>正在生成</h1>
            <p>{title}<Pill>{type}</Pill><Pill muted>自动模式</Pill></p>
          </div>
        </div>
        <section className="progress-card">
          <div className="progress-steps">
            {steps.map((step, index) => (
              <div className={index < currentStep ? "done" : index === currentStep ? "current" : ""} key={step}>
                <span>{index === 0 && compactHero ? "✓" : index + 1}</span>
                <b>{step}</b>
                <small>{index < currentStep ? "已完成" : index === currentStep ? (displayProgress >= 100 ? "已完成" : "处理中") : "等待中"}</small>
              </div>
            ))}
          </div>
          <div className="progress-stats">
            <p><i>◷</i><span>已用时<b>{interactive ? `00:0${Math.min(9, Math.floor(progress / 12))}:28` : "00:01:28"}</b></span></p>
            <p><i>◷</i><span>预计剩余<b>{displayProgress >= 100 ? "已完成" : "约 02:36"}</b></span></p>
            <p><i>⊕</i><span>{interactive ? "当前进度" : "预计完成时间"}<b>{interactive ? `${progress}%` : "今天 14:32"}</b></span></p>
          </div>
        </section>
        <div className="generate-actions">
          <button onClick={() => navigate?.("D08")}>返回我的作品</button>
          <button onClick={() => {
            if (displayProgress >= 100) navigate?.("D08");
            else {
              setProgress(0);
              navigate?.("D01");
            }
          }}>{displayProgress >= 100 ? "查看结果" : "取消任务"}</button>
        </div>
      </section>
    </>
  );
}

function ResultScreen({ navigate }) {
  const [notice, setNotice] = useState("");
  const notify = (message) => {
    setNotice(message);
    window.setTimeout(() => setNotice(""), 1600);
  };
  return (
    <>
      <TopNav active="我的作品" navigate={navigate} />
      <section className="result-page page">
        <Breadcrumb>我的作品&nbsp;&nbsp;/&nbsp;&nbsp;都市情感解说-07月03日</Breadcrumb>
        <h1>成片结果</h1>
        <div className="result-title">都市情感解说-07月03日 <Pill>影视解说</Pill><Pill muted>自动模式</Pill><span>已完成</span></div>
        <img className="video-preview" src="/assets/d08/preview.png" alt="成片预览" />
        <aside className="export-panel">
          <section><h2>导出与分享</h2><button className="download" onClick={() => notify("已模拟下载视频")}>⇩ 下载视频</button><button onClick={() => notify("已模拟导出剪映草稿")}>✂ 导出剪映草稿</button><button onClick={() => navigate?.("D09")}>↻ 重新生成</button><button onClick={() => navigate?.("D01")}>↩ 返回首页</button></section>
          <section><h2>生成内容</h2>{["解说文案", "剪辑脚本", "字幕文件", "配音音频"].map((item) => <p key={item}><i />{item}<span onClick={() => notify(`${item} 已预览/下载`)}>◎ ⇩</span></p>)}</section>
          <section className="video-meta">
            <b><i className="meta-icon phone" /><span>9:16<br />视频比例</span></b>
            <b><i className="meta-icon hd" /><span>1080P<br />视频分辨率</span></b>
            <b><i className="meta-icon file" /><span>MP4<br />视频格式</span></b>
          </section>
        </aside>
        {notice && <div className="product-toast result-notice">{notice}</div>}
      </section>
    </>
  );
}

const fineMeta = {
  D13: ["剧情理解", 2, "确认剧情，下一步"],
  D14: ["解说文案", 3, "确认文案，下一步"],
  D15: ["剪辑脚本", 4, "确认脚本，下一步"],
  D16: ["配音字幕", 5, "确认配音字幕，下一步"],
  D17: ["合成导出", 6, "开始合成视频"],
};

function FineStepScreen({ id, navigate }) {
  const [title, current, confirmText] = fineMeta[id];
  const flow = ["D13", "D14", "D15", "D16", "D17"];
  const index = flow.indexOf(id);
  return (
    <>
      <TopNav active="我的作品" navigate={navigate} />
      <section className={`fine-page page ${id.toLowerCase()}`}>
        <Breadcrumb>我的作品&nbsp;&nbsp;/&nbsp;&nbsp;影视解说&nbsp;&nbsp;/&nbsp;&nbsp;精细模式</Breadcrumb>
        <h1>{title}</h1>
        <div className="fine-title">都市情感解说-07月03日 <Pill>影视解说</Pill><Pill muted>精细模式</Pill></div>
        <FineStepper current={current} screenId={id} />
        {id === "D13" && <PlotPanel />}
        {id === "D14" && <CopyPanel />}
        {id === "D15" && <ScriptPanel />}
        {id === "D16" && <VoiceSubtitlePanel />}
        {id === "D17" && <ExportConfirmPanel navigate={navigate} />}
        <footer className="fine-actions">
          <button onClick={() => navigate?.(index > 0 ? flow[index - 1] : "D02")}>上一步</button>
          <button onClick={() => navigate?.(id === "D17" ? "D08" : flow[index + 1])}>{confirmText}</button>
        </footer>
      </section>
    </>
  );
}

function FineStepper({ current, screenId }) {
  const steps = ["字幕确认", "剧情理解", "解说文案", "剪辑脚本", "配音字幕", "合成导出"];
  const checkSteps = {
    D13: new Set([1]),
    D14: new Set([1, 2]),
    D16: new Set([1]),
  }[screenId] ?? new Set();
  return (
    <div className="fine-stepper">
      {steps.map((step, index) => {
        const n = index + 1;
        return <div className={n < current ? "done" : n === current ? "current" : ""} key={step}><span>{n < current && checkSteps.has(n) ? "✓" : n}</span><b>{step}</b></div>;
      })}
    </div>
  );
}

function PlotPanel() {
  const [version, setVersion] = usePersistentState("narrato.fine.plot.version", 1);
  const [editing, setEditing] = useState(false);
  const [summary, setSummary] = usePersistentState(
    "narrato.fine.plot.summary",
    "林晚与顾北辰因一场商业阴谋产生误会，导致两人分手。多年后重逢，真相揭开，彼此理解并共同面对过去，最终携手走向幸福。",
  );
  return (
    <div className="fine-grid plot">
      <section className="fine-main">
        <header>
          <h2>剧情理解结果</h2>
          <button onClick={() => {
            setVersion(version + 1);
            setSummary(`第 ${version + 1} 版：误会、反转与重逢线索已重新聚焦，强调女主成长后的主动选择。`);
          }} type="button">↻ 重新理解</button>
          <button onClick={() => setEditing(!editing)} type="button">{editing ? "✓ 保存" : "✎ 编辑"}</button>
        </header>
        <div className="article-text">
          <b>一、基础识别</b>
          <p>类型：都市 / 情感 / 成长<br />时空背景：现代都市，主线时间约三年<br />核心主题：信任与误会导致关系破裂，自我成长后和解</p>
          <b>二、人物与关系</b>
          <table><tbody>{["林晚","顾北辰","林母","顾父"].map((name) => <tr key={name}><td>{name}</td><td>关键角色</td><td>推动剧情发展</td><td>关系转折</td></tr>)}</tbody></table>
          <b>三、整体剧情概括</b>
          {editing ? (
            <textarea className="inline-editor plot-editor" value={summary} onChange={(event) => setSummary(event.target.value)} />
          ) : (
            <p>{summary}</p>
          )}
          <b>四、分段剧情解析</b>
          <table><tbody>{Array.from({ length: 5 }).map((_, i) => <tr key={i}><td>{i + 1}. 阶段</td><td>00:0{i}:00 - 00:0{i + 1}:18</td><td>核心事件</td><td>情绪推进</td></tr>)}</tbody></table>
        </div>
      </section>
      <aside className="fine-side"><h2>结果状态</h2><p><i className="green">✓</i>第 {version} 版已生成</p><p><i className="blue">✎</i>{editing ? "正在编辑" : "可编辑"}</p><p><i className="purple">▤</i>用于生成文案</p></aside>
    </div>
  );
}

function CopyPanel() {
  const defaultRows = [
    ["01", "00:00-00:06", "她被所有人看不起，却是隐藏的顶级大佬。", "这不是童话，而是林晚的现实。"],
    ["02", "00:06-00:14", "三年前，一场商业阴谋让她一夜之间失去了一切。", "从云端跌落，成了人人口中的笑话。"],
    ["03", "00:14-00:22", "可他们不知道，林晚早已在暗中布局。", "她从未离开，只是在等一个时机。"],
    ["04", "00:22-00:30", "当真相被揭开，所有人都惊呆了。", "曾经的她，被他们视为尘埃，如今却是无人能及的存在。"],
    ["05", "00:30-00:38", "她不再隐忍，也不再退让。", "这一次，她要让所有人，为曾经的轻视付出代价。"],
    ["06", "00:38-00:46", "逆袭之路，才刚刚开始。", "林晚，将用实力，改写属于她的命运。"],
  ];
  const [rows, setRows] = usePersistentState("narrato.fine.copy.rows", defaultRows);
  const [tone, setTone] = usePersistentState("narrato.fine.copy.tone", "强反转");
  const [editing, setEditing] = useState(null);
  const updateRow = (index, patch) => {
    setRows(rows.map((row, i) => (i === index ? [...row.slice(0, 2), ...(patch ?? row.slice(2))] : row)));
  };
  const regenerate = () => {
    setRows(rows.map(([n, time], index) => [n, time, `第 ${index + 1} 段已按「${tone}」重新生成。`, "保留短句节奏，强化开头钩子与情绪推进。"]));
  };
  const rewriteRow = (index) => {
    updateRow(index, [`这一段已重写：冲突升级，人物选择更明确。`, "节奏更短，更适合短视频口播。"]);
  };
  const wordCount = rows.reduce((sum, row) => sum + row.slice(2).join("").length, 0);
  return (
    <>
      <div className="copy-tools">
        <button onClick={regenerate} type="button">↻ 重新生成</button>
        <button onClick={() => setTone(tone === "强反转" ? "温柔叙事" : "强反转")} type="button">⇆ 调整语气：{tone}</button>
      </div>
      <div className="fine-grid copy">
        <section className="copy-list">{rows.map(([n, time, text, text2], index) => (
          <article key={n}>
            <b>{n}<span>{time}</span></b>
            {editing === index ? (
              <textarea
                className="inline-editor copy-editor"
                value={`${text}\n${text2}`}
                onChange={(event) => {
                  const [nextText, ...rest] = event.target.value.split("\n");
                  updateRow(index, [nextText, rest.join("\n")]);
                }}
              />
            ) : <p>{text}<br />{text2}</p>}
            <em><button onClick={() => setEditing(editing === index ? null : index)} type="button">{editing === index ? "✓ 完成" : "✎ 编辑"}</button><button onClick={() => rewriteRow(index)} type="button">↻ 重写</button></em>
          </article>
        ))}</section>
        <aside className="summary-card"><h2>文案概览</h2><p>字数<br /><b>{wordCount} 字</b></p><p>段落<br /><b>{rows.length} 段</b></p><p>预计时长<br /><b>约 {Math.max(20, rows.length * 8)} 秒</b></p></aside>
      </div>
    </>
  );
}

function ScriptPanel() {
  const defaultRows = [
    ["00:00 – 00:05", "城市夜景航拍，车流灯光延时", "这座城市，从不缺少故事的开始。"],
    ["00:05 – 00:12", "男女在咖啡厅对坐，氛围温馨", "相遇，总是在不经意的瞬间。"],
    ["00:12 – 00:20", "女主低头微笑转身", "一个眼神，心动就有了形状。"],
    ["00:20 – 00:28", "两人雨中撑伞并肩而行", "雨，会冲淡很多东西，却冲不淡记忆。"],
    ["00:28 – 00:36", "男主认真凝视女主", "有些话，藏在眼神里，胜过千言万语。"],
    ["00:36 – 00:45", "手机屏幕闪烁，收到消息", "一条消息，打破了所有的平静。"],
    ["00:45 – 00:54", "女主转身离开，背影镜头", "转身的那一刻，才明白有些人只能陪你一程。"],
    ["00:54 – 01:02", "城市街道夜景，镜头拉远", "夜色依旧，人潮如常，故事却留在了心里。"],
  ];
  const [rows, setRows] = usePersistentState("narrato.fine.script.rows", defaultRows);
  const [editing, setEditing] = useState(null);
  const [rhythm, setRhythm] = usePersistentState("narrato.fine.script.rhythm", "标准节奏");
  const moveRow = (index, direction) => {
    const target = index + direction;
    if (target < 0 || target >= rows.length) return;
    const next = [...rows];
    [next[index], next[target]] = [next[target], next[index]];
    setRows(next);
  };
  const updateRow = (index, fieldIndex, value) => {
    setRows(rows.map((row, i) => (i === index ? row.map((item, j) => (j === fieldIndex ? value : item)) : row)));
  };
  return (
    <section className="script-panel">
      <div className="fine-tools">
        <button onClick={() => setRows(defaultRows.map(([time, visual, copy], index) => [time, `${visual}（重排镜头${index + 1}）`, copy]))} type="button">↻ 重新生成</button>
        <button onClick={() => setRhythm(rhythm === "标准节奏" ? "快节奏" : "标准节奏")} type="button">☷ 调整节奏：{rhythm}</button>
        <span>▣ 片段 {rows.length}　◷ 总时长 01:02　🔗 已匹配 {rows.length}</span>
      </div>
      <table>
        <colgroup><col className="clip-col" /><col className="time-col" /><col className="visual-col" /><col className="copy-col" /><col className="action-col" /></colgroup>
        <thead><tr><th>片段</th><th>时间段</th><th>画面内容</th><th>解说文案</th><th>操作</th></tr></thead>
        <tbody>{rows.map(([time, visual, copy], i) => (
          <tr key={`${time}-${i}`}>
            <td>{String(i + 1).padStart(2, "0")}</td>
            <td>{time}</td>
            <td>{editing === i ? <input className="cell-editor" value={visual} onChange={(event) => updateRow(i, 1, event.target.value)} /> : visual}</td>
            <td>{editing === i ? <input className="cell-editor" value={copy} onChange={(event) => updateRow(i, 2, event.target.value)} /> : copy}</td>
            <td className="table-actions">
              <button onClick={() => setEditing(editing === i ? null : i)} type="button">{editing === i ? "完成" : "编辑"}</button>
              <button onClick={() => moveRow(i, -1)} disabled={i === 0} type="button">上移</button>
              <button onClick={() => moveRow(i, 1)} disabled={i === rows.length - 1} type="button">下移</button>
            </td>
          </tr>
        ))}</tbody>
      </table>
    </section>
  );
}

function VoiceSubtitlePanel() {
  const defaultVoiceRows = [
    ["00:00:00 – 00:00:10", "她被所有人看不起"],
    ["00:00:10 – 00:00:22", "却是隐藏的顶级大佬"],
    ["00:00:22 – 00:00:35", "三年前的一场商业阴谋"],
    ["00:00:35 – 00:00:47", "让林晚失去了一切"],
    ["00:00:47 – 00:01:02", "所有人都以为她从此沉沦"],
  ];
  const [voiceRows, setVoiceRows] = usePersistentState("narrato.fine.voice.rows", defaultVoiceRows.map((row) => [...row, "已生成"]));
  const [voiceName, setVoiceName] = usePersistentState("narrato.fine.voice.name", "温柔女声");
  const [align, setAlign] = usePersistentState("narrato.fine.subtitle.align", "中");
  const [color, setColor] = usePersistentState("narrato.fine.subtitle.color", "yellow");
  const [musicPlaying, setMusicPlaying] = usePersistentState("narrato.fine.music.playing", false);
  const [volume, setVolume] = usePersistentState("narrato.fine.music.volume", 30);
  const setVoiceStatus = (index, status) => setVoiceRows(voiceRows.map((row, i) => (i === index ? [row[0], row[1], status] : row)));
  const regenerateVoice = () => setVoiceRows(voiceRows.map(([time, text]) => [time, text, `已重配 · ${voiceName}`]));
  return (
    <div className="voice-layout">
      <section className="voice-card">
        <h2>配音</h2>
        <label className="voice-select-label">选择音色<span className="voice-select"><img src="/assets/d16/voice-avatar.png" alt="" /><input value={voiceName} onChange={(event) => setVoiceName(event.target.value)} /><i>⌄</i></span></label>
        <button onClick={regenerateVoice} type="button">↻ 重新生成配音</button>
        <p className="segment-label">分段配音（共 5 段）</p>
        <table>
          <thead><tr><th>序号</th><th>时间</th><th>解说内容</th><th>状态</th><th>操作</th></tr></thead>
          <tbody>{voiceRows.map(([time, text, status], index) => (
            <tr key={time}>
              <td>{index + 1}</td><td>{time}</td><td>{text}</td><td>{status}</td>
              <td className="table-actions"><button onClick={() => setVoiceStatus(index, "试听中")} type="button">试听</button><button onClick={() => setVoiceStatus(index, `已重配 · ${voiceName}`)} type="button">重配</button></td>
            </tr>
          ))}</tbody>
        </table>
        <div className="voice-pagination"><button>‹</button><b>1</b><button>›</button></div>
      </section>
      <section className="subtitle-card-fine">
        <h2>字幕</h2>
        <button className="restore-subtitle" onClick={() => {
          setAlign("中");
          setColor("yellow");
        }} type="button">↻ 恢复默认</button>
        <label>字体<input value="思源黑体" readOnly /></label>
        <label>字号<input value="40 px" readOnly /></label>
        <div className="subtitle-align"><span>位置</span>{["左", "中", "右"].map((item) => <button className={align === item ? "active" : ""} key={item} onClick={() => setAlign(item)} type="button">{item}</button>)}</div>
        <div className="subtitle-colors"><span>颜色</span>{["white", "yellow", "black"].map((item) => <i className={`${item}${color === item ? " active" : ""}`} key={item} onClick={() => setColor(item)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") setColor(item); }} role="button" tabIndex={0} />)}<button onClick={() => setColor(color === "yellow" ? "white" : "yellow")} type="button">🎨⌄</button></div>
        <b className="preview-label">样式预览</b>
        <img className="subtitle-preview-img" src="/assets/d16/subtitle-preview.png" alt="字幕样式预览" />
      </section>
      <section className="music-bar">♫ 背景音乐（可选） <img src="/assets/d16/music-thumb.png" alt="" /><span>温暖治愈 · 钢琴</span><button onClick={() => setMusicPlaying(!musicPlaying)} type="button">{musicPlaying ? "暂停" : "试听"}</button><i>音量</i><strong style={{ background: `linear-gradient(90deg, var(--red) ${volume}%, #d8dde7 ${volume}%)` }} onClick={() => setVolume(volume >= 90 ? 30 : volume + 15)} /><em>{volume}%</em></section>
    </div>
  );
}

function ExportConfirmPanel({ navigate }) {
  const confirmed = [
    ["T", "字幕"],
    ["▤", "剧情理解"],
    ["✎", "解说文案"],
    ["✂", "剪辑脚本"],
    ["◖", "配音字幕"],
  ];
  const tasks = [
    ["🎙", "处理配音", "已完成"],
    ["T", "处理字幕", "已完成"],
    ["▶", "处理视频素材", "已完成"],
    ["▣", "生成成片", "等待开始"],
  ];
  return (
    <div className="export-confirm">
      <section><h2>合成视频</h2><p><i className="ok-dot">✓</i>准备合成</p><small>所有步骤已确认，点击下方按钮开始合成视频</small><ul>{tasks.map(([icon, item, status], index) => <li key={item}><i className={`task-icon c${index}`}>{icon}</i>{item}<span>{status} <em>{index < 3 ? "✓" : "◷"}</em></span></li>)}</ul><button onClick={() => navigate?.("D08")}>▶ 开始合成视频</button></section>
      <aside><h2>已确认内容</h2>{confirmed.map(([icon, item], index) => <p key={item}><i className={`confirm-icon c${index}`}>{icon}</i>{item}<span>已确认 <em>✓</em></span></p>)}<div className="output-title">输出设置</div><div className="export-output"><b><i className="meta-icon phone" /><span>9:16<br />视频比例</span></b><b><i className="meta-icon hd" /><span>1080P<br />视频分辨率</span></b><b><i className="meta-icon file" /><span>MP4<br />视频格式</span></b></div></aside>
    </div>
  );
}

function SettingsScreen({ id, title, navigate, interactive }) {
  const defaultValues = {
    protocol: "OpenAI兼容",
    model: "gpt-4o-mini",
    baseUrl: "https://api.openai.com/v1",
    apiKey: "••••••••••••••••••••••••",
    tavily: "",
    defaultOption: "默认配置",
    serviceUrl: "https://api.example.com",
    resourceDir: "/resources",
    style: "标准",
    preview: "开启",
  };
  const [settings, setSettings] = usePersistentState("narrato.config.center", defaultValues);
  const [notice, setNotice] = useState("");
  const updateSetting = (key, value) => setSettings({ ...settings, [key]: value });
  const save = () => {
    writeStorage("narrato.config.center", settings);
    setNotice("配置已保存到 localStorage");
    window.setTimeout(() => setNotice(""), 1800);
  };
  const reset = () => {
    setSettings(defaultValues);
    setNotice("已恢复默认配置");
    window.setTimeout(() => setNotice(""), 1800);
  };
  return (
    <>
      <TopNav active="配置中心" navigate={navigate} />
      <section className="settings-page page">
        <h1>配置中心</h1>
        <div className="settings-layout">
          <aside>
            {["模型与接口", "配音设置", "字幕设置", "背景音乐", "视频导出", "通用设置"].map((item, index) => (
              <button
                className={item === title ? "active" : ""}
                key={item}
                onClick={() => navigate?.(["D27", "D28", "D29", "D30", "D31", "D27"][index])}
                type="button"
              >
                {item}
              </button>
            ))}
          </aside>
          <div className="settings-content">
            <SettingsContent id={id} title={title} settings={interactive ? settings : defaultValues} updateSetting={updateSetting} editable={interactive} />
          </div>
        </div>
        {notice && <div className="product-toast settings-notice">{notice}</div>}
        <footer className="settings-footer">
          <button onClick={reset}>重置</button>
          <button className="primary" onClick={save}>保存配置</button>
        </footer>
      </section>
    </>
  );
}

function SettingsContent({ id, title, settings, updateSetting, editable }) {
  if (id === "D27") {
    return (
      <>
        <ConfigGroup title="视觉分析模型" groupKey="vision" fields={["协议", "模型名称", "Base URL", "API Key"]} settings={settings} updateSetting={updateSetting} editable={editable} />
        <ConfigGroup title="文案生成模型" groupKey="copy" fields={["协议", "模型名称", "Base URL", "API Key"]} settings={settings} updateSetting={updateSetting} editable={editable} />
        <ConfigGroup title="联网检索" groupKey="search" fields={["Tavily API Key"]} settings={settings} updateSetting={updateSetting} editable={editable} compact />
      </>
    );
  }
  if (id === "D29") return <SubtitleSettings editable={editable} />;
  return <ConfigGroup title={title} groupKey={id} fields={["默认选项", "服务地址", "资源目录", "音量 / 样式", "预览设置"]} settings={settings} updateSetting={updateSetting} editable={editable} />;
}

function SubtitleSettings({ editable = false }) {
  const [asrStatus, setAsrStatus] = usePersistentState("narrato.subtitle.asrStatus", "● 未测试");
  return (
    <div className="subtitle-settings-page">
      <div className="subtitle-form">
        <section><h2>1. 字幕开关</h2><label>启用字幕 <span className="switch on" /></label></section>
        <section><h2>2. 自动字幕</h2><div className="two-col"><label>自动提取字幕 <span className="switch on" /></label><label>ASR服务<input defaultValue="FunASR" readOnly={!editable} /></label><label>API URL<input defaultValue="https://api.funasr.com/v1/asr" readOnly={!editable} /></label><label>热词（可选）<input defaultValue="请输入热词，多个热词用逗号分隔" readOnly={!editable} /></label><label>说话人识别 <span className="check-red">✓</span></label><label>连接状态 <b>{asrStatus}</b></label></div><button onClick={() => setAsrStatus("● 连接成功")}>测试连接</button></section>
        <section><h2>3. 字体样式</h2><div className="two-col"><label>字体<input value="SimHei" readOnly /></label><label>字体大小<span className="range" /><input value="60 px" readOnly /></label><label>字体颜色<input value="□" readOnly /></label><label>描边颜色<input value="■" readOnly /></label><label>描边宽度<span className="range short" /><input value="1.5 px" readOnly /></label></div></section>
        <section><h2>4. 位置</h2><div className="position-tabs"><button>顶部</button><button>居中</button><button className="active">底部</button><button>自定义</button></div><div className="position-grid"><div>竖屏（9:16）<span className="dots" /></div><label>Y 轴位置<span className="range short" /><input value="8 %" readOnly /></label><div>横屏（16:9）<span className="dots" /></div><label>Y 轴位置<span className="range short" /><input value="8 %" readOnly /></label></div></section>
        <section><h2>5. 字幕遮罩</h2><label>启用字幕遮罩 <span className="switch" /></label><button disabled>设置遮罩</button></section>
      </div>
      <aside className="subtitle-preview-config"><h2>预览（9:16）</h2><img src="/assets/d29/preview.png" alt="字幕预览" /></aside>
    </div>
  );
}

function SubtitleSettingsScreen({ navigate }) {
  return (
    <>
      <TopNav active="配置中心" navigate={navigate} />
      <section className="subtitle-settings-screen page">
        <aside className="config-rail">{["模型与接口", "配音设置", "字幕设置", "背景音乐", "视频导出", "通用设置"].map((item) => <button className={item === "字幕设置" ? "active" : ""} key={item}>{item}</button>)}</aside>
        <h1>字幕设置</h1>
        <SubtitleSettings />
        <footer><button>保存配置</button><button>恢复默认</button></footer>
      </section>
    </>
  );
}

function getSettingKey(groupKey, field, index) {
  const map = ["protocol", "model", "baseUrl", "apiKey"];
  if (field === "Tavily API Key") return "tavily";
  if (["默认选项", "服务地址", "资源目录", "音量 / 样式", "预览设置"].includes(field)) {
    return ["defaultOption", "serviceUrl", "resourceDir", "style", "preview"][index];
  }
  return `${groupKey}.${map[index] ?? field}`;
}

function defaultFieldValue(field, index, settings) {
  if (field === "Tavily API Key") return settings.tavily ?? "";
  return index === 0 ? "OpenAI兼容" : index === 1 ? "gpt-4o-mini" : index === 2 ? "https://api.openai.com/v1" : "••••••••••••••••••••••••";
}

function ConfigGroup({ title, fields, groupKey, settings, updateSetting, editable, compact = false }) {
  return (
    <section className={compact ? "config-group compact" : "config-group"}>
      <h2>{title}</h2>
      {fields.map((field, index) => (
        <label key={field}>
          <span>{field}</span>
          <input
            value={settings[getSettingKey(groupKey, field, index)] ?? defaultFieldValue(field, index, settings)}
            onChange={(event) => updateSetting?.(getSettingKey(groupKey, field, index), event.target.value)}
            readOnly={!editable}
          />
        </label>
      ))}
    </section>
  );
}

function HelpScreen({ navigate }) {
  return (
    <>
      <TopNav active="帮助" navigate={navigate} />
      <section className="help-page page">
        <h1>帮助中心</h1>
        <p>这是 NarratoAI C 端产品原型的可交互帮助页，覆盖素材上传、生成模式、精细流程和配置保存。</p>
        <div className="help-grid">
          <article><b>1. 如何开始创作？</b><span>从首页选择影视解说、短剧解说、画面解说或短剧混剪，上传素材后进入自动或精细模式。</span><button onClick={() => navigate?.("D01")}>回到首页</button></article>
          <article><b>2. 自动模式会做什么？</b><span>系统模拟字幕处理、剧情理解、文案、配音和合成进度，完成后可进入成片结果页。</span><button onClick={() => navigate?.("D09")}>查看生成中</button></article>
          <article><b>3. 配置如何保存？</b><span>配置中心表单可编辑，保存后写入 localStorage；重置会恢复默认 mock 配置。</span><button onClick={() => navigate?.("D27")}>打开配置中心</button></article>
        </div>
      </section>
    </>
  );
}

function BaselineTodo({ screen }) {
  return (
    <>
      <TopNav active={screen.id.startsWith("D27") ? "配置中心" : "我的作品"} />
      <section className="todo-page page">
        <h1>{screen.title}</h1>
        <p>该页面已进入基准映射，后续按 PNG diff 逐页重建。</p>
        <img src={screen.baseline} alt={`${screen.id} PNG 基准`} />
      </section>
    </>
  );
}
