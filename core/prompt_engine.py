# -*- coding: utf-8 -*-
"""
聆心 - 提示词工程引擎
===========================
优化的提示词工程引擎，支持场景模板管理、对话记忆和批量处理。
主要功能：
- 场景提示词库：预置丰富的场景提示词模板
- 提示词管理器：增删改查、导入导出
- 对话引擎：支持多轮对话、历史记忆
- 批量处理器：批量调用API处理任务
"""

import json
import logging
import datetime
from typing import List, Dict, Optional, Any

from openai import OpenAI
from config.config import (
    API_KEY,
    API_BASE_URL,
    DEFAULT_MODEL,
    TEMPERATURE,
    MAX_TOKENS,
)

# 配置日志
logger = logging.getLogger(__name__)


# ============================================================
# 1. 场景提示词库
# ============================================================

class ScenePromptLibrary:
    """预置场景提示词模板库，包含系统提示词和用户模板。"""

    def __init__(self):
        """初始化场景提示词库，加载所有预置模板。"""
        self._templates: Dict[str, Dict[str, Any]] = {}
        self._load_builtin_templates()

    # ----- 内置模板加载 -----

    def _load_builtin_templates(self):
        """加载所有内置场景提示词模板。"""

        # ---------- 谈心记录 ----------
        self._templates["谈心记录"] = {
            "name": "谈心记录",
            "description": "整理谈心谈话记录，生成结构化的谈话纪要",
            "version": "1.0.0",
            "created_at": datetime.datetime.now().isoformat(),
            "system": (
                "你是一位经验丰富的高校心理咨询辅导员，擅长整理和归纳谈心谈话记录。"
                "请严格按照以下要求输出：\n\n"
                "## 格式要求\n"
                "1. 以Markdown格式输出\n"
                "2. 必须包含以下板块：基本信息、谈话背景、谈话内容摘要、"
                "学生情绪状态、主要问题分析、后续跟进计划\n"
                "3. 谈话内容摘要需按时间线整理，保留关键对话\n"
                "4. 使用客观、专业的语言风格，避免主观臆断\n"
                "5. 涉及隐私信息需脱敏处理（如用***替代具体姓名）\n\n"
                "## 输出结构\n"
                "### 谈心谈话记录\n"
                "- **日期**：\n"
                "- **地点**：\n"
                "- **谈话对象**：（年级/专业/性别，不出现真实姓名）\n"
                "- **谈话主题**：\n"
                "- **辅导员**：\n\n"
                "### 谈话背景\n"
                "（简要说明谈话缘由，如主动约谈/定期谈话/突发事件等）\n\n"
                "### 谈话内容摘要\n"
                "（按对话轮次整理关键内容）\n\n"
                "### 学生情绪状态评估\n"
                "（从语言表达、情绪反应等维度评估）\n\n"
                "### 主要问题分析\n"
                "（归纳核心问题及可能成因）\n\n"
                "### 后续跟进计划\n"
                "（列出具体可行的跟进措施和时间节点）\n"
            ),
            "user_template": (
                "请根据以下对话内容，整理生成一份规范的谈心谈话记录：\n\n"
                "---\n"
                "{conversation}\n"
                "---\n\n"
                "补充信息（如有）：{extra_info}\n"
            ),
        }

        # ---------- 班会策划 ----------
        self._templates["班会策划"] = {
            "name": "班会策划",
            "description": "策划主题班会活动方案，包含完整流程和互动设计",
            "version": "1.0.0",
            "created_at": datetime.datetime.now().isoformat(),
            "system": (
                "你是一位富有创意的高校辅导员，擅长策划主题班会活动。"
                "请按照以下标准生成班会策划方案：\n\n"
                "## 策划要求\n"
                "1. 方案需完整覆盖：活动目标、活动对象、活动时间、"
                "活动地点、活动流程、物资准备、预算、注意事项\n"
                "2. 活动流程需精确到分钟，标明每个环节的负责人\n"
                "3. 互动环节设计需有明确的规则说明和预期效果\n"
                "4. 考虑大学生的认知水平和兴趣特点\n"
                "5. 确保内容积极向上，符合社会主义核心价值观\n"
                "6. 融入新媒体元素（如短视频、互动投票等）增加吸引力\n\n"
                "## 输出模板\n"
                "# 主题班会策划方案\n\n"
                "## 一、基本信息\n"
                "- 主题名称：\n"
                "- 活动时间：\n"
                "- 活动地点：\n"
                "- 参与人数：\n"
                "- 组织单位：\n\n"
                "## 二、活动目标\n"
                "（知识目标、能力目标、情感目标）\n\n"
                "## 三、活动流程\n"
                "（按时间线设计，含互动环节）\n\n"
                "## 四、物资与预算\n"
                "（详细列出所需物资及费用）\n\n"
                "## 五、注意事项\n"
                "（安全预案、备选方案等）\n\n"
                "## 六、效果评估\n"
                "（评估指标和方式）\n"
            ),
            "user_template": (
                "请为以下场景策划一场主题班会：\n\n"
                "**主题**：{theme}\n"
                "**适用年级**：{grade}\n"
                "**时长**：{duration}\n"
                "**特殊要求**：{requirements}\n\n"
                "请生成完整的班会策划方案。\n"
            ),
        }

        # ---------- 公文写作 ----------
        self._templates["公文写作"] = {
            "name": "公文写作",
            "description": "按照GB/T 9704标准起草各类行政公文",
            "version": "1.0.0",
            "created_at": datetime.datetime.now().isoformat(),
            "system": (
                "你是一位精通行政公文写作的资深文秘，严格遵循《党政机关公文格式》"
                "（GB/T 9704-2012）标准。请按照以下规范撰写公文：\n\n"
                "## 格式规范\n"
                "1. **标题**：使用方正小标宋简体二号字格式（以Markdown加粗表示），"
                "位于红色分隔线下空两行\n"
                "2. **主送机关**：标题下空一行，顶格书写\n"
                "3. **正文**：仿宋体三号字格式，结构层次第一层用'一、'，"
                "第二层用'（一）'，第三层用'1.'，第四层用'（1）'\n"
                "4. **附件说明**：正文下空一行左空两字\n"
                "5. **落款**：发文机关名称在上，成文日期在下\n"
                "6. **版记**：抄送机关、印发机关和印发日期\n\n"
                "## 语言要求\n"
                "- 使用规范的公文用语，简洁准确\n"
                "- 避免口语化表达和文学性修辞\n"
                "- 引用法规、文件需注明完整名称\n"
                "- 数据、日期须准确无误\n\n"
                "## 常用文种\n"
                "通知、通报、报告、请示、批复、函、纪要\n"
            ),
            "user_template": (
                "请按GB/T 9704标准起草以下公文：\n\n"
                "**文种**：{doc_type}\n"
                "**发文机关**：{issuer}\n"
                "**主送机关**：{recipient}\n"
                "**公文主题**：{subject}\n"
                "**主要内容**：{content}\n"
                "**要求/目的**：{purpose}\n\n"
                "请生成完整的公文。\n"
            ),
        }

        # ---------- 情绪分析 ----------
        self._templates["情绪分析"] = {
            "name": "情绪分析",
            "description": "从文本中分析学生的情绪状态，提供专业评估和建议",
            "version": "1.0.0",
            "created_at": datetime.datetime.now().isoformat(),
            "system": (
                "你是一位具备心理学专业背景的AI辅导员助手，擅长从文本中识别和分析情绪。"
                "请按以下框架进行情绪分析：\n\n"
                "## 分析框架\n\n"
                "### 1. 情绪识别\n"
                "- 从文本中识别主要情绪类型（焦虑、抑郁、愤怒、恐惧、"
                "悲伤、快乐、平静等）\n"
                "- 标注情绪强度（1-5分，5为最强）\n"
                "- 识别是否存在复合情绪\n\n"
                "### 2. 语言特征分析\n"
                "- 情感词汇使用频率和类型\n"
                "- 句式结构特征（陈述/疑问/感叹/祈使比例）\n"
                "- 否定词和程度副词的使用\n"
                "- 话题转换频率和逻辑连贯性\n\n"
                "### 3. 心理风险评估\n"
                "- 是否存在心理危机信号（自我伤害倾向、极端言论等）\n"
                "- 社会功能影响程度\n"
                "- 是否需要转介专业心理干预\n"
                "- 风险等级：低风险/中风险/高风险/紧急\n\n"
                "### 4. 辅导建议\n"
                "- 沟通策略建议（共情、引导、支持等方向）\n"
                "- 后续关注要点\n"
                "- 需要跟进的时间节点\n\n"
                "## 输出格式\n"
                "以结构化报告形式输出，使用Markdown格式。\n"
            ),
            "user_template": (
                "请对以下文本进行情绪分析：\n\n"
                "---\n"
                "{text}\n"
                "---\n\n"
                "**补充背景**（如有）：{background}\n\n"
                "请按照分析框架输出完整的情绪分析报告。\n"
            ),
        }

        # ---------- 请假审批 ----------
        self._templates["请假审批"] = {
            "name": "请假审批",
            "description": "处理学生请假申请，生成规范的审批意见和回复",
            "version": "1.0.0",
            "created_at": datetime.datetime.now().isoformat(),
            "system": (
                "你是一位高校辅导员助理，负责处理学生请假申请。"
                "请按照以下流程和规范进行审批辅助：\n\n"
                "## 审批流程\n"
                "1. **信息核实**：核验请假人基本信息、课程安排、请假事由\n"
                "2. **规则检查**：对照学校请假管理办法判断是否符合规定\n"
                "3. **风险评估**：评估请假对学业的影响，是否有旷课风险\n"
                "4. **审批建议**：给出明确的审批意见\n\n"
                "## 输出要求\n"
                "### 请假申请处理单\n"
                "- 申请人信息（脱敏）\n"
                "- 请假类型：事假/病假/公假/其他\n"
                "- 请假时间：起止日期及时长\n"
                "- 请假事由摘要\n"
                "- 审核意见：同意/不同意/需补充材料\n"
                "- 审核说明（含理由）\n"
                "- 后续提醒事项\n\n"
                "## 审批原则\n"
                "1. 病假需附医院证明，紧急情况可先批后补\n"
                "2. 考试周请假需特别慎重，建议当面沟通\n"
                "3. 长期请假（3天以上）需家长知情同意\n"
                "4. 所有审批结果需记录存档\n"
            ),
            "user_template": (
                "请处理以下请假申请：\n\n"
                "**申请人**：{student_info}\n"
                "**请假类型**：{leave_type}\n"
                "**请假时间**：{leave_period}\n"
                "**请假事由**：{reason}\n"
                "**相关证明**：{evidence}\n"
                "**辅导员备注**：{notes}\n\n"
                "请给出审批意见和处理建议。\n"
            ),
        }

    # ----- 公共方法 -----

    def get_template(self, name: str) -> Optional[Dict[str, Any]]:
        """根据名称获取模板。"""
        return self._templates.get(name)

    def list_templates(self) -> List[Dict[str, Any]]:
        """列出所有模板的元数据信息。"""
        result = []
        for tpl in self._templates.values():
            result.append({
                "name": tpl["name"],
                "description": tpl["description"],
                "version": tpl["version"],
                "created_at": tpl["created_at"],
            })
        return result

    def add_template(self, name: str, system: str, user_template: str,
                     description: str = "") -> None:
        """添加新模板。"""
        if name in self._templates:
            raise ValueError(f"模板 '{name}' 已存在，请使用 update_template 更新")
        self._templates[name] = {
            "name": name,
            "description": description,
            "version": "1.0.0",
            "created_at": datetime.datetime.now().isoformat(),
            "system": system,
            "user_template": user_template,
        }
        logger.info("已添加新模板: %s", name)

    def update_template(self, name: str, **kwargs) -> None:
        """更新已有模板的字段。"""
        if name not in self._templates:
            raise KeyError(f"模板 '{name}' 不存在")
        for key, value in kwargs.items():
            if key in ("system", "user_template", "description", "version"):
                self._templates[name][key] = value
        logger.info("已更新模板: %s", name)

    def delete_template(self, name: str) -> None:
        """删除模板。"""
        if name not in self._templates:
            raise KeyError(f"模板 '{name}' 不存在")
        del self._templates[name]
        logger.info("已删除模板: %s", name)

    def export_all(self) -> Dict[str, Any]:
        """导出全部模板为字典。"""
        return {name: dict(tpl) for name, tpl in self._templates.items()}

    def import_templates(self, data: Dict[str, Any]) -> int:
        """从字典导入模板，返回导入数量。"""
        count = 0
        for name, tpl in data.items():
            self._templates[name] = tpl
            count += 1
        logger.info("已导入 %d 个模板", count)
        return count


# ============================================================
# 2. 提示词管理器
# ============================================================

class PromptManager:
    """提示词管理器，提供模板的增删改查和导入导出功能。"""

    def __init__(self):
        """初始化管理器，加载内置模板库。"""
        self._library = ScenePromptLibrary()
        self._logger = logging.getLogger(f"{__name__}.PromptManager")

    def get_prompt(self, scene_name: str) -> Optional[Dict[str, str]]:
        """
        获取指定场景的提示词模板。

        Args:
            scene_name: 场景名称

        Returns:
            包含 system 和 user_template 的字典，不存在则返回 None
        """
        tpl = self._library.get_template(scene_name)
        if tpl is None:
            self._logger.warning("未找到场景 '%s' 的模板", scene_name)
            return None
        return {
            "system": tpl["system"],
            "user_template": tpl["user_template"],
        }

    def list_prompts(self) -> List[Dict[str, Any]]:
        """列出所有可用提示词模板的元数据。"""
        return self._library.list_templates()

    def add_prompt(self, name: str, system: str, user_template: str,
                   description: str = "") -> None:
        """
        添加自定义提示词模板。

        Args:
            name: 模板名称（唯一标识）
            system: 系统提示词
            user_template: 用户提示词模板，支持 {变量} 占位符
            description: 模板描述
        """
        self._library.add_template(name, system, user_template, description)
        self._logger.info("已添加自定义模板: %s", name)

    def update_prompt(self, name: str, **kwargs) -> None:
        """
        更新已有模板。

        Args:
            name: 模板名称
            **kwargs: 可更新字段 (system, user_template, description, version)
        """
        self._library.update_template(name, **kwargs)
        self._logger.info("已更新模板: %s", name)

    def delete_prompt(self, name: str) -> None:
        """
        删除指定模板。

        Args:
            name: 模板名称
        """
        self._library.delete_template(name)
        self._logger.info("已删除模板: %s", name)

    def export_prompts(self, filepath: str) -> None:
        """
        将所有模板导出到JSON文件。

        Args:
            filepath: 导出文件路径
        """
        data = self._library.export_all()
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._logger.info("已导出 %d 个模板到 %s", len(data), filepath)
        except IOError as e:
            self._logger.error("导出失败: %s", e)
            raise

    def import_prompts(self, filepath: str) -> int:
        """
        从JSON文件导入模板。

        Args:
            filepath: 导入文件路径

        Returns:
            成功导入的模板数量
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            count = self._library.import_templates(data)
            self._logger.info("从 %s 导入了 %d 个模板", filepath, count)
            return count
        except (IOError, json.JSONDecodeError) as e:
            self._logger.error("导入失败: %s", e)
            raise


# ============================================================
# 3. 对话引擎
# ============================================================

class ConversationEngine:
    """对话引擎，支持单轮和多轮对话，内置会话历史管理。"""

    def __init__(self, prompt_manager: Optional[PromptManager] = None):
        """
        初始化对话引擎。

        Args:
            prompt_manager: 提示词管理器实例，不传则自动创建
        """
        self._pm = prompt_manager or PromptManager()
        self._client = OpenAI(
            api_key=API_KEY,
            base_url=API_BASE_URL,
        )
        # 会话历史，每条记录包含 role、content、timestamp
        self._history: List[Dict[str, str]] = []
        self._logger = logging.getLogger(f"{__name__}.ConversationEngine")

    def chat(self, scene: str, user_message: str,
             model: str = "qwen-plus") -> str:
        """
        单轮对话：不携带历史，只发送当前消息。

        Args:
            scene: 场景名称
            user_message: 用户消息
            model: 模型标识

        Returns:
            模型回复文本
        """
        prompt = self._pm.get_prompt(scene)
        if prompt is None:
            raise ValueError(f"未找到场景 '{scene}' 的提示词模板")

        messages = [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": user_message},
        ]

        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )
            reply = response.choices[0].message.content or ""
            self._logger.info("单轮对话完成 | 场景=%s | 模型=%s", scene, model)
            return reply
        except Exception as e:
            self._logger.error("单轮对话失败: %s", e)
            raise

    def organize(self, raw_content: str, student_name: str = None,
                 context: str = None) -> str:
        """整理原始谈话内容为结构化谈心记录（供批量整理路由调用）。

        复用「谈心记录」场景模板，支持追加学生姓名与背景信息。
        """
        extra_parts = []
        if student_name:
            extra_parts.append(f"学生姓名：{student_name}")
        if context:
            extra_parts.append(f"补充背景：{context}")
        message = raw_content
        if extra_parts:
            message = message + "\n\n补充信息：\n" + "\n".join(extra_parts)
        return self.chat(scene="谈心记录", user_message=message)

    def chat_with_history(self, scene: str, user_message: str,
                          history: Optional[List[Dict[str, str]]] = None,
                          max_history: int = 10,
                          model: str = "qwen-plus") -> str:
        """
        多轮对话：携带会话历史上下文。

        Args:
            scene: 场景名称
            user_message: 当前用户消息
            history: 外部传入的历史记录（可选，格式为 [{role, content}]）
            max_history: 最多保留的历史轮数（一条 = user + assistant 各一条）
            model: 模型标识

        Returns:
            模型回复文本
        """
        prompt = self._pm.get_prompt(scene)
        if prompt is None:
            raise ValueError(f"未找到场景 '{scene}' 的提示词模板")

        messages = [{"role": "system", "content": prompt["system"]}]

        # 确定历史来源
        src_history = history if history is not None else self._history
        # 截取最近 N 轮（每轮含 user + assistant = 2 条）
        trimmed = src_history[-(max_history * 2):]
        for record in trimmed:
            messages.append({
                "role": record["role"],
                "content": record["content"],
            })

        messages.append({"role": "user", "content": user_message})

        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )
            reply = response.choices[0].message.content or ""

            # 将本轮对话写入内部历史
            now = datetime.datetime.now().isoformat()
            self._history.append({
                "role": "user",
                "content": user_message,
                "timestamp": now,
            })
            self._history.append({
                "role": "assistant",
                "content": reply,
                "timestamp": now,
            })

            self._logger.info(
                "多轮对话完成 | 场景=%s | 历史条数=%d",
                scene, len(self._history),
            )
            return reply
        except Exception as e:
            self._logger.error("多轮对话失败: %s", e)
            raise

    def format_history(self, history: List[Dict[str, str]]) -> str:
        """
        将对话历史格式化为可读文本。

        Args:
            history: 历史记录列表

        Returns:
            格式化后的文本字符串
        """
        lines = []
        for i, record in enumerate(history, 1):
            role_label = "学生" if record["role"] == "user" else "辅导员"
            ts = record.get("timestamp", "未知时间")
            lines.append(f"[{i}] ({ts}) {role_label}: {record['content']}")
        return "\n\n".join(lines)

    def clear_history(self) -> None:
        """清空内部会话历史。"""
        self._history.clear()
        self._logger.info("会话历史已清空")

    def get_history(self) -> List[Dict[str, str]]:
        """返回当前内部会话历史的副本。"""
        return list(self._history)


# ============================================================
# 4. 批量处理器
# ============================================================

class BatchProcessor:
    """批量处理器，支持批量调用API、模板填充和结果导出。"""

    def __init__(self, prompt_manager: Optional[PromptManager] = None):
        """
        初始化批量处理器。

        Args:
            prompt_manager: 提示词管理器实例
        """
        self._pm = prompt_manager or PromptManager()
        self._client = OpenAI(
            api_key=API_KEY,
            base_url=API_BASE_URL,
        )
        self._logger = logging.getLogger(f"{__name__}.BatchProcessor")

    def process_batch(self, scene: str, input_list: List[str],
                      model: str = "qwen-plus") -> List[Dict[str, Any]]:
        """
        批量处理输入列表。

        Args:
            scene: 场景名称
            input_list: 用户输入文本列表
            model: 模型标识

        Returns:
            结果列表，每项包含 index、input、output、status、error
        """
        prompt = self._pm.get_prompt(scene)
        if prompt is None:
            raise ValueError(f"未找到场景 '{scene}' 的提示词模板")

        results = []
        total = len(input_list)

        for idx, user_input in enumerate(input_list):
            self._logger.info("批量处理进度: %d/%d", idx + 1, total)
            messages = [
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": user_input},
            ]

            try:
                response = self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=TEMPERATURE,
                    max_tokens=MAX_TOKENS,
                )
                output = response.choices[0].message.content or ""
                results.append({
                    "index": idx,
                    "input": user_input,
                    "output": output,
                    "status": "success",
                    "error": None,
                })
            except Exception as e:
                self._logger.error("批量处理第 %d 条失败: %s", idx, e)
                results.append({
                    "index": idx,
                    "input": user_input,
                    "output": None,
                    "status": "error",
                    "error": str(e),
                })

        self._logger.info(
            "批量处理完成 | 成功=%d | 失败=%d",
            sum(1 for r in results if r["status"] == "success"),
            sum(1 for r in results if r["status"] == "error"),
        )
        return results

    def process_with_template(self, scene: str, template_data: Dict[str, str],
                              model: str = "qwen-plus") -> Dict[str, Any]:
        """
        使用模板变量填充后处理单条输入。

        Args:
            scene: 场景名称
            template_data: 模板变量字典，key为变量名，value为实际值
            model: 模型标识

        Returns:
            包含 input、output、status、error 的结果字典
        """
        prompt = self._pm.get_prompt(scene)
        if prompt is None:
            raise ValueError(f"未找到场景 '{scene}' 的提示词模板")

        # 填充模板变量
        try:
            filled_user = prompt["user_template"].format(**template_data)
        except KeyError as e:
            return {
                "input": template_data,
                "output": None,
                "status": "error",
                "error": f"模板缺少变量: {e}",
            }

        messages = [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": filled_user},
        ]

        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )
            output = response.choices[0].message.content or ""
            return {
                "input": filled_user,
                "output": output,
                "status": "success",
                "error": None,
            }
        except Exception as e:
            self._logger.error("模板处理失败: %s", e)
            return {
                "input": filled_user,
                "output": None,
                "status": "error",
                "error": str(e),
            }

    @staticmethod
    def export_results(results: Any, filepath: str) -> None:
        """
        将处理结果导出到JSON文件。

        Args:
            results: 结果数据（列表或字典）
            filepath: 导出文件路径
        """
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info("结果已导出到 %s", filepath)
        except IOError as e:
            logger.error("导出结果失败: %s", e)
            raise


# ============================================================
# 5. 主程序演示
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    print("=" * 60)
    print("   聆心 - 提示词工程引擎 功能演示")
    print("=" * 60)

    # ---------- 提示词管理器演示 ----------
    pm = PromptManager()

    print("\n📋 当前所有提示词模板：")
    for item in pm.list_prompts():
        print(f"  - {item['name']}: {item['description']} (v{item['version']})")

    # 添加自定义模板
    pm.add_prompt(
        name="学术预警",
        system=(
            "你是一位高校学业辅导员，负责处理学生学业预警。"
            "请分析学生的学业状况并给出改进建议。"
        ),
        user_template=(
            "请对以下学生的学业状况进行预警分析：\n\n"
            "**学生**：{student_info}\n"
            "**学业数据**：{academic_data}\n"
        ),
        description="分析学生学业预警状况",
    )
    print("\n[OK] 已添加自定义模板 '学术预警'")

    print("\n📋 更新后的模板列表：")
    for item in pm.list_prompts():
        print(f"  - {item['name']}: {item['description']}")

    # 导出模板
    export_path = "prompts_backup.json"
    pm.export_prompts(export_path)
    print(f"\n💾 模板已导出到 {export_path}")

    # ---------- 对话引擎演示 ----------
    engine = ConversationEngine(pm)

    print("\n--- 对话引擎演示（需有效API配置）---")
    print("以下为代码示例，实际运行需要有效的API密钥：\n")

    print("📌 单轮对话调用示例：")
    print("  reply = engine.chat(scene='情绪分析', user_message='我最近很焦虑...')")
    print("  print(reply)\n")

    print("📌 多轮对话调用示例：")
    print("  reply1 = engine.chat_with_history('谈心记录', '我最近压力很大')")
    print("  reply2 = engine.chat_with_history('谈心记录', '主要是学业方面的压力')")
    print("  history = engine.get_history()")
    print("  formatted = engine.format_history(history)")
    print("  print(formatted)")
    print("  engine.clear_history()\n")

    # ---------- 批量处理器演示 ----------
    processor = BatchProcessor(pm)

    print("📌 批量处理调用示例：")
    print("  inputs = ['学生A的请假条', '学生B的请假条']")
    print("  results = processor.process_batch('请假审批', inputs)")
    print("  processor.export_results(results, 'batch_results.json')\n")

    print("📌 模板填充处理示例：")
    print("  data = {")
    print('    "student_info": "张三 / 大二 / 计算机专业",')
    print('    "leave_type": "病假",')
    print('    "leave_period": "2026-06-15 至 2026-06-16",')
    print('    "reason": "发烧38.5度，需要就医休息",')
    print('    "evidence": "校医院就诊记录",')
    print('    "notes": ""')
    print("  }")
    print("  result = processor.process_with_template('请假审批', data)")
    print("  print(result['output'])\n")

    # 清理导出的备份文件
    import os
    if os.path.exists(export_path):
        os.remove(export_path)

    print("=" * 60)
    print("   演示完成！所有功能模块均已就绪。")
    print("=" * 60)

