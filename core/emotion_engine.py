"""
聆心 - 多模态情感识别引擎
Optimized multimodal emotion recognition engine for university counselor AI platform.

Supports real-time streaming analysis, batch processing, risk alerting,
and report generation for student mental health monitoring.
"""

import os
import re
import json
import logging
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Generator, Tuple, Any

import numpy as np
import soundfile as sf

# 注：本模块不引入 torch/transformers —— 只做规则融合与风险联动，
# 声学推理由 core/speech_emotion.py（funasr，懒加载 + 优雅降级）承担，
# 便于小内存云服务器跳过重型 ML 依赖部署。

logger = logging.getLogger(__name__)

# ============================================================
# 配置与常量
# ============================================================

# 支持的12种情感标签
EMOTION_LABELS = [
    "正常", "高兴", "低落", "焦虑", "烦躁", "压抑",
    "愤怒", "恐惧", "惊讶", "厌恶", "悲伤", "紧张",
]

# 中文情感标签到英文的映射（用于内部处理）
EMOTION_MAP_CN_EN = {
    "正常": "neutral",
    "高兴": "happy",
    "低落": "down",
    "焦虑": "anxious",
    "烦躁": "irritated",
    "压抑": "depressed",
    "愤怒": "angry",
    "恐惧": "fearful",
    "惊讶": "surprised",
    "厌恶": "disgusted",
    "悲伤": "sad",
    "紧张": "nervous",
}

# 情感严重程度权重（用于风险评估）
EMOTION_SEVERITY = {
    "正常": 0,
    "高兴": 0,
    "惊讶": 1,
    "低落": 4,
    "烦躁": 5,
    "紧张": 5,
    "焦虑": 7,
    "悲伤": 7,
    "愤怒": 8,
    "压抑": 8,
    "恐惧": 9,
    "厌恶": 6,
}

# 高风险情感集合
HIGH_RISK_EMOTIONS = {"焦虑", "压抑", "恐惧", "愤怒", "悲伤"}
MEDIUM_RISK_EMOTIONS = {"烦躁", "低落", "紧张"}

# 默认采样率
DEFAULT_SAMPLE_RATE = 16000

# 模型名称
MODEL_NAME = "FunAudioLLM/SenseVoiceSmall"


# ============================================================
# 工具函数
# ============================================================

def _ffmpeg_convert(audio_path: str, target_sr: int = DEFAULT_SAMPLE_RATE) -> Tuple[np.ndarray, int]:
    """Use ffmpeg (via imageio-ffmpeg) to convert any audio format to numpy array."""
    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise RuntimeError("无法读取音频文件，请安装 imageio-ffmpeg 或将文件转换为 WAV 格式")

    import subprocess, tempfile
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        cmd = [
            ffmpeg_path, "-y", "-i", audio_path,
            "-ar", str(target_sr), "-ac", "1", "-f", "wav", tmp_path,
        ]
        subprocess.run(cmd, capture_output=True, timeout=60, check=True)
        audio, sr = sf.read(tmp_path, dtype="float32")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return audio, sr


def load_audio(audio_path: str, target_sr: int = DEFAULT_SAMPLE_RATE) -> Tuple[np.ndarray, int]:
    """
    加载音频文件，执行预处理：重采样至目标采样率，立体声转单声道。

    Args:
        audio_path: 音频文件路径
        target_sr: 目标采样率，默认16kHz

    Returns:
        (audio_data, sample_rate) 元组
    """
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    # Try soundfile first (works for WAV, FLAC, OGG); fall back to ffmpeg for MP3/M4A/etc.
    try:
        audio, sr = sf.read(audio_path, dtype="float32")
    except Exception:
        logger.info("soundfile 无法读取 %s，尝试使用 ffmpeg 转换", audio_path)
        audio, sr = _ffmpeg_convert(audio_path, target_sr)

    # 立体声转单声道：取各通道均值
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    # 重采样至目标采样率
    if sr != target_sr:
        try:
            import resampy
            audio = resampy.resample(audio, sr, target_sr)
        except ImportError:
            # 降级方案：使用简单的线性插值重采样
            logger.warning("resampy未安装，使用线性插值重采样")
            duration = len(audio) / sr
            target_len = int(duration * target_sr)
            audio = np.interp(
                np.linspace(0, len(audio) - 1, target_len),
                np.arange(len(audio)),
                audio,
            ).astype(np.float32)
        sr = target_sr

    return audio, sr


def audio_chunks_generator(
    audio_path: str, chunk_duration: float = 2.0, sr: int = DEFAULT_SAMPLE_RATE
) -> Generator[Tuple[np.ndarray, int], None, None]:
    """
    将音频文件分割为固定时长的块，用于流式处理。

    Args:
        audio_path: 音频文件路径
        chunk_duration: 每块时长（秒），默认2秒
        sr: 采样率

    Yields:
        (chunk_array, chunk_index) 元组
    """
    audio, file_sr = load_audio(audio_path, target_sr=sr)
    chunk_size = int(chunk_duration * sr)
    total_chunks = max(1, len(audio) // chunk_size)

    for i in range(total_chunks):
        start = i * chunk_size
        end = min(start + chunk_size, len(audio))
        yield audio[start:end], i

    # 处理最后一段不足一个完整块的音频
    remainder = audio[total_chunks * chunk_size :]
    if len(remainder) > 0:
        yield remainder, total_chunks

# ============================================================
# 1. 情感识别器
# ============================================================

class EmotionRecognizer:
    """
    基于音频特征提取 + LLM 分析的情感识别器。
    无需下载大型模型，通过提取音频声学特征并调用 DashScope LLM 进行情绪判断。
    """

    def __init__(self):
        """初始化识别器（无需加载模型）。"""
        self._loaded = True
        logger.info("情感识别器初始化完毕（音频特征+LLM模式）")

    def _extract_features(self, audio: np.ndarray, sr: int) -> Dict[str, Any]:
        """提取音频声学特征。"""
        duration = len(audio) / sr
        rms = float(np.sqrt(np.mean(audio ** 2)))
        peak = float(np.max(np.abs(audio)))
        zcr = float(np.sum(np.abs(np.diff(np.sign(audio)))) / (2 * len(audio)))
        # 短时能量分布
        frame_size = int(sr * 0.025)
        hop = int(sr * 0.010)
        frames = [audio[i:i+frame_size] for i in range(0, len(audio)-frame_size, hop)]
        energies = [float(np.sqrt(np.mean(f**2))) for f in frames if len(f) > 0]
        energy_std = float(np.std(energies)) if energies else 0.0
        energy_mean = float(np.mean(energies)) if energies else 0.0

        return {
            "duration": round(duration, 1),
            "rms": round(rms, 4),
            "peak": round(peak, 4),
            "zero_crossing_rate": round(zcr, 4),
            "energy_mean": round(energy_mean, 4),
            "energy_std": round(energy_std, 4),
        }

    def _analyze_with_llm(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """调用 DashScope LLM 分析音频特征对应的情绪。"""
        from dotenv import load_dotenv
        load_dotenv()

        api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        if not api_key:
            raise RuntimeError("DASHSCOPE_API_KEY 未配置，无法进行情绪分析")

        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")

        energy_level = "安静" if features["rms"] < 0.01 else ("适中" if features["rms"] < 0.1 else "响亮")
        speech_active = "有语音活动" if features["zero_crossing_rate"] >= 0.01 else "接近静音"

        prompt = (
            f"基于以下音频声学特征，分析说话人的情绪状态：\n"
            f"- 时长: {features['duration']}秒\n"
            f"- 音频能量(RMS): {features['rms']} ({energy_level})\n"
            f"- 峰值振幅: {features['peak']}\n"
            f"- 零交叉率: {features['zero_crossing_rate']} ({speech_active})\n"
            f"- 能量均值: {features['energy_mean']}\n"
            f"- 能量波动: {features['energy_std']}\n\n"
            f"请严格返回JSON格式（不要其他文字）：\n"
            f'{{"emotion": "情绪类型", "intensity": 数字1到10, "risk_level": "low/medium/high", '
            f'"confidence": 0.0到1.0之间的数字, "description": "简短中文描述"}}\n\n'
            f"情绪类型只能是以下之一：正常、高兴、低落、焦虑、烦躁、压抑、愤怒、恐惧、惊讶、厌恶、悲伤、紧张"
        )

        response = client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.3,
        )

        text = response.choices[0].message.content.strip()
        # Extract JSON from response
        import json
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON in the text
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                result = json.loads(match.group())
            else:
                result = {
                    "emotion": "正常", "intensity": 3, "risk_level": "low",
                    "confidence": 0.5, "description": text,
                }

        result.setdefault("emotion", "正常")
        result.setdefault("intensity", 3)
        result.setdefault("risk_level", "low")
        result.setdefault("confidence", 0.5)
        result.setdefault("description", "")
        return result

    def _quick_rule_check(self, features: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """规则预判：低能量静音段直接返回"正常"，跳过LLM调用节省成本"""
        # 近乎静音 → 无需调用LLM
        if features["rms"] < 0.001 and features["zero_crossing_rate"] < 0.005:
            return {
                "emotion": "正常", "intensity": 1, "risk_level": "low",
                "confidence": 0.95, "description": "静音或极低能量音频，判定为正常",
            }
        # 低能量 + 低波动 → 大概率正常
        if features["rms"] < 0.005 and features["energy_std"] < 0.003:
            return {
                "emotion": "正常", "intensity": 2, "risk_level": "low",
                "confidence": 0.80, "description": "低能量平稳音频，判定为正常",
            }
        return None  # 需要LLM进一步分析

    def _rule_emotion_guess(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """最后兜底：本地模型与 LLM 均不可用时，基于声学特征做保守判定，保证识别链路不中断。"""
        rms = float(features.get("rms", 0) or 0)
        energy_std = float(features.get("energy_std", 0) or 0)
        if rms > 0.08 and energy_std > 0.02:
            # 高能量 + 高波动：疑似激动/烦躁
            emotion, intensity, confidence = "烦躁", 6, 0.55
        else:
            emotion, intensity, confidence = "正常", 3, 0.5
        risk_level = "medium" if emotion in ("烦躁", "焦虑", "愤怒", "压抑") and intensity >= 6 else "low"
        return {
            "emotion": emotion,
            "intensity": intensity,
            "risk_level": risk_level,
            "confidence": confidence,
            "description": "本地模型与API均不可用，基于声学特征保守判定；建议配置 DASHSCOPE_API_KEY 或稍后重试",
        }

    def recognize(self, audio_path: str) -> Dict[str, Any]:
        """
        单文件情感识别：真实模型（emotion2vec）→ 规则预判 → LLM 研判。

        Args:
            audio_path: 音频文件路径

        Returns:
            情感识别结果字典（含 _source 标记识别来源）
        """
        audio, sr = load_audio(audio_path)
        features = self._extract_features(audio, sr)

        # 1. 优先使用真实语音情绪模型（emotion2vec），失败自动降级
        real = self._try_real_model(audio, sr)
        if real is not None:
            real["source_file"] = audio_path
            real["features"] = features
            real["timestamp"] = datetime.now().isoformat()
            real["_source"] = real.get("engine", "emotion2vec")
            real["risk_level"] = RiskAlertSystem.evaluate_risk_level(real)
            logger.info(
                "模型识别 [%s]: %s (置信度:%s)",
                audio_path, real["emotion"], real["confidence"],
            )
            return real

        # 2. 规则预判：静音/低能量段直接判定为正常，跳过 LLM 调用
        quick_result = self._quick_rule_check(features)
        if quick_result is not None:
            quick_result["source_file"] = audio_path
            quick_result["features"] = features
            quick_result["timestamp"] = datetime.now().isoformat()
            quick_result["_source"] = "rule"
            logger.info("规则预判 [%s]: %s (跳过LLM)", audio_path, quick_result["emotion"])
            return quick_result

        # 3. LLM 研判；无 key 或调用失败时退回声学保守判定，保证接口永不 500
        try:
            result = self._analyze_with_llm(features)
            llm_source = "llm"
            logger.info("LLM识别 [%s]: %s (强度:%s)", audio_path, result["emotion"], result["intensity"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM 研判不可用 [%s]: %s，回退声学规则兜底", audio_path, exc)
            result = self._rule_emotion_guess(features)
            llm_source = "rule"
        result["source_file"] = audio_path
        result["features"] = features
        result["timestamp"] = datetime.now().isoformat()
        result["_source"] = llm_source
        return result

    def _try_real_model(self, audio, sr: int) -> Optional[Dict[str, Any]]:
        """尝试用真实语音情绪模型识别；模型不可用或推理失败返回 None。"""
        try:
            from core.speech_emotion import get_speech_emotion_recognizer
            recognizer = get_speech_emotion_recognizer()
            return recognizer.analyze(audio, sample_rate=sr)
        except Exception as e:  # noqa: BLE001
            logger.debug("真实语音情绪模型不可用: %s", e)
            return None

    def batch_recognize(self, audio_dir: str) -> List[Dict[str, Any]]:
        """
        批量识别目录下的所有音频文件。

        Args:
            audio_dir: 音频文件目录

        Returns:
            识别结果列表
        """
        results = []
        for fname in os.listdir(audio_dir):
            ext = os.path.splitext(fname)[1].lower()
            if ext in (".wav", ".mp3", ".flac", ".m4a", ".ogg"):
                fpath = os.path.join(audio_dir, fname)
                try:
                    results.append(self.recognize(fpath))
                except Exception as e:
                    logger.error("识别失败 [%s]: %s", fpath, e)
                    results.append({"source_file": fpath, "error": str(e)})
        return results

class EmotionAnalyzer:
    """
    情感分析器：提供单次分析、批量分析、趋势数据、热力图数据和统计功能。
    """

    def __init__(self, recognizer: Optional[EmotionRecognizer] = None):
        """
        初始化分析器。

        Args:
            recognizer: 情感识别器实例，为None时自动创建
        """
        self.recognizer = recognizer or EmotionRecognizer()

    def analyze_single(self, audio_path: str) -> Dict[str, Any]:
        """
        单文件完整分析流水线：识别 → 风险评估 → 报告元数据。

        Args:
            audio_path: 音频文件路径

        Returns:
            包含识别结果和分析元数据的完整字典
        """
        result = self.recognizer.recognize(audio_path)

        # 补充分析元数据
        result["risk_level"] = RiskAlertSystem.evaluate_risk_level(result)
        result["analysis_timestamp"] = datetime.now().isoformat()
        result["severity_label"] = self._severity_label(result["intensity"])

        return result

    def analyze_batch(self, audio_dir: str) -> Dict[str, Any]:
        """
        批量分析并生成统计数据。

        Args:
            audio_dir: 音频目录路径

        Returns:
            包含results, statistics, risk_summary的综合字典
        """
        results = self.recognizer.batch_recognize(audio_dir)
        valid_results = [r for r in results if "error" not in r]
        failed_results = [r for r in results if "error" in r]

        statistics = self.generate_statistics(valid_results)
        risk_alerts = RiskAlertSystem.batch_risk_scan(valid_results)

        return {
            "total_files": len(results),
            "successful": len(valid_results),
            "failed": len(failed_results),
            "results": results,
            "statistics": statistics,
            "risk_summary": {
                "high_risk": len([a for a in risk_alerts if a["risk_level"] == "high"]),
                "medium_risk": len([a for a in risk_alerts if a["risk_level"] == "medium"]),
                "alerts": risk_alerts,
            },
        }

    def batch_analyze(self, audio_paths: List[str]) -> Dict[str, Any]:
        """批量分析给定文件路径列表的音频（供 /emotion/batch-analyze 调用）。

        Args:
            audio_paths: 音频文件路径列表

        Returns:
            包含 results / total / successful / failed / statistics 的字典
        """
        results = []
        for path in audio_paths:
            try:
                results.append(self.analyze_single(path))
            except Exception as e:
                logger.error("分析失败 [%s]: %s", path, e)
                results.append({"source_file": path, "error": str(e)})
        valid = [r for r in results if "error" not in r]
        return {
            "total": len(results),
            "successful": len(valid),
            "failed": len(results) - len(valid),
            "results": results,
            "statistics": self.generate_statistics(valid),
        }

    def generate_trend_data(self, results_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        生成时间序列情感数据，用于前端趋势图展示。

        Args:
            results_list: 识别结果列表（需含timestamp字段）

        Returns:
            时间序列数据字典，包含labels, datasets
        """
        sorted_results = sorted(results_list, key=lambda r: r.get("timestamp", ""))

        labels = []
        emotion_series = defaultdict(list)
        intensity_series = []

        for result in sorted_results:
            ts = result.get("timestamp", "")
            emotion = result.get("emotion", "未知")
            intensity = result.get("intensity", 0)

            labels.append(ts)
            for emo in EMOTION_LABELS:
                raw_scores = result.get("raw_scores", {})
                emotion_series[emo].append(raw_scores.get(emo, 0))
            intensity_series.append(intensity)

        datasets = {
            "emotion_trends": {
                emo: {"label": emo, "data": scores}
                for emo, scores in emotion_series.items()
            },
            "intensity_trend": {
                "label": "情绪强度",
                "data": intensity_series,
            },
        }

        return {
            "labels": labels,
            "datasets": datasets,
            "data_points": len(labels),
            "time_range": {
                "start": labels[0] if labels else None,
                "end": labels[-1] if labels else None,
            },
        }

    def generate_heatmap_data(self, results_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        生成情感分布热力图数据。

        Args:
            results_list: 识别结果列表

        Returns:
            热力图数据矩阵和标签
        """
        if not results_list:
            return {"matrix": [], "emotion_labels": EMOTION_LABELS, "intensity_labels": []}

        # 按强度区间分组统计
        intensity_bins = ["0-2", "3-4", "5-6", "7-8", "9-10"]
        bin_ranges = [(0, 2), (3, 4), (5, 6), (7, 8), (9, 10)]

        matrix = []
        for emotion in EMOTION_LABELS:
            row = []
            for low, high in bin_ranges:
                count = sum(
                    1 for r in results_list
                    if r.get("emotion") == emotion
                    and low <= r.get("intensity", 0) <= high
                )
                row.append(count)
            matrix.append(row)

        return {
            "matrix": matrix,
            "emotion_labels": EMOTION_LABELS,
            "intensity_labels": intensity_bins,
            "total_samples": len(results_list),
        }

    def generate_statistics(self, results_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        生成综合统计数据：平均强度、情感分布、风险计数等。

        Args:
            results_list: 识别结果列表

        Returns:
            统计数据字典
        """
        if not results_list:
            return {
                "total": 0,
                "avg_intensity": 0,
                "emotion_distribution": {},
                "high_risk_count": 0,
                "medium_risk_count": 0,
            }

        valid = [r for r in results_list if "error" not in r]
        if not valid:
            return {
                "total": len(results_list),
                "avg_intensity": 0,
                "emotion_distribution": {},
                "high_risk_count": 0,
                "medium_risk_count": 0,
            }

        # 情感分布统计
        emotion_counts = Counter(r.get("emotion", "未知") for r in valid)
        total = len(valid)
        emotion_distribution = {
            emo: {"count": count, "percentage": round(count / total * 100, 1)}
            for emo, count in emotion_counts.most_common()
        }

        # 强度统计
        intensities = [r.get("intensity", 0) for r in valid]
        avg_intensity = round(np.mean(intensities), 2)
        max_intensity = round(np.max(intensities), 2)
        min_intensity = round(np.min(intensities), 2)
        std_intensity = round(np.std(intensities), 2)

        # 风险统计
        risk_counts = Counter(
            RiskAlertSystem.evaluate_risk_level(r) for r in valid
        )

        return {
            "total": total,
            "avg_intensity": avg_intensity,
            "max_intensity": max_intensity,
            "min_intensity": min_intensity,
            "std_intensity": std_intensity,
            "emotion_distribution": emotion_distribution,
            "high_risk_count": risk_counts.get("high", 0),
            "medium_risk_count": risk_counts.get("medium", 0),
            "low_risk_count": risk_counts.get("low", 0),
            "none_risk_count": risk_counts.get("none", 0),
        }

    @staticmethod
    def _severity_label(intensity: float) -> str:
        """根据强度值返回中文严重程度标签"""
        if intensity >= 8:
            return "严重"
        elif intensity >= 6:
            return "中度"
        elif intensity >= 4:
            return "轻度"
        else:
            return "正常"

# ============================================================
# 3. 风险预警系统
# ============================================================

class RiskAlertSystem:
    """
    心理健康风险预警系统。
    根据情感类型和强度评估风险等级，生成预警报告。
    """

    # 风险等级常量
    HIGH_RISK = "high"
    MEDIUM_RISK = "medium"
    LOW_RISK = "low"
    NO_RISK = "none"

    # 升级阈值：需要上报学生事务处的风险等级
    ESCALATION_LEVELS = {HIGH_RISK}

    @staticmethod
    def evaluate_risk_level(result: Dict[str, Any]) -> str:
        """
        评估单条结果的风险等级（静态方法，供其他类调用）。

        规则：
        - HIGH_RISK: 焦虑/压抑/恐惧/愤怒/悲伤 且 强度 >= 7
        - MEDIUM_RISK: 强度 >= 5 或 烦躁/低落/紧张 且 强度 >= 6
        - LOW_RISK: 有一定负面情感但未达到中度
        - NO_RISK: 正常或积极情感
        """
        emotion = result.get("emotion", "正常")
        intensity = result.get("intensity", 0)

        # 高风险判定
        if emotion in HIGH_RISK_EMOTIONS and intensity >= 7:
            return RiskAlertSystem.HIGH_RISK

        # 中风险判定
        if intensity >= 5:
            return RiskAlertSystem.MEDIUM_RISK
        if emotion in MEDIUM_RISK_EMOTIONS and intensity >= 6:
            return RiskAlertSystem.MEDIUM_RISK

        # 低风险：负面情感但强度较低
        if emotion not in ("正常", "高兴") and intensity >= 3:
            return RiskAlertSystem.LOW_RISK

        return RiskAlertSystem.NO_RISK

    def check_risk(self, emotion_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        评估单条情感结果的风险等级。

        Args:
            emotion_result: 情感识别结果

        Returns:
            风险评估结果字典
        """
        risk_level = self.evaluate_risk_level(emotion_result)
        return {
            "student_id": emotion_result.get("student_id", "unknown"),
            "emotion": emotion_result.get("emotion", "未知"),
            "intensity": emotion_result.get("intensity", 0),
            "risk_level": risk_level,
            "should_escalate": self.should_escalate(risk_level),
            "checked_at": datetime.now().isoformat(),
        }

    def batch_risk_scan(self, results_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量扫描并返回需要关注的学生列表。

        Args:
            results_list: 识别结果列表

        Returns:
            被标记的学生预警列表（仅包含medium和high风险）
        """
        flagged = []
        for result in results_list:
            if "error" in result:
                continue
            risk_info = self.check_risk(result)
            if risk_info["risk_level"] in (self.MEDIUM_RISK, self.HIGH_RISK):
                flagged.append(risk_info)

        # 按风险等级排序：高风险在前
        risk_priority = {self.HIGH_RISK: 0, self.MEDIUM_RISK: 1}
        flagged.sort(key=lambda x: risk_priority.get(x["risk_level"], 2))

        logger.info(f"批量风险扫描完成: {len(flagged)}/{len(results_list)} 条预警")
        return flagged

    def generate_alert_report(self, alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        格式化预警报告，用于通知推送。

        Args:
            alerts: 预警列表

        Returns:
            格式化的预警报告字典
        """
        high_alerts = [a for a in alerts if a["risk_level"] == self.HIGH_RISK]
        medium_alerts = [a for a in alerts if a["risk_level"] == self.MEDIUM_RISK]

        report = {
            "report_title": "心理危机预警报告",
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_alerts": len(alerts),
                "high_risk_count": len(high_alerts),
                "medium_risk_count": len(medium_alerts),
                "escalation_required": any(a["should_escalate"] for a in alerts),
            },
            "high_risk_students": [],
            "medium_risk_students": [],
            "notifications": [],
        }

        # 高风险学生详情
        for alert in high_alerts:
            report["high_risk_students"].append({
                "student_id": alert["student_id"],
                "emotion": alert["emotion"],
                "intensity": alert["intensity"],
                "message": (
                    f"⚠️ 高风险预警：学生 {alert['student_id']} 表现出"
                    f"「{alert['emotion']}\u300d情感，强度 {alert['intensity']},"
                    f"建议立即关注。"
                ),
            })

        # 中风险学生详情
        for alert in medium_alerts:
            report["medium_risk_students"].append({
                "student_id": alert["student_id"],
                "emotion": alert["emotion"],
                "intensity": alert["intensity"],
                "message": (
                    f"🔶 中风险提示：学生 {alert['student_id']} 表现出"
                    f"「{alert['emotion']}\u300d情感，强度 {alert['intensity']},"
                    f"建议持续关注。"
                ),
            })

        # 生成通知消息列表
        for student in report["high_risk_students"]:
            report["notifications"].append({
                "type": "urgent",
                "target": "student_affairs",
                "message": student["message"],
            })
        for student in report["medium_risk_students"]:
            report["notifications"].append({
                "type": "normal",
                "target": "counselor",
                "message": student["message"],
            })

        return report

    def should_escalate(self, risk_level: str) -> bool:
        """
        判断是否需要上报学生事务处。

        Args:
            risk_level: 风险等级

        Returns:
            True 表示需要上报
        """
        return risk_level in self.ESCALATION_LEVELS

# ============================================================
# 4. 报告生成器
# ============================================================

class EmotionReportGenerator:
    """
    心理健康报告生成器。
    支持个人报告、班级报告和周汇总报告。
    """

    def __init__(self):
        """初始化报告生成器"""
        self.risk_system = RiskAlertSystem()

    def create_individual_report(
        self, student_id: str, emotion_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        为单个学生生成个人情感报告。

        Args:
            student_id: 学生ID
            emotion_history: 该学生的历史情感数据列表

        Returns:
            个人报告字典
        """
        if not emotion_history:
            return {
                "report_type": "individual",
                "student_id": student_id,
                "generated_at": datetime.now().isoformat(),
                "status": "no_data",
                "message": "该学生暂无情感记录数据。",
            }

        # 统计分析
        emotions = [r.get("emotion", "正常") for r in emotion_history]
        intensities = [r.get("intensity", 0) for r in emotion_history]
        emotion_counts = Counter(emotions)

        # 情感变化趋势：连续出现的负面情感次数
        consecutive_negative = 0
        max_consecutive_negative = 0
        negative_emotions = HIGH_RISK_EMOTIONS | MEDIUM_RISK_EMOTIONS
        for emo in emotions:
            if emo in negative_emotions:
                consecutive_negative += 1
                max_consecutive_negative = max(max_consecutive_negative, consecutive_negative)
            else:
                consecutive_negative = 0

        # 最近5次情感记录
        recent_emotions = [r.get("emotion", "未知") for r in emotion_history[-5:]]

        # 风险扫描
        risk_alerts = self.risk_system.batch_risk_scan(emotion_history)
        latest_risk = self.risk_system.check_risk(emotion_history[-1]) if emotion_history else None

        report = {
            "report_type": "individual",
            "student_id": student_id,
            "generated_at": datetime.now().isoformat(),
            "data_summary": {
                "total_sessions": len(emotion_history),
                "date_range": {
                    "first": emotion_history[0].get("timestamp"),
                    "last": emotion_history[-1].get("timestamp"),
                },
            },
            "emotion_analysis": {
                "dominant_emotion": emotion_counts.most_common(1)[0][0] if emotion_counts else "未知",
                "emotion_distribution": dict(emotion_counts.most_common()),
                "avg_intensity": round(np.mean(intensities), 2),
                "max_intensity": round(float(np.max(intensities)), 2),
                "intensity_trend": intensities,
            },
            "recent_emotions": recent_emotions,
            "risk_assessment": {
                "current_risk_level": latest_risk["risk_level"] if latest_risk else "unknown",
                "total_risk_alerts": len(risk_alerts),
                "max_consecutive_negative": max_consecutive_negative,
                "needs_attention": max_consecutive_negative >= 3,
            },
            "recommendations": self._generate_recommendations(
                emotion_counts, intensities, max_consecutive_negative
            ),
        }

        return report

    def create_class_report(
        self, class_id: str, all_emotions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        为班级生成集体情感报告。

        Args:
            class_id: 班级ID
            all_emotions: 班级所有学生的情感数据列表（需含student_id）

        Returns:
            班级报告字典
        """
        if not all_emotions:
            return {
                "report_type": "class",
                "class_id": class_id,
                "generated_at": datetime.now().isoformat(),
                "status": "no_data",
            }

        # 按学生分组
        student_data = defaultdict(list)
        for record in all_emotions:
            sid = record.get("student_id", "unknown")
            student_data[sid].append(record)

        total_students = len(student_data)

        # 情感分布统计
        all_emotions_list = [r.get("emotion", "正常") for r in all_emotions]
        emotion_distribution = Counter(all_emotions_list)

        # 强度统计
        all_intensities = [r.get("intensity", 0) for r in all_emotions]

        # 需关注的学生
        at_risk_students = []
        for sid, records in student_data.items():
            risk_alerts = self.risk_system.batch_risk_scan(records)
            if risk_alerts:
                at_risk_students.append({
                    "student_id": sid,
                    "alert_count": len(risk_alerts),
                    "highest_risk": risk_alerts[0]["risk_level"],
                })

        # 风险排序
        risk_priority = {"high": 0, "medium": 1, "low": 2, "none": 3}
        at_risk_students.sort(key=lambda x: risk_priority.get(x["highest_risk"], 4))

        report = {
            "report_type": "class",
            "class_id": class_id,
            "generated_at": datetime.now().isoformat(),
            "overview": {
                "total_students": total_students,
                "total_records": len(all_emotions),
                "avg_intensity": round(np.mean(all_intensities), 2) if all_intensities else 0,
            },
            "emotion_distribution": {
                emo: {
                    "count": count,
                    "percentage": round(count / len(all_emotions_list) * 100, 1),
                }
                for emo, count in emotion_distribution.most_common()
            },
            "at_risk_students": at_risk_students,
            "at_risk_count": len(at_risk_students),
            "recommendations": [
                f"班级整体情绪强度均值为 {round(np.mean(all_intensities), 2)}，"
                + ("处于正常范围" if np.mean(all_intensities) < 4 else "需要关注"),
                f"共有 {len(at_risk_students)} 名学生需要重点关注",
                "建议安排辅导员对高风险学生进行一对一面谈",
            ],
        }

        return report

    def create_weekly_summary(self, weekly_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        生成周汇总报告，供学生事务处审阅。

        Args:
            weekly_data: 一周内所有情感数据列表

        Returns:
            周汇总报告字典
        """
        if not weekly_data:
            return {
                "report_type": "weekly_summary",
                "generated_at": datetime.now().isoformat(),
                "status": "no_data",
            }

        # 按天分组
        daily_data = defaultdict(list)
        for record in weekly_data:
            ts = record.get("timestamp", "")
            try:
                date_str = ts[:10]  # YYYY-MM-DD
                daily_data[date_str].append(record)
            except (IndexError, TypeError):
                daily_data["unknown"].append(record)

        # 每日统计
        daily_stats = {}
        for date_str, records in sorted(daily_data.items()):
            emotions = [r.get("emotion", "正常") for r in records]
            intensities = [r.get("intensity", 0) for r in records]
            daily_stats[date_str] = {
                "record_count": len(records),
                "dominant_emotion": Counter(emotions).most_common(1)[0][0] if emotions else "未知",
                "avg_intensity": round(np.mean(intensities), 2) if intensities else 0,
            }

        # 全周统计
        all_intensities = [r.get("intensity", 0) for r in weekly_data]
        all_emotions = [r.get("emotion", "正常") for r in weekly_data]

        # 全周风险扫描
        risk_alerts = self.risk_system.batch_risk_scan(weekly_data)
        high_risk_count = len([a for a in risk_alerts if a["risk_level"] == "high"])
        medium_risk_count = len([a for a in risk_alerts if a["risk_level"] == "medium"])

        # 按学生统计高风险次数
        student_risk_count = Counter(
            a["student_id"] for a in risk_alerts if a["risk_level"] == "high"
        )
        repeat_risk_students = [
            sid for sid, count in student_risk_count.items() if count >= 3
        ]

        summary = {
            "report_type": "weekly_summary",
            "generated_at": datetime.now().isoformat(),
            "period": {
                "days": len(daily_stats),
                "dates": sorted(daily_stats.keys()),
            },
            "overview": {
                "total_records": len(weekly_data),
                "avg_weekly_intensity": round(np.mean(all_intensities), 2) if all_intensities else 0,
                "emotion_distribution": dict(Counter(all_emotions).most_common()),
            },
            "daily_breakdown": daily_stats,
            "risk_summary": {
                "high_risk_total": high_risk_count,
                "medium_risk_total": medium_risk_count,
                "repeat_risk_students": repeat_risk_students,
                "escalation_needed": high_risk_count > 0,
            },
            "alerts_report": self.risk_system.generate_alert_report(risk_alerts) if risk_alerts else None,
            "action_items": self._generate_weekly_action_items(
                high_risk_count, medium_risk_count, repeat_risk_students
            ),
        }

        return summary

    @staticmethod
    def _generate_recommendations(
        emotion_counts: Counter, intensities: List[float], max_consecutive: int
    ) -> List[str]:
        """根据情感数据生成个性化建议"""
        recommendations = []

        dominant = emotion_counts.most_common(1)[0][0] if emotion_counts else "正常"
        avg_intensity = np.mean(intensities) if intensities else 0

        if dominant in HIGH_RISK_EMOTIONS:
            recommendations.append(
                f"主要情感为「{dominant}」，建议安排专业心理咨询师进行评估。"
            )
        elif dominant in MEDIUM_RISK_EMOTIONS:
            recommendations.append(
                f"近期主要表现为「{dominant}」，建议辅导员主动关注并安排谈话。"
            )
        elif dominant in ("正常", "高兴"):
            recommendations.append("情感状态良好，建议继续保持。")

        if avg_intensity >= 7:
            recommendations.append("情绪强度持续偏高，建议进行压力管理和放松训练。")
        elif avg_intensity >= 5:
            recommendations.append("情绪强度中等，建议关注生活作息和社交支持。")

        if max_consecutive >= 3:
            recommendations.append(
                f"连续 {max_consecutive} 次检测到负面情绪，建议启动危机干预流程。"
            )

        if not recommendations:
            recommendations.append("当前数据不足以给出具体建议，建议增加观察频次。")

        return recommendations

    @staticmethod
    def _generate_weekly_action_items(
        high_risk: int, medium_risk: int, repeat_students: List[str]
    ) -> List[Dict[str, str]]:
        """生成周汇总的待办事项"""
        action_items = []

        if high_risk > 0:
            action_items.append({
                "priority": "urgent",
                "action": f"本周有 {high_risk} 次高风险预警，需立即安排心理危机干预。",
                "responsible": "学生事务处 + 心理咨询中心",
            })

        if medium_risk > 5:
            action_items.append({
                "priority": "high",
                "action": f"本周中风险预警 {medium_risk} 次，建议辅导员集体约谈相关学生。",
                "responsible": "辅导员团队",
            })

        if repeat_students:
            action_items.append({
                "priority": "urgent",
                "action": (
                    f"以下学生本周多次触发高风险预警: {', '.join(repeat_students)}，"
                    f"建议进行一对一个案评估。"
                ),
                "responsible": "心理咨询中心",
            })

        if not action_items:
            action_items.append({
                "priority": "normal",
                "action": "本周整体情绪状况良好，继续保持日常观察。",
                "responsible": "辅导员",
            })

        return action_items

# ============================================================
# 主程序入口
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("=" * 60)
    logger.info("聆心 - 多模态情感识别引擎 演示")
    logger.info("=" * 60)

    # 1. 初始化各组件
    recognizer = EmotionRecognizer()
    analyzer = EmotionAnalyzer(recognizer)
    risk_system = RiskAlertSystem()
    report_generator = EmotionReportGenerator()

    # 2. 模拟情感识别结果（演示分析流程）
    demo_results = [
        {"emotion": "焦虑", "intensity": 8.2, "confidence": 0.91,
         "student_id": "S20240001", "timestamp": "2026-06-10T09:00:00",
         "raw_scores": {"焦虑": 0.91, "紧张": 0.04, "正常": 0.02, "低落": 0.03}},
        {"emotion": "正常", "intensity": 1.5, "confidence": 0.88,
         "student_id": "S20240002", "timestamp": "2026-06-10T09:05:00",
         "raw_scores": {"正常": 0.88, "高兴": 0.07, "惊讶": 0.03, "低落": 0.02}},
        {"emotion": "悲伤", "intensity": 7.5, "confidence": 0.85,
         "student_id": "S20240003", "timestamp": "2026-06-10T09:10:00",
         "raw_scores": {"悲伤": 0.85, "低落": 0.08, "压抑": 0.04, "正常": 0.03}},
        {"emotion": "烦躁", "intensity": 6.3, "confidence": 0.79,
         "student_id": "S20240004", "timestamp": "2026-06-11T14:00:00",
         "raw_scores": {"烦躁": 0.79, "愤怒": 0.08, "紧张": 0.07, "正常": 0.06}},
        {"emotion": "高兴", "intensity": 0.8, "confidence": 0.93,
         "student_id": "S20240005", "timestamp": "2026-06-11T14:05:00",
         "raw_scores": {"高兴": 0.93, "正常": 0.05, "惊讶": 0.01, "低落": 0.01}},
        {"emotion": "恐惧", "intensity": 7.8, "confidence": 0.87,
         "student_id": "S20240006", "timestamp": "2026-06-12T10:00:00",
         "raw_scores": {"恐惧": 0.87, "焦虑": 0.06, "紧张": 0.04, "正常": 0.03}},
        {"emotion": "压抑", "intensity": 8.9, "confidence": 0.82,
         "student_id": "S20240001", "timestamp": "2026-06-13T08:30:00",
         "raw_scores": {"压抑": 0.82, "悲伤": 0.09, "焦虑": 0.05, "低落": 0.04}},
        {"emotion": "紧张", "intensity": 5.5, "confidence": 0.76,
         "student_id": "S20240007", "timestamp": "2026-06-14T09:00:00",
         "raw_scores": {"紧张": 0.76, "焦虑": 0.10, "正常": 0.08, "烦躁": 0.06}},
    ]

    # 3. 生成统计数据
    logger.info("--- 统计分析 ---")
    stats = analyzer.generate_statistics(demo_results)
    logger.info(f"情感分布: {json.dumps(stats['emotion_distribution'], ensure_ascii=False, indent=2)}")
    logger.info(f"平均强度: {stats['avg_intensity']}, 高风险数: {stats['high_risk_count']}")

    # 4. 生成趋势数据
    logger.info("--- 趋势数据 ---")
    trend = analyzer.generate_trend_data(demo_results)
    logger.info(f"数据点: {trend['data_points']}, 时间范围: {trend['time_range']}")

    # 5. 生成热力图数据
    logger.info("--- 热力图数据 ---")
    heatmap = analyzer.generate_heatmap_data(demo_results)
    logger.info(f"矩阵维度: {len(heatmap['matrix'])}x{len(heatmap['intensity_labels'])}")

    # 6. 风险扫描
    logger.info("--- 风险预警扫描 ---")
    alerts = risk_system.batch_risk_scan(demo_results)
    logger.info(f"预警总数: {len(alerts)}")
    for alert in alerts:
        logger.info(
            f"  [{alert['risk_level'].upper()}] {alert['student_id']}: "
            f"{alert['emotion']} (强度:{alert['intensity']})"
        )

    # 7. 生成预警报告
    logger.info("--- 预警报告 ---")
    alert_report = risk_system.generate_alert_report(alerts)
    logger.info(
        f"高风险: {alert_report['summary']['high_risk_count']}, "
        f"中风险: {alert_report['summary']['medium_risk_count']}"
    )
    logger.info(f"需要上报: {alert_report['summary']['escalation_required']}")

    # 8. 生成个人报告
    logger.info("--- 个人报告 (S20240001) ---")
    student_1_records = [r for r in demo_results if r["student_id"] == "S20240001"]
    individual_report = report_generator.create_individual_report(
        "S20240001", student_1_records
    )
    logger.info(f"主要情感: {individual_report['emotion_analysis']['dominant_emotion']}")
    logger.info(f"风险等级: {individual_report['risk_assessment']['current_risk_level']}")
    logger.info(f"建议: {individual_report['recommendations']}")

    # 9. 生成班级报告
    logger.info("--- 班级报告 (CSE-2024-01) ---")
    class_report = report_generator.create_class_report("CSE-2024-01", demo_results)
    logger.info(f"班级人数: {class_report['overview']['total_students']}")
    logger.info(f"需关注人数: {class_report['at_risk_count']}")

    # 10. 生成周汇总
    logger.info("--- 周汇总报告 ---")
    weekly = report_generator.create_weekly_summary(demo_results)
    logger.info(f"周期天数: {weekly['period']['days']}")
    logger.info(f"高风险预警: {weekly['risk_summary']['high_risk_total']}")
    logger.info(f"待办事项: {len(weekly['action_items'])} 条")

    # 11. 输出完整报告为JSON（演示前后端数据传输）
    output_dir = os.path.join(os.path.dirname(__file__), "..", "outputs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "demo_report.json")

    full_output = {
        "statistics": stats,
        "trend_data": trend,
        "heatmap_data": heatmap,
        "alert_report": alert_report,
        "individual_report": individual_report,
        "class_report": class_report,
        "weekly_summary": weekly,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(full_output, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"\n完整报告已导出至: {output_path}")
    logger.info("=" * 60)
    logger.info("演示完成")
    logger.info("=" * 60)


