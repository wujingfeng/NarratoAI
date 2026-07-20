import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { createDebouncedEditorSaver, submitRender } from "../features/projects/projectApi.js";

const initialContent = { title: "未命名视频", notes: "" };

/**
 * Deliberately a content-draft editor, not a media editor. Media editing needs real
 * duration and track data; this screen only exposes the API's editable
 * project metadata and keeps every write behind its content-only debounce.
 */
export function ProjectEditorPage() {
  const { projectId } = useParams();
  const saverRef = useRef(null);
  const [content, setContent] = useState(initialContent);
  const [readOnly, setReadOnly] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const saver = createDebouncedEditorSaver(projectId);
    saverRef.current = saver;
    return () => saver.cancel?.();
  }, [projectId]);

  const updateContent = (field, value) => {
    if (readOnly || submitting) return;
    const next = { ...content, [field]: value };
    setContent(next);
    void saverRef.current(next).catch((error) => {
      setMessage(error.message || "草稿保存失败，请继续编辑后重试。");
    });
  };

  const handleRender = async () => {
    if (readOnly || submitting) return;
    saverRef.current?.cancel?.();
    setSubmitting(true);
    setMessage("");
    try {
      await submitRender(projectId, undefined, () => setReadOnly(true));
      setMessage("已提交渲染，草稿现为只读状态。");
    } catch (error) {
      setSubmitting(false);
      setMessage(error.message || "提交渲染失败，请重试。");
    }
  };

  return (
    <main className="project-editor" aria-labelledby="project-editor-title">
      <header className="project-editor__header">
        <div>
          <p className="project-editor__eyebrow">项目草稿</p>
          <h1 id="project-editor-title" data-route-heading tabIndex="-1">编辑项目内容</h1>
          <p>仅编辑项目文案；每次内容变更将自动保存。</p>
        </div>
        <Link to={`/projects/${projectId}/result`}>查看项目结果</Link>
      </header>

      <section className="project-editor__panel" aria-label="项目内容草稿">
        <label htmlFor="project-title">视频标题</label>
        <input
          id="project-title"
          value={content.title}
          onChange={(event) => updateContent("title", event.target.value)}
          readOnly={readOnly || submitting}
        />
        <label htmlFor="project-notes">创作说明</label>
        <textarea
          id="project-notes"
          value={content.notes}
          onChange={(event) => updateContent("notes", event.target.value)}
          readOnly={readOnly || submitting}
          rows="8"
        />
        <div className="project-editor__actions">
          <p aria-live="polite">{message || (readOnly ? "草稿已锁定" : "自动保存已开启")}</p>
          <button type="button" onClick={handleRender} disabled={readOnly || submitting}>
            {submitting ? "正在提交…" : readOnly ? "已提交渲染" : "提交渲染"}
          </button>
        </div>
      </section>
    </main>
  );
}
