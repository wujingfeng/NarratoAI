"""LLM-powered SRT subtitle correction."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable

from loguru import logger

from app.services.llm.manager import LLMServiceManager
from app.services.llm.migration_adapter import _run_async_safely
from app.services.llm.unified_service import UnifiedLLMService
from app.services.subtitle_text import has_timecodes, normalize_subtitle_text, read_subtitle_text
from app.utils import utils


class SubtitleCorrectionError(RuntimeError):
    """Raised when subtitle correction cannot produce a valid SRT."""


DEFAULT_BATCH_SIZE = 20
DEFAULT_MAX_REPAIR_ATTEMPTS = 3
DEFAULT_GLOBAL_CONTEXT_MAX_CHARS = 4000

CorrectionProgressCallback = Callable[[int, int, str], None]


_TIME_LINE_RE = re.compile(
    r"^\s*\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}(?:\s+.*)?$"
)
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class SubtitleBlock:
    order: int
    index_line: str
    time_line: str
    text: str


def _ensure_llm_providers_registered() -> None:
    if LLMServiceManager.is_registered():
        return
    from app.services.llm.providers import register_all_providers

    register_all_providers()


def parse_srt_blocks(srt_content: str) -> list[SubtitleBlock]:
    normalized = normalize_subtitle_text(srt_content)
    if not normalized or not has_timecodes(normalized):
        raise SubtitleCorrectionError("字幕内容为空或未检测到有效 SRT 时间轴")

    blocks: list[SubtitleBlock] = []
    raw_blocks = re.split(r"\n\s*\n", normalized)
    for raw_block in raw_blocks:
        lines = [line.rstrip() for line in raw_block.splitlines() if line.strip()]
        if not lines:
            continue

        if len(lines) >= 2 and _TIME_LINE_RE.match(lines[1]):
            index_line = lines[0].strip()
            time_line = lines[1].strip()
            text = "\n".join(lines[2:]).strip()
        elif _TIME_LINE_RE.match(lines[0]):
            index_line = str(len(blocks) + 1)
            time_line = lines[0].strip()
            text = "\n".join(lines[1:]).strip()
        else:
            raise SubtitleCorrectionError(f"无法解析字幕块: {raw_block[:80]}")

        blocks.append(
            SubtitleBlock(
                order=len(blocks) + 1,
                index_line=index_line,
                time_line=time_line,
                text=text,
            )
        )

    if not blocks:
        raise SubtitleCorrectionError("字幕内容为空或未检测到有效字幕块")
    return blocks


def _build_compact_global_context(
    blocks: list[SubtitleBlock],
    max_chars: int = DEFAULT_GLOBAL_CONTEXT_MAX_CHARS,
) -> str:
    context = "\n".join(block.text.strip() for block in blocks if block.text.strip()).strip()
    if len(context) <= max_chars:
        return context

    suffix = "\n...[已截断]"
    return context[: max(0, max_chars - len(suffix))].rstrip() + suffix


def _build_correction_prompt(
    blocks: list[SubtitleBlock],
    *,
    global_context: str = "",
) -> str:
    payload = [
        {
            "id": block.order,
            "time": block.time_line,
            "text": block.text,
        }
        for block in blocks
    ]
    return f"""
请校准以下 SRT 字幕文本中的明显语音识别错误。字幕可能是中文、英文、日文、韩文或其他语言，也可能包含多语言混合内容。

校准要求：
1. 先结合当前批字幕和全片字幕上下文识别原语言、专名和语境，保持原语言输出；多语言混合内容也要保持原有语言混合方式。
2. 只纠正明显的 ASR 错字、拼写错误、同音或近音误识别、词形误识别、专有名词前后不一致。
3. 不要润色、扩写、改写句意，不要翻译，不要增删剧情信息。
4. 不要修改时间轴、序号、条目数量或条目顺序。
5. 不确定的内容保持原样。
6. 保留必要的说话人标记、标点和换行。

全片字幕上下文（仅供判断语言、专名和前后语境，不要按上下文增删当前批字幕）：
{global_context or "（无）"}

只输出严格 JSON，不要输出 Markdown 或解释文字。格式必须为：
{{"items":[{{"id":1,"text":"校准后的字幕文本"}}]}}

待校准字幕条目：
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()


def _get_positive_int(value: Any, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _resolve_batch_size(batch_size: int | None = None) -> int:
    return _get_positive_int(batch_size, DEFAULT_BATCH_SIZE, minimum=1, maximum=200)


def _resolve_repair_attempts(repair_attempts: int | None = None) -> int:
    # 当前语义是最大总尝试次数：首轮校准 + 后续修复轮次。
    return _get_positive_int(repair_attempts, DEFAULT_MAX_REPAIR_ATTEMPTS, minimum=1, maximum=5)


def _split_blocks(blocks: list[SubtitleBlock], batch_size: int) -> list[list[SubtitleBlock]]:
    return [blocks[index:index + batch_size] for index in range(0, len(blocks), batch_size)]


def _build_repair_prompt(
    *,
    blocks: list[SubtitleBlock],
    previous_output: str,
    error_message: str,
    global_context: str = "",
) -> str:
    payload = [
        {
            "id": block.order,
            "time": block.time_line,
            "text": block.text,
        }
        for block in blocks
    ]
    return f"""
你上一轮返回的字幕校准 JSON 无法通过校验，请修复后重新输出。

校验错误：
{error_message}

原始字幕条目：
{json.dumps(payload, ensure_ascii=False, indent=2)}

全片字幕上下文（仅供判断语言、专名和前后语境，不要按上下文增删当前批字幕）：
{global_context or "（无）"}

上一轮输出：
{previous_output}

请只输出严格 JSON，不要输出 Markdown 或解释文字。格式必须为：
{{"items":[{{"id":1,"text":"校准后的字幕文本"}}]}}
必须包含并且只包含原始字幕条目的所有 id；不要修改时间轴、序号、条目数量或条目顺序。
""".strip()


def _call_progress_callback(
    progress_callback: CorrectionProgressCallback | None,
    completed: int,
    total: int,
    message: str,
) -> None:
    if not progress_callback:
        return
    try:
        progress_callback(completed, total, message)
    except Exception as exc:
        logger.debug(f"字幕校准进度回调失败: {exc}")


def _extract_json_text(raw_output: str) -> str:
    text = str(raw_output or "").strip()
    block_match = _JSON_BLOCK_RE.search(text)
    if block_match:
        return block_match.group(1).strip()

    if not text.startswith(("{", "[")):
        starts = [pos for pos in (text.find("{"), text.find("[")) if pos >= 0]
        if starts:
            start = min(starts)
            end = max(text.rfind("}"), text.rfind("]"))
            if end > start:
                return text[start:end + 1]
    return text


def _parse_corrections(raw_output: str, expected_ids: set[int]) -> dict[int, str]:
    json_text = _extract_json_text(raw_output)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise SubtitleCorrectionError("LLM 未返回有效 JSON 字幕校准结果") from exc

    if isinstance(data, dict) and "items" in data:
        items = data["items"]
    elif isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = []
        for key, value in data.items():
            try:
                item_id = int(key)
            except (TypeError, ValueError) as exc:
                raise SubtitleCorrectionError(f"LLM 字幕校准结果包含无法解析的字幕 id: {key}") from exc
            items.append({"id": item_id, "text": value})
    else:
        raise SubtitleCorrectionError("LLM 字幕校准结果格式无效")

    corrections: dict[int, str] = {}
    returned_ids: list[int] = []
    duplicate_ids: set[int] = set()
    if not isinstance(items, list):
        raise SubtitleCorrectionError("LLM 字幕校准结果缺少 items 列表")

    for item in items:
        if not isinstance(item, dict):
            raise SubtitleCorrectionError("LLM 字幕校准结果 items 中包含非对象条目")
        if "id" not in item:
            raise SubtitleCorrectionError("LLM 字幕校准结果 items 中存在缺少 id 的条目")
        try:
            item_id = int(item.get("id"))
        except (TypeError, ValueError) as exc:
            raise SubtitleCorrectionError(f"LLM 字幕校准结果包含无法解析的字幕 id: {item.get('id')}") from exc
        if item_id in returned_ids:
            duplicate_ids.add(item_id)
        returned_ids.append(item_id)
        if item_id in expected_ids:
            corrections[item_id] = str(item.get("text") or "").strip()

    extra_ids = sorted(set(returned_ids) - expected_ids)
    if extra_ids:
        raise SubtitleCorrectionError(f"LLM 字幕校准结果包含额外字幕条目: {extra_ids[:10]}")
    if duplicate_ids:
        raise SubtitleCorrectionError(f"LLM 字幕校准结果包含重复字幕条目: {sorted(duplicate_ids)[:10]}")

    missing_ids = sorted(expected_ids - set(corrections.keys()))
    if missing_ids:
        raise SubtitleCorrectionError(f"LLM 字幕校准结果缺少字幕条目: {missing_ids[:10]}")
    return corrections


def _render_srt(blocks: list[SubtitleBlock], corrections: dict[int, str]) -> str:
    rendered_blocks = []
    for block in blocks:
        corrected_text = corrections.get(block.order, "").strip() or block.text
        rendered_blocks.append(f"{block.index_line}\n{block.time_line}\n{corrected_text}")
    return "\n\n".join(rendered_blocks).rstrip() + "\n"


def _correct_chunk(
    *,
    chunk: list[SubtitleBlock],
    chunk_index: int,
    total_chunks: int,
    provider: str,
    api_key: str,
    base_url: str,
    temperature: float,
    repair_attempts: int,
    global_context: str = "",
) -> dict[int, str]:
    start_order = chunk[0].order
    end_order = chunk[-1].order
    expected_ids = {block.order for block in chunk}
    logger.info(
        f"字幕校准批次 {chunk_index}/{total_chunks} 开始: "
        f"条目 {start_order}-{end_order}, 共 {len(chunk)} 条"
    )

    prompt = _build_correction_prompt(chunk, global_context=global_context)
    last_output = ""
    last_error = ""
    for attempt in range(1, repair_attempts + 1):
        if attempt > 1:
            logger.warning(
                f"字幕校准批次 {chunk_index}/{total_chunks} 第 {attempt} 次修复: {last_error}"
            )
            prompt = _build_repair_prompt(
                blocks=chunk,
                previous_output=last_output,
                error_message=last_error,
                global_context=global_context,
            )

        try:
            raw_output = _run_async_safely(
                UnifiedLLMService.generate_text,
                prompt=prompt,
                system_prompt="你是一位专业的多语言字幕校对员，擅长修正 ASR 语音识别造成的明显错字、拼写错误、同音或近音误识别，同时严格保留字幕结构和原语言。",
                provider=provider,
                temperature=temperature,
                response_format="json",
                api_key=api_key,
                api_base=base_url,
            )
        except Exception as exc:
            message = (
                f"字幕校准批次 {chunk_index}/{total_chunks} 失败: "
                f"条目 {start_order}-{end_order}, {exc}"
            )
            logger.error(message)
            raise SubtitleCorrectionError(message) from exc

        last_output = str(raw_output or "")
        try:
            corrections = _parse_corrections(last_output, expected_ids)
        except SubtitleCorrectionError as exc:
            last_error = str(exc)
            if attempt >= repair_attempts:
                message = (
                    f"字幕校准批次 {chunk_index}/{total_chunks} 失败: "
                    f"条目 {start_order}-{end_order}, {last_error}"
                )
                logger.error(message)
                raise SubtitleCorrectionError(message) from exc
            continue

        logger.info(
            f"字幕校准批次 {chunk_index}/{total_chunks} 完成: "
            f"条目 {start_order}-{end_order}"
        )
        return corrections

    raise SubtitleCorrectionError(
        f"字幕校准批次 {chunk_index}/{total_chunks} 未生成有效结果: 条目 {start_order}-{end_order}"
    )


def correct_srt_content(
    srt_content: str,
    *,
    provider: str = "",
    api_key: str = "",
    base_url: str = "",
    temperature: float = 0.1,
    batch_size: int | None = None,
    repair_attempts: int | None = None,
    progress_callback: CorrectionProgressCallback | None = None,
) -> str:
    blocks = parse_srt_blocks(srt_content)
    _ensure_llm_providers_registered()

    resolved_batch_size = _resolve_batch_size(batch_size)
    resolved_repair_attempts = _resolve_repair_attempts(repair_attempts)
    chunks = _split_blocks(blocks, resolved_batch_size)
    global_context = _build_compact_global_context(blocks)
    total_chunks = len(chunks)
    total_blocks = len(blocks)

    logger.info(
        f"开始批量校准字幕: 共 {total_blocks} 条, {total_chunks} 批, "
        f"每批最多 {resolved_batch_size} 条"
    )
    _call_progress_callback(
        progress_callback,
        0,
        total_blocks,
        f"开始校准字幕，共 {total_blocks} 条，{total_chunks} 批",
    )

    corrections: dict[int, str] = {}
    completed_blocks = 0
    for chunk_index, chunk in enumerate(chunks, start=1):
        chunk_corrections = _correct_chunk(
            chunk=chunk,
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            repair_attempts=resolved_repair_attempts,
            global_context=global_context,
        )
        corrections.update(chunk_corrections)
        completed_blocks += len(chunk)
        message = (
            f"字幕校准进度: {completed_blocks}/{total_blocks} 条, "
            f"完成批次 {chunk_index}/{total_chunks}"
        )
        _call_progress_callback(progress_callback, completed_blocks, total_blocks, message)

    missing_ids = sorted({block.order for block in blocks} - set(corrections.keys()))
    if missing_ids:
        raise SubtitleCorrectionError(f"字幕校准结果缺少字幕条目: {missing_ids[:10]}")

    corrected_srt = _render_srt(blocks, corrections)
    logger.info(f"字幕校准完成，共 {total_blocks} 条")
    return corrected_srt


def write_srt_file(srt_content: str, subtitle_file: str = "") -> str:
    if not subtitle_file:
        subtitle_file = os.path.join(utils.subtitle_dir(), "subtitle_corrected.srt")
    parent = os.path.dirname(subtitle_file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(subtitle_file, "w", encoding="utf-8") as f:
        f.write(srt_content)
    return subtitle_file


def correct_subtitle_file(
    subtitle_file: str,
    output_file: str = "",
    *,
    provider: str = "",
    api_key: str = "",
    base_url: str = "",
    temperature: float = 0.1,
    batch_size: int | None = None,
    repair_attempts: int | None = None,
    progress_callback: CorrectionProgressCallback | None = None,
) -> str:
    if not subtitle_file or not os.path.isfile(subtitle_file):
        raise SubtitleCorrectionError(f"字幕文件不存在: {subtitle_file}")

    decoded = read_subtitle_text(subtitle_file)
    corrected_srt = correct_srt_content(
        decoded.text,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        batch_size=batch_size,
        repair_attempts=repair_attempts,
        progress_callback=progress_callback,
    )
    return write_srt_file(corrected_srt, output_file)
