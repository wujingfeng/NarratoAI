from __future__ import annotations

import json
import math
import wave
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from core_api.adapters.narrato.media_probe import (
    AdapterError,
    SRT_MAX_BYTES,
    VIDEO_MAX_BYTES,
    parse_srt,
)
from core_api.infrastructure.oss_client import Downloader
from core_api.runtime.artifact_store import ArtifactStore
from core_api.runtime.workspace import CoreTaskWorkspace
from core_api.runtime.process_runner import ProcessRunner
from core_api.adapters.narrato.tts import TtsProvider, validate_wav

JSON_MAX_BYTES = 5 * 1024 * 1024


class RenderInputError(AdapterError):
    """不可变快照、来源或时间线输入无效。"""

    code = "RENDER_INPUT_INVALID"


class RenderTemporaryError(AdapterError):
    """渲染后端发生可自动重试的临时错误。"""

    code = "RENDER_TEMPORARY_FAILURE"
    retryable = True


class RenderBackend(Protocol):
    """接收显式输入路径的请求级渲染后端协议。"""

    def render(
        self,
        *,
        sources: Sequence[Path],
        source_order: Sequence[str],
        timeline: Sequence[Mapping[str, object]],
        output_dir: Path,
        heartbeat: Callable[[], None] | None = None,
    ) -> Mapping[str, object]:
        """返回最终视频、字幕和合并配音路径。"""
        ...


class FakeRenderBackend:
    """无 FFmpeg/网络依赖的确定性渲染测试后端。"""

    def render(self, *, sources, source_order, timeline, output_dir, heartbeat=None):
        """在 attempt output 内创建最小但非空的媒体产物。"""

        video = output_dir / "final.mp4"
        subtitle = output_dir / "subtitle.srt"
        voice = output_dir / "voice.wav"
        video.write_bytes(b"\x00\x00\x00\x18ftypmp42fake-render")
        cues = []
        adjusted = []
        cursor = 0.0
        for index, item in enumerate(timeline, 1):

            def stamp(value):
                milliseconds = int(float(value) * 1000)
                hours, remainder = divmod(milliseconds, 3_600_000)
                minutes, remainder = divmod(remainder, 60_000)
                seconds, millis = divmod(remainder, 1000)
                return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"

            duration = float(item["end"]) - float(item["start"])
            adjusted.append(
                {
                    **item,
                    "source_start": float(item["start"]),
                    "source_end": float(item["end"]),
                    "start": cursor,
                    "end": cursor + duration,
                }
            )
            cues.append(
                f"{index}\n{stamp(cursor)} --> {stamp(cursor + duration)}\n{item['narration']}\n"
            )
            cursor += duration
        subtitle.write_text("\n".join(cues), encoding="utf-8")
        with wave.open(str(voice), "wb") as output:
            output.setparams((1, 2, 16_000, 1_600, "NONE", "not compressed"))
            output.writeframes(b"\0\0" * 1_600)
        return {
            "video": video,
            "subtitle": subtitle,
            "voice": voice,
            "timeline": adjusted,
        }


@dataclass(slots=True)
class FfmpegRenderBackend:
    """用受治理 FFmpeg 与请求级 TTS Provider 合成最终媒体。"""

    provider: TtsProvider
    voice_snapshot: Mapping[str, object]
    runner: ProcessRunner
    timeout_seconds: float = 1800.0

    @staticmethod
    def _require_process_success(result) -> None:
        """区分可恢复进程超时与确定性媒体/codec/format 错误。"""
        if result.timed_out:
            raise RenderTemporaryError("RENDER_TEMPORARY_FAILURE")
        if result.exit_code != 0:
            raise RenderInputError("RENDER_MEDIA_INVALID")

    def render(self, *, sources, source_order, timeline, output_dir, heartbeat=None):
        """逐段裁剪、规范化视频与配音时长，再生成严格对齐的最终媒体。"""
        source_by_id = dict(zip(source_order, sources, strict=True))
        for source_id, source in source_by_id.items():
            try:
                probe = self.runner.run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        str(source),
                    ],
                    timeout_seconds=min(self.timeout_seconds, 60),
                    cwd=output_dir,
                    heartbeat=heartbeat,
                )
            except OSError as exc:
                raise RenderTemporaryError("RENDER_PROCESS_UNAVAILABLE") from exc
            self._require_process_success(probe)
            try:
                duration = float(probe.stdout.strip())
            except ValueError as exc:
                raise RenderInputError("RENDER_MEDIA_INVALID") from exc
            if not math.isfinite(duration) or duration <= 0:
                raise RenderInputError("RENDER_MEDIA_INVALID")
            if any(
                str(item["source_asset_id"]) == source_id
                and float(item["end"]) > duration + 0.02
                for item in timeline
            ):
                raise RenderInputError("RENDER_SOURCE_RANGE_INVALID")

        segment_voices: list[Path] = []
        durations: list[float] = []
        adjusted_timeline: list[dict[str, object]] = []
        cursor = 0.0
        for index, item in enumerate(timeline):
            source_duration = float(item["end"]) - float(item["start"])
            target = output_dir / f"voice_segment_{index:04}.wav"
            self.provider.synthesize(
                str(item["narration"]), target, voice_snapshot=self.voice_snapshot
            )
            validate_wav(target)
            with wave.open(str(target), "rb") as voice_file:
                voice_duration = voice_file.getnframes() / voice_file.getframerate()
            duration = max(source_duration, voice_duration)
            durations.append(duration)
            segment_voices.append(target)
            adjusted_timeline.append(
                {
                    **item,
                    "source_start": float(item["start"]),
                    "source_end": float(item["end"]),
                    "start": cursor,
                    "end": cursor + duration,
                }
            )
            cursor += duration

        subtitle = output_dir / "subtitle.srt"

        def stamp(value: float) -> str:
            total = int(round(value * 1000))
            hours, rem = divmod(total, 3_600_000)
            minutes, rem = divmod(rem, 60_000)
            seconds, millis = divmod(rem, 1_000)
            return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"

        subtitle.write_text(
            "\n".join(
                f"{index}\n{stamp(float(item['start']))} --> "
                f"{stamp(float(item['end']))}\n{item['narration']}\n"
                for index, item in enumerate(adjusted_timeline, 1)
            ),
            encoding="utf-8",
        )

        raw_video = output_dir / "video_raw.mp4"
        argv = ["ffmpeg", "-nostdin", "-y"]
        for item in timeline:
            argv.extend(
                [
                    "-ss",
                    str(item["start"]),
                    "-t",
                    str(float(item["end"]) - float(item["start"])),
                    "-i",
                    str(source_by_id[str(item["source_asset_id"])]),
                ]
            )
        filters = []
        for index, (item, duration) in enumerate(zip(timeline, durations, strict=True)):
            source_duration = float(item["end"]) - float(item["start"])
            extension = max(0.0, duration - source_duration)
            filters.append(
                f"[{index}:v:0]scale=640:360:force_original_aspect_ratio=decrease,"
                f"pad=640:360:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1,settb=AVTB,"
                f"setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={extension:.6f},"
                f"trim=duration={duration:.6f},setpts=PTS-STARTPTS[v{index}]"
            )
        labels = "".join(f"[v{index}]" for index in range(len(timeline)))
        filters.append(f"{labels}concat=n={len(timeline)}:v=1:a=0[v]")
        argv.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[v]",
                "-c:v",
                "libx264",
                str(raw_video),
            ]
        )
        result = self.runner.run(
            argv,
            timeout_seconds=self.timeout_seconds,
            cwd=output_dir,
            heartbeat=heartbeat,
        )
        self._require_process_success(result)

        voice = output_dir / "voice.wav"
        audio_argv = ["ffmpeg", "-nostdin", "-y"]
        for target in segment_voices:
            audio_argv.extend(["-i", str(target)])
        audio_filters = []
        for index, duration in enumerate(durations):
            audio_filters.append(
                f"[{index}:a:0]aresample=16000,apad,atrim=duration={duration:.6f},"
                f"asetpts=PTS-STARTPTS[a{index}]"
            )
        audio_labels = "".join(f"[a{index}]" for index in range(len(durations)))
        audio_filters.append(f"{audio_labels}concat=n={len(durations)}:v=0:a=1[a]")
        audio_argv.extend(
            [
                "-filter_complex",
                ";".join(audio_filters),
                "-map",
                "[a]",
                "-c:a",
                "pcm_s16le",
                str(voice),
            ]
        )
        result = self.runner.run(
            audio_argv,
            timeout_seconds=self.timeout_seconds,
            cwd=output_dir,
            heartbeat=heartbeat,
        )
        self._require_process_success(result)
        validate_wav(voice)

        final = output_dir / "final.mp4"
        total_duration = sum(durations)
        result = self.runner.run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-i",
                str(raw_video),
                "-i",
                str(voice),
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-t",
                f"{total_duration:.6f}",
                str(final),
            ],
            timeout_seconds=self.timeout_seconds,
            cwd=output_dir,
            heartbeat=heartbeat,
        )
        self._require_process_success(result)
        return {
            "video": final,
            "subtitle": subtitle,
            "voice": voice,
            "timeline": adjusted_timeline,
        }


@dataclass(slots=True)
class RenderAdapter:
    """按不可变 revision 与显式 source order 生成四类正式产物。"""

    downloader: Downloader
    backend: RenderBackend
    artifact_store: ArtifactStore

    def run_subtitle(
        self,
        *,
        workspace: CoreTaskWorkspace,
        core_task_id: str,
        attempt_no: int,
        snapshot_id: str,
        timeline: Sequence[Mapping[str, object]],
        lease_guard: Callable[[], None] | None = None,
    ) -> dict[str, object]:
        """从不可变时间线生成 UTF-8 SRT，不读取共享字幕文件。"""
        if not snapshot_id or not timeline:
            raise RenderInputError("RENDER_TIMELINE_INVALID")
        cues: list[str] = []
        previous = 0.0
        for index, item in enumerate(timeline, 1):
            start, end, text = item.get("start"), item.get("end"), item.get("text")
            if (
                type(start) not in (int, float)
                or type(end) not in (int, float)
                or not math.isfinite(float(start))
                or not math.isfinite(float(end))
                or float(start) < previous
                or float(end) <= float(start)
                or not isinstance(text, str)
                or not text.strip()
            ):
                raise RenderInputError("RENDER_TIMELINE_INVALID")
            previous = float(end)

            def stamp(value: float) -> str:
                total = int(value * 1000)
                hours, rem = divmod(total, 3_600_000)
                minutes, rem = divmod(rem, 60_000)
                seconds, millis = divmod(rem, 1_000)
                return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"

            cues.append(
                f"{index}\n{stamp(float(start))} --> {stamp(float(end))}\n{text.strip()}\n"
            )
        target = workspace.controlled_path("output", "subtitle", "srt")
        target.write_text("\n".join(cues), encoding="utf-8")
        if target.stat().st_size > SRT_MAX_BYTES:
            raise RenderInputError("RENDER_SUBTITLE_INVALID")
        metadata = parse_srt(target.read_bytes())
        if lease_guard:
            lease_guard()
        artifact = self.artifact_store.upload(
            workspace=workspace,
            local_path=target,
            core_task_id=core_task_id,
            attempt_no=attempt_no,
            kind="subtitle",
            content_type="application/x-subrip; charset=utf-8",
        )
        return {
            "metadata": {**metadata, "snapshot_id": snapshot_id},
            "artifacts": [artifact.to_dict()],
        }

    def run(
        self,
        *,
        workspace: CoreTaskWorkspace,
        core_task_id: str,
        attempt_no: int,
        snapshot_id: str,
        source_order: Sequence[str],
        sources: Sequence[Mapping[str, object]],
        timeline: Sequence[Mapping[str, object]],
        voice_id: str,
        voice_snapshot: Mapping[str, object],
        lease_guard: Callable[[], None] | None = None,
    ) -> dict[str, object]:
        """下载显式来源、验证时间线并上传 video/subtitle/voice/timeline。"""

        if not snapshot_id or voice_snapshot.get("voice_id") != voice_id:
            raise RenderInputError("RENDER_INPUT_INVALID")
        source_ids = [item.get("source_asset_id") for item in sources]
        if (
            list(source_order) != source_ids
            or len(source_ids) != len(set(source_ids))
            or not source_ids
        ):
            raise RenderInputError("RENDER_SOURCE_ORDER_INVALID")
        source_set = set(source_ids)
        validated: list[dict[str, object]] = []
        first_seen: list[str] = []
        for item in timeline:
            source_id = item.get("source_asset_id")
            start, end, narration = (
                item.get("start"),
                item.get("end"),
                item.get("narration"),
            )
            if (
                source_id not in source_set
                or type(start) not in (int, float)
                or type(end) not in (int, float)
                or not math.isfinite(float(start))
                or not math.isfinite(float(end))
                or float(start) < 0
                or float(end) <= float(start)
                or not isinstance(narration, str)
                or not narration.strip()
            ):
                raise RenderInputError("RENDER_TIMELINE_INVALID")
            if source_id not in first_seen:
                first_seen.append(str(source_id))
            validated.append(
                {
                    "source_asset_id": source_id,
                    "start": float(start),
                    "end": float(end),
                    "narration": narration.strip(),
                }
            )
        expected_seen = [item for item in source_order if item in first_seen]
        if first_seen != expected_seen or not validated:
            raise RenderInputError("RENDER_TIMELINE_INVALID")
        paths = []
        for index, source in enumerate(sources):
            target = workspace.controlled_path("input", f"source_{index:03}", "mp4")
            self.downloader.download(
                str(source["video_url"]), target, max_bytes=VIDEO_MAX_BYTES
            )
            paths.append(target)
        try:
            produced = self.backend.render(
                sources=paths,
                source_order=source_order,
                timeline=validated,
                output_dir=workspace.output_dir,
                heartbeat=lease_guard,
            )
        except AdapterError:
            raise
        except Exception as exc:
            raise RenderTemporaryError("RENDER_TEMPORARY_FAILURE") from exc
        rendered_timeline = produced.get("timeline")
        if not isinstance(rendered_timeline, Sequence) or isinstance(
            rendered_timeline, (str, bytes)
        ):
            raise RenderInputError("RENDER_OUTPUT_INVALID")
        timeline_path = workspace.controlled_path("output", "timeline", "json")
        timeline_path.write_text(
            json.dumps(
                {
                    "schema_version": "short-drama-render.v1",
                    "snapshot_id": snapshot_id,
                    "source_order": list(source_order),
                    "items": list(rendered_timeline),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        try:
            if timeline_path.stat().st_size > JSON_MAX_BYTES:
                raise RenderInputError("RENDER_TIMELINE_TOO_LARGE")
            subtitle = Path(produced["subtitle"])
            if subtitle.stat().st_size > SRT_MAX_BYTES:
                raise RenderInputError("RENDER_SUBTITLE_INVALID")
            parse_srt(subtitle.read_bytes())
            video, voice = Path(produced["video"]), Path(produced["voice"])
            for path in (video, subtitle, voice):
                if (
                    path.parent.resolve() != workspace.output_dir.resolve()
                    or not path.is_file()
                    or path.stat().st_size <= 0
                ):
                    raise RenderInputError("RENDER_OUTPUT_INVALID")
            with video.open("rb") as stream:
                if b"ftyp" not in stream.read(32):
                    raise RenderInputError("RENDER_VIDEO_INVALID")
            validate_wav(voice)
        except (OSError, KeyError, ValueError) as exc:
            if isinstance(exc, RenderInputError):
                raise
            raise RenderInputError("RENDER_OUTPUT_INVALID") from exc
        if lease_guard:
            lease_guard()
        uploaded = []
        try:
            for kind, path, content_type in (
                ("video", video, "video/mp4"),
                ("subtitle", subtitle, "application/x-subrip; charset=utf-8"),
                ("voice", voice, "audio/wav"),
                ("timeline", timeline_path, "application/json"),
            ):
                if lease_guard:
                    lease_guard()
                uploaded.append(
                    self.artifact_store.upload(
                        workspace=workspace,
                        local_path=path,
                        core_task_id=core_task_id,
                        attempt_no=attempt_no,
                        kind=kind,
                        content_type=content_type,
                    )
                )
        except BaseException:
            self.artifact_store.compensate(uploaded)
            raise
        return {
            "metadata": {"snapshot_id": snapshot_id, "source_count": len(paths)},
            "artifacts": [item.to_dict() for item in uploaded],
        }
