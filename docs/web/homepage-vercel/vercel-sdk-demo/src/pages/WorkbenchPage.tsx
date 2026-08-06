import { useEffect, useState } from "react";
import { ChatPanel } from "../components/chat/ChatPanel";
import { PreviewPanel } from "../components/preview/PreviewPanel";
import { InspectorPanel } from "../components/inspector/InspectorPanel";
import { postJSON } from "../lib/api";

export function WorkbenchPage() {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [title, setTitle] = useState<string>("");

  useEffect(() => {
    let alive = true;
    postJSON<{ id: string; title: string }>("/api/projects", {
      title: "演示项目",
    })
      .then((p) => {
        if (alive) {
          setProjectId(p.id);
          setTitle(p.title);
        }
      })
      .catch((err) => {
        console.error("[WorkbenchPage] 创建项目失败", err);
      });
    return () => {
      alive = false;
    };
  }, []);

  if (!projectId) return <div className="loading">初始化项目…</div>;
  return (
    <div className="workbench">
      <header className="workbench__topbar">
        <span className="workbench__brand">vercel-sdk-demo</span>
        <span className="workbench__title">{title}</span>
      </header>
      <div className="workbench__grid">
        <ChatPanel projectId={projectId} />
        <PreviewPanel />
        <InspectorPanel />
      </div>
    </div>
  );
}
