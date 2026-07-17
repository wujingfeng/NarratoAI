import { TextReader, ZipWriter } from "@zip.js/zip.js";

function exportEnvironment(environment = window) {
  return environment;
}

/** 剪映草稿只允许在带 File System Access 的桌面 Chrome/Edge 导出。 */
export function supportsJianyingExport(environment = exportEnvironment()) {
  const userAgent = environment.navigator?.userAgent || "";
  const desktopChromium = /(?:Chrome|Edg)\/\d+/.test(userAgent)
    && !/Android|Mobile|iPhone|iPad|CriOS|FxiOS/i.test(userAgent);
  return desktopChromium && typeof environment.showSaveFilePicker === "function";
}

function manifestReader(file) {
  if (typeof file.content === "string") return new TextReader(file.content);
  if (file.content_base64) return new TextReader(atob(file.content_base64));
  return null;
}

/**
 * 将每项 Manifest 内容按 entry 流式写入 ZIP；绝不聚合为 Blob。
 * 文件系统 writable 在成功后关闭、在失败后 abort，调用方可重新选择位置重试。
 */
export async function writeManifestAsZipStream(manifest, writable, dependencies = {}) {
  const request = dependencies.fetch || fetch;
  const sink = new WritableStream({ write: (chunk) => writable.write(chunk) });
  const zipWriter = (dependencies.createZipWriter || ((target) => new ZipWriter(target)))(sink);
  try {
    for (const file of manifest.files || []) {
      const inline = manifestReader(file);
      if (inline) {
        await zipWriter.add(file.zip_path, inline);
        continue;
      }
      if (!file.url) throw new Error(`Manifest file ${file.zip_path} has no content or URL`);
      const response = await request(file.url, { headers: { Range: "bytes=0-" } });
      if (!response.ok || !response.body) throw new Error(`CDN ${response.status}`);
      await zipWriter.add(file.zip_path, response.body);
    }
    await zipWriter.close();
    await writable.close();
  } catch (error) {
    await writable.abort?.(error);
    throw error;
  }
}

/** 弹出保存位置后创建浏览器本地 ZIP；不请求服务器端 ZIP 或 Artifact。 */
export async function exportJianyingZip(manifest, environment = exportEnvironment()) {
  if (!supportsJianyingExport(environment)) throw new Error("仅支持桌面 Chrome/Edge 导出到剪映草稿");
  const handle = await environment.showSaveFilePicker({
    suggestedName: manifest.package_name || "jianying-draft.zip",
    types: [{ description: "ZIP archive", accept: { "application/zip": [".zip"] } }],
  });
  await writeManifestAsZipStream(manifest, await handle.createWritable());
}
