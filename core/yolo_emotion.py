# -*- coding: utf-8 -*-
"""
聆心 - YOLO 实时情绪识别引擎
基于 YOLOv8 面部检测 + 情绪分类，用于视频咨询中实时监测学生情绪状态
"""

import os
import sys
import json
import base64
import logging
import threading
from io import BytesIO
from datetime import datetime
from typing import Optional, Dict, List, Tuple

import numpy as np
from PIL import Image

logger = logging.getLogger("campus_mind.yolo_emotion")

# 高危情绪阈值配置
HIGH_RISK_EMOTIONS = ["焦虑", "恐惧", "愤怒", "悲伤", "压抑", "紧张"]
DEFAULT_THRESHOLD = 0.65  # 情绪置信度阈值
SEVERITY_LEVELS = {
    (0.0, 0.5): 2,   # 轻度
    (0.5, 0.75): 5,  # 中度
    (0.75, 0.9): 7,  # 重度
    (0.9, 1.0): 9,   # 严重
}

# 情绪标签映射（英文→中文）
EMOTION_LABELS_ZH = {
    "angry": "愤怒", "disgust": "厌恶", "fear": "恐惧",
    "happy": "高兴", "sad": "悲伤", "surprise": "惊讶",
    "neutral": "正常", "anxious": "焦虑", "depressed": "压抑",
    "nervous": "紧张", "calm": "平静"
}


class YoloEmotionDetector:
    """YOLO 面部检测 + 情绪识别引擎"""

    def __init__(self):
        self.face_model = None
        self.face_model_kind = None
        self.emotion_model = None
        self.emotion_processor = None
        self._emotion_model_loaded = False
        self._emotion_lock = threading.Lock()
        self.ready = False
        self._init_models()

    def _init_models(self):
        """初始化人脸检测器；情绪分类模型改为懒加载。"""
        try:
            self._init_face_detector()
            self.ready = True
        except Exception as e:
            logger.error(f"模型初始化失败: {e}")
            self.ready = False

    def _init_face_detector(self):
        """人脸检测器：本地已有 yolov8n-face 时用之，否则直接用 Haar Cascade。

        注意：ultralytics 的 YOLO('yolov8n-face.pt') 在本地缺失时会尝试从 GitHub
        下载，国内网络易卡死；因此这里仅在本地已存在该权重时才走 YOLO 路径，
        否则直接使用内置 Haar 级联（视频通话正脸场景足够）。
        """
        local_face_pt = None
        candidates = [
            "yolov8n-face.pt",
            os.path.join(os.path.dirname(__file__), "..", "yolov8n-face.pt"),
        ]
        for cand in candidates:
            if os.path.isfile(cand):
                local_face_pt = cand
                break
        if local_face_pt:
            try:
                from ultralytics import YOLO
                self.face_model = YOLO(local_face_pt)
                self.face_model_kind = "yolov8n-face"
                logger.info("YOLOv8n-face 人脸检测模型加载成功（本地）")
                return
            except Exception as e:
                logger.warning("YOLOv8n-face 加载失败，回退 Haar Cascade: %s", e)
        self.face_model_kind = "haar"
        self._init_haar_cascade()

    def _ensure_emotion_model(self):
        """懒加载情绪分类模型（transformers FER，线程安全），失败则保持 None。"""
        if self._emotion_model_loaded:
            return self.emotion_model
        with self._emotion_lock:
            # 双重检查：避免预热线程与请求线程并发重复加载
            if self._emotion_model_loaded:
                return self.emotion_model
            self._try_load_transformers_emotion()
            self._emotion_model_loaded = True
            if self.emotion_model:
                logger.info("人脸情绪分类模型加载成功")
            else:
                logger.warning("人脸情绪分类模型不可用，将返回「未知」而非启发式猜测")
            return self.emotion_model

    def _init_haar_cascade(self):
        """OpenCV Haar Cascade 面部检测后备方案"""
        try:
            import cv2
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            if os.path.exists(cascade_path):
                self.face_model = cv2.CascadeClassifier(cascade_path)
                logger.info("Haar Cascade 面部检测器加载成功")
            else:
                logger.warning("Haar Cascade 文件未找到")
        except Exception:
            pass

    def detect_faces(self, image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """检测图像中的面部区域，返回 [(x, y, w, h), ...]"""
        faces = []
        try:
            if self.face_model_kind == "yolov8n-face":
                from ultralytics import YOLO
                if isinstance(self.face_model, YOLO):
                    results = self.face_model(image, verbose=False, conf=0.4)
                    for r in results:
                        for box in r.boxes.xyxy:
                            x1, y1, x2, y2 = map(int, box.tolist())
                            faces.append((x1, y1, x2 - x1, y2 - y1))
            elif self.face_model_kind == "haar":
                import cv2
                gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
                detected = self.face_model.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
                faces = [(x, y, w, h) for (x, y, w, h) in detected]
        except Exception as e:
            logger.debug(f"面部检测异常: {e}")
        return faces

    def _try_load_transformers_emotion(self):
        """尝试加载 HuggingFace 情绪模型（可能因网络问题失败）。

        优先使用本地缓存（local_files_only），避免国内访问 huggingface.co 超时；
        缓存缺失时回退走 HF 镜像下载。
        """
        try:
            from transformers import pipeline
            import warnings
            # 国内网络优先走 HF 镜像
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    self.emotion_model = pipeline(
                        "image-classification",
                        model="dima806/facial_emotions_image_detection",
                        top_k=3,
                        local_files_only=True,
                    )
                except Exception:
                    self.emotion_model = pipeline(
                        "image-classification",
                        model="dima806/facial_emotions_image_detection",
                        top_k=3,
                    )
            logger.info("HuggingFace 情绪分类模型加载成功")
        except Exception:
            pass  # 静默降级到本地分析

    def classify_emotion(self, face_img: Image.Image) -> List[Dict]:
        """对裁剪的面部图像进行情绪分类（真实 FER 模型，懒加载）。"""
        model = self._ensure_emotion_model()
        if model:
            try:
                raw = model(face_img)
                return [{"emotion": EMOTION_LABELS_ZH.get(r["label"], r["label"]),
                         "confidence": round(r["score"], 4)} for r in raw]
            except Exception:
                pass  # 推理失败则如实返回未知
        # 情绪模型不可用时，如实返回「未知」，不用亮度/颜色等启发式猜测
        return [{"emotion": "未知", "confidence": 0.0}]

    def analyze_frame(self, image_b64: str) -> Dict:
        """分析单帧图像（base64 编码），返回完整分析结果"""
        result = {
            "success": False,
            "faces_detected": 0,
            "emotions": [],
            "high_risk_alerts": [],
            "timestamp": datetime.now().isoformat()
        }

        if not self.ready:
            result["error"] = "模型未就绪"
            return result

        try:
            # 解码 base64 图像
            if "," in image_b64:
                image_b64 = image_b64.split(",")[1]
            img_bytes = base64.b64decode(image_b64)
            img = Image.open(BytesIO(img_bytes)).convert("RGB")
            img_np = np.array(img)

            # 面部检测
            faces = self.detect_faces(img_np)
            result["faces_detected"] = len(faces)

            if not faces:
                result["emotions"] = [{"emotion": "未检测到面部", "confidence": 0}]
                result["success"] = True
                return result

            # 对每个面部进行情绪分类
            for i, (x, y, w, h) in enumerate(faces):
                # 裁剪并放大面部区域
                pad = int(min(w, h) * 0.2)
                fx1 = max(0, x - pad)
                fy1 = max(0, y - pad)
                fx2 = min(img.width, x + w + pad)
                fy2 = min(img.height, y + h + pad)
                face_crop = img.crop((fx1, fy1, fx2, fy2)).resize((96, 96))

                # 情绪分类
                emotions = self.classify_emotion(face_crop)
                primary = emotions[0] if emotions else {"emotion": "未知", "confidence": 0}
                result["emotions"].append({
                    "face_index": i,
                    "bbox": [x, y, w, h],
                    "primary_emotion": primary["emotion"],
                    "confidence": primary["confidence"],
                    "all_emotions": emotions
                })

                # 检查是否触发高危告警
                if primary["emotion"] in HIGH_RISK_EMOTIONS and primary["confidence"] >= DEFAULT_THRESHOLD:
                    severity = self._calc_severity(primary["confidence"])
                    alert = {
                        "emotion": primary["emotion"],
                        "confidence": primary["confidence"],
                        "severity": severity,
                        "severity_label": self._severity_label(severity),
                        "timestamp": datetime.now().isoformat(),
                        "face_index": i
                    }
                    result["high_risk_alerts"].append(alert)
                    # 记录到日志
                    logger.warning(
                        f"⚠ 高危情绪检测: {primary['emotion']} "
                        f"(置信度: {primary['confidence']:.2f}, 严重程度: {severity}/10)"
                    )

            result["success"] = True

        except Exception as e:
            logger.error(f"帧分析失败: {e}")
            result["error"] = str(e)

        return result

    def _calc_severity(self, confidence: float) -> int:
        """根据置信度计算严重程度 (0-10)"""
        for (lo, hi), severity in SEVERITY_LEVELS.items():
            if lo <= confidence < hi:
                return severity
        return 10 if confidence >= 1.0 else 1

    def _severity_label(self, severity: int) -> str:
        """严重程度标签"""
        if severity <= 3:
            return "轻度"
        elif severity <= 6:
            return "中度"
        elif severity <= 8:
            return "重度"
        else:
            return "严重"


# 全局告警记录存储（内存中，生产环境应持久化到数据库）
_alert_logs: List[Dict] = []
MAX_LOGS = 500


def add_alert_log(alert: Dict):
    """添加告警记录"""
    _alert_logs.insert(0, alert)
    if len(_alert_logs) > MAX_LOGS:
        _alert_logs.pop()


def get_alert_logs(limit: int = 50) -> List[Dict]:
    """获取最近的告警记录"""
    return _alert_logs[:limit]


def clear_alert_logs():
    """清空告警记录"""
    _alert_logs.clear()


# 全局检测器实例（懒加载）
_detector: Optional[YoloEmotionDetector] = None


def get_detector() -> YoloEmotionDetector:
    """获取或创建 YOLO 情绪检测器（单例）"""
    global _detector
    if _detector is None:
        _detector = YoloEmotionDetector()
    return _detector


# ===== 演示/测试入口 =====
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("  聆心 - YOLO 实时情绪识别引擎")
    print("=" * 60)

    detector = get_detector()
    status = "✅ 就绪" if detector.ready else "⚠ 部分就绪（模型下载中或缺失）"
    print(f"  状态: {status}")
    print(f"  高危情绪: {', '.join(HIGH_RISK_EMOTIONS)}")
    print(f"  告警阈值: {DEFAULT_THRESHOLD}")
    print(f"  告警记录数: {len(_alert_logs)}")
    print("=" * 60)
