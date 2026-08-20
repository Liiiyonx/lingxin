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
# 2. 会话管理路由 (Conversation Routes)
# ===================================================================

@api.route("/conversation/organize", methods=["POST"])
@auth_required
@log_action("整理会话记录")
def organize_conversation():
    """将原始会话内容整理为结构化记录。"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请提供原始会话内容"}), 400

    raw_content = data.get("content") or data.get("raw_content")
    if not raw_content:
        return jsonify({"success": False, "message": "会话内容不能为空"}), 400

    scene = data.get("scene", "谈心记录")

    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        return jsonify({"success": False, "message": "API密钥未配置"}), 500

    scene_prompts = {
        "谈心记录": """你是一位资深高校辅导员助手。请将以下对话内容整理为标准的谈心谈话记录。

请严格按照以下格式输出（使用Markdown格式）：

## 谈心谈话记录

| 项目 | 内容 |
|------|------|
| **时间** | （根据内容推断合理时间） |
| **地点** | （根据内容推断） |
| **谈话人** | （辅导员姓名，可写XXX） |
| **谈话对象** | （学生姓名，可写XXX） |
| **谈话主题** | （提炼核心主题） |

### 一、谈话背景
（简要说明谈话的起因和背景）

### 二、谈话主要内容
（用问答形式整理对话要点，条理清晰）

### 三、学生思想与情绪状态评估
（根据对话判断学生的心理状态、情绪变化）

### 四、发现的主要问题
- （问题1）
- （问题2）

### 五、后续跟进措施
- （具体措施1，含时间节点）
- （具体措施2，含时间节点）
- （具体措施3）

请确保内容真实客观，语言专业温和。""",

        "班会策划": """你是一位经验丰富的高校辅导员，请根据主题策划一次主题班会方案。

请严格按照以下格式输出（使用Markdown格式）：

# 主题班会策划方案

## 一、班会基本信息

| 项目 | 内容 |
|------|------|
| **班会主题** | （根据用户输入确定） |
| **班会时间** | 建议45-60分钟 |
| **班会地点** | XX教室 |
| **参加人员** | XX学院XX级全体学生 |
| **主持人** | XXX（辅导员/学生干部） |

## 二、班会目标

1. **知识目标**：（学生应了解的知识点）
2. **能力目标**：（学生应提升的能力）
3. **情感目标**：（学生应形成的态度和价值观）

## 三、班会准备

1. 前期准备：
   - （准备工作1）
   - （准备工作2）
2. 所需材料：
   - （材料清单）
3. 人员分工：
   - （分工安排）

## 四、班会流程

### 第一环节：导入（约5分钟）
- 具体内容和方式

### 第二环节：主体活动（约30分钟）
- 活动一：（名称）
  - 目的、方式、时间
- 活动二：（名称）
  - 目的、方式、时间

### 第三环节：讨论分享（约10分钟）
- 讨论题目和分享方式

### 第四环节：总结升华（约5分钟）
- 辅导员总结要点

## 五、预期效果

（描述预期达到的教育效果）

## 六、注意事项

1. （注意事项1）
2. （注意事项2）
3. （注意事项3）

请确保方案具有可操作性，活动设计贴近学生实际。""",

        "公文写作": """你是高校行政公文写作助手。请按照GB/T 9704国家标准格式起草公文。

请严格按照以下格式输出（使用Markdown格式）：

# 关于XXXX的通知

各学院、各部门：

## 一、背景与目的
（说明发文背景和目的）

## 二、工作安排

### （一）时间安排
- （时间节点1）
- （时间节点2）

### （二）工作内容
1. （内容1）
2. （内容2）

### （三）具体要求
1. （要求1）
2. （要求2）

## 三、联系方式

联系人：XXX
联系电话：XXX
邮箱：XXX

---

**XX大学学生工作处**
**2024年X月X日**

请确保用语准确、简洁、庄重，符合行政公文规范。""",

        "情绪分析": """你是专业的心理咨询分析助手。请分析以下文本中的情绪状态。

请严格按照以下格式输出（使用Markdown格式）：

## 情绪分析报告

### 一、情绪识别

| 情绪类型 | 强度 | 依据 |
|----------|------|------|
| （主要情绪） | 高/中/低 | （文本中的具体表达） |
| （次要情绪） | 高/中/低 | （文本中的具体表达） |

### 二、关键风险信号
- （信号1：具体文本片段）
- （信号2：具体文本片段）

### 三、风险评估
- **风险等级**：高/中/低
- **判断依据**：（具体说明）
- **是否需要启动危机干预**：是/否

### 四、建议措施
1. （辅导员应采取的具体行动1）
2. （辅导员应采取的具体行动2）
3. （辅导员应采取的具体行动3）

### 五、后续关注要点
- （需要持续观察的方面）

请保持专业、客观、温和的分析态度。""",

        "请假审批": """你是高校学工处处理助手，负责协助辅导员处理学生请假审批。

请严格按照以下格式输出（使用Markdown格式）：

## 请假审批意见

### 一、学生信息
| 项目 | 内容 |
|------|------|
| **姓名** | XXX |
| **班级** | XX学院XX班 |
| **请假类型** | 事假/病假/公假 |
| **请假时间** | X月X日至X月X日（共X天） |

### 二、请假理由
（根据学生描述整理）

### 三、审批建议
- **建议结果**：批准/暂缓/不予批准
- **审批理由**：（具体说明）

### 四、注意事项
1. （提醒事项1）
2. （提醒事项2）
3. （相关跟进安排）

请根据学校规定给出合理建议。""",
    }

    system_msg = scene_prompts.get(scene, "你是高校辅导员助手。请整理以下内容。")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        resp = client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": raw_content}
            ],
            temperature=0.7,
            max_tokens=3000
        )
        result = resp.choices[0].message.content
        return jsonify({"success": True, "message": "整理完成", "content": result}), 200
    except Exception as exc:
        logger.error("整理失败: %s", exc)
        return jsonify({"success": False, "message": "整理失败: " + "内部错误，请稍后重试"}), 500



@api.route("/conversation/recognize-image", methods=["POST"])
@auth_required
def recognize_image():
    """识别聊天记录截图，提取对话内容并整理为谈心记录。"""
    if "image" not in request.files:
        return jsonify({"success": False, "message": "请上传图片"}), 400

    image_file = request.files["image"]
    if not image_file.filename:
        return jsonify({"success": False, "message": "文件名为空"}), 400

    allowed_ext = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    ext = os.path.splitext(image_file.filename)[1].lower()
    if ext not in allowed_ext:
        return jsonify({"success": False, "message": "仅支持jpg/png/gif/webp格式"}), 400

    try:
        # Read image and convert to base64
        import base64
        image_bytes = image_file.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        # Determine MIME type
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                     ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}
        mime_type = mime_map.get(ext, "image/jpeg")

        api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        if not api_key:
            return jsonify({"success": False, "message": "API密钥未配置"}), 500

        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")

        # Use qwen-vl-plus for image recognition
        resp = client.chat.completions.create(
            model="qwen-vl-plus",
            messages=[
                {
                    "role": "system",
                    "content": """你是一位高校辅导员助手。请完成以下两步：

第一步：识别图片中的聊天记录，提取出所有对话内容，按照“发言人：内容”的格式整理。

第二步：将识别出的对话内容整理为标准的谈心谈话记录格式：

## 谈心谈话记录

| 项目 | 内容 |
|------|------|
| **时间** | 根据图片中的时间戳填写 |
| **地点** | 根据内容推断 |
| **谈话人** | 辅导员 |
| **谈话对象** | 学生姓名 |
| **谈话主题** | 提炼核心主题 |

### 一、谈话背景
(简要说明谈话起因)

### 二、谈话主要内容
(用问答形式整理对话要点)

### 三、学生思想与情绪状态评估
(根据对话判断学生心理状态)

### 四、发现的主要问题
- (问题1)
- (问题2)

### 五、后续跟进措施
- (具体措施1，含时间节点)
- (具体措施2)

如果图片中的内容不是聊天记录，则说明图片内容并尝试了解其含义。"""
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}
                        },
                        {"type": "text", "text": "请识别这张聊天记录截图，提取对话内容并整理为标准的谈心谈话记录。"}
                    ]
                }
            ],
            max_tokens=3000
        )

        result = resp.choices[0].message.content
        return jsonify({"success": True, "message": "图片识别完成", "content": result}), 200

    except Exception as exc:
        logger.error("图片识别失败: %s", exc)
        return jsonify({"success": False, "message": "图片识别失败: " + "内部错误，请稍后重试"}), 500


@api.route("/conversation/upload-document", methods=["POST"])
@auth_required
@log_action("上传文档识别")
def upload_document():
    """上传文档（PDF/Word/文本等），提取内容并用AI整理为谈心记录。"""
    if "file" not in request.files:
        return jsonify({"success": False, "message": "请上传文件", "content": "请上传文件"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"success": False, "message": "文件名为空", "content": "文件名为空"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    allowed = {".pdf", ".doc", ".docx", ".txt", ".md", ".csv", ".xls", ".xlsx"}
    if ext not in allowed:
        return jsonify({"success": False, "message": f"不支持的文件格式: {ext}", "content": f"不支持的文件格式: {ext}，支持: {', '.join(allowed)}"}), 400

    try:
        content_text = ""
        if ext in (".txt", ".md", ".csv"):
            content_text = file.read().decode("utf-8", errors="ignore")
        elif ext == ".pdf":
            try:
                import pdfplumber
                with pdfplumber.open(file) as pdf:
                    for page in pdf.pages:
                        t = page.extract_text()
                        if t:
                            content_text += t + "\n"
            except ImportError:
                content_text = "[PDF文件已上传，但服务器未安装pdfplumber库]"
        elif ext in (".doc", ".docx"):
            try:
                import docx
                doc = docx.Document(file)
                content_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            except ImportError:
                content_text = "[Word文件已上传，但服务器未安装python-docx库]"
        elif ext in (".xls", ".xlsx"):
            content_text = "[Excel文件已上传]"
        else:
            content_text = file.read().decode("utf-8", errors="ignore")

        if not content_text.strip():
            content_text = f"[文件 {file.filename} 已上传，但未能提取到有效文本内容]"

        if len(content_text) > 5000:
            content_text = content_text[:5000] + "\n\n[内容已截断，共" + str(len(content_text)) + "字]"

        organized = ""
        api_key = config["llm"].DASHSCOPE_API_KEY
        if api_key and common.conversation_engine:
            try:
                reply = common.conversation_engine.chat(
                    scene="谈心记录",
                    user_message=f"以下是上传的文档内容（{file.filename}），请整理为谈心记录：\n\n{content_text}"
                )
                organized = reply
            except Exception as e:
                logger.warning("LLM organize failed: %s", e)

        if not organized:
            organized = f"## 文档内容摘要 - {file.filename}\n\n{content_text[:2000]}\n\n---\n*提示：配置API密钥后可AI自动整理为结构化谈心记录*"

        return jsonify({
            "success": True,
            "content": organized,
            "message": f"文档 {file.filename} 已识别",
            "filename": file.filename,
            "raw_content": content_text[:500],
        }), 200

    except Exception as exc:
        logger.error("upload_document error: %s", exc)
        return jsonify({"success": False, "message": f"文件处理失败: {exc}", "content": f"文件处理失败: {exc}"}), 500

@api.route("/conversation/list", methods=["GET"])
@auth_required
@log_action("查看会话列表")
def list_conversations():
    """分页获取会话列表，支持按学院、日期、状态等过滤。"""
    try:
        filters = {
            "college": request.args.get("college"),
            "status": request.args.get("status"),
            "date_from": request.args.get("date_from"),
            "date_to": request.args.get("date_to"),
            "student_name": request.args.get("student_name"),
        }
        filters = {k: v for k, v in filters.items() if v is not None}

        page = max(1, request.args.get("page", 1, type=int))
        per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))

        result = common.db.search_conversations(
            filters=filters,
            page=page,
            per_page=per_page,
            user_id=g.user_id,
            role=g.role,
        )

        return jsonify({
            "success": True,
            "data": result.get("items", []),
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": result.get("total", 0),
                "total_pages": result.get("total_pages", 0),
            },
        }), 200
    except Exception as exc:
        logger.error("获取会话列表失败: %s", exc)
        return jsonify({"success": False, "message": "获取会话列表失败"}), 500


@api.route("/conversation/<int:conversation_id>", methods=["GET"])
@auth_required
@log_action("查看会话详情")
def get_conversation(conversation_id):
    """获取单条会话的完整信息。"""
    try:
        conversation = common.db.get_conversation(conversation_id)
        if conversation is None:
            return jsonify({"success": False, "message": "会话记录不存在"}), 404
        return jsonify({"success": True, "data": conversation}), 200
    except Exception as exc:
        logger.error("获取会话详情失败: %s", exc)
        return jsonify({"success": False, "message": "获取会话详情失败"}), 500


@api.route("/conversation/<int:conversation_id>", methods=["PUT"])
@auth_required
@log_action("更新会话记录")
def update_conversation(conversation_id):
    """更新会话记录信息。"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请提供要更新的字段"}), 400

    allowed_fields = {
        "status", "summary", "notes", "tags",
        "risk_level", "follow_up_needed", "follow_up_date",
    }
    updates = {k: v for k, v in data.items() if k in allowed_fields and v is not None}

    if not updates:
        return jsonify({"success": False, "message": "没有可更新的字段"}), 400

    try:
        existing = common.db.get_conversation(conversation_id)
        if existing is None:
            return jsonify({"success": False, "message": "会话记录不存在"}), 404

        common.db.update_conversation(conversation_id, updates)
        return jsonify({"success": True, "message": "会话记录更新成功"}), 200
    except Exception as exc:
        logger.error("更新会话记录失败: %s", exc)
        return jsonify({"success": False, "message": "更新失败，请稍后重试"}), 500


@api.route("/conversation/<int:conversation_id>", methods=["DELETE"])
@auth_required
@log_action("删除会话记录")
def delete_conversation(conversation_id):
    """删除一条会话记录。"""
    try:
        existing = common.db.get_conversation(conversation_id)
        if existing is None:
            return jsonify({"success": False, "message": "会话记录不存在"}), 404

        common.db.delete_conversation(conversation_id)
        return jsonify({"success": True, "message": "会话记录已删除"}), 200
    except Exception as exc:
        logger.error("删除会话记录失败: %s", exc)
        return jsonify({"success": False, "message": "删除失败，请稍后重试"}), 500


@api.route("/conversation/batch-organize", methods=["POST"])
@auth_required
@log_action("批量整理会话")
def batch_organize():
    """批量将多条原始会话整理为结构化记录。"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请提供待整理的会话列表"}), 400

    conversations = data.get("conversations") or data.get("items")
    if not conversations or not isinstance(conversations, list):
        return jsonify({"success": False, "message": "会话列表不能为空"}), 400

    if len(conversations) > 50:
        return jsonify({"success": False, "message": "单次批量操作最多处理 50 条记录"}), 400

    results = []
    errors = []

    for idx, item in enumerate(conversations):
        raw_content = item.get("content") or item.get("raw_content")
        if not raw_content:
            errors.append({"index": idx, "message": "会话内容为空"})
            continue
        try:
            structured = common.conversation_engine.organize(
                raw_content=raw_content,
                student_name=item.get("student_name"),
                context=item.get("context"),
            )
            results.append({"index": idx, "data": structured, "status": "success"})
        except Exception as exc:
            errors.append({"index": idx, "message": "内部错误，请稍后重试"})

    return jsonify({
        "success": True,
        "message": "批量整理完成：成功 {} 条，失败 {} 条".format(len(results), len(errors)),
        "data": {
            "results": results,
            "errors": errors,
        },
    }), 200
