import { ProjectInfoCard } from "./ProjectInfoCard";
import { PlotAnalysisCard } from "./PlotAnalysisCard";
import { ScriptSegmentsCard } from "./ScriptSegmentsCard";
import { VoiceSelectionCard } from "./VoiceSelectionCard";
import { RenderStatusCard } from "./RenderStatusCard";

export function InspectorPanel() {
  return (
    <aside className="inspector-panel">
      <ProjectInfoCard />
      <PlotAnalysisCard />
      <ScriptSegmentsCard />
      <VoiceSelectionCard />
      <RenderStatusCard />
    </aside>
  );
}
