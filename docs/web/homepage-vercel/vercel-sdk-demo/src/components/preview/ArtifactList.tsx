import { useProjectStore } from "../../features/project/store";

export function ArtifactList() {
  const artifacts = useProjectStore((s) => s.render.artifacts);
  if (artifacts.length === 0) {
    return (
      <div className="artifact-list artifact-list--empty">
        渲染完成后这里会列出产物
      </div>
    );
  }
  return (
    <ul className="artifact-list">
      {artifacts.map((a) => (
        <li key={a.url} className="artifact-list__row">
          <span>{a.label}</span>
          <a href={a.url} target="_blank" rel="noreferrer">
            下载
          </a>
        </li>
      ))}
    </ul>
  );
}
