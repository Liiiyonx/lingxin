from core.digital_human import generate_reply, digital_human_status

from api import common
from api.common import *  # noqa: F401,F403
from api.common import api, logger, auth_required, role_required, log_action
from api.common import (
    _check_login_rate_limit,
    _audit_login_failure,
    _validate_password_strength,
    _fallback_knowledge_search,
)

# ===================================================================
# 即时通讯 API
# ===================================================================

@api.route("/messages/contacts", methods=["GET"])
@auth_required
def get_message_contacts():
    """获取消息联系人列表"""
    user_type = getattr(g, "user_type", "staff")
    if user_type == "student":
        user_id = g.student_id
    else:
        user_id = g.user_id

    contacts = common.db.get_message_contacts(user_id, user_type)

    return jsonify({
        "success": True,
        "data": contacts,
    }), 200


@api.route("/messages/<int:contact_id>", methods=["GET"])
@auth_required
def get_messages(contact_id):
    """获取与联系人的消息列表"""
    user_type = getattr(g, "user_type", "staff")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    if user_type == "student":
        student_id = g.student_id
        counselor_id = contact_id
        result = common.db.get_conversation_messages(student_id, counselor_id, page, per_page)
        common.db.mark_messages_read(student_id, counselor_id, "student")
    else:
        counselor_id = g.user_id
        student_id = contact_id
        result = common.db.get_conversation_messages(student_id, counselor_id, page, per_page)
        common.db.mark_messages_read(student_id, counselor_id, "counselor")

    return jsonify({
        "success": True,
        "data": result.get("items", []),
        "total": result.get("total", 0),
    }), 200


@api.route("/messages/send", methods=["POST"])
@auth_required
def send_message():
    """发送消息"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请求参数无效"}), 400

    contact_id = data.get("contact_id")
    content = (data.get("content") or "").strip()
    message_type = data.get("message_type", "text")
    file_url = data.get("file_url")

    if not contact_id or not content:
        return jsonify({"success": False, "message": "联系人和消息内容不能为空"}), 400

    user_type = getattr(g, "user_type", "staff")

    if user_type == "student":
        student_id = g.student_id
        counselor_id = contact_id
        sender_type = "student"
        sender_id = student_id
    else:
        counselor_id = g.user_id
        student_id = contact_id
        sender_type = "counselor"
        sender_id = counselor_id

    msg_id = common.db.create_message(
        student_id=student_id,
        counselor_id=counselor_id,
        sender_type=sender_type,
        sender_id=sender_id,
        content=content,
        message_type=message_type,
        file_url=file_url,
    )

    # 统一由服务端实时推送，客户端不再自行转发，避免房间串线和重复消息。
    created_msg = common.db.get_message(msg_id)
    if created_msg:
        common.emit_conversation_message(created_msg)

    # 学生给辅导员发消息，且辅导员离线、数字人已开启时，异步生成 AI 分身回复。
    ai_reply_pending = False
    if user_type == "student":
        try:
            presence = common.db.get_user_presence(counselor_id)
            settings = common.db.get_digital_human_settings(counselor_id)
            if not presence.get("online") and settings.get("enabled"):
                student = common.db.get_student_by_id(student_id) or {}
                student_name = student.get("name") or ""
                student_class = student.get("class_name") or ""
                delay = max(0, min(int(settings.get("delay") or 0), 10))
                ai_reply_pending = True

                def _deliver_assistant_reply():
                    try:
                        if delay:
                            time.sleep(delay)
                        reply, crisis = generate_reply(content, settings, student_name)
                        reply_id = common.db.create_message(
                            student_id=student_id,
                            counselor_id=counselor_id,
                            sender_type="assistant",
                            sender_id=counselor_id,
                            content=reply,
                            message_type="text",
                            file_url=None,
                        )
                        common.db.create_digital_human_log(
                            counselor_id=counselor_id,
                            student_id=student_id,
                            message_id=msg_id,
                            content=reply,
                            crisis=crisis,
                        )
                        if crisis:
                            try:
                                alert_id = common.db.create_alert(
                                    student_name=student_name,
                                    student_class=student_class,
                                    risk_level="high",
                                    emotion_type="危机",
                                    intensity=10,
                                    description="数字人对话中识别到自伤/危机信号：{}".format(content[:200]),
                                    assigned_to=counselor_id,
                                    student_id=student_id,
                                )
                                alert = common.db.get_alert(alert_id)
                                common.emit_alert_created(alert)
                            except Exception as alert_exc:
                                logger.warning("数字人危机预警生成失败: %s", alert_exc)
                        reply_msg = common.db.get_message(reply_id)
                        if reply_msg:
                            common.emit_conversation_message(reply_msg)
                    except Exception as exc:
                        logger.warning("数字人自动回复生成失败: %s", exc)

                threading.Thread(target=_deliver_assistant_reply, daemon=True).start()
        except Exception as exc:
            logger.warning("数字人离线状态判断失败: %s", exc)

    return jsonify({
        "success": True,
        "data": {"id": msg_id, "ai_reply_pending": ai_reply_pending},
    }), 200


@api.route("/digital-human/settings", methods=["GET"])
@role_required(["counselor"])
def get_digital_human_settings():
    """获取当前辅导员的 AI 数字人设置。"""
    try:
        settings = common.db.get_digital_human_settings(g.user_id)
        return jsonify({"success": True, "data": settings}), 200
    except Exception as exc:
        logger.error("获取数字人设置失败: %s", exc)
        return jsonify({"success": False, "message": "获取数字人设置失败"}), 500


@api.route("/digital-human/settings", methods=["PUT"])
@role_required(["counselor"])
def update_digital_human_settings():
    """保存当前辅导员的 AI 数字人设置。"""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"success": False, "message": "请提供设置数据"}), 400
    try:
        settings = common.db.save_digital_human_settings(g.user_id, data)
        return jsonify({"success": True, "data": settings}), 200
    except Exception as exc:
        logger.error("保存数字人设置失败: %s", exc)
        return jsonify({"success": False, "message": "保存数字人设置失败"}), 500


@api.route("/digital-human/logs", methods=["GET"])
@role_required(["counselor"])
def get_digital_human_logs():
    """获取当前辅导员的数字人值班日志。"""
    try:
        status = request.args.get("status")
        logs = common.db.get_digital_human_logs(g.user_id, status=status)
        return jsonify({"success": True, "data": logs}), 200
    except Exception as exc:
        logger.error("获取数字人日志失败: %s", exc)
        return jsonify({"success": False, "message": "获取数字人日志失败"}), 500


@api.route("/digital-human/logs/<int:log_id>/handle", methods=["PUT"])
@role_required(["counselor"])
@log_action("处理数字人值班日志")
def handle_digital_human_log(log_id):
    """老师上线后将一条数字人自动回复标记为已处理。"""
    data = request.get_json(silent=True) or {}
    try:
        updated = common.db.mark_digital_human_log_handled(log_id, g.user_id, data.get("note"))
        if updated is None:
            return jsonify({"success": False, "message": "日志不存在或无权处理"}), 404
        return jsonify({"success": True, "message": "已标记处理", "data": updated}), 200
    except Exception as exc:
        logger.error("处理数字人值班日志失败: %s", exc)
        return jsonify({"success": False, "message": "操作失败，请稍后重试"}), 500


@api.route("/digital-human/preview", methods=["POST"])
@role_required(["counselor"])
def preview_digital_human():
    """在教师端试聊页面生成数字人回复。"""
    data = request.get_json(silent=True)
    if not data or not (data.get("message") or "").strip():
        return jsonify({"success": False, "message": "请输入试聊内容"}), 400
    try:
        settings = common.db.get_digital_human_settings(g.user_id)
        student_name = "同学"
        reply, crisis = generate_reply(data["message"], settings, student_name)
        return jsonify({
            "success": True,
            "data": {"reply": reply, "crisis": crisis},
        }), 200
    except Exception as exc:
        logger.error("数字人试聊失败: %s", exc)
        return jsonify({"success": False, "message": "数字人试聊失败"}), 500


@api.route("/digital-human/status/<int:counselor_id>", methods=["GET"])
@auth_required
def get_digital_human_status(counselor_id):
    """获取指定辅导员在线状态与 AI 数字人状态。"""
    try:
        presence = common.db.get_user_presence(counselor_id)
        settings = common.db.get_digital_human_settings(counselor_id)
        return jsonify({
            "success": True,
            "data": digital_human_status(presence, settings),
        }), 200
    except Exception as exc:
        logger.error("获取数字人状态失败: %s", exc)
        return jsonify({"success": False, "message": "获取数字人状态失败"}), 500


@api.route("/presence/ping", methods=["POST"])
@role_required(["counselor"])
def presence_ping():
    """刷新辅导员在线心跳。"""
    try:
        common.db.ping_user_presence(g.user_id, True)
        return jsonify({
            "success": True,
            "data": {"online": True, "user_id": g.user_id},
        }), 200
    except Exception as exc:
        logger.error("在线心跳刷新失败: %s", exc)
        return jsonify({"success": False, "message": "在线状态更新失败"}), 500


@api.route("/messages/unread", methods=["GET"])
@auth_required
def get_unread_count():
    """获取未读消息数量"""
    user_type = getattr(g, "user_type", "staff")
    if user_type == "student":
        user_id = g.student_id
    else:
        user_id = g.user_id

    count = common.db.get_unread_count(user_id, user_type)

    return jsonify({
        "success": True,
        "data": {"unread_count": count},
    }), 200


@api.route("/messages/analyze-emotion", methods=["POST"])
@auth_required
def analyze_message_emotion():
    """分析消息文字中的情绪（核心功能：文字情绪检测）"""
    data = request.get_json(silent=True)
    if not data or not data.get("text"):
        return jsonify({"success": False, "message": "请提供要分析的文本"}), 400

    text = data["text"].strip()
    if len(text) < 2:
        return jsonify({"success": True, "data": {"emotion": "正常", "risk": "low", "intensity": 1}}), 200

    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        # 本地关键词匹配作为后备
        return jsonify({"success": True, "data": _local_text_emotion(text)}), 200

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        system_prompt = (
            'You are a mental health emotion analysis expert. Analyze the text emotion '
            'and return strictly as JSON: {"emotion":"type","risk":"low/medium/high",'
            '"intensity":1-10,"keywords":["word1"],"suggestion":"brief advice"}. '
            'Emotion types: neutral,happy,down,anxious,irritated,depressed,angry,fearful,sad,nervous.'
        )
        resp = client.chat.completions.create(
            model="qwen-turbo",
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": text}],
            max_tokens=200, temperature=0.1
        )
        result_text = resp.choices[0].message.content.strip()
        import re, json
        match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            # Map English emotion names back to Chinese
            en_map = {"neutral":"正常","happy":"高兴","down":"低落","anxious":"焦虑",
                      "irritated":"烦躁","depressed":"压抑","angry":"愤怒",
                      "fearful":"恐惧","sad":"悲伤","nervous":"紧张"}
            if result.get("emotion","") in en_map:
                result["emotion"] = en_map[result["emotion"]]
        else:
            result = {"emotion": "正常", "risk": "low", "intensity": 1, "keywords": [], "suggestion": ""}
        return jsonify({"success": True, "data": result}), 200
    except Exception as e:
        logger.warning("文字情绪分析失败: %s", e)
        return jsonify({"success": True, "data": _local_text_emotion(text)}), 200


def _local_text_emotion(text):
    """本地关键词情绪分析（无需API）"""
    keywords = {
        "焦虑": ["焦虑", "担心", "紧张", "不安", "压力", "崩溃", "受不了"],
        "悲伤": ["难过", "伤心", "哭了", "失去", "痛苦", "绝望", "想死", "自杀"],
        "愤怒": ["生气", "愤怒", "讨厌", "恨", "不公平", "凭什么", "滚"],
        "恐惧": ["害怕", "恐惧", "恐怖", "吓", "噩梦", "不敢"],
        "压抑": ["压抑", "憋着", "没人理解", "孤独", "寂寞", "一个人"],
        "低落": ["低落", "没意思", "无聊", "懒得", "不想动", "好累", "没劲"],
        "高兴": ["开心", "高兴", "哈哈", "太好了", "棒", "喜欢", "谢谢老师"],
        "正常": ["好的", "收到", "知道", "嗯", "谢谢"],
    }
    scores = {}
    for emotion, words in keywords.items():
        score = sum(1 for w in words if w in text)
        if score > 0:
            scores[emotion] = score
    if not scores:
        return {"emotion": "正常", "risk": "low", "intensity": 1, "keywords": [], "suggestion": ""}
    top = max(scores, key=scores.get)
    risk = "high" if top in ("悲伤","恐惧","压抑") and scores[top] >= 2 else ("medium" if top in ("焦虑","愤怒","低落") else "low")
    intensity = min(10, scores[top] * 3 + 2)
    return {"emotion": top, "risk": risk, "intensity": intensity, "keywords": [], "suggestion": "建议关注学生情绪状态" if risk != "low" else ""}



# 心理专家级话术推荐：话术分类元信息（icon/颜色/定位）
GUIDANCE_CATEGORY_META = [
    {"type": "共情安抚", "icon": "💗", "color": "#ec4899",
     "description": "先接住情绪，让学生感到被理解、被看见"},
    {"type": "开放式提问", "icon": "❓", "color": "#3b82f6",
     "description": "用开放式问题引导倾诉，避免「是/否」式封闭回答"},
    {"type": "积极引导", "icon": "🌱", "color": "#10b981",
     "description": "从积极视角重构问题，激发学生自身力量"},
    {"type": "资源支持", "icon": "🤝", "color": "#8b5cf6",
     "description": "提供具体、可获得的资源与行动路径"},
    {"type": "危机干预", "icon": "🚨", "color": "#ef4444",
     "description": "高风险情境下的安全确认与即时干预"},
]

# 各情绪类型的关键词，用于本地兜底话术生成（无 API Key 时）
GUIDANCE_EMOTION_KEYWORDS = {
    "悲伤": ["难过", "伤心", "哭", "失去", "痛苦", "绝望", "想死", "自杀", "活不下去", "没意思"],
    "焦虑": ["焦虑", "担心", "紧张", "不安", "压力", "崩溃", "受不了", "害怕考", "挂科"],
    "愤怒": ["生气", "愤怒", "讨厌", "恨", "不公平", "凭什么", "吵架", "闹矛盾"],
    "恐惧": ["害怕", "恐惧", "噩梦", "不敢", "吓"],
    "压抑": ["压抑", "憋着", "没人理解", "孤独", "寂寞", "一个人", "提不起兴趣"],
    "低落": ["低落", "无聊", "懒得", "不想动", "好累", "没劲", "失眠", "睡不好"],
    "烦躁": ["烦", "烦躁", "受够", "吵", "打扰"],
    "紧张": ["紧张", "发抖", "心跳", "慌"],
    "高兴": ["开心", "高兴", "太好了", "棒", "喜欢", "谢谢老师"],
}

# 兜底话术库：key = 情绪，value = 5 类话术各 1~2 条
GUIDANCE_FALLBACK_SCRIPTS = {
    "共情安抚": {
        "default": [
            "我能感受到你现在很不容易，谢谢你愿意把这些告诉我。",
            "换作是我处在你这个位置，可能也会有类似的感受，这很正常。",
        ],
        "悲伤": ["听起来你心里积压了很多委屈和难过，能说出来真的很勇敢。", "你不是一个人在面对，我在这里陪着你。"],
        "焦虑": ["压力这么大，会焦虑是很自然的反应，我们先一起把它拆开看看。", "先别急着逼自己，一步一步来，你已经做得很好了。"],
        "愤怒": ["我能理解你的生气，这种情绪本身没有错，我们先别被它带着走。", "谢谢你没有憋在心里，而是选择说出来。"],
        "恐惧": ["害怕是身体在保护你，我们一起看看这份恐惧背后是什么。", "不用一个人扛，说出来会轻松一些。"],
        "压抑": ["你承受的比表面看到的多得多，辛苦你了。", "能感到孤独和压抑，恰恰说明你很在意，也很敏感。"],
        "低落": ["最近一定很累吧，允许自己慢下来，这不丢人。", "状态不好没关系，我们一点点来。"],
        "烦躁": ["最近是不是有什么事情一直让你心里堵得慌？", "烦躁背后通常藏着某种没被满足的需要，我们聊聊。"],
        "紧张": ["紧张说明你在乎这件事，这是好事。", "深呼吸，我们慢慢说，不着急。"],
    },
    "开放式提问": {
        "default": [
            "能和我说说，最近是什么时候开始有这种感觉的吗？",
            "如果用一个词形容现在的状态，你会想到什么？",
        ],
        "悲伤": ["这种难过的感觉，一般在什么情况下会特别强烈？", "你希望身边的人怎么帮你，才会感觉好一点？"],
        "焦虑": ["如果把这个压力分成十份，你觉得最让你喘不过气的是哪一部分？", "过去有没有哪次，你成功扛过类似的情况？"],
        "愤怒": ["这件事里，最让你接受不了的是哪一点？", "如果对方现在就在你面前，你最想对他说什么？"],
        "恐惧": ["你害怕的具体是什么？是结果，还是过程中的某个环节？", "如果最坏的情况发生了，你觉得自己能承受吗？"],
        "压抑": ["你感觉最不被理解的地方是什么？", "有没有一个人，是你愿意多说两句的？"],
        "低落": ["这种提不起劲的状态，持续了多久了？", "有没有哪一刻，你觉得自己稍微轻松了一点？"],
        "烦躁": ["最近哪件事最让你心烦？", "你觉得是什么让这种烦躁感一直消不掉？"],
        "紧张": ["你紧张的具体是什么场合？", "如果紧张程度从 1 到 10，你给自己打几分？"],
    },
    "积极引导": {
        "default": [
            "其实你已经迈出了求助这一步，这本身就是一种力量。",
            "我们先把能控制的事做好，剩下的交给时间。",
        ],
        "悲伤": ["你愿意说出来，说明你内心依然渴望被理解、渴望变好。", "难过会过去的，但这段时间我会一直支持你。"],
        "焦虑": ["你担心，说明你有责任心、想把事情做好，这是你的优点。", "把大目标切成小步，每完成一步都是进步。"],
        "愤怒": ["能把情绪说出来而不是憋着或爆发，你已经在用更成熟的方式处理了。", "你的底线和感受值得被尊重。"],
        "恐惧": ["恐惧的反面不是勇敢，而是行动。我们找一个最小的第一步试试。", "你已经面对了很多人会选择逃避的事，这很了不起。"],
        "压抑": ["你比你以为的更有韧性，能走到现在就是证明。", "表达出来的那一刻，你就已经在治愈自己了。"],
        "低落": ["情绪有起伏是正常的，低谷里也能慢慢积攒力气。", "今天能来和我说这些，本身就是一件值得肯定的事。"],
        "烦躁": ["你能敏锐地察觉到自己的烦躁，这是自我觉察的第一步。", "把烦躁的事一件件理清，你会发现没想象中那么难。"],
        "紧张": ["适度的紧张能帮你发挥得更好，关键是别让它失控。", "你已经准备了，剩下的就是相信自己。"],
    },
    "资源支持": {
        "default": [
            "学校心理中心有专业咨询师，我可以帮你预约，全程保密。",
            "这个学期学习上有困难，我可以帮你联系学习委员或学长学姐。",
        ],
        "悲伤": ["我建议你近期去心理中心找专业老师聊聊，我可以陪你去。", "如果需要，我可以和你的任课老师沟通，适当调整学习节奏。"],
        "焦虑": ["关于这门课，我帮你约一下任课老师，梳理一下重点。", "学校有学业辅导小组，我帮你对接一个。"],
        "愤怒": ["如果涉及人际冲突，我可以先和对方/室友聊聊，帮你协调。", "需要的话我们可以一起定个规则或方案，把问题解决掉。"],
        "恐惧": ["心理中心的老师处理过很多类似的情况，经验很丰富。", "我会在接下来的时间里多关注你的状态，你随时可以来找我。"],
        "压抑": ["心理中心的咨询完全保密，你可以放心去聊。", "多参加一点集体活动，我可以帮你推荐适合的社团。"],
        "低落": ["睡眠和饮食如果持续不好，我陪你去校医院看看。", "心理中心的咨询时段我可以帮你优先预约。"],
        "烦躁": ["把烦心事列出来，我们一起分个优先级，一件件处理。", "如果环境太吵影响你，我可以帮你协调宿舍或自习空间。"],
        "紧张": ["我可以帮你做一些放松训练，或者推荐你听一些减压音频。", "考前我们可以约一次模拟，帮你熟悉流程降低紧张。"],
    },
    "危机干预": {
        "default": [
            "我很担心你的安全，我们先确保你现在是安全的，好吗？",
            "你现在的感受非常重要，我会一直陪着你，不会让你一个人面对。",
        ],
        "悲伤": ["关于你提到的伤害自己的想法，我需要确认一下：你现在安全吗？", "我们先不谈别的，先确认你此刻是安全的，这比什么都重要。"],
        "恐惧": ["如果你感到非常害怕或难以承受，我们一起去心理中心找专业老师，现在就可以。"],
        "压抑": ["你一个人扛了这么久，我很心疼。接下来的事我们一起来想办法，好吗？"],
    },
}


def _local_guidance(conversation_text, student_name="学生"):
    """本地兜底话术生成：基于情绪关键词，产出多类型心理专家级话术（无需 API）。"""
    emotion = "default"
    best_score = 0
    for emo, words in GUIDANCE_EMOTION_KEYWORDS.items():
        score = sum(1 for w in words if w in conversation_text)
        if score > best_score:
            best_score = score
            emotion = emo
    if best_score == 0:
        emotion = "default"

    emo_label = "正常" if emotion == "default" else emotion
    # 情绪评估一句话
    assessment_map = {
        "悲伤": f"从对话看，{student_name} 情绪偏低落，可能存在悲伤或无助的感受，需优先共情与安全确认。",
        "焦虑": f"从对话看，{student_name} 表现出明显的焦虑与压力，需先缓解紧张、再逐层拆解压力来源。",
        "愤怒": f"从对话看，{student_name} 有较强的愤怒或不公平感，需先承接情绪、再引导理性表达。",
        "恐惧": f"从对话看，{student_name} 存在恐惧或回避情绪，需营造安全感、逐步澄清恐惧对象。",
        "压抑": f"从对话看，{student_name} 情绪较为压抑，可能长期独自承受，需耐心引导其表达。",
        "低落": f"从对话看，{student_name} 状态偏低落、动力不足，需温和陪伴并关注睡眠饮食。",
        "烦躁": f"从对话看，{student_name} 有些烦躁不安，需帮助其梳理具体困扰。",
        "紧张": f"从对话看，{student_name} 较为紧张，需通过放松与具体化降低紧张感。",
        "default": f"从对话看，{student_name} 整体状态尚可，可正常沟通并给予适度支持。",
    }

    categories = []
    tips = []
    high_risk = emotion in ("悲伤", "恐惧") and any(
        w in conversation_text for w in ["想死", "自杀", "活不下去", "伤害自己"]
    )
    for meta in GUIDANCE_CATEGORY_META:
        ctype = meta["type"]
        scripts = GUIDANCE_FALLBACK_SCRIPTS[ctype]
        # 危机干预仅在高风险时展示
        if ctype == "危机干预" and not high_risk:
            continue
        pool = scripts.get(emotion) or scripts.get("default") or []
        if not pool:
            continue
        categories.append({
            "type": ctype,
            "icon": meta["icon"],
            "color": meta["color"],
            "description": meta["description"],
            "scripts": pool,
        })
        tips.extend(pool[:1])

    return {
        "emotion_assessment": assessment_map.get(emotion, assessment_map["default"]),
        "risk_alert": "建议预警" if high_risk else ("建议关注" if emotion in ("悲伤", "焦虑", "压抑", "恐惧") else "无风险"),
        "categories": categories,
        "communication_tips": tips[:3] if tips else ["先倾听学生的感受，再逐步引导。"],
        "counseling_plan": "先建立信任与安全感，通过共情稳定情绪；再开放式提问澄清问题；最后结合资源支持给出可执行建议。",
        "source": "local",
    }


@api.route("/messages/counselor-guidance", methods=["POST"])
@auth_required
def counselor_guidance():
    """AI辅导助手：分析学生对话，输出多类型心理专家级沟通话术（可点击填入聊天框）。"""
    data = request.get_json(silent=True)
    if not data or not data.get("messages"):
        return jsonify({"success": False, "message": "请提供对话内容"}), 400

    messages = data["messages"]
    student_name = data.get("student_name", "学生")
    conversation_text = "\n".join([
        ("学生" if m.get("sender_type") == "student" else "老师") + "：" + m.get("content", "")
        for m in messages[-10:]  # 最近10条
    ])

    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        return jsonify({"success": True, "data": _local_guidance(conversation_text, student_name)}), 200

    # 构建分类话术的输出说明，供模型严格遵循
    category_spec = "、".join([
        '{"type":"%s","icon":"%s","scripts":["可直接发送的话术1","话术2","话术3"]}'
        % (m["type"], m["icon"]) for m in GUIDANCE_CATEGORY_META
    ])

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        prompt = (
            f"你是高校心理辅导专家。以下是辅导员与{student_name}的对话记录，请分析并给出可落地的辅导话术。\n\n"
            f"对话记录：\n{conversation_text}\n\n"
            f"请严格返回 JSON（不要输出任何多余文字）：\n"
            f'{{\n'
            f'  "emotion_assessment":"学生当前情绪评估（1-2句话）",\n'
            f'  "risk_alert":"无风险 / 建议关注 / 建议预警（三选一）",\n'
            f'  "categories":[\n'
            f'    {category_spec}\n'
            f'  ]\n'
            f'}}\n\n'
            f"要求：\n"
            f"1. categories 必须包含上述 5 个分类，每个分类 2~4 条「可直接发送」的话术；\n"
            f"2. 话术要具体、温和、专业，符合心理咨询伦理，避免说教与评判；\n"
            f"3. 若学生无自伤/自杀风险，「危机干预」分类改为安全与支持性话术。"
        )
        resp = client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200, temperature=0.4
        )
        result_text = resp.choices[0].message.content.strip()
        import re, json
        match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if not match:
            return jsonify({"success": True, "data": _local_guidance(conversation_text, student_name)}), 200
        result = json.loads(match.group())
        # 归一化：补齐分类元信息 icon/color，并把 scripts 洗成列表
        meta_by_type = {m["type"]: m for m in GUIDANCE_CATEGORY_META}
        categories = []
        for cat in result.get("categories", []) or []:
            if not isinstance(cat, dict):
                continue
            ctype = cat.get("type", "")
            scripts = cat.get("scripts", [])
            if isinstance(scripts, str):
                scripts = [scripts]
            scripts = [str(s).strip() for s in scripts if str(s).strip()]
            if not ctype or not scripts:
                continue
            meta = meta_by_type.get(ctype, {})
            categories.append({
                "type": ctype,
                "icon": cat.get("icon") or meta.get("icon", "💬"),
                "color": meta.get("color", "#6366f1"),
                "description": meta.get("description", ""),
                "scripts": scripts,
            })
        tips = []
        for cat in categories:
            tips.extend(cat["scripts"][:1])
        if not categories:
            # 模型返回异常时兜底
            return jsonify({"success": True, "data": _local_guidance(conversation_text, student_name)}), 200
        result["categories"] = categories
        result["communication_tips"] = result.get("communication_tips") or tips[:3]
        result["counseling_plan"] = result.get("counseling_plan") or "先共情稳定情绪，再开放式提问澄清，最后给出资源支持与可执行建议。"
        result["source"] = "ai"
        return jsonify({"success": True, "data": result}), 200
    except Exception as e:
        logger.error("辅导分析失败: %s", e)
        return jsonify({"success": True, "data": _local_guidance(conversation_text, student_name)}), 200


def _generate_report_local(conversation_text, student_name, topic):
    """本地兜底：基于情绪关键词生成结构化谈心记录（无需 API）。"""
    emo_result = _local_text_emotion(conversation_text)
    emo = emo_result.get("emotion", "正常")
    risk = emo_result.get("risk", "low")
    student_lines = [l for l in conversation_text.split("\n") if l.startswith("学生：")]
    points = student_lines[-5:] or ["（暂无学生发言记录）"]
    summary = (
        f"# 谈心记录\n\n"
        f"- 学生：{student_name}\n"
        f"- 主题：{topic}\n"
        f"- 时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"## 一、情绪评估\n{student_name} 当前情绪偏向「{emo}」，综合风险等级为「{risk}」。\n\n"
        f"## 二、学生反馈要点\n" + "\n".join(f"- {p.replace('学生：', '')}" for p in points) + "\n\n"
        f"## 三、沟通策略\n- 先共情稳定情绪，再开放式提问澄清，最后给予资源支持。\n\n"
        f"## 四、后续跟进\n- 根据风险等级安排复查（高风险 3 日内、中风险 7 日内）。\n"
    )
    return {
        "summary": summary,
        "emotion_tags": {"primary": emo, "risk": risk},
        "risk_level": "high" if risk == "high" else "medium" if risk == "medium" else "low",
    }


def _generate_report(conversation_text, student_name, topic):
    """生成结构化谈心记录报告：优先 LLM，失败/无 Key 时本地兜底。"""
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        return _generate_report_local(conversation_text, student_name, topic)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        prompt = (
            f"你是高校辅导员，请把以下与学生「{student_name}」的谈心对话整理成一份结构化谈心记录（Markdown 格式）。\n\n"
            f"对话主题：{topic}\n\n"
            f"对话记录：\n{conversation_text}\n\n"
            f"请按以下结构输出：\n"
            f"# 谈心记录\n"
            f"- 学生 / 主题 / 时间\n"
            f"## 一、情绪评估\n## 二、学生反馈要点\n## 三、沟通策略\n## 四、后续跟进\n"
            f"要求：客观、简洁、可归档，符合心理辅导伦理，避免评判性语言。"
        )
        resp = client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=900, temperature=0.4,
        )
        summary = resp.choices[0].message.content.strip() or _generate_report_local(conversation_text, student_name, topic)["summary"]
        emo_result = _local_text_emotion(conversation_text)
        return {
            "summary": summary,
            "emotion_tags": {"primary": emo_result.get("emotion", "正常"), "risk": emo_result.get("risk", "low")},
            "risk_level": "high" if emo_result.get("risk") == "high" else "medium" if emo_result.get("risk") == "medium" else "low",
        }
    except Exception as exc:
        logger.warning("报告生成调用 LLM 失败，使用本地兜底: %s", exc)
        return _generate_report_local(conversation_text, student_name, topic)


@api.route("/conversation/generate-report", methods=["POST"])
@auth_required
@log_action("生成谈心记录报告")
def generate_conversation_report():
    """一键生成结构化谈心记录报告，并沉淀到学生档案（StudentProfile）。"""
    data = request.get_json(silent=True) or {}
    student_id = data.get("student_id")  # Student.id
    messages = data.get("messages") or []
    topic = (data.get("topic") or "").strip() or "日常谈心"
    student_name = data.get("student_name") or "学生"

    if not student_id:
        return jsonify({"success": False, "message": "缺少学生信息"}), 400

    conversation_text = "\n".join([
        ("学生" if m.get("sender_type") == "student" else "老师") + "：" + m.get("content", "")
        for m in messages[-30:]
    ])
    if not conversation_text.strip():
        return jsonify({"success": False, "message": "暂无对话内容，无法生成记录"}), 400

    report = _generate_report(conversation_text, student_name, topic)

    # 保存到学生档案
    profile_id = None
    try:
        counselor_id = g.user_id if getattr(g, "user_type", "staff") != "student" else None
        profile_id = common.db.create_student_profile(
            student_id=student_id,
            counselor_id=counselor_id,
            record_type="talk_report",
            summary=report["summary"],
            structured_content=json.dumps(report, ensure_ascii=False),
            emotion_tags=report.get("emotion_tags"),
            risk_level=report.get("risk_level", "low"),
            counselor_impression="AI 辅助生成，建议辅导员复核补充。",
        )
        emotion_tags = report.get("emotion_tags") or {}
        emotion_status = ""
        if isinstance(emotion_tags, dict):
            emotion_status = emotion_tags.get("primary") or emotion_tags.get("emotion") or ""
        common.db.update_student_state_from_evidence(
            student_id=student_id,
            risk_level=report.get("risk_level", "low"),
            emotion_status=emotion_status,
            source="talk_report",
            counselor_id=counselor_id,
            description="谈心记录已生成，请复核学生当前风险状态。",
        )
    except Exception as exc:
        logger.error("谈心记录保存失败: %s", exc)

    return jsonify({
        "success": True,
        "data": {
            "profile_id": profile_id,
            "report": report,
            "student_name": student_name,
            "topic": topic,
        },
    }), 200
