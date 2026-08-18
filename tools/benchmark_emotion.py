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
from collections import Counter, defaultdict

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# 内置文本示例样本（label -> 例句列表），用于演示评测框架，可替换为真实标注数据
BUILTIN_TEXT_SAMPLES = [
    ("正常", "好的，收到，谢谢老师。"),
    ("正常", "知道了，我会按时完成的。"),
    ("高兴", "太好了，我通过了考试，好开心！"),
    ("高兴", "哈哈，这次活动太棒了，我特别喜欢。"),
    ("焦虑", "我最近压力特别大，总觉得时间不够用，很担心考不好。"),
    ("焦虑", "马上要答辩了，我紧张得睡不着觉，心里很不安。"),
    ("悲伤", "我奶奶去世了，我真的好难过，每天都在哭。"),
    ("悲伤", "失去了最好的朋友，心里好痛苦。"),
    ("愤怒", "这太不公平了！凭什么这样对我，我真的很生气。"),
    ("愤怒", "我讨厌这种被人欺负的感觉，恨不得马上发作。"),
    ("恐惧", "我每天晚上都做噩梦，很害怕一个人待着。"),
    ("恐惧", "不敢去人多的地方，一想到就浑身发抖。"),
    ("压抑", "没人理解我，感觉特别孤独，一直憋着。"),
    ("压抑", "我总是一个人扛着，越来越觉得喘不过气。"),
    ("低落", "最近什么都不想干，觉得好累，提不起劲。"),
    ("低落", "每天都好没意思，懒得动，也不想说话。"),
]

# 关键词情绪分类器（与 api/routes.py 的 _local_text_emotion 逻辑一致）
_KEYWORDS = {
    "焦虑": ["焦虑", "担心", "紧张", "不安", "压力", "崩溃", "受不了"],
    "悲伤": ["难过", "伤心", "哭了", "失去", "痛苦", "绝望", "想死", "自杀"],
    "愤怒": ["生气", "愤怒", "讨厌", "恨", "不公平", "凭什么", "滚"],
    "恐惧": ["害怕", "恐惧", "恐怖", "吓", "噩梦", "不敢"],
    "压抑": ["压抑", "憋着", "没人理解", "孤独", "寂寞", "一个人"],
    "低落": ["低落", "没意思", "无聊", "懒得", "不想动", "好累", "没劲"],
    "高兴": ["开心", "高兴", "哈哈", "太好了", "棒", "喜欢"],
    "正常": ["好的", "收到", "知道", "嗯", "谢谢"],
}


def keyword_classify(text: str) -> str:
    """关键词情绪分类（确定性，用于文本评测基线）。"""
    scores = Counter()
    for emotion, words in _KEYWORDS.items():
        scores[emotion] = sum(1 for w in words if w in text)
    if not scores or max(scores.values()) == 0:
        return "正常"
    return scores.most_common(1)[0][0]


def compute_metrics(y_true, y_pred):
    """计算准确率、宏 F1、各类别指标与混淆矩阵。"""
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
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1, "n": sum(confusion[label].values())}
        f1s.append(f1)
    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0
    return {"accuracy": accuracy, "macro_f1": macro_f1,
            "per_class": per_class, "confusion": confusion, "labels": labels}


def render_report(metrics, mode, sample_count):
    """生成 Markdown 报告文本。"""
    lines = []
    lines.append("# 情绪识别评测报告")
    lines.append("")
    lines.append(f"- 评测模式：{'文本情绪（关键词基线）' if mode == 'text' else '语音情绪'}")
    lines.append(f"- 样本数量：{sample_count}")
    lines.append(f"- 准确率：**{metrics['accuracy']:.2%}**")
    lines.append(f"- 宏 F1：**{metrics['macro_f1']:.2%}**")
    lines.append("")
    lines.append("## 各类别指标")
    lines.append("")
    lines.append("| 情绪 | 精确率 | 召回率 | F1 | 样本数 |")
    lines.append("|------|--------|--------|-----|--------|")
    for label in metrics["labels"]:
        c = metrics["per_class"][label]
        lines.append(f"| {label} | {c['precision']:.2%} | {c['recall']:.2%} | {c['f1']:.2%} | {c['n']} |")
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
    lines.append("> 说明：本报告由 `tools/benchmark_emotion.py` 自动生成。"
                 "文本模式使用内置关键词分类器作为基线；语音模式使用实际情绪识别管线。")
    lines.append("")
    return "\n".join(lines)


def run_text_benchmark(samples):
    y_true = [label for label, _ in samples]
    y_pred = [keyword_classify(text) for _, text in samples]
    return compute_metrics(y_true, y_pred)


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
