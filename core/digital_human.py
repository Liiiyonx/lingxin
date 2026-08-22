# -*- coding: utf-8 -*-
"""AI 数字人回复引擎。

在辅导员离线时，以心理专家视角、幽默亲切的方式回复学生。
优先尝试 DashScope 大模型，失败时使用本地关键词回复，保证演示环境可用。
"""

import os
import re
import json
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

CRISIS_LEVEL = {
    0: "正常",
    1: "关注",
    2: "高风险",
    3: "紧急",
}

URGENT_KEYWORDS = (
    "想死", "不想活", "自杀", "自残", "结束生命", "活不下去",
    "伤害自己", "割腕", "跳楼", "轻生", "去死", "自杀意念",
    "结束自己", "自伤", "不想活了",
    "suicide", "self-harm", "self harm", "kill myself", "end my life",
    "want to die", "don't want to live", "cut myself",
)

RISK_SIGNAL_WORDS = (
    "没有意义", "活着没意思", "没人在乎", "没人管", "撑不下去",
    "熬不过去", "不想继续", "不想坚持", "坚持不下去", "解脱",
    "想消失", "没有希望", "毫无希望", "看不到希望", "孤立无援",
    "再也受不了", "撑不住", "活着像", "没有活下去",
)

NEGATIVE_EMOTION_WORDS = (
    "难过", "伤心", "哭", "孤独", "失落", "委屈", "痛苦", "绝望",
    "焦虑", "紧张", "担心", "害怕", "慌", "不安", "压力", "好累",
    "低落", "压抑", "烦", "生气", "愤怒", "讨厌", "没意思", "累",
    "无助", "无望", "没人理解", "不被理解",
)


def _clean_text(text):
    return re.sub(r"\s+", " ", (text or "").strip())


def _has_keywords(text, words):
    return any(word in text for word in words)


def _has_crisis_response_markers(content):
    """判断大模型回复是否已经按危机协议进入安全支持流程。"""
    return _has_keywords(_clean_text(content), CRISIS_RESPONSE_MARKERS)


class ReplyResult:
    """数字人回复结果。

    支持旧的 ``content, crisis = generate_reply(...)`` 解包方式，同时给新调用方
    提供 ``crisis_level``、``emotion`` 和 ``triggered_keywords`` 等结构化信息。
    """

    def __init__(self, content, crisis=False, crisis_level=0, emotion="neutral",
                 triggered_keywords=None):
        self.content = content
        self.crisis = bool(crisis or crisis_level >= 2)
        self.crisis_level = int(crisis_level or 0)
        self.emotion = emotion or "neutral"
        self.triggered_keywords = list(triggered_keywords or [])

    def __iter__(self):
        yield self.content
        yield self.crisis

    def __getitem__(self, index):
        return (self.content, self.crisis)[index]

    def get(self, key, default=None):
        return self.to_dict().get(key, default)

    def to_dict(self):
        return {
            "content": self.content,
            "crisis": self.crisis,
            "crisis_level": self.crisis_level,
            "emotion": self.emotion,
            "triggered_keywords": self.triggered_keywords,
        }


def _matched_keywords(text, words):
    return [word for word in words if word in text]


def _engagement_hint(history):
    """根据历史 AI 回复是否被学生继续回应，给出本轮话术策略提示。"""
    history = [item for item in (history or []) if isinstance(item, dict)]
    assistant_indexes = [
        index for index, item in enumerate(history)
        if item.get("role") == "assistant"
    ]
    if not assistant_indexes:
        return ""

    continued = 0
    for index in assistant_indexes:
        next_item = history[index + 1] if index + 1 < len(history) else None
        if (
            next_item
            and next_item.get("role") == "user"
            and (next_item.get("content") or "").strip()
        ):
            continued += 1

    ratio = continued / len(assistant_indexes)
    if ratio >= 0.7:
        return "历史对话显示该学生通常愿意继续回应，可在结尾留一个开放问题促进深入。"
    if ratio < 0.4:
        return "历史对话显示该学生回复后较少继续回应，本轮宜简短、降低压力，并给出一个可选择的小动作。"
    return "历史对话显示该学生回应节奏一般，可给一个低压力的小问题或选择。"


def _effective_settings(settings, student_context):
    """按学生风险画像调整风格与幽默度，保证高危学生本地兜底也谨慎。"""
    result = dict(settings or {})
    context = student_context or {}
    risk = str(context.get("risk_level") or "").strip().lower()
    if risk in ("high", "critical"):
        result["style"] = "pro"
        result["humor"] = 1
    elif risk == "medium":
        result["humor"] = max(1, min(int(result.get("humor") or 3), 2))
    return result


def _llm_risk_probe(message, settings=None):
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=4,
        )
        system_prompt = (
            "你是高校心理健康危机分级器。只判断学生消息的心理危机等级，"
            "不要输出建议。等级定义：0=正常，1=一般负面情绪，2=高风险语义，"
            "3=明确自伤/自杀意图。严格返回 JSON："
            '{"level":0,"reason":"简短原因"}'
        )
        resp = client.chat.completions.create(
            model="qwen-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": _clean_text(message)},
            ],
            temperature=0,
            max_tokens=60,
        )
        raw = (resp.choices[0].message.content or "").strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        data = json.loads(match.group())
        level = int(data.get("level", 0))
        return max(0, min(3, level))
    except Exception as exc:
        logger.info("危机语义兜底失败，回退到本地分级: %s", exc)
        return None


def _infer_emotion(message, crisis_level):
    text = _clean_text(message)
    if crisis_level >= 2:
        return "concerned"
    if _has_keywords(text, ("开心", "高兴", "太好了", "哈哈", "谢谢", "喜欢", "棒")):
        return "happy"
    if _has_keywords(text, NEGATIVE_EMOTION_WORDS):
        return "sad"
    return "neutral"


def _detect_crisis_level(message, settings=None):
    text = _clean_text(message)
    urgent = _matched_keywords(text, URGENT_KEYWORDS)
    if urgent:
        return 3, urgent

    risk = _matched_keywords(text, RISK_SIGNAL_WORDS)
    if risk:
        return 2, risk

    probe_level = _llm_risk_probe(text, settings)
    if probe_level == 3:
        return 3, ["语义兜底-紧急"]
    if probe_level == 2:
        return 2, ["语义兜底-高风险"]

    negative = _matched_keywords(text, NEGATIVE_EMOTION_WORDS)
    if negative:
        return 1, negative

    if probe_level == 1:
        return 1, ["语义兜底-关注"]
    return 0, []


def _crisis_reply(settings, student_name):
    name = (student_name or "同学").strip()
    return (
        f"{name}，你现在安全吗？这非常重要，请先停下来，不要一个人扛。"
        "如果此刻有伤害自己的冲动，请立即联系身边信任的人，或拨打 24 小时心理援助热线 "
        "12356 / 400-161-9995。我也会立刻提醒你的辅导员和心理中心。"
        "你愿意先告诉我，现在在哪里、身边有没有可以陪你的人吗？"
    ), True


def _risk_reply(settings, student_name):
    name = (student_name or "同学").strip()
    return (
        f"{name}，我听见你现在的坚持已经耗掉很多力气了，谢谢你愿意说出来。"
        "我们先不急着判断，先照顾好当下：如果可以，找一个安静安全的地方，"
        "喝点温水，做几次深长呼吸。"
        "如果你已经出现伤害自己的念头，请立刻联系身边信任的人，或拨打 24 小时心理援助热线 "
        "12356 / 400-161-9995。我也会提醒你的辅导员尽快跟进，你不会被丢下。"
        "你愿意先告诉我，现在最让你喘不过气的是什么吗？"
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


def _openai_reply(message, settings, history=None, student_context=None):
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
    context_notes = []
    if student_context:
        risk_level = str(student_context.get("risk_level") or "").strip()
        emotion_status = str(student_context.get("emotion_status") or "").strip()
        if risk_level or emotion_status:
            context_notes.append(
                f"该学生当前档案风险等级为「{risk_level or '未知'}」，"
                f"情绪状态为「{emotion_status or '未知'}」。"
                "风险越高，语气越要克制、谨慎、少幽默，优先稳定情绪并引导线下求助。"
            )
        engagement_hint = str(student_context.get("engagement_hint") or "").strip()
        if engagement_hint:
            context_notes.append(engagement_hint)
    risk_note = " ".join(context_notes)

    system_prompt = (
        "你是高校心理辅导员的 AI 数字分身，在学生看不到老师在线时代为回复。"
        "你要以心理专家视角回应，尊重、不诊断、不贴标签、不承诺药物或治疗。"
        + style_guide
        + " 回复控制在 80 到 180 个中文字符，只输出给学生的回复正文。"
        "如果识别到自伤、自杀或严重危机，必须停止幽默，优先询问安全状态并提供 12356 / 400-161-9995 热线。"
        + risk_note
    )
    messages = [{"role": "system", "content": system_prompt}]
    for item in (history or [])[-8:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": _clean_text(message)})
    resp = client.chat.completions.create(
        model="qwen-turbo",
        messages=messages,
        temperature=0.75,
        max_tokens=320,
    )
    content = (resp.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("大模型返回为空")
    return content, _has_crisis_response_markers(content)


def generate_reply_result(message, settings=None, student_name="", history=None,
                          student_context=None):
    """生成数字人回复并返回结构化结果。"""
    settings = settings or {
        "enabled": True,
        "name": "小聆",
        "humor": 3,
        "style": "humor",
        "delay": 2,
    }
    message = _clean_text(message)
    student_context = dict(student_context or {})
    history = [item for item in (history or []) if isinstance(item, dict)]
    if not student_context.get("engagement_hint"):
        student_context["engagement_hint"] = _engagement_hint(history)
    settings = _effective_settings(settings, student_context)
    if not message:
        return ReplyResult(
            "我在呢，想聊什么都可以慢慢说 (｡･ω･｡)ﾉ",
            False, 0, "neutral", [],
        )

    level, keywords = _detect_crisis_level(message, settings)
    if level >= 3:
        content, _ = _crisis_reply(settings, student_name)
        return ReplyResult(content, True, level, "concerned", keywords)
    if level == 2:
        content, _ = _risk_reply(settings, student_name)
        return ReplyResult(content, True, level, "concerned", keywords)

    try:
        content, has_markers = _openai_reply(
            message, settings, history=history, student_context=student_context
        )
        if has_markers and level < 2:
            level = 2
            keywords = list(keywords) + ["回复中出现危机干预标记"]
        return ReplyResult(
            content,
            level >= 2,
            level,
            _infer_emotion(message, level),
            keywords,
        )
    except Exception as exc:
        logger.warning("数字人大模型调用失败，使用本地回复: %s", exc)
        content, crisis = _local_reply(message, settings)
        if crisis:
            level = max(level, 2)
        return ReplyResult(
            content,
            level >= 2,
            level,
            _infer_emotion(message, level),
            keywords,
        )


def generate_reply(message, settings=None, student_name=""):
    """兼容旧调用：仍可用 ``content, crisis = generate_reply(...)``。"""
    return generate_reply_result(message, settings=settings, student_name=student_name)


def digital_human_status(presence, settings):
    """组装前端所需的数字人状态。"""
    return {
        "online": bool(presence and presence.get("online")),
        "last_seen": presence.get("last_seen") if presence else None,
        "dh_enabled": bool(settings.get("enabled")) if settings else False,
        "dh_name": (settings or {}).get("name") or "小聆",
    }
