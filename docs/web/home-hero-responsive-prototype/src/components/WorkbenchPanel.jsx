import { Coins, Sparkle } from "@phosphor-icons/react";
import { useState } from "react";
import { AnalysisFlow } from "./AnalysisFlow.jsx";
import { Timeline } from "./Timeline.jsx";
import { ToolCards } from "./ToolCards.jsx";
import { VideoPreview } from "./VideoPreview.jsx";

export function WorkbenchPanel() {
  const [activeTool, setActiveTool] = useState("commentary");
  const [playing, setPlaying] = useState(false);

  return (
    <div className="workbench-shell">
      <div className="workbench-depth-frame workbench-depth-frame--far" aria-hidden="true" />
      <div className="workbench-depth-frame workbench-depth-frame--near" aria-hidden="true" />
      <div className="workbench-top-reflection" aria-hidden="true"><span /></div>
      <div className="workbench-side-face" aria-hidden="true" />
      <div className="workbench-bottom-face" aria-hidden="true" />
      <div className="workbench-void-rail" aria-hidden="true" />
      <div className="workbench-reflection" aria-hidden="true" />
      <article className="workbench-panel" aria-label="AI 出片工作台预览">
        <header className="workbench-topbar">
          <div className="workbench-name">
            <span><Sparkle weight="fill" /></span>
            智能出片工作台
          </div>
          <div className="credit-balance">
            <Coins weight="duotone" aria-hidden="true" />
            <span>创作点</span>
            <strong>1,280</strong>
            <button type="button">充值</button>
            <img src="/assets/d16/voice-avatar.png" alt="当前用户头像" />
          </div>
        </header>

        <div className="workbench-content">
          <AnalysisFlow />
          <VideoPreview playing={playing} onToggle={() => setPlaying((value) => !value)} />
          <ToolCards activeTool={activeTool} onSelect={setActiveTool} />
        </div>

        <Timeline />
      </article>
    </div>
  );
}
