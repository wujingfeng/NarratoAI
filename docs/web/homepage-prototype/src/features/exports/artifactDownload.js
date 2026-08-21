/**
 * 在不离开当前页面的前提下，把任意 CDN 上的产物下载到本地。
 * - 优先走 fetch + Blob：浏览器原生把 blob URL 写入下载目录，不会跳到预览页。
 * - 当 CDN 不带 CORS 头、无法 fetch 时，回退到 `<a download>` 仍然在当前页内触发下载；
 *   对完全无法控制的跨域地址，提示用户改用预览按钮。
 */

function filenameFromArtifact(artifact) {
  if (!artifact) return "artifact";
  if (typeof artifact.filename === "string" && artifact.filename) return artifact.filename;
  if (typeof artifact.id === "string" && artifact.id) return artifact.id;
  return "artifact";
}

function inferExtension(artifact, fallback = "bin") {
  if (typeof artifact?.filename === "string") {
    const ext = artifact.filename.split(".").pop();
    if (ext && ext.length <= 6) return ext;
  }
  if (typeof artifact?.content_type === "string") {
    const map = {
      "video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm",
      "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-m4a": "m4a",
      "application/json": "json", "text/vtt": "vtt", "text/plain": "txt",
    };
    if (map[artifact.content_type]) return map[artifact.content_type];
  }
  return fallback;
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(url), 0);
  return { method: "blob" };
}

function downloadViaAnchor(artifact) {
  // 兜底：保留 <a download>，对未携带 CORS 的资源某些浏览器仍会直接下载；
  // 如浏览器忽略 download 属性，也只会作为兜底，至少不会跳离当前 SPA 路由。
  const link = document.createElement("a");
  link.href = artifact.cdn_url;
  link.download = filenameFromArtifact(artifact);
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  return { method: "anchor" };
}

/**
 * 触发单个产物的下载。返回 { method, filename }；不会改变当前页路由。
 * @param {{ id?: string, filename?: string, content_type?: string, cdn_url?: string }} artifact
 * @param {{ fetcher?: typeof fetch }} [options]
 */
export async function downloadArtifact(artifact, options = {}) {
  if (!artifact?.cdn_url) throw new Error("产物缺少下载地址");
  const request = options.fetcher || fetch;
  const filename = filenameFromArtifact(artifact);
  const extension = inferExtension(artifact);
  const downloadName = filename.includes(".") ? filename : `${filename}.${extension}`;

  try {
    const response = await request(artifact.cdn_url, { mode: "cors" });
    if (!response.ok) throw new Error(`CDN ${response.status}`);
    const blob = await response.blob();
    downloadBlob(blob, downloadName);
    return { method: "blob", filename: downloadName };
  } catch (error) {
    // CORS 失败或网络失败：尝试在当前页内通过 <a download> 兜底，失败则抛出由调用方 toast。
    try {
      downloadViaAnchor(artifact);
      return { method: "anchor", filename: downloadName };
    } catch (anchorError) {
      throw error;
    }
  }
}
