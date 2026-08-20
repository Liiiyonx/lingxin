# -*- coding: utf-8 -*-
"""AI 数字人回复引擎。

在辅导员离线时，以心理专家视角、幽默亲切的方式回复学生。
优先尝试 DashScope 大模型，失败时使用本地关键词回复，保证演示环境可用。
"""

import os
import re
import logging
from datetime import datetime

logger = logging.getLogger("core.digital_human")


CRISIS_KEYWORDS = (
    "自杀", "自残", "想死", "不想活", "结束生命", "活不下去",
    "伤害自己", "割腕", "跳楼", "轻生", "去死", "没有意义",
    "自杀意念", "结束自己", "不想继续", "熬不过去", "自伤",
    "suicide", "self-harm", "self harm", "kill myself", "end my life",
    "want to die", "don't want to live", "cut myself",
)

CRISIS_RESPONSE_MARKERS = (
    "12356", "400-161-9995", "心理援助热线", "危机干预",
    "立即联系", "身边信任的人", "你现在安全吗",
)


def _clean_text(text):
    return re.sub(r"\s+", " ", (text or "").strip())


def _has_keywords(text, words):
    return any(word in text for word in words)


def _has_crisis_response_markers(content):
    """判断大模型回复是否已经按危机协议进入安全支持流程。"""
    return _has_keywords(_clean_text(content), CRISIS_RESPONSE_MARKERS)


def _crisis_reply(settings, student_name):
    name = (student_name or "同学").strip()
    return (
        f"{name}，你现在安全吗？这非常重要，请先停下来，不要一个人扛。"
        "如果此刻有伤害自己的冲动，请立即联系身边信任的人，或拨打 24 小时心理援助热线 "
        "12356 / 400-161-9995。我也会立刻提醒你的辅导员和心理中心。"
        "你愿意先告诉我，现在在哪里、身边有没有可以陪你的人吗？"
    ), True


def _local_reply(message, settings):
    """基于关键词的本地回复，保证离线/无密钥环境也能工作。"""
    style = settings.get("style") or "humor"
    humor = int(settings.get("humor") or 3)
    text = _clean_text(message)

    tone_suffix = {
        "humor": "先不急着给自己下结论，我们一步一步来 (｡･ω･｡)ﾉ",
        "warm": "你可以放心地说，我在这里陪着你。",
        "pro": "我们可以先一起梳理一下当前最困扰你的部分。",
    }.get(style, "我们慢慢说。")

    if _has_keywords(text, CRISIS_KEYWORDS):
        return _crisis_reply(settings, "")

    if _has_keywords(text, ("考试", "压力", "复习", "成绩", "挂科", "学习", "论文", "毕业")):
        if style == "warm":
            content = "听起来你最近把很多力气都花在学业上了，真的很不容易。压力不是因为你不够好，而是你在意这件事。我们先只选今天能做的一小步，比如先睡好、吃口热饭，再把任务拆成 20 分钟一段，好吗？"
        elif style == "pro":
            content = "学业压力通常会同时带来焦虑、睡眠和注意力问题。你可以试试“任务外化”：把担心写下来，区分可控与不可控，再安排 20 分钟专注 + 5 分钟休息的节奏。如果需要，我可以陪你做一次呼吸练习。"
        else:
            content = "考试这个 boss 确实有点烦人，但你不是一个人在刷副本 (ง •̀_•́)ง。先把目标从“必须考好”换成“今天先拿下 20 分钟”，压力就会小很多。你现在最担心的是哪一门？"

    elif _has_keywords(text, ("失眠", "睡不着", "熬夜", "睡不好", "困", "没精神")):
        if style == "warm":
            content = "睡不好的夜晚会让人更累，也更容易想很多。今晚试着比平时早 30 分钟放下手机，做几次缓慢呼吸；如果躺下 20 分钟还睡不着，就起来喝点温水、写两行心事，不强迫自己。"
        elif style == "pro":
            content = "睡眠问题常与焦虑和高唤醒状态有关。可以固定起床时间、白天增加一点运动，睡前 1 小时减少屏幕蓝光。若持续两周以上并明显影响白昼状态，建议进一步评估。"
        else:
            content = "大脑在晚上特别爱开脑内演唱会，越躺越清醒 (¬_¬)。先别跟失眠硬碰硬，试试“4-7-8 呼吸”：吸气 4 秒、屏住 7 秒、慢慢呼气 8 秒，做 4 轮。你昨晚大概几点睡的？"

    elif _has_keywords(text, ("室友", "同学", "朋友", "吵架", "矛盾", "恋爱", "分手", "孤立", "排挤", "关系")):
        if style == "warm":
            content = "关系里的不舒服很真实，愿意说出来已经是一种勇气。你不需要马上解决所有人际问题，可以先把自己的感受和边界说清楚。你希望这段关系变成什么样？"
        elif style == "pro":
            content = "人际冲突里，情绪背后往往藏着未被满足的需要。我们可以先区分事实、感受和期待，再用“我陈述句”表达，例如“当你……时，我感到……，我希望……”。这比指责更容易让对方听进去。"
        else:
            content = "和重要的人闹别扭，确实像手机突然卡在 1% 电量，心里又急又堵 (╯﹏╰）。别急着开“吵架模式”，先说说你最委屈的一点是什么？我帮你把话说顺一点。"

    elif _has_keywords(text, ("迷茫", "未来", "工作", "就业", "考研", "没方向", "不知道怎么办")):
        if style == "warm":
            content = "迷茫不是因为你不努力，而是你正在认真思考未来。方向可以慢慢找，不必一次把整个人生都决定完。可以先从“最近哪件事让我有一点成就感”开始。"
        elif style == "pro":
            content = "对未来感到迷茫，往往是因为选项太多、信息不足，而不是能力缺失。我们可以做一个简单梳理：写下你在意的价值、当前资源、短期可行动项，把“人生大选择”拆成可验证的小实验。"
        else:
            content = "人生不像导航，没有谁会提前把路线全点亮 (・ω・｀)。不过可以先开个“探索模式”：这学期做一件你有点好奇但还没试过的事。你更纠结继续读书还是找工作？"

    elif _has_keywords(text, ("难过", "伤心", "哭", "孤独", "失落", "委屈", "痛苦", "绝望")):
        if style == "warm":
            content = "我听见了，你心里一定很不好受。难过不需要被赶走，它只是在提醒你：最近太辛苦了。先给自己一点允许，慢慢呼吸，告诉我发生了什么。"
        elif style == "pro":
            content = "这种低落可能已经持续一段时间了。我们可以先把情绪强度、持续时间和触发事件简单记录一下，也留意睡眠、食欲和注意力变化。若连续两周以上仍明显低落，建议尽快和老师或专业机构谈一谈。"
        else:
            content = "抱抱，先不要求自己立刻振作 (っ´▽`)っ。难过的时候不适合讲大道理，先喝点温水，做几次深长呼吸。你愿意说说，最近是哪件事让你最难受吗？"

    elif _has_keywords(text, ("焦虑", "紧张", "担心", "害怕", "慌", "不安")):
        if style == "warm":
            content = "焦虑是在提醒你，你很在意接下来会发生的事。先不用和它对抗，可以把注意力放到脚下，感受脚踩地面的重量，再慢慢呼气。你担心的事情具体是什么？"
        elif style == "pro":
            content = "焦虑通常来自对未来威胁的预期。我们可以做一个“事实核查”：这件事最坏、最好和最可能的结果分别是什么？把你担心的内容写下来，会降低大脑反复报警的强度。"
        else:
            content = "你的大脑又提前点开了“灾难片预告” (｡•́︿•̀｡)。先暂停脑补，试试把担心的事写成一句话，然后问自己：现在这一刻，我能做的最小动作是什么？"

    elif _has_keywords(text, ("生气", "愤怒", "烦", "讨厌", "不公平", "凭什么")):
        if style == "warm":
            content = "你有权利生气，这说明你有在意和坚持的东西。先不急着做决定，找一个安全的方式把情绪释放掉，比如走走、写下来或运动一下。等你愿意说时，我在。"
        elif style == "pro":
            content = "愤怒通常是边界被侵犯时的保护信号。我们可以先降温，再处理问题：离开刺激源、做 6 次慢呼吸，然后写下触发事件和你真正想维护的边界。"
        else:
            content = "这股火气我接住了，先不急着喷火 (ノ｀Д´)ノ彡。深呼吸三次，喝口水，然后告诉我：是哪件事让你这么生气？"

    elif _has_keywords(text, ("开心", "高兴", "太好了", "哈哈", "谢谢", "老师", "好的")):
        content = "收到～看到你状态轻松一点，我也很开心！继续保持这个节奏，记得按时吃饭、早点休息。有需要随时来找我 (๑•̀ㅂ•́)و✧"

    else:
        content = (
            "我在这儿呢，慢慢说，不用急。"
            + tone_suffix
        )
        if humor >= 3 and style == "humor":
            content += " 你放心，我会先把“心理学模式”打开，不会只发鸡汤的～"

    if style == "humor" and not re.search(r"[\(（][^()（）]{1,12}[\)）]", content):
        content += " (｡･ω･｡)ﾉ"
    return content, False


def _openai_reply(message, settings):
    """尝试使用 DashScope 生成更自然的回复，失败时抛出异常由调用方降级。"""
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 未配置")

    from openai import OpenAI
    client = OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        timeout=6,
    )
    style = settings.get("style") or "humor"
    style_guide = {
        "humor": "语气幽默风趣、亲切自然，适当使用颜文字或 emoji，但不要浮夸。",
        "warm": "语气温暖亲切、有陪伴感，少说教，多共情。",
        "pro": "语气专业稳重，像有经验的心理专家，给出清晰、可执行的建议。",
    }[style]
    system_prompt = (
        "你是高校心理辅导员的 AI 数字分身，在学生看不到老师在线时代为回复。"
        "你要以心理专家视角回应，尊重、不诊断、不贴标签、不承诺药物或治疗。"
        + style_guide
        + " 回复控制在 80 到 180 个中文字符，只输出给学生的回复正文。"
        "如果识别到自伤、自杀或严重危机，必须停止幽默，优先询问安全状态并提供 12356 / 400-161-9995 热线。"
    )
    resp = client.chat.completions.create(
        model="qwen-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _clean_text(message)},
        ],
        temperature=0.75,
        max_tokens=320,
    )
    content = (resp.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("大模型返回为空")
    return content, _has_crisis_response_markers(content)


def generate_reply(message, settings=None, student_name=""):
    """生成数字人回复，返回 (content, crisis)。"""
    settings = settings or {
        "enabled": True,
        "name": "小聆",
        "humor": 3,
        "style": "humor",
        "delay": 2,
    }
    message = _clean_text(message)
    if not message:
        return "我在呢，想聊什么都可以慢慢说 (｡･ω･｡)ﾉ", False
    if _has_keywords(message, CRISIS_KEYWORDS):
        return _crisis_reply(settings, student_name)

    try:
        return _openai_reply(message, settings)
    except Exception as exc:
        logger.warning("数字人大模型调用失败，使用本地回复: %s", exc)
        return _local_reply(message, settings)


def digital_human_status(presence, settings):
    """组装前端所需的数字人状态。"""
    return {
        "online": bool(presence and presence.get("online")),
        "last_seen": presence.get("last_seen") if presence else None,
        "dh_enabled": bool(settings.get("enabled")) if settings else False,
        "dh_name": (settings or {}).get("name") or "小聆",
    }
