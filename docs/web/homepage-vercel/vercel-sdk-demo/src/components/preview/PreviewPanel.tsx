import { useProjectStore } from "../../features/project/store";
import { VideoPlayer } from "./VideoPlayer";
import { RenderProgress } from "./RenderProgress";
import { ArtifactList } from "./ArtifactList";

export function PreviewPanel() {
  const stage = useProjectStore((s) => s.render.stage);
  return (
    <section className="preview-panel">
      {stage === "idle" && <VideoPlayer />}
      {(stage === "tts" ||
        stage === "subtitle" ||
        stage === "mixing" ||
        stage === "encoding") && (
        <>
          <VideoPlayer />
          <RenderProgress />
        </>
      )}
      {stage === "done" && (
        <>
          <RenderProgress />
          <ArtifactList />
        </>
      )}
    </section>
  );
}
