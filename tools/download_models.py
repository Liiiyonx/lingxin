# -*- coding: utf-8 -*-
"""
聆心 — 模型下载脚本（含重试）
=============================
下载并验证以下模型（网络失败自动重试）：
  1. yolov8n-face.pt           人脸检测（ultralytics）
  2. dima806/facial_emotions_image_detection  人脸情绪分类（transformers FER）
  3. iic/emotion2vec_plus_large               语音情绪（modelscope，若未缓存）

运行:  python tools/download_models.py
"""
import os
import sys
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# 国内网络优先走 HF 镜像（hf-mirror.com），加速模型下载
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

MAX_RETRIES = 5
RETRY_DELAY = 10  # 秒


def download_with_retry(name, fn, retries=MAX_RETRIES):
    for attempt in range(1, retries + 1):
        try:
            print(f"[{name}] 尝试 {attempt}/{retries} ...")
            fn()
            print(f"[{name}] ✅ 完成")
            return True
        except Exception as e:
            print(f"[{name}] ❌ 失败（第 {attempt} 次）: {type(e).__name__}: {e}")
            if attempt < retries:
                print(f"[{name}] {RETRY_DELAY}s 后重试 ...")
                time.sleep(RETRY_DELAY)
    print(f"[{name}] 全部重试失败")
    return False


def dl_fer():
    from transformers import pipeline
    p = pipeline("image-classification", model="dima806/facial_emotions_image_detection", top_k=3)
    from PIL import Image
    _ = p(Image.new("RGB", (96, 96), (128, 128, 128)))
    del p


def dl_emotion2vec():
    from funasr import AutoModel
    m = AutoModel(model="iic/emotion2vec_plus_large", disable_update=True)
    del m


def main():
    print("=" * 60)
    print("  聆心 模型下载（已配置 HF 镜像加速）")
    print("=" * 60)
    results = {
        "FER 表情模型": download_with_retry("FER", dl_fer),
        "emotion2vec": download_with_retry("emotion2vec", dl_emotion2vec),
    }
    print("\n" + "=" * 60)
    for k, v in results.items():
        print(f"  {'✅' if v else '❌'} {k}")
    print("=" * 60)
    print("说明：人脸检测默认使用内置 Haar 级联（无需下载），")
    print("      如需要更鲁棒的 yolov8n-face，可手动下载 yolov8n-face.pt 放入项目根目录。")
    if all(results.values()):
        print("[OK] 全部模型就绪")
    else:
        print("[!] 部分模型未就绪（对应功能会自动降级），可重新运行本脚本")


if __name__ == "__main__":
    main()
