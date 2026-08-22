# -*- coding: utf-8 -*-
"""本地文本情绪分类器。

API 与评测脚本共用这一份关键词规则，确保评测口径和线上一致。
"""

LOCAL_EMOTION_KEYWORDS = {
    "焦虑": ["焦虑", "担心", "紧张", "不安", "压力", "崩溃", "受不了"],
    "悲伤": ["难过", "伤心", "哭了", "失去", "痛苦", "绝望", "想死", "自杀"],
    "愤怒": ["生气", "愤怒", "讨厌", "恨", "不公平", "凭什么", "滚"],
    "恐惧": ["害怕", "恐惧", "恐怖", "吓", "噩梦", "不敢"],
    "压抑": ["压抑", "憋着", "没人理解", "孤独", "寂寞", "一个人"],
    "低落": ["低落", "没意思", "无聊", "懒得", "不想动", "好累", "没劲"],
    "高兴": ["开心", "高兴", "哈哈", "太好了", "棒", "喜欢", "谢谢老师"],
    "正常": ["好的", "收到", "知道", "嗯", "谢谢"],
}

HIGH_RISK_EMOTIONS = {"悲伤", "恐惧", "压抑"}
MEDIUM_RISK_EMOTIONS = {"焦虑", "愤怒", "低落"}


def classify_local_text_emotion(text):
    """关键词情绪分类，返回与线上接口兼容的结果。

    新增 score / confidence / matched_keywords，不删除原有 emotion/risk/intensity。
    """
    text = text or ""
    scores = {}
    matched_keywords = []
    for emotion, words in LOCAL_EMOTION_KEYWORDS.items():
        hits = [word for word in words if word in text]
        score = len(hits)
        if score > 0:
            scores[emotion] = score
            matched_keywords.extend(hits)

    if not scores:
        return {
            "emotion": "正常",
            "risk": "low",
            "intensity": 1,
            "score": 0,
            "confidence": 0.35,
            "keywords": [],
            "matched_keywords": [],
            "suggestion": "",
        }

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top, top_score = ranked[0]
    runner_score = ranked[1][1] if len(ranked) > 1 else 0
    margin = max(0, top_score - runner_score)
    confidence = round(min(0.95, 0.55 + 0.08 * top_score + 0.04 * margin), 2)

    risk = "low"
    if top in HIGH_RISK_EMOTIONS and top_score >= 2:
        risk = "high"
    elif top in MEDIUM_RISK_EMOTIONS:
        risk = "medium"

    intensity = min(10, top_score * 3 + 2)
    return {
        "emotion": top,
        "risk": risk,
        "intensity": intensity,
        "score": top_score,
        "confidence": confidence,
        "keywords": [],
        "matched_keywords": matched_keywords,
        "suggestion": "建议关注学生情绪状态" if risk != "low" else "",
    }
