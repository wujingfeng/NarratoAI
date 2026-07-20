import { useRef } from "react";

export function VideoUploadPanel({ videos, maxVideos, isDragging, onFiles, onDragStateChange, onRemove, onSubtitleSelect }) {
  const inputRef = useRef(null);
  const acceptFiles = (files) => onFiles(Array.from(files));

  return (
    <section className="create-video-panel" aria-labelledby="create-video-title">
      <div className="create-video-panel__heading">
        <div><h2 id="create-video-title">上传视频素材</h2><p>最多 {maxVideos} 个，支持 MP4、MOV、AVI</p></div>
      </div>
      <div
        className={`create-video-dropzone${isDragging ? " is-dragging" : ""}`}
        onDragEnter={(event) => { event.preventDefault(); onDragStateChange(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => onDragStateChange(false)}
        onDrop={(event) => { event.preventDefault(); onDragStateChange(false); acceptFiles(event.dataTransfer.files); }}
      >
        <p>拖拽视频到这里，或选择本地文件</p>
        <button type="button" onClick={() => inputRef.current?.click()}>选择视频</button>
        <input ref={inputRef} type="file" accept="video/mp4,video/quicktime,video/x-msvideo" multiple hidden onChange={(event) => { acceptFiles(event.target.files); event.target.value = ""; }} />
      </div>
      <ol className="create-video-list">
        {videos.map((video, index) => (
          <li data-video-row key={video.id}>
            <span data-video-index>{String(index + 1).padStart(2, "0")}</span>
            <div><strong>{video.name}</strong><small>{video.durationLabel} · {video.subtitleStatus}</small></div>
            <label>字幕<input type="file" accept=".srt,application/x-subrip,text/plain" onChange={(event) => { const [file] = event.target.files; if (file) onSubtitleSelect(video.id, file); event.target.value = ""; }} /></label>
            <button type="button" aria-label={`删除 ${video.name}`} onClick={() => onRemove(video.id)}>删除</button>
          </li>
        ))}
      </ol>
    </section>
  );
}
