# -*- coding: utf-8 -*-
"""
聆心 — 情绪识别评测框架
=======================
对情绪识别能力做可量化评测，输出准确率、宏 F1、混淆矩阵。
这是答辩时「准确率 XX% 是怎么来的」这一必答题的答案来源。

模式：
  1. 文本情绪评测（--mode text）   内置示例样本，无需模型/网络，秒级出报告
  2. 语音情绪评测（--mode audio）  使用 EmotionAnalyzer（真实模型 → 规则 → LLM）

用法：
  python tools/benchmark_emotion.py                     # 默认文本评测（内置样例）
  python tools/benchmark_emotion.py --mode audio --manifest audio_labels.json
  python tools/benchmark_emotion.py --mode audio --dir audio_samples

manifest JSON 格式（audio 模式）：
  [ {"file": "audio_samples/happy_01.wav", "label": "高兴"}, ... ]

输出：打印控制台报告，并写入 docs/评测报告.md
"""
import argparse
import json
import os
import sys
from collections import defaultdict

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# 内置小样本人为标注评测集，刻意混入口语、歧义和短句，避免“全对但无区分度”。
BUILTIN_TEXT_SAMPLES = [
    ("正常", "好的，收到，谢谢老师。"),
    ("正常", "我知道了，今晚会早点睡。"),
    ("正常", "老师，这题我不太会，能再讲一遍吗？"),
    ("正常", "最近事情有点多，但我觉得还能安排好。"),
    ("正常", "我担心今天下雨，记得带伞。"),
    ("正常", "我不想动，所以周末就在宿舍休息。"),
    ("高兴", "太好了，我通过了考试，好开心！"),
    ("高兴", "哈哈，这次活动太棒了，我特别喜欢。"),
    ("高兴", "今天和朋友聊得很开心，感觉轻松多了。"),
    ("焦虑", "我最近压力特别大，总觉得时间不够用，很担心考不好。"),
    ("焦虑", "马上要答辩了，我紧张得睡不着觉，心里很不安。"),
    ("焦虑", "我担心自己跟不上进度。"),
    ("悲伤", "我奶奶去世了，我真的好难过，每天都在哭。"),
    ("悲伤", "失去了最好的朋友，心里好痛苦。"),
    ("悲伤", "我觉得没人真的在乎我，活着没有意义。"),
    ("悲伤", "我感觉好绝望，好像没人能帮我。"),
    ("愤怒", "这太不公平了！凭什么这样对我，我真的很生气。"),
    ("愤怒", "我讨厌这种被人欺负的感觉，恨不得马上发作。"),
    ("愤怒", "凭什么每次都是我背锅。"),
    ("愤怒", "他们总是故意针对我，我快气炸了。"),
    ("恐惧", "我每天晚上都做噩梦，很害怕一个人待着。"),
    ("恐惧", "不敢去人多的地方，一想到就浑身发抖。"),
    ("恐惧", "我一到考试就发慌，手心冒汗。"),
    ("压抑", "没人理解我，感觉特别孤独，一直憋着。"),
    ("压抑", "我总是一个人扛着，越来越觉得喘不过气。"),
    ("压抑", "白天装没事，晚上却经常睡不着。"),
    ("压抑", "心里像压了一块石头，越来越累。"),
    ("低落", "最近什么都不想干，觉得好累，提不起劲。"),
    ("低落", "每天都好没意思，懒得动，也不想说话。"),
    ("低落", "我最近上课老走神，但下课又没精神。"),
]

from core.text_emotion import classify_local_text_emotion


def compute_metrics(y_true, y_pred, confidences=None, details=None):
    """计算准确率、宏 F1、各类别指标、混淆矩阵与置信度统计。"""
    labels = sorted(set(y_true) | set(y_pred))
    n = len(y_true)
    accuracy = sum(1 for t, p in zip(y_true, y_pred) if t == p) / n if n else 0.0

    confusion = defaultdict(lambda: defaultdict(int))
    for t, p in zip(y_true, y_pred):
        confusion[t][p] += 1

    per_class = {}
    f1s = []
    for label in labels:
        tp = confusion[label][label]
        fp = sum(confusion[t][label] for t in labels if t != label)
        fn = sum(confusion[label][p] for p in labels if p != label)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "n": sum(confusion[label].values()),
        }
        f1s.append(f1)
    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0

    metrics = {
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "per_class": per_class,
        "confusion": confusion,
        "labels": labels,
    }

    if confidences:
        conf_by_true = defaultdict(list)
        for true_label, confidence in zip(y_true, confidences):
            conf_by_true[true_label].append(confidence)
        for label, class_metrics in per_class.items():
            values = conf_by_true.get(label) or [0.0]
            class_metrics["avg_confidence"] = round(sum(values) / len(values), 4)
        metrics["avg_confidence"] = round(sum(confidences) / len(confidences), 4)
        metrics["min_confidence"] = round(min(confidences), 4)
        metrics["max_confidence"] = round(max(confidences), 4)
        metrics["low_confidence_count"] = sum(1 for c in confidences if c < 0.60)

    if details:
        metrics["errors"] = [
            item for item in details if item["true"] != item["predicted"]
        ]

    return metrics


def render_report(metrics, mode, sample_count):
    """生成 Markdown 报告文本。"""
    lines = []
    lines.append("# 情绪识别评测报告")
    lines.append("")
    lines.append(f"- 评测模式：{'文本情绪（生产关键词基线）' if mode == 'text' else '语音情绪'}")
    lines.append(f"- 样本数量：{sample_count}")
    lines.append("- 数据口径：内置人工标注小样本评测集，非真实用户脱敏数据")
    lines.append(f"- 准确率：**{metrics['accuracy']:.2%}**")
    lines.append(f"- 宏 F1：**{metrics['macro_f1']:.2%}**")
    if "avg_confidence" in metrics:
        lines.append(f"- 平均置信度：**{metrics['avg_confidence']:.2%}**")
        lines.append(f"- 置信度范围：{metrics['min_confidence']:.2%} ~ {metrics['max_confidence']:.2%}")
        lines.append(f"- 低置信度样本（<60%）：{metrics['low_confidence_count']} 条")
    lines.append("")
    lines.append("## 各类别指标")
    lines.append("")
    header = "| 情绪 | 精确率 | 召回率 | F1 | 样本数 |"
    separator = "|------|--------|--------|-----|--------|"
    if "avg_confidence" in metrics:
        header += " 平均置信度 |"
        separator += "------------|"
    lines.append(header)
    lines.append(separator)
    for label in metrics["labels"]:
        c = metrics["per_class"][label]
        row = f"| {label} | {c['precision']:.2%} | {c['recall']:.2%} | {c['f1']:.2%} | {c['n']} |"
        if "avg_confidence" in metrics:
            row += f" {c['avg_confidence']:.2%} |"
        lines.append(row)
    lines.append("")
    lines.append("## 混淆矩阵（行=真实，列=预测）")
    lines.append("")
    labels = metrics["labels"]
    lines.append("| 真实\\预测 | " + " | ".join(labels) + " |")
    lines.append("|---|" + "---|" * len(labels))
    for t in labels:
        row = " | ".join(str(metrics["confusion"][t][p]) for p in labels)
        lines.append(f"| {t} | {row} |")
    lines.append("")

    if "errors" in metrics:
        lines.append("## 预测错误样本")
        lines.append("")
        if metrics["errors"]:
            lines.append("| 真实 | 预测 | 置信度 | 文本 |")
            lines.append("|------|------|--------|------|")
            for item in metrics["errors"]:
                text = item["text"].replace("|", "\\|")
                lines.append(
                    f"| {item['true']} | {item['predicted']} | "
                    f"{item['confidence']:.2%} | {text} |"
                )
        else:
            lines.append("无")
        lines.append("")

    lines.append("> 说明：本报告由 `tools/benchmark_emotion.py` 自动生成。"
                 "文本模式复用 `core.text_emotion.classify_local_text_emotion`，"
                 "与线上接口使用同一套分类规则；语音模式使用实际情绪识别管线。")
    lines.append("")
    return "\n".join(lines)


def run_text_benchmark(samples):
    y_true = [label for label, _ in samples]
    y_pred = []
    confidences = []
    details = []
    for label, text in samples:
        result = classify_local_text_emotion(text)
        predicted = result.get("emotion", "正常")
        confidence = result.get("confidence", 0.0)
        y_pred.append(predicted)
        confidences.append(confidence)
        details.append({
            "true": label,
            "predicted": predicted,
            "confidence": confidence,
            "text": text,
        })
    return compute_metrics(y_true, y_pred, confidences, details)


def run_audio_benchmark(manifest):
    from core.emotion_engine import EmotionAnalyzer
    analyzer = EmotionAnalyzer()
    y_true, y_pred = [], []
    for item in manifest:
        path = item["file"]
        if not os.path.isabs(path):
            path = os.path.join(ROOT_DIR, path)
        if not os.path.exists(path):
            print(f"  [跳过] 文件不存在: {path}")
            continue
        label = item["label"]
        try:
            result = analyzer.analyze_single(path)
            y_true.append(label)
            y_pred.append(result.get("emotion", "未知"))
            print(f"  {os.path.basename(path)}: 真实={label} 预测={result.get('emotion')} 来源={result.get('_source')}")
        except Exception as e:  # noqa: BLE001
            print(f"  [失败] {path}: {e}")
    return compute_metrics(y_true, y_pred)


def main():
    parser = argparse.ArgumentParser(description="聆心情绪识别评测")
    parser.add_argument("--mode", choices=["text", "audio"], default="text")
    parser.add_argument("--manifest", help="音频评测的标注 JSON 文件")
    parser.add_argument("--dir", help="音频评测的标注目录（文件名前缀为标签，如 高兴_01.wav）")
    args = parser.parse_args()

    if args.mode == "text":
        samples = BUILTIN_TEXT_SAMPLES
        metrics = run_text_benchmark(samples)
        sample_count = len(samples)
    else:
        if args.manifest:
            with open(args.manifest, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        elif args.dir:
            manifest = []
            for fname in sorted(os.listdir(args.dir)):
                if fname.startswith("."):
                    continue
                label = fname.split("_")[0]
                manifest.append({"file": os.path.join(args.dir, fname), "label": label})
        else:
            print("[X] 音频评测需提供 --manifest 或 --dir")
            sys.exit(1)
        if not manifest:
            print("[X] 标注数据为空")
            sys.exit(1)
        metrics = run_audio_benchmark(manifest)
        sample_count = len(manifest)

    report = render_report(metrics, args.mode, sample_count)
    print(report)

    out_path = os.path.join(ROOT_DIR, "docs", "评测报告.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n[OK] 报告已写入 {out_path}")


if __name__ == "__main__":
    main()
