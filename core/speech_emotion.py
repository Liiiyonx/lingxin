# -*- coding: utf-8 -*-
"""
聆心 — 语音情绪识别引擎（真实模型）
====================================
基于 FunASR `emotion2vec_plus_large`（阿里达摩院开源语音情绪模型，SOTA SER）
对音频做真正的声学情绪识别。

设计原则：
- **懒加载**：模型在首次调用时才加载，避免拖慢应用启动。
- **优雅降级**：模型未安装 / 下载失败 / 推理异常时返回 None，由上层
  `EmotionRecognizer` 自动回退到「声学特征 + LLM 研判」路径，应用永远可用。
- **结果标注**：返回结果携带 `engine` 字段，如实区分「模型推理 / 规则 / LLM」。

依赖：`pip install funasr modelscope`（首次运行会自动联网下载模型，约数百 MB）。
"""

import logging
import threading

import numpy as np

logger = logging.getLogger(__name__)

# emotion2vec 输出的英文情绪标签 → 中文映射（覆盖常见输出标签）
EMOTION2VEC_LABELS_ZH = {
    "angry": "愤怒",
    "disgust": "厌恶",
    "fear": "恐惧",
    "happy": "高兴",
    "neutral": "正常",
    "other": "正常",
    "sad": "悲伤",
    "surprise": "惊讶",
    "contempt": "厌恶",
    "happiness": "高兴",
    "angry_lo": "愤怒",
    "angry_hi": "愤怒",
    "happy_lo": "高兴",
    "happy_hi": "高兴",
    "sad_lo": "悲伤",
    "sad_hi": "悲伤",
    "neutral_lo": "正常",
    "neutral_hi": "正常",
}

# emotion2vec 的中文标签 → 系统规范标签（12 类）
EMOTION2VEC_ZH_TO_CANONICAL = {
    "生气": "愤怒",
    "厌恶": "厌恶",
    "恐惧": "恐惧",
    "开心": "高兴",
    "中立": "正常",
    "正常": "正常",
    "其他": "正常",
    "难过": "悲伤",
    "吃惊": "惊讶",
    "惊讶": "惊讶",
    "愤怒": "愤怒",
    "高兴": "高兴",
    "悲伤": "悲伤",
    "<unk>": "正常",
}

# 情绪严重程度基准（用于推导 1-10 的强度值，与 emotion_engine 风险判定兼容）
_EMOTION_SEVERITY_BASE = {
    "正常": 1,
    "高兴": 2,
    "惊讶": 3,
    "厌恶": 5,
    "悲伤": 7,
    "愤怒": 8,
    "恐惧": 9,
}


def _derive_intensity(emotion: str, confidence: float) -> int:
    """由情绪类型 + 模型置信度推导 1-10 的强度值。

    强度 = 情绪严重程度基准 + round(置信度 * 2)，上限 10。
    例如：悲伤(基准7) + 置信度0.9 → 9；正常(基准1) + 0.9 → 3。
    """
    base = _EMOTION_SEVERITY_BASE.get(emotion, 3)
    return int(min(10, max(1, base + round(confidence * 2))))


class SpeechEmotionRecognizer:
    """真实的语音情绪识别器（emotion2vec）。"""

    def __init__(self, model_name: str = "iic/emotion2vec_plus_large"):
        self.model_name = model_name
        self._model = None
        self._ready = False
        self._load_error = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        """模型是否可用（懒加载成功过一次）。"""
        return self._ready

    def _ensure_model(self) -> bool:
        """懒加载模型（线程安全）；失败则记录错误并保持未就绪。"""
        if self._ready:
            return True
        if self._load_error:
            return False
        with self._lock:
            # 双重检查：避免预热线程与请求线程并发重复加载
            if self._ready:
                return True
            if self._load_error:
                return False
            try:
                from funasr import AutoModel
                self._model = AutoModel(model=self.model_name, disable_update=True)
                self._ready = True
                logger.info("语音情绪模型加载成功: %s", self.model_name)
            except Exception as e:  # noqa: BLE001
                self._load_error = str(e)
                logger.warning("语音情绪模型加载失败，将降级为特征+LLM 模式: %s", e)
        return self._ready

    def _to_list(self, value):
        """把 numpy 数组 / list / 标量统一转为 list。"""
        if hasattr(value, "tolist"):
            return value.tolist()
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    def analyze(self, audio: np.ndarray, sample_rate: int = 16000):
        """对音频 numpy 数组做情绪识别。

        Args:
            audio: float32 音频数据，单声道。
            sample_rate: 采样率，默认 16000。

        Returns:
            dict: {"emotion": 中文标签, "confidence": 0~1, "scores": {...},
                   "intensity": 1~10, "engine": "emotion2vec"}；
            失败返回 None。
        """
        if not self._ensure_model():
            return None
        try:
            # emotion2vec 需走 AutoModel.generate 高层接口（内部完成音频加载 + 特征提取）
            # fs 参数 = 输入音频的真实采样率，funasr 会自动重采样到 16kHz
            result = self._model.generate(
                input=audio,
                granularity="utterance",
                extract_embedding=False,
                fs=int(sample_rate or 16000),
            )
            if not result:
                return None
            first = result[0] if isinstance(result, list) else result
            labels = self._to_list(first.get("labels", []))
            scores = self._to_list(first.get("scores", []))
            if not labels or not scores:
                return None

            # 取概率最高的标签
            idx = int(np.argmax(scores)) if len(scores) > 1 else 0
            raw_label = str(labels[idx])
            emotion = self._parse_zh_label(raw_label)
            top_score = float(scores[idx])

            score_map = {}
            for lb, sc in zip(labels, scores):
                score_map[self._parse_zh_label(str(lb))] = float(sc)

            return {
                "emotion": emotion,
                "confidence": round(top_score, 4),
                "scores": score_map,
                "intensity": _derive_intensity(emotion, top_score),
                "engine": "emotion2vec",
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("语音情绪模型推理失败: %s", e)
            return None

    @staticmethod
    def _parse_zh_label(raw_label: str) -> str:
        """把 emotion2vec 标签解析为系统规范中文标签（12 类之一）。

        标签形如 "生气/angry"、"难过/sad"；先取中文部分，再映射到规范标签；
        "<unk>" 或空标签回退为「正常」。
        """
        raw = (raw_label or "").strip()
        zh = raw.split("/")[0].strip() if "/" in raw else raw
        if zh in EMOTION2VEC_ZH_TO_CANONICAL:
            return EMOTION2VEC_ZH_TO_CANONICAL[zh]
        # 未命中的英文标签走英文映射，仍不识别则回退正常
        return EMOTION2VEC_LABELS_ZH.get(raw, "正常")


# 模块级单例（懒加载，进程内复用）
_speech_emotion_recognizer = None


def get_speech_emotion_recognizer() -> SpeechEmotionRecognizer:
    """获取全局语音情绪识别器单例。"""
    global _speech_emotion_recognizer
    if _speech_emotion_recognizer is None:
        _speech_emotion_recognizer = SpeechEmotionRecognizer()
    return _speech_emotion_recognizer
