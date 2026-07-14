"""
视频预处理模块

提供场景切换检测、关键帧提取和视频预处理主流程功能。
使用 FFmpeg scene filter 检测镜头切换点，并为每个镜头提取代表性关键帧。
"""

import os
import re
import subprocess
from typing import List, Tuple

from loguru import logger

from app.models.diagnosis_schema import PreprocessedVideo
from app.utils.video_processor import VideoProcessor
from app.services.video_diagnosis.profiles import VideoTypeProfile, get_video_type_profile


def _write_minimal_jpeg(filepath: str) -> None:
    """写入一个最小合法 JPEG 文件作为最终兜底"""
    # 最小合法 JPEG: SOI + APP0 + DQT + SOF0 + DHT + SOS + EOI
    # 使用 1x1 灰色像素
    minimal_jpeg = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00,
        0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB,
        0x00, 0x43, 0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07,
        0x07, 0x07, 0x09, 0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B,
        0x0B, 0x0C, 0x19, 0x12, 0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E,
        0x1D, 0x1A, 0x1C, 0x1C, 0x20, 0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C,
        0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29, 0x2C, 0x30, 0x31, 0x34, 0x34,
        0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32, 0x3C, 0x2E, 0x33, 0x34,
        0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00, 0x01, 0x01,
        0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00, 0x01, 0x05,
        0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01,
        0x03, 0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00,
        0x01, 0x7D, 0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21,
        0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32,
        0x81, 0x91, 0xA1, 0x08, 0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1,
        0xF0, 0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0A, 0x16, 0x17, 0x18,
        0x19, 0x1A, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x34, 0x35, 0x36,
        0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
        0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x63, 0x64,
        0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75, 0x76, 0x77,
        0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8A,
        0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
        0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5,
        0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7,
        0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9,
        0xDA, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA,
        0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF,
        0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x7B, 0x94,
        0x11, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xD9,
    ])
    with open(filepath, "wb") as f:
        f.write(minimal_jpeg)


class ShotDetector:
    """镜头检测器 - 使用FFmpeg scene filter检测场景切换点"""

    def __init__(self, threshold: float = 0.4):
        """
        Args:
            threshold: 场景切换敏感度阈值 (0.2-0.6), 默认0.4
                       值越小越敏感(检测到更多切换点)
        """
        self.threshold = threshold

    def detect_scenes(self, video_path: str) -> List[Tuple[float, float]]:
        """
        检测视频中的场景切换点, 返回镜头列表

        Args:
            video_path: 视频文件路径

        Returns:
            镜头列表: [(start_sec, end_sec), ...]
                     例如: [(0.0, 3.5), (3.5, 8.2), (8.2, 12.0)]

        Raises:
            RuntimeError: FFmpeg执行失败
        """
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-vf",
            f"select='gt(scene,{self.threshold})',showinfo",
            "-f",
            "null",
            "-",
        ]

        try:
            result = subprocess.run(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                timeout=300,  # 5分钟超时
            )

            # 解析FFmpeg输出, 提取pts_time字段
            switch_points = self._parse_ffmpeg_output(result.stderr)

            # 构建镜头列表
            shots = self._build_shot_list(switch_points, video_path)

            logger.info(
                f"场景检测完成: 阈值={self.threshold}, "
                f"检测到 {len(shots)} 个镜头"
            )
            return shots

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"FFmpeg执行超时(视频: {video_path})")
        except Exception as e:
            raise RuntimeError(f"FFmpeg执行失败: {str(e)}")

    def _parse_ffmpeg_output(self, stderr: str) -> List[float]:
        """
        解析FFmpeg showinfo输出, 提取场景切换时间点

        Args:
            stderr: FFmpeg的stderr输出

        Returns:
            切换时间点列表(秒), 已排序
        """
        switch_points = []
        pattern = r"pts_time:(\d+\.?\d*)"

        for match in re.finditer(pattern, stderr):
            time_sec = float(match.group(1))
            switch_points.append(time_sec)

        # 去重并排序
        switch_points = sorted(set(switch_points))
        return switch_points

    def _build_shot_list(
        self, switch_points: List[float], video_path: str
    ) -> List[Tuple[float, float]]:
        """
        根据切换点构建镜头列表

        Args:
            switch_points: 场景切换时间点列表
            video_path: 视频文件路径(用于获取总时长)

        Returns:
            镜头列表: [(start, end), ...]
        """
        duration = self._get_video_duration(video_path)

        if not switch_points:
            # 没有检测到切换点, 整个视频作为一个镜头
            return [(0.0, duration)]

        shots = []
        prev_time = 0.0

        for switch_time in switch_points:
            if switch_time > prev_time + 0.5:  # 过滤过短的镜头(<0.5秒)
                shots.append((prev_time, switch_time))
                prev_time = switch_time  # 只在添加镜头时更新

        # 添加最后一个镜头
        if duration > prev_time + 0.5:
            shots.append((prev_time, duration))

        return shots

    def _get_video_duration(self, video_path: str) -> float:
        """获取视频总时长(秒)"""
        info = VideoProcessor.get_video_info(video_path)
        return float(info.get("duration", 0.0))


class KeyframeExtractor:
    """关键帧提取器 - 为每个镜头提取代表性关键帧"""

    @staticmethod
    def extract_for_shots(
        video_path: str,
        shots: List[Tuple[float, float]],
        output_dir: str,
    ) -> List[str]:
        """
        为每个镜头提取一张关键帧(取镜头中间时刻)

        Args:
            video_path: 视频文件路径
            shots: 镜头列表 [(start, end), ...]
            output_dir: 输出目录

        Returns:
            关键帧文件路径列表, 按镜头顺序排列
        """
        os.makedirs(output_dir, exist_ok=True)
        keyframe_paths = []

        for idx, (start, end) in enumerate(shots, start=1):
            # 取镜头中间时刻作为关键帧时间点
            middle_time = (start + end) / 2.0

            # 生成文件名: shot_001.jpg, shot_002.jpg, ...
            filename = f"shot_{idx:03d}.jpg"
            filepath = os.path.join(output_dir, filename)

            try:
                success = VideoProcessor.extract_frame_at_time(
                    video_path,
                    middle_time,
                    filepath,
                )
                if success:
                    keyframe_paths.append(filepath)
                else:
                    raise RuntimeError("extract_frame_at_time 返回 False")

            except Exception as e:
                logger.warning(f"提取镜头{idx}关键帧失败: {e}")
                # 创建占位文件
                placeholder = os.path.join(
                    output_dir, f"shot_{idx:03d}_placeholder.jpg"
                )
                fallback_ok = False
                try:
                    from PIL import Image

                    Image.new("RGB", (1920, 1080), color="gray").save(placeholder)
                    keyframe_paths.append(placeholder)
                    fallback_ok = True
                except Exception as img_err:
                    logger.warning(f"PIL 占位图创建失败，尝试最小 JPEG 兜底: {img_err}")

                if not fallback_ok:
                    # 最终兜底：手写一个最小合法 JPEG 文件
                    try:
                        _write_minimal_jpeg(placeholder)
                        keyframe_paths.append(placeholder)
                        fallback_ok = True
                    except Exception as final_err:
                        logger.error(f"所有兜底方式均失败 (镜头{idx}): {final_err}")

                if not fallback_ok:
                    # 确保 keyframe_paths 长度与 shots 一致，用空字符串占位
                    logger.error(f"镜头{idx}关键帧提取全部失败，使用空路径占位")
                    keyframe_paths.append("")

        assert len(keyframe_paths) == len(shots), (
            f"keyframe_paths 长度({len(keyframe_paths)})与 shots 长度({len(shots)})不一致"
        )
        logger.info(f"关键帧提取完成: {len(keyframe_paths)}/{len(shots)} 张")
        return keyframe_paths


class VideoPreprocessor:
    """视频预处理器 - 整合场景检测和关键帧提取"""

    def __init__(self, scene_threshold: float = 0.4, profile: VideoTypeProfile | None = None):
        """
        Args:
            scene_threshold: 场景切换敏感度阈值, 默认0.4
        """
        self.profile = profile or get_video_type_profile()
        threshold = self.profile.scene_threshold if profile else scene_threshold
        self.shot_detector = ShotDetector(threshold=threshold)
        self.keyframe_extractor = KeyframeExtractor()

    def preprocess(
        self,
        video_path: str,
        task_id: str,
        storage_base: str = "storage/tasks",
    ) -> PreprocessedVideo:
        """
        执行完整的视频预处理流程

        Args:
            video_path: 视频文件路径
            task_id: 任务ID
            storage_base: 存储基础目录

        Returns:
            PreprocessedVideo: 预处理结果

        Raises:
            RuntimeError: 预处理失败
        """
        # 1. 获取视频元信息
        logger.info(f"开始预处理视频: {video_path} (task_id={task_id})")

        video_info = VideoProcessor.get_video_info(video_path)
        if not video_info:
            raise RuntimeError(f"无法获取视频信息: {video_path}")

        duration = float(video_info.get("duration", 0.0))
        width = int(video_info.get("width", 0))
        height = int(video_info.get("height", 0))
        fps = float(video_info.get("fps", 0.0))

        if duration <= 0 or width <= 0 or height <= 0 or fps <= 0:
            raise RuntimeError(
                f"视频元信息无效: width={width}, height={height}, "
                f"fps={fps:.2f}, duration={duration:.2f}"
            )

        logger.info(
            f"视频信息: {width}x{height}, {fps:.1f}fps, {duration:.1f}s"
        )

        # 2. 检测场景切换
        shots = self.shot_detector.detect_scenes(video_path)

        if len(shots) == 0:
            raise RuntimeError("未检测到任何镜头")

        # 3. 提取关键帧
        keyframe_dir = os.path.join(storage_base, task_id, "keyframes")
        keyframe_paths = self.keyframe_extractor.extract_for_shots(
            video_path, shots, keyframe_dir
        )

        if not keyframe_paths or all(p == "" for p in keyframe_paths):
            raise RuntimeError(
                f"关键帧提取全部失败，无法继续诊断。请检查视频文件: {video_path}"
            )

        result = PreprocessedVideo(
            video_path=video_path,
            duration=duration,
            width=width,
            height=height,
            fps=fps,
            shots=shots,
            keyframe_dir=keyframe_dir,
            keyframe_paths=keyframe_paths,
        )

        logger.info(
            f"预处理完成: {len(shots)} 个镜头, "
            f"{len(keyframe_paths)} 张关键帧"
        )
        return result
