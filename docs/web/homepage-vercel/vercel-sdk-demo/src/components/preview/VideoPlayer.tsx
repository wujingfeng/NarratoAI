import { useProjectStore } from "../../features/project/store";

export function VideoPlayer() {
  const videos = useProjectStore((s) => s.videos);
  const render = useProjectStore((s) => s.render);
  const first = videos[0];
  const src = render.artifactUrl
    ? render.artifactUrl
    : first
      ? `/media/episode-${(Date.now() % 3) + 1}.mp4`
      : null;

  if (!src)
    return <div className="player player--empty">等待视频上传…</div>;
  return (
    <div className="player">
      <video src={src} controls className="player__video" />
      <div className="player__caption">
        {render.artifactUrl ? "渲染产出" : first?.name ?? "视频"}
      </div>
    </div>
  );
}
