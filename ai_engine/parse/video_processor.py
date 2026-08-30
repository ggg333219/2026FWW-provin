"""
视频/音频处理器 (video_processor.py)

使用成熟开源方案解析视频/音频，带多级回退链确保始终产出 chunks。

处理管线（各阶段依次尝试，任一成功即返回）：
  - 元数据提取:    纯 Python 文件分析（始终可用）
  - 关键帧抽取:    FFmpeg → 跳过（无依赖时返回空）
  - 帧视觉描述:    Qwen-VL (LLMClient) → 基础元数据描述
  - ASR 语音识别:  Faster-Whisper → 不可用标记

依赖安装（可选，非必须）：
    pip install faster-whisper
    ffmpeg 需在系统 PATH 中

使用方式：
    from ai_engine.parse.video_processor import VideoProcessor

    vp = VideoProcessor()

    # 一次性全量解析
    result = vp.process("path/to/video.mp4")
    # -> [{"type": "video_meta|frame|transcript", ...}]

    # 渐进式流式解析（用于 SSE 推送）
    async for chunk in vp.process_stream("path/to/video.mp4"):
        print(chunk["type"], chunk["content"][:50])
"""

import asyncio
import base64
import os
import struct
import subprocess
import tempfile
from typing import Any, AsyncGenerator, Optional

from ai_engine.core.llm import LLMClient


def _resolve_tool(name: str) -> Optional[str]:
    """
    解析外部工具的可执行路径。

    优先取系统 PATH 中的同名工具；若 name 为 "ffmpeg" 且 PATH 中不存在，
    则回退到 imageio-ffmpeg 自带的静态 ffmpeg 二进制（pip install imageio-ffmpeg）。
    注意：imageio-ffmpeg 只提供 ffmpeg，不提供 ffprobe。

    Returns:
        str 或 None（找不到时返回 None，由调用方走降级路径）。
    """
    from shutil import which
    found = which(name)
    if found:
        return found
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None
    return None


class VideoProcessor:
    """
    视频处理器，多级回退确保始终产出解析块。

    处理管线：
      1. 提取视频元数据（纯 Python，始终可用）
      2. FFmpeg 抽帧 + Qwen-VL Caption（降级时跳过）
      3. Faster-Whisper ASR（降级时标记不可用）
      4. 保底：至少返回一个 metadata chunk

    也支持纯音频处理（process_audio）。
    """

    def __init__(
        self,
        max_keyframes: int = 5,
        whisper_model: Optional[str] = None,
        asr_language: Optional[str] = None,
        vlm_model: Optional[str] = None,
        llm_model: Optional[str] = None,
        initial_prompt: Optional[str] = None,
    ):
        """
        Args:
            max_keyframes: 最大抽取关键帧数。
            whisper_model: Faster-Whisper 模型尺寸
                           ("base", "small", "medium", "large-v3", 或 HuggingFace 路径)。
            asr_language:  ASR 语言代码（"zh"/"en"/None=自动检测）。
            vlm_model:     多模态视觉模型名
                           (默认 "qwen-vl-plus"，可被 AI_VLM_MODEL 环境变量覆盖)。
            llm_model:     ASR 纠错用的 LLM 模型名
                           (默认 settings.MODEL，可被 AI_MODEL 环境变量覆盖)。
            initial_prompt: Whisper initial_prompt，引导模型识别专有名词和领域术语。
                           默认值为中文 AI/工具/编程场景的领域提示词；传空字符串禁用。


        """
        self.max_keyframes = max_keyframes
        # whisper 模型解析优先级（离线优先）：
        #   显式参数 > AI_WHISPER_MODEL 环境变量 > 项目内置模型目录 > "base"（联网从 HF 下载）
        if whisper_model:
            self.whisper_model_name = whisper_model
        else:
            env_model = os.getenv("AI_WHISPER_MODEL")
            if env_model:
                self.whisper_model_name = env_model
            else:
                from pathlib import Path
                local_model_dir = (
                    Path(__file__).resolve().parent.parent / "data" / "models" / "faster-whisper-base"
                )
                self.whisper_model_name = (
                    str(local_model_dir) if local_model_dir.is_dir() else "base"
                )
        self.asr_language = asr_language
        self.initial_prompt = initial_prompt if initial_prompt is not None else (
            "这是一段关于 AI 工具、VS Code、PPT 制作、播客、Plexigate、编程的视频。"
        )
        self._vlm_model = vlm_model or os.getenv("AI_VLM_MODEL", "qwen-vl-plus")
        self._llm_model = llm_model or os.getenv("AI_MODEL", None)
        # 统一 LLM 客户端，VLM 和 ASR 纠错共用（模型名通过调用参数覆盖）
        self._llm_client: Optional[LLMClient] = None
        self._whisper_instance = None

    # ======================================================================
    # 主入口
    # ======================================================================

    def process(self, video_path: str) -> list[dict[str, Any]]:
        """
        处理视频：元数据 + 关键帧视觉摘要 + ASR 字幕。

        无论外部依赖是否齐全，始终返回至少一个块。

        Args:
            video_path: 视频文件路径。

        Returns:
            list[dict]: 统一原始块列表。
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件未找到: {video_path}")

        result: list[dict[str, Any]] = []

        # 0. 基础元数据（纯 Python，始终可用）
        meta = self._get_metadata(video_path)
        if meta:
            result.append(meta)

        # 1. FFmpeg 抽帧 + Qwen-VL Caption
        keyframes = self._extract_keyframes(video_path)
        for kf in keyframes:
            frame_desc = self._describe_frame_with_qwen(kf["path"])
            result.append({
                "type": "frame",
                "page": 0,
                "content": frame_desc,
                "metadata": {
                    "timestamp_sec": kf["timestamp_sec"],
                    "frame_path": kf["path"],
                    "vlm_model": self._vlm_model,
                },
            })

        # 2. ASR 语音识别
        asr_chunk = self._transcribe(video_path)
        if asr_chunk:
            result.append(asr_chunk)

        return result

    async def process_stream(
        self, video_path: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        渐进式流式处理视频，每个阶段实时 yield chunk。

        与 process() 不同，此方法不会等所有阶段完成才返回，
        而是在每个阶段产出数据时立即 yield，适合 SSE 流式推送。

        Yield 顺序:
          1. video_meta chunk（元数据，几乎即时）
          2. frame chunk × N（每处理完一个关键帧立即 yield）
          3. transcript chunk（ASR + LLM 纠错完成后）

        每个 yield 的 dict 结构与 process() 返回的原始块一致:
          {"type": "video_meta|frame|transcript", "page": 0, "content": "...", "metadata": {...}}

        Args:
            video_path: 视频文件路径。

        Yields:
            dict: 单个原始块（每阶段完成时）。
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件未找到: {video_path}")

        # 阶段 0: 元数据 — 纯 Python，几乎即时
        meta = self._get_metadata(video_path)
        if meta:
            yield meta

        # 阶段 1: 关键帧抽取（FFmpeg，IO 密集 → 线程池）
        loop = asyncio.get_running_loop()
        keyframes = await loop.run_in_executor(
            None, self._extract_keyframes, video_path
        )

        # 阶段 2: 逐帧 VLM 描述（网络 IO 密集），每完成一帧立即 yield
        for kf in keyframes:
            frame_desc = await loop.run_in_executor(
                None, self._describe_frame_with_qwen, kf["path"]
            )
            yield {
                "type": "frame",
                "page": 0,
                "content": frame_desc,
                "metadata": {
                    "timestamp_sec": kf["timestamp_sec"],
                    "frame_path": kf["path"],
                    "vlm_model": self._vlm_model,
                },
            }

        # 阶段 3: ASR 语音识别（CPU 密集 → 线程池）
        asr_chunk = await loop.run_in_executor(
            None, self._transcribe, video_path
        )
        if asr_chunk:
            yield asr_chunk

    def process_audio(self, audio_path: str) -> list[dict[str, Any]]:
        """
        处理纯音频文件：元数据 + ASR 语音识别。

        Args:
            audio_path: 音频文件路径。

        Returns:
            list[dict]: 统一原始块列表。
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件未找到: {audio_path}")

        result: list[dict[str, Any]] = []

        meta = self._get_metadata(audio_path)
        if meta:
            result.append(meta)

        asr_chunk = self._transcribe(audio_path)
        if asr_chunk:
            result.append(asr_chunk)

        return result

    async def process_audio_stream(
        self, audio_path: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        渐进式流式处理纯音频文件。

        Yield 顺序:
          1. video_meta chunk（元数据）
          2. transcript chunk（ASR + LLM 纠错完成后）

        Args:
            audio_path: 音频文件路径。

        Yields:
            dict: 单个原始块。
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件未找到: {audio_path}")

        meta = self._get_metadata(audio_path)
        if meta:
            yield meta

        loop = asyncio.get_running_loop()
        asr_chunk = await loop.run_in_executor(
            None, self._transcribe, audio_path
        )
        if asr_chunk:
            yield asr_chunk

    # ======================================================================
    # 视频元数据（纯 Python，始终可用）
    # ======================================================================

    @staticmethod
    def _parse_mp4_duration(file_path: str) -> float:
        """
        纯 Python 解析 MP4 文件时长（无需 ffprobe）。

        通过读取 moov → mvhd atom 获取 timescale 和 duration。
        适用于 MP4/M4V/M4A 等 ISO Base Media File Format。

        Returns:
            float: 时长（秒），解析失败返回 0.0。
        """
        try:
            with open(file_path, "rb") as f:
                # 扫描找到 moov box
                while True:
                    header = f.read(8)
                    if len(header) < 8:
                        break
                    box_size = struct.unpack(">I", header[:4])[0]
                    box_type = header[4:8]

                    if box_type == b"moov":
                        # 在 moov 内找 mvhd atom
                        moov_end = f.tell() + box_size - 8
                        while f.tell() < moov_end:
                            atom_header = f.read(8)
                            if len(atom_header) < 8:
                                break
                            atom_size = struct.unpack(">I", atom_header[:4])[0]
                            atom_type = atom_header[4:8]
                            if atom_type == b"mvhd":
                                # 跳过 version(1) + flags(3)
                                f.read(4)
                                # timescale (uint32) + duration (uint32)
                                # 或者 version=1 时是 uint64 + uint64
                                # 读取 version 字节判断
                                f.seek(-4, os.SEEK_CUR)  # 回到 version 开始处
                                version_data = f.read(1)
                                version = version_data[0]
                                f.read(3)  # flags
                                if version == 0:
                                    f.read(4)  # creation_time
                                    f.read(4)  # modification_time
                                    timescale = struct.unpack(">I", f.read(4))[0]
                                    duration = struct.unpack(">I", f.read(4))[0]
                                else:
                                    f.read(8)  # creation_time
                                    f.read(8)  # modification_time
                                    timescale = struct.unpack(">I", f.read(4))[0]
                                    duration = struct.unpack(">Q", f.read(8))[0]
                                if timescale > 0:
                                    return duration / timescale
                                break
                            else:
                                # 跳到下一个 atom
                                if atom_size < 8:
                                    break
                                f.seek(atom_size - 8, os.SEEK_CUR)
                        break
                    else:
                        if box_size < 8:
                            break
                        f.seek(box_size - 8, os.SEEK_CUR)
        except Exception:
            pass
        return 0.0

    @staticmethod
    def _get_metadata(media_path: str) -> Optional[dict[str, Any]]:
        """
        提取媒体文件基础元数据。

        纯 Python 实现，不依赖外部工具。
        如果 ffprobe 可用，补充更精确的时长和分辨率信息。
        """
        if not os.path.exists(media_path):
            return None

        file_size = os.path.getsize(media_path)
        file_name = os.path.basename(media_path)
        ext = os.path.splitext(file_name)[1].lower()

        metadata: dict[str, Any] = {
            "source_type": "video" if ext in (".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv") else "audio",
            "file_name": file_name,
            "file_size": file_size,
            "file_size_mb": round(file_size / (1024 * 1024), 2),
        }

        # 尝试 ffprobe 获取更精确信息
        duration = 0.0
        ffprobe_exe = _resolve_tool("ffprobe")
        if ffprobe_exe:
            try:
                result = subprocess.run(
                    [ffprobe_exe, "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", media_path],
                    capture_output=True, text=True, timeout=10, check=True,
                )
                duration = float(result.stdout.strip())
                metadata["duration_sec"] = round(duration, 2)
                metadata["duration_method"] = "ffprobe"

                # 获取分辨率
                try:
                    v_result = subprocess.run(
                        [ffprobe_exe, "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=width,height",
                         "-of", "csv=p=0", media_path],
                        capture_output=True, text=True, timeout=10, check=True,
                    )
                    parts = v_result.stdout.strip().split(",")
                    if len(parts) == 2:
                        metadata["width"] = int(parts[0])
                        metadata["height"] = int(parts[1])
                except Exception:
                    pass

            except Exception:
                # ffprobe 不可用 → 纯 Python 解析时长
                duration = VideoProcessor._parse_mp4_duration(media_path)
                if duration > 0:
                    metadata["duration_sec"] = round(duration, 2)
                    metadata["duration_method"] = "python_parser"
        else:
            duration = VideoProcessor._parse_mp4_duration(media_path)
            if duration > 0:
                metadata["duration_sec"] = round(duration, 2)
                metadata["duration_method"] = "python_parser"

        # 无 ffprobe 时，用 ffmpeg -i 的 stderr 解析分辨率（imageio-ffmpeg 场景）
        if "width" not in metadata:
            ffmpeg_exe = _resolve_tool("ffmpeg")
            if ffmpeg_exe and metadata.get("source_type") == "video":
                try:
                    import re
                    probe = subprocess.run(
                        [ffmpeg_exe, "-i", media_path],
                        capture_output=True, text=True, timeout=10,
                    )
                    m = re.search(
                        r"Stream #.*Video:.*?, (\d{2,5})x(\d{2,5})",
                        probe.stderr or "",
                    )
                    if m:
                        metadata["width"] = int(m.group(1))
                        metadata["height"] = int(m.group(2))
                        metadata["resolution_method"] = "ffmpeg_stderr"
                except Exception:
                    pass

        if not metadata.get("duration_sec"):
            metadata["duration_sec"] = 0.0
            metadata["duration_note"] = "无法获取视频时长"

        return {
            "type": "video_meta",
            "page": 0,
            "content": (
                f"文件: {metadata['file_name']}\n"
                f"大小: {metadata['file_size_mb']}MB\n"
                f"时长: {metadata['duration_sec']}秒\n"
                + (f"分辨率: {metadata.get('width', '?')}x{metadata.get('height', '?')}\n"
                   if "width" in metadata else "")
            ),
            "metadata": metadata,
        }

    # ======================================================================
    # FFmpeg 关键帧抽取
    # ======================================================================

    def _extract_keyframes(self, video_path: str) -> list[dict[str, Any]]:
        """
        使用 FFmpeg 按时间均匀抽帧。

        如果 ffmpeg 不可用，返回空列表（不阻塞流水线）。
        """
        ffmpeg_exe = _resolve_tool("ffmpeg")
        if not ffmpeg_exe:
            return []

        duration = self._get_video_duration(video_path)
        if duration <= 0:
            return []

        interval = max(int(duration // self.max_keyframes), 1)
        timestamps = list(range(0, int(duration), interval))[:self.max_keyframes]

        keyframes: list[dict[str, Any]] = []
        tmp_dir = tempfile.mkdtemp(prefix="video_frames_")

        for ts in timestamps:
            output_path = os.path.join(tmp_dir, f"frame_{ts:04d}.jpg")
            try:
                subprocess.run(
                    [ffmpeg_exe, "-y", "-ss", str(ts), "-i", video_path,
                     "-vframes", "1", "-q:v", "2", output_path],
                    capture_output=True, timeout=30, check=True,
                )
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    keyframes.append({"path": output_path, "timestamp_sec": ts})
            except (subprocess.SubprocessError, FileNotFoundError):
                continue

        return keyframes

    @staticmethod
    def _get_video_duration(video_path: str) -> float:
        """
        获取视频时长（秒），多级回退：
          1. ffprobe（PATH 中存在时，最精确）
          2. ffmpeg -i 输出中解析 Duration 行（imageio-ffmpeg 场景）
          3. 纯 Python 解析 MP4 moov/mvhd atom
        """
        # 1) ffprobe
        ffprobe_exe = _resolve_tool("ffprobe")
        if ffprobe_exe:
            try:
                result = subprocess.run(
                    [ffprobe_exe, "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", video_path],
                    capture_output=True, text=True, timeout=10, check=True,
                )
                return float(result.stdout.strip())
            except (subprocess.SubprocessError, ValueError, FileNotFoundError):
                pass

        # 2) ffmpeg -i 的 stderr 中解析 "Duration: 00:00:25.00"
        ffmpeg_exe = _resolve_tool("ffmpeg")
        if ffmpeg_exe:
            try:
                result = subprocess.run(
                    [ffmpeg_exe, "-i", video_path],
                    capture_output=True, text=True, timeout=10,
                )
                import re
                m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr or "")
                if m:
                    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
            except (subprocess.SubprocessError, FileNotFoundError):
                pass

        # 3) 纯 Python MP4 解析
        return VideoProcessor._parse_mp4_duration(video_path)

    # ======================================================================
    # 帧视觉描述 — Qwen-VL
    # ======================================================================

    def _describe_frame_with_qwen(self, frame_path: str) -> str:
        """
        使用 Qwen-VL 生成帧描述。

        降级策略：
          1. Qwen-VL via LLMClient — 需要 API key
          2. 返回图片基本信息（文件大小、尺寸）
          3. 完全不可用时返回占位标记
        """
        # 1) Qwen-VL 主方案（通过统一 LLMClient，按调用传入 vlm 模型名）
        try:
            if self._llm_client is None:
                self._llm_client = LLMClient(temperature=0.1, timeout=300)

            with open(frame_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("utf-8")

            response = self._llm_client.chat_messages(
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url",
                             "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}},
                            {"type": "text",
                             "text": "这是教学视频的一个关键帧。请用中文简要描述："
                                     "1）画面主要内容；2）是否有文字、公式或图表；"
                                     "3）这段可能的教学主题是什么。"},
                        ],
                    }
                ],
                model=self._vlm_model,
            )
            return response.content.strip()
        except Exception:
            pass

        # 2) 基础文件信息（降级）
        try:
            from PIL import Image
            img = Image.open(frame_path)
            size_info = f"尺寸: {img.width}x{img.height}"
            file_size = os.path.getsize(frame_path)
            return f"(帧图像: {size_info}, {round(file_size/1024,1)}KB — 需配置 VLM 模型获取详细描述)"
        except Exception:
            pass

        # 3) 完全降级
        return "(视频关键帧 — 需配置 VLM 模型获取帧内容描述)"

    # ======================================================================
    # ASR — Faster-Whisper
    # ======================================================================

    def _transcribe(self, media_path: str) -> Optional[dict[str, Any]]:
        """
        语音识别 + LLM 纠错，含多级回退。

        降级策略：
          1. Faster-Whisper — 最优方案，带时间戳
          2. LLM 纠错 — 修正 ASR 识别错误，使输出通顺合理
          3. 标记 ASR 不可用 — 返回基本信息

        Returns:
            dict 或 None（完全无法提取语音信息时返回 None）。
        """
        # 1) Faster-Whisper 主方案（失败返回空列表 → 自然走降级分支）
        segments = self._transcribe_with_faster_whisper(media_path)

        if segments:
            combined_raw = "\n".join(
                f"[{seg['start']:.1f}s-{seg['end']:.1f}s] {seg['text']}"
                for seg in segments
            )

            # 2) LLM 纠错 — 将 ASR 原始文本送入 LLM 修正
            corrected = self._correct_asr_text(combined_raw)

            return {
                "type": "transcript",
                "page": 0,
                "content": corrected,
                "metadata": {
                    "source": "faster-whisper",
                    "model": self.whisper_model_name,
                    "segment_count": len(segments),
                    "segments": segments[:100],
                    "llm_corrected": True,
                },
            }

        # 3) 降级
        return self._make_asr_fallback("Faster-Whisper 未安装或识别无结果")

    # ======================================================================
    # ASR 文本 LLM 纠错
    # ======================================================================

    def _correct_asr_text(self, raw_text: str) -> str:
        """
        使用 LLM 对 ASR 语音识别文本进行纠错，使输出通顺合理。

        ASR 常见问题：
          - 同音字/近音字错误（如"普通"→"普京"、"AI"→"爱"）
          - 断句不合理
          - 专有名词识别错误
          - 口语语气词/重复

        纠错要求：
          - 修正识别错误，保留原意
          - 保留时间戳标记 [xx.xs-xx.xs]
          - 不增删实质性教学内容
          - 使文本通顺、合理

        降级策略：
          1. LLM 纠错 — 调用 core/LLMClient（使用配置的 AI_BASE_URL）
          2. 返回原始文本 — LLM 不可用或因任何原因失败时

        Args:
            raw_text: 带时间戳的 ASR 原始文本。

        Returns:
            str: 纠错后的文本（或原始文本的降级）。
        """
        # 无内容或不含时间戳 → 直接返回
        if not raw_text.strip() or "[" not in raw_text:
            return raw_text

        # 截断过长的纠错文本：超过 1500 字符的前缀足以捕捉典型 ASR 错误模式，
        # 后面未被纠错的片段在时间戳上独立，不影响整体可读性
        truncated = raw_text[:1500] if len(raw_text) > 1500 else raw_text

        try:
            # 使用统一的 LLMClient（避免重复创建）
            if self._llm_client is None:
                self._llm_client = LLMClient(temperature=0.1, timeout=300)

            # 增强型 ASR 纠错 prompt — 针对口语转文字的常见问题
            prompt = (
                "你是一个文本校对员。请将以下语音识别出来的口语字幕进行纠错和润色：\n"
                "1. 修正明显的同音错别字（如将 Cup Code 改为 VS Code，PBT 改为 PPT）。\n"
                "2. 删除无意义的口头禅（如 '嗯'、'啊'、'就是说'）。\n"
                "3. 保持原本的意思不变，输出通顺的段落。\n"
                "4. 保持原有的时间戳标记 [xx.xs-xx.xs] 完全不变、换行结构不变。\n\n"
                "原始字幕：\n"
                f"{truncated}"
            )
            response = self._llm_client.chat(
                system="你是一个文本校对员，负责将语音识别出来的口语字幕进行纠错和润色。", user=prompt,
                model=self._llm_model or "qwen-turbo",
            )

            if not response.used_fallback:
                corrected = response.content.strip()
                if corrected and "[" in corrected:
                    # 如果截断纠错，将未纠错的剩余部分拼接回去
                    if len(raw_text) > 1500:
                        return corrected + raw_text[1500:]
                    return corrected

        except Exception:
            pass

        return raw_text

    @staticmethod
    def _make_asr_fallback(reason: str) -> dict[str, Any]:
        """构造 ASR 降级响应块。"""
        return {
            "type": "transcript",
            "page": 0,
            "content": f"[ASR 语音识别不可用] {reason}。如需语音转文字，请安装: pip install faster-whisper",
            "metadata": {
                "source": "fallback",
                "note": reason,
            },
        }

    def _merge_segments_smart(
        self,
        segments: list[dict[str, Any]],
        max_pause: float = 1.5,
    ) -> list[dict[str, Any]]:
        """
        智能长句合并。

        不要直接用 Whisper 默认的短时间戳切行，而是：
          - 只有遇到句末标点（。？；！.!?）或停顿超过 max_pause 秒时才切分。
          否则将碎片化的段落拼成一个完整长句。

        Args:
            segments: 原始 segment 列表（含 start / end / text）。
            max_pause: 最大允许停顿秒数（超过则切分），默认 1.5s。

        Returns:
            list[dict]: 合并后的 segment 列表。
        """
        if not segments:
            return segments

        merged = [segments[0].copy()]
        for seg in segments[1:]:
            prev = merged[-1]
            gap = seg["start"] - prev["end"]
            prev_text = prev["text"].strip()
            # 判断前一句是否以句末标点结尾
            ends_with_punct = any(
                prev_text.endswith(p) for p in ("。", "？", "；", "！", ".", "?", "!", ";")
            )

            if gap < max_pause and not ends_with_punct:
                # 合并：延后结束时间，拼接文本
                prev["end"] = seg["end"]
                prev["text"] = f"{prev_text}，{seg['text'].strip()}"
            else:
                merged.append(seg.copy())

        return merged

    def _transcribe_with_faster_whisper(
        self,
        media_path: str,
    ) -> list[dict[str, Any]]:
        """
        使用 Faster-Whisper 进行语音识别，返回带时间戳的片段列表。

        增强特性：
          - 传入 initial_prompt 引导专有名词识别
          - 智能长句合并（取代默认 0.8s 切行）
        """
        try:
            if self._whisper_instance is None:
                from faster_whisper import WhisperModel

                self._whisper_instance = WhisperModel(
                    model_size_or_path=self.whisper_model_name,
                    device="cpu",
                    compute_type="int8",
                )

            # 注入 initial_prompt 挽救专有名词
            transcribe_kwargs = dict(
                beam_size=5,
                language=self.asr_language,
            )
            if self.initial_prompt:
                transcribe_kwargs["initial_prompt"] = self.initial_prompt

            segments, info = self._whisper_instance.transcribe(
                media_path,
                **transcribe_kwargs,
            )

            raw_segments = [
                {
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": seg.text.strip(),
                }
                for seg in segments
                if seg.text and seg.text.strip()
            ]

            # 智能长句合并：仅按标点或 >1.5s 停顿切分
            return self._merge_segments_smart(raw_segments)

        except ImportError:
            return []
        except Exception as e:
            # 保留错误信息用于排查（模型下载失败、音频解码失败等），但不阻塞流水线
            import logging
            logging.getLogger(__name__).warning(
                "Faster-Whisper 转写失败（将走 ASR 降级路径）: %s: %s",
                type(e).__name__, e,
            )
            return []
