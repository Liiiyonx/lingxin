"""
聆心 — 实时流式音频情绪分析引擎
用于视频通话中的实时语音情绪检测，接收短音频片段并快速分析
"""
import base64
import io
import logging
import os
from datetime import datetime
from typing import Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger("campus_mind.realtime_emotion")

# 12种情绪标签
EMOTION_LABELS = [
    "正常", "高兴", "低落", "焦虑", "烦躁", "压抑",
    "愤怒", "恐惧", "惊讶", "厌恶", "悲伤", "紧张",
]

# 情绪严重程度权重
EMOTION_SEVERITY = {
    "正常": 0, "高兴": 0, "惊讶": 1,
    "低落": 4, "烦躁": 5, "紧张": 5,
    "焦虑": 7, "悲伤": 7, "愤怒": 8,
    "压抑": 8, "恐惧": 9, "厌恶": 6,
}

# 高风险情绪集合
HIGH_RISK_EMOTIONS = {"焦虑", "压抑", "恐惧", "愤怒", "悲伤"}
MEDIUM_RISK_EMOTIONS = {"烦躁", "低落", "紧张"}

# 连续高风险阈值：连续N次高风险才触发告警
CONSECUTIVE_HIGH_RISK_THRESHOLD = 3


class RealtimeAudioEmotionAnalyzer:
    """实时音频情绪分析器：接收短音频块，快速提取声学特征并判断情绪"""

    def __init__(self):
        self._history: list = []  # 历史分析结果
        self._consecutive_high = 0
        self._ready = True
        logger.info("实时音频情绪分析器初始化完毕")

    def extract_features(self, audio_data: np.ndarray, sample_rate: int = 16000) -> Dict:
        """从音频数据中提取声学特征（与emotion_engine.py逻辑一致，但不依赖文件IO）

        Args:
            audio_data: 音频numpy数组 (float32, -1.0 ~ 1.0)
            sample_rate: 采样率

        Returns:
            特征字典
        """
        if audio_data is None or len(audio_data) == 0:
            return self._silence_features()

        duration = len(audio_data) / sample_rate

        # RMS 能量
        rms = float(np.sqrt(np.mean(audio_data ** 2)))
        # 峰值振幅
        peak = float(np.max(np.abs(audio_data)))
        # 零交叉率
        zcr = float(np.sum(np.abs(np.diff(np.sign(audio_data)))) / (2 * len(audio_data)))

        # 短时能量分布
        frame_size = int(sample_rate * 0.025)
        hop = int(sample_rate * 0.010)
        if frame_size > 0 and len(audio_data) > frame_size:
            frames = [audio_data[i:i + frame_size] for i in range(0, len(audio_data) - frame_size, hop)]
            energies = [float(np.sqrt(np.mean(f ** 2))) for f in frames if len(f) > 0]
            energy_std = float(np.std(energies)) if energies else 0.0
            energy_mean = float(np.mean(energies)) if energies else 0.0
        else:
            energy_std = 0.0
            energy_mean = rms

        # 频谱质心（简单的频率分布指标）
        try:
            fft = np.abs(np.fft.rfft(audio_data))
            freqs = np.fft.rfftfreq(len(audio_data), 1 / sample_rate)
            if np.sum(fft) > 0:
                spectral_centroid = float(np.sum(freqs * fft) / np.sum(fft))
            else:
                spectral_centroid = 0.0
        except Exception:
            spectral_centroid = 0.0

        return {
            "duration": round(duration, 2),
            "rms": round(rms, 4),
            "peak": round(peak, 4),
            "zero_crossing_rate": round(zcr, 4),
            "energy_mean": round(energy_mean, 4),
            "energy_std": round(energy_std, 4),
            "spectral_centroid": round(spectral_centroid, 1),
        }

    def _silence_features(self) -> Dict:
        return {
            "duration": 0, "rms": 0.0, "peak": 0.0,
            "zero_crossing_rate": 0.0, "energy_mean": 0.0,
            "energy_std": 0.0, "spectral_centroid": 0.0,
        }

    def quick_analyze(self, features: Dict) -> Dict:
        """快速规则分析（不调用LLM，毫秒级响应）

        基于声学特征的启发式规则判断情绪状态：
        - 高能量 + 高ZCR → 激动/愤怒/烦躁
        - 低能量 + 低ZCR → 低落/压抑
        - 高ZCR + 适中能量 → 焦虑/紧张
        - 极低能量 → 静音/正常
        """
        # 静音检测
        if features["rms"] < 0.001 and features["zero_crossing_rate"] < 0.005:
            return self._make_result("正常", 1, "low", 0.95, "静音段")

        # 低能量检测
        if features["rms"] < 0.005 and features["energy_std"] < 0.003:
            return self._make_result("正常", 2, "low", 0.80, "低能量平稳段")

        rms = features["rms"]
        zcr = features["zero_crossing_rate"]
        energy_std = features["energy_std"]
        centroid = features.get("spectral_centroid", 0)

        # 高能量 + 高波动 → 愤怒
        if rms > 0.08 and energy_std > 0.03:
            return self._make_result("愤怒", 8, "high", 0.72, "高能量高波动")

        # 高ZCR + 适中能量 → 紧张/焦虑
        if zcr > 0.06 and rms > 0.01:
            return self._make_result("紧张", 6, "medium", 0.68, "高语速波动")

        # 低能量 + 低波动 + 低ZCR → 低落
        if rms < 0.008 and energy_std < 0.005 and zcr < 0.02:
            return self._make_result("低落", 5, "medium", 0.65, "低能量低波动")

        # 高频谱质心 + 适中能量 → 高兴
        if centroid > 800 and rms > 0.02:
            return self._make_result("高兴", 2, "low", 0.70, "高频谱能量")

        # 高波动 → 烦躁
        if energy_std > 0.025 and rms > 0.01:
            return self._make_result("烦躁", 5, "medium", 0.66, "能量波动较大")

        # 默认正常
        return self._make_result("正常", 2, "low", 0.60, "声学特征正常范围")

    def _make_result(self, emotion: str, intensity: int, risk_level: str, confidence: float, description: str) -> Dict:
        return {
            "emotion": emotion,
            "intensity": intensity,
            "risk_level": risk_level,
            "confidence": confidence,
            "description": description,
            "timestamp": datetime.now().isoformat(),
        }

    def analyze_chunk(self, audio_base64: str, sample_rate: int = 16000) -> Dict:
        """分析单个音频块（真实模型 emotion2vec → 规则降级）

        Args:
            audio_base64: base64编码的音频数据 (wav/pcm float32)
            sample_rate: 采样率，默认16kHz

        Returns:
            情绪分析结果 + 风险状态
        """
        try:
            # 解码base64
            audio_bytes = base64.b64decode(audio_base64)
            audio_data = np.frombuffer(audio_bytes, dtype=np.float32)
        except Exception as e:
            logger.warning(f"音频解码失败: {e}")
            return {
                "emotion": "正常", "intensity": 1, "risk_level": "low",
                "confidence": 0.5, "description": f"解码失败: {e}",
                "timestamp": datetime.now().isoformat(), "error": str(e),
            }

        # 1. 优先使用真实语音情绪模型 emotion2vec
        result = self._try_emotion2vec(audio_data, sample_rate)

        if result is None:
            # 2. 降级：声学特征 + 快速规则分析
            features = self.extract_features(audio_data, sample_rate)
            result = self.quick_analyze(features)
            result["features"] = features
            result["_source"] = "rule"

        # 风险追踪
        self._track_risk(result)

        # 存储历史（最多保留60条）
        self._history.append(result)
        if len(self._history) > 60:
            self._history = self._history[-60:]

        return result

    def _try_emotion2vec(self, audio_data, sample_rate: int) -> Optional[Dict]:
        """尝试用真实语音情绪模型识别；不可用/失败返回 None。

        注意：静音/极低能量音频会被 emotion2vec 误判为负面情绪，
        因此先做能量检测，接近静音时直接返回 None（走规则降级）。
        """
        try:
            if audio_data is None or len(audio_data) == 0:
                return None
            # 静音/低能量检测：RMS 过低 → 不调用 emotion2vec
            rms = float(np.sqrt(np.mean(audio_data ** 2)))
            if rms < 0.005:
                return None
            from core.speech_emotion import get_speech_emotion_recognizer
            recognizer = get_speech_emotion_recognizer()
            res = recognizer.analyze(audio_data, sample_rate=sample_rate)
            if res is None:
                return None
            res["_source"] = "emotion2vec"
            res["risk_level"] = self._risk_level_for(res.get("emotion"), res.get("intensity"))
            res["description"] = "真实语音情绪模型（emotion2vec）"
            return res
        except Exception as e:  # noqa: BLE001
            logger.debug("emotion2vec 实时分析不可用: %s", e)
            return None

    @staticmethod
    def _risk_level_for(emotion, intensity) -> str:
        """由情绪类型 + 强度推导风险等级（与 emotion_engine 规则一致）。"""
        try:
            intensity = float(intensity or 0)
        except (TypeError, ValueError):
            intensity = 0
        if emotion in HIGH_RISK_EMOTIONS and intensity >= 7:
            return "high"
        if intensity >= 5:
            return "medium"
        if emotion in MEDIUM_RISK_EMOTIONS and intensity >= 6:
            return "medium"
        if emotion not in ("正常", "高兴") and intensity >= 3:
            return "low"
        return "low"

    def analyze_chunk_with_llm(self, audio_base64: str, sample_rate: int = 16000) -> Dict:
        """带LLM分析的音频块分析（较慢但更准确，用于高置信度判断）

        先做快速规则分析，如果规则分析的置信度低于阈值，则调用LLM。
        """
        result = self.analyze_chunk(audio_base64, sample_rate)

        # 如果规则置信度低且不是静音，尝试LLM
        if result.get("confidence", 0) < 0.65 and result.get("rms", 0) > 0.005:
            try:
                llm_result = self._call_llm(result.get("features", {}))
                if llm_result:
                    result.update(llm_result)
                    result["_source"] = "llm"
            except Exception as e:
                logger.debug(f"LLM分析跳过: {e}")
                result["_source"] = "rule"
        else:
            result["_source"] = "rule"

        return result

    def _call_llm(self, features: Dict) -> Optional[Dict]:
        """调用DashScope LLM进行更准确的音频情绪分析"""
        api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        if not api_key:
            return None

        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")

            energy_level = "安静" if features.get("rms", 0) < 0.01 else (
                "适中" if features.get("rms", 0) < 0.05 else "响亮")

            prompt = (
                "基于以下音频声学特征，分析说话人的情绪状态（用中文回答）：\n"
                f"- 时长: {features.get('duration', 0)}秒\n"
                f"- 音频能量(RMS): {features.get('rms', 0)} ({energy_level})\n"
                f"- 峰值振幅: {features.get('peak', 0)}\n"
                f"- 零交叉率: {features.get('zero_crossing_rate', 0)}\n"
                f"- 能量均值: {features.get('energy_mean', 0)}\n"
                f"- 能量波动: {features.get('energy_std', 0)}\n"
                f"- 频谱质心: {features.get('spectral_centroid', 0)}Hz\n\n"
                "请严格返回JSON格式（不要其他文字）：\n"
                '{"emotion": "情绪类型", "intensity": 数字1到10, "risk_level": "low/medium/high", '
                '"confidence": 0.0到1.0之间的数字, "description": "简短中文描述"}'
            )

            response = client.chat.completions.create(
                model="qwen-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.2,
            )

            import json, re
            text = response.choices[0].message.content.strip()
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                result = json.loads(match.group())
                result.setdefault("emotion", "正常")
                result.setdefault("intensity", 3)
                result.setdefault("risk_level", "low")
                result.setdefault("confidence", 0.6)
                result.setdefault("description", "")
                return result
        except Exception:
            pass
        return None

    def _track_risk(self, result: Dict):
        """追踪连续高风险次数，防止误报"""
        if result.get("risk_level") == "high":
            self._consecutive_high += 1
        elif result.get("emotion") not in HIGH_RISK_EMOTIONS:
            self._consecutive_high = max(0, self._consecutive_high - 1)

    @property
    def should_alert(self) -> bool:
        """连续高风险达到阈值时才触发告警"""
        return self._consecutive_high >= CONSECUTIVE_HIGH_RISK_THRESHOLD

    def get_recent_trend(self, n: int = 10) -> list:
        """获取最近n次分析的情绪趋势"""
        return [
            {"emotion": r.get("emotion"), "intensity": r.get("intensity", 0), "time": r.get("timestamp", "")}
            for r in self._history[-n:]
        ]

    def get_summary(self) -> Dict:
        """获取当前会话的情绪总结"""
        if not self._history:
            return {"status": "no_data", "message": "暂无实时分析数据"}

        emotions = [r.get("emotion", "正常") for r in self._history]
        from collections import Counter
        emotion_counts = Counter(emotions)
        dominant = emotion_counts.most_common(1)[0][0] if emotion_counts else "正常"

        # 风险统计
        high_count = sum(1 for r in self._history if r.get("risk_level") == "high")
        medium_count = sum(1 for r in self._history if r.get("risk_level") == "medium")

        return {
            "total_chunks": len(self._history),
            "dominant_emotion": dominant,
            "emotion_distribution": dict(emotion_counts.most_common()),
            "high_risk_count": high_count,
            "medium_risk_count": medium_count,
            "should_alert": self.should_alert,
            "consecutive_high": self._consecutive_high,
            "trend": self.get_recent_trend(10),
        }

    def reset(self):
        """重置分析器状态"""
        self._history = []
        self._consecutive_high = 0


# 全局会话级分析器存储
_sessions: Dict[str, RealtimeAudioEmotionAnalyzer] = {}


def get_or_create_analyzer(session_id: str) -> RealtimeAudioEmotionAnalyzer:
    """获取或创建会话级分析器"""
    if session_id not in _sessions:
        _sessions[session_id] = RealtimeAudioEmotionAnalyzer()
    return _sessions[session_id]


def cleanup_session(session_id: str):
    """清理会话分析器"""
    _sessions.pop(session_id, None)


def cleanup_old_sessions(max_age_minutes: int = 30):
    """清理过期会话"""
    # 简化实现：保留最近100个会话
    if len(_sessions) > 100:
        keys_to_remove = list(_sessions.keys())[:-100]
        for k in keys_to_remove:
            _sessions.pop(k, None)
