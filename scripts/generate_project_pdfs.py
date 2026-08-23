# -*- coding: utf-8 -*-
"""Generate the two Chinese project PDFs for the Lingxin platform."""
import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
)


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "pdf"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FONT_PATH = r"C:/Windows/Fonts/simhei.ttf"
pdfmetrics.registerFont(TTFont("SimHei", FONT_PATH))

NAVY = colors.HexColor("#123047")
TEAL = colors.HexColor("#0F766E")
TEAL_LIGHT = colors.HexColor("#CCFBF1")
AMBER = colors.HexColor("#B45309")
AMBER_LIGHT = colors.HexColor("#FEF3C7")
INK = colors.HexColor("#1F2937")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#CBD5E1")
SOFT = colors.HexColor("#F8FAFC")
WHITE = colors.white


def _style(name, size, leading, color=INK, bold=False, align=TA_LEFT,
           space_before=0, space_after=6, font="SimHei"):
    return ParagraphStyle(
        name=name,
        fontName=font,
        fontSize=size,
        leading=leading,
        textColor=color,
        alignment=align,
        spaceBefore=space_before,
        spaceAfter=space_after,
        wordWrap="CJK",
    )


S = {
    "cover_title": _style("cover_title", 27, 34, WHITE, True, TA_CENTER, 0, 18),
    "cover_sub": _style("cover_sub", 14, 20, colors.HexColor("#D1FAE5"), False, TA_CENTER, 0, 12),
    "cover_meta": _style("cover_meta", 10, 16, colors.HexColor("#E2E8F0"), False, TA_CENTER, 0, 6),
    "h1": _style("h1", 16, 21, NAVY, True, TA_LEFT, 14, 8),
    "h2": _style("h2", 12.5, 17, TEAL, True, TA_LEFT, 10, 6),
    "h3": _style("h3", 11, 15, INK, True, TA_LEFT, 7, 4),
    "body": _style("body", 10, 16, INK, False, TA_LEFT, 0, 6),
    "body_small": _style("body_small", 9, 14, MUTED, False, TA_LEFT, 0, 4),
    "bullet": _style("bullet", 10, 16, INK, False, TA_LEFT, 0, 4, font="SimHei"),
    "table": _style("table", 9, 13, INK, False, TA_LEFT, 0, 2),
    "table_head": _style("table_head", 9, 13, WHITE, True, TA_LEFT, 0, 2),
    "caption": _style("caption", 8.5, 12, MUTED, False, TA_CENTER, 0, 4),
}


def _cover(canvas, doc, title, subtitle, doc_name):
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 7.0 * cm, w, 7.0 * cm, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.rect(0, h - 7.0 * cm, w, 0.16 * cm, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#0B3B4B"))
    canvas.rect(0, h - 12.6 * cm, w, 5.6 * cm, fill=1, stroke=0)
    canvas.setFillColor(TEAL_LIGHT)
    canvas.rect(0, h - 12.6 * cm, 0.18 * cm, 5.6 * cm, fill=1, stroke=0)
    canvas.restoreState()


def _content_page(canvas, doc, project_name):
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 1.25 * cm, w, 1.25 * cm, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("SimHei", 9)
    canvas.drawString(2.0 * cm, h - 0.80 * cm, project_name)
    canvas.setFillColor(MUTED)
    canvas.setFont("SimHei", 8.5)
    canvas.drawRightString(w - 2.0 * cm, h - 0.80 * cm, "内部项目材料")
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.6)
    canvas.line(2.0 * cm, 1.25 * cm, w - 2.0 * cm, 1.25 * cm)
    canvas.setFillColor(MUTED)
    canvas.setFont("SimHei", 8.5)
    canvas.drawCentredString(w / 2, 0.75 * cm, f"第 {doc.page} 页")
    canvas.restoreState()


def _section(number, title):
    return Paragraph(f"{number}  {title}", S["h1"])


def _subsection(number, title):
    return Paragraph(f"{number}  {title}", S["h2"])


def _body(text):
    return Paragraph(text, S["body"])


def _bullet(text):
    return Paragraph(f"●  {text}", S["bullet"])


def _table(data, col_widths, header=True):
    flowable_data = []
    for row_index, row in enumerate(data):
        style_name = "table_head" if header and row_index == 0 else "table"
        flowable_data.append([Paragraph(str(cell), S[style_name]) for cell in row])
    table = Table(flowable_data, colWidths=col_widths, repeatRows=1 if header else 0, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY if header else WHITE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SOFT]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    table.setStyle(TableStyle(style))
    return table


def _flowable_text_table(rows, col_widths):
    data = []
    for row_index, row in enumerate(rows):
        style_name = "table_head" if row_index == 0 else "table"
        data.append([Paragraph(cell, S[style_name]) for cell in row])
    table = Table(data, colWidths=col_widths, hAlign="LEFT", repeatRows=1)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SOFT]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _doc(path, cover_title, cover_sub, project_name, on_first, on_later, story):
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=1.9 * cm,
        bottomMargin=1.8 * cm,
        title=cover_title,
        author="聆心项目组",
        subject=cover_sub,
    )
    doc.build(story, onFirstPage=on_first, onLaterPages=on_later)


def build_overview():
    path = OUT_DIR / "高校学生心理状态AI感知与分级辅导项目概要介绍.pdf"
    project_name = "高校学生心理状态AI感知与分级辅导"
    cover_title = "高校学生心理状态AI感知与分级辅导"
    cover_sub = "基于大模型的教育管理应用创新方案"
    cover_doc = "项目概要介绍"

    story = [
        Spacer(1, 3.0 * cm),
        Paragraph(cover_title, S["cover_title"]),
        Spacer(1, 0.25 * cm),
        Paragraph(cover_sub, S["cover_sub"]),
        Spacer(1, 0.15 * cm),
        Paragraph(cover_doc, S["cover_meta"]),
        Spacer(1, 0.12 * cm),
        Paragraph("教育信息技术应用创新大赛  |  基于大模型教育管理应用创新赛", S["cover_meta"]),
        Spacer(1, 0.5 * cm),
        Paragraph("版本 v1.0  |  2026-08-21", S["cover_meta"]),
        Spacer(1, 2.1 * cm),
        PageBreak(),
        _section("一", "项目介绍"),
        _body(
            "高校辅导员人均管理学生数量大，学生心理状态变化难以及时感知，谈心记录长期依赖手写或事后补录，心理危机线索散落在测评、即时消息、视频通话等渠道。"
            "本方案以通义千问大模型为底座，将多模态情绪识别、心理量表与大模型研判相结合，对学生心理状态进行 AI 感知与分级辅导，"
            "自动生成结构化谈心记录，并按“关注、高风险、紧急”分级联动预警与危机干预，形成可追溯的处置闭环。"
        ),
        _section("二", "核心功能"),
        _flowable_text_table(
            [
                ["功能模块", "大模型驱动的能力说明"],
                ["心理状态 AI 感知", "语音情绪、人脸表情、文本语义与 PHQ-9/GAD-7/ISI 量表联合研判，输出心理状态、情绪强度与风险等级。"],
                ["AI 分级辅导", "按正常、关注、高风险、紧急生成差异化辅导话术、谈心记录与跟进建议，一键生成结构化记录并导出。"],
                ["AI 数字人陪护", "老师离线时由大模型分级响应学生倾诉；紧急场景停止幽默、立即预警、热线引导与人工介入。"],
                ["预警处置闭环", "大模型研判结合规则引擎，按“取最高不降级”聚合风险，保留证据时间线并联动危机工单。"],
            ],
            [3.0 * cm, 12.0 * cm],
        ),
        Spacer(1, 0.15 * cm),
        _section("三", "技术路线"),
        _flowable_text_table(
            [
                ["技术层次", "主要能力"],
                ["大模型层", "通义千问 qwen-turbo/qwen-plus，承担心理状态研判、分级话术、谈心报告、数字人对话与危机识别。"],
                ["多模态层", "emotion2vec 语音情绪、FER 人脸表情、文本语义与心理量表，多信号加权融合。"],
                ["知识层", "RAG 检索增强，融合向量检索、BM25 与新鲜度加权，提供学校规章制度问答与证据引用。"],
                ["应用层", "Flask + Vue3 + WebRTC + Socket.IO，承载分级辅导、风险看板、视频通话与处置闭环。"],
            ],
            [3.0 * cm, 12.0 * cm],
        ),
        Spacer(1, 0.12 * cm),
        _section("四", "预期成果"),
        _bullet("心理状态感知覆盖语音、人脸、文本与心理量表，通过多信号加权投票输出统一研判结果。"),
        _bullet("74 项自动化测试全部通过，61 项账号与数据校验全部通过；文本情绪八分类评测样本 16 条，准确率与宏平均 F1 均为 100%。"),
        _bullet("谈心记录由手写约 30 分钟压缩为一键生成，辅导员可将时间用于真实沟通与重点学生跟进。"),
        _bullet("危机识别从事后发现升级为“关注、高风险、紧急”实时分级预警与自动危机工单，实现风险前置和处置留痕。"),
        _section("五", "创新性说明"),
        _bullet("相较单模态情绪识别，平台融合语音、人脸、文本与心理量表，减少单一信号噪声造成的误判与漏判。"),
        _bullet("相较“预警只是一个列表”，平台把感知、分级、辅导、预警、危机工单串成可追溯闭环，并采用取最高不降级机制。"),
        _bullet("相较“大模型只是聊天机器人”，平台按学生风险等级差异化生成辅导话术，真正服务于教育管理动作。"),
        _bullet("AI 数字人离线陪护与老师上线值班摘要联动，保证非工作时间也有边界清晰的分级响应。"),
        _section("六", "应用价值说明"),
        _body(
            "对辅导员，平台将状态感知、分级辅导、记录生成和跟进动作自动化，降低重复事务负担；"
            "对学工处和心理中心，平台提供全校心理状态总览、危机工单协同和跨学院调度，提高响应效率；"
            "对学校，平台形成跨角色、跨来源的心理风险台账与处置留痕，支持合规审计、风险前置和干预复盘。"
        ),
        Spacer(1, 0.2 * cm),
    ]
    _doc(
        path,
        cover_title,
        cover_sub,
        project_name,
        lambda c, d: _cover(c, d, cover_title, cover_sub, project_name),
        lambda c, d: _content_page(c, d, project_name),
        story,
    )
    return path


def build_design_doc():
    path = OUT_DIR / "高校学生心理状态AI感知与分级辅导设计方案书.pdf"
    project_name = "高校学生心理状态AI感知与分级辅导设计方案书"
    cover_title = "高校学生心理状态AI感知与分级辅导设计方案书"
    cover_sub = "基于大模型的教育管理应用创新方案"
    cover_doc = "需求分析报告  |  系统设计说明书  |  测试方案与结果"

    story = [
        Spacer(1, 2.8 * cm),
        Paragraph(cover_title, S["cover_title"]),
        Spacer(1, 0.25 * cm),
        Paragraph(cover_sub, S["cover_sub"]),
        Spacer(1, 0.15 * cm),
        Paragraph(cover_doc, S["cover_meta"]),
        Spacer(1, 0.12 * cm),
        Paragraph("教育信息技术应用创新大赛  |  基于大模型教育管理应用创新赛", S["cover_meta"]),
        Spacer(1, 0.5 * cm),
        Paragraph("版本 v1.0  |  2026-08-21", S["cover_meta"]),
        Spacer(1, 1.6 * cm),
        PageBreak(),
        _section("1", "需求分析报告"),
        _subsection("1.1", "教育管理现状痛点"),
        _bullet("管理压力大：辅导员人均服务学生数量多，谈心覆盖难、口径不一，记录主要靠手写或事后补录，耗时且难沉淀。"),
        _bullet("危机发现滞后：风险线索散落在心理测评、即时消息、视频通话和数字人对话中，缺少实时汇聚，往往事后才发现。"),
        _bullet("数据未形成闭环：测评结果、谈心记录、预警处置和危机工单分散在不同渠道，证据不可溯源，处置状态不透明。"),
        _bullet("陪伴存在空档：学生非工作时间倾诉缺少及时回应，老师离线后服务断层，线上沟通与线下跟进难以衔接。"),
        _subsection("1.2", "用户画像与核心诉求"),
        _flowable_text_table(
            [
                ["角色", "核心诉求", "对应能力"],
                ["辅导员", "减少事务性写作，快速掌握本班学生状态并处置预警", "心理状态 AI 感知、AI 分级辅导、预警流转、数字人值班摘要"],
                ["学工处/管理员", "全校风险总览、跨辅导员危机调度、全程操作留痕", "情绪看板、危机工单、权限隔离、审计日志"],
                ["学生", "低门槛倾诉、自评、预约，并获得及时、有边界的情感支持", "即时消息、心理测评、预约咨询、AI 数字人陪伴"],
            ],
            [3.1 * cm, 6.0 * cm, 5.9 * cm],
        ),
        Spacer(1, 0.12 * cm),
        _subsection("1.3", "竞品对比"),
        _flowable_text_table(
            [
                ["对比项", "传统心理测评系统", "通用 AI 聊天机器人", "本方案"],
                ["核心逻辑", "只测评、不形成处置闭环", "只对话、不进入教育管理", "大模型对话与生成，服务教育管理闭环"],
                ["危机处置", "以量表分和预警列表为主", "缺少学校场景工单", "多模态研判、实时预警、危机工单协同"],
                ["辅导员角色", "主要查看测评结果", "无辅导员工作场景", "AI 感知、分级辅导、数字人陪护、无缝接管"],
                ["数据闭环", "测评数据静态沉淀", "对话记录相对分散", "生成记录、回写状态、证据时间线、工单复盘"],
            ],
            [2.4 * cm, 3.8 * cm, 3.7 * cm, 5.1 * cm],
        ),
        Spacer(1, 0.12 * cm),
        _subsection("1.4", "可行性分析"),
        _bullet("技术可行：已具备 Flask、Vue3、SQLite、ChromaDB 和本地情绪识别管线，能够在一个平台内完成数据汇聚与闭环流转。"),
        _bullet("成本可控：qwen-turbo 承担高并发对话，qwen-plus 处理高质量生成；无 API Key 时由规则和本地模型降级，核心预警不中断。"),
        _bullet("数据可复现：采用确定性 seed，覆盖 12 名辅导员、600 名学生、146 条预警和 1880 条情绪日志，便于演示与回归验证。"),
        _bullet("边界清晰：平台提供辅助研判与预警，不替代专业医学诊断；隐私数据本地化处理，后续可接入本地大模型实现数据不出校。"),
        _subsection("1.5", "核心需求边界"),
        _bullet("必须打通“谈心记录生成、状态回写、预警流转、危机工单、老师接管”的关键闭环，而不是孤立功能页面。"),
        _bullet("情绪识别必须标注来源与强度；风险状态必须采用“取最高不降级”机制，危机等级 2 级及以上必须触发预警。"),
        _bullet("数字人只在老师离线时作为分身值班，老师上线后必须通过值班摘要快速接管，不能替代人工处置。"),
        _bullet("演示数据必须可重置、可校验，自动化测试与前端冒烟结果必须可复现，作为项目可交付的量化基线。"),
        PageBreak(),
        _section("2", "系统设计说明书"),
        _subsection("2.1", "总体架构"),
        _body(
            "系统采用前后端分离架构：Vue 3 前端通过 REST API 和 Socket.IO 与 Flask 后端通信；"
            "后端由接口层、大模型编排层、多模态层和知识/数据层组成。"
            "大模型编排层统一调度情绪识别、对话话术、数字人对话和风险决策四个能力模块，"
            "所有生成、研判与状态回写都围绕教育管理闭环展开。"
        ),
        _flowable_text_table(
            [
                ["层次", "主要组件", "职责"],
                ["展示层", "Vue 3、ECharts、WebRTC、SVG 头像", "页面交互、看板、实时通话和数字人视觉表现"],
                ["接口层", "Flask REST API、Socket.IO", "认证、权限、事件推送和跨模块服务调用"],
                ["大模型层", "qwen-plus/qwen-turbo", "情绪分析、话术生成、谈心报告、数字人对话与危机识别"],
                ["多模态层", "emotion2vec、YOLOv8-face、transformers FER", "语音情绪、人脸表情和姿态微表情识别"],
                ["知识/数据层", "RAG、SQLite、SQLAlchemy、ChromaDB", "制度知识检索、业务持久化、证据保存与审计"],
            ],
            [2.2 * cm, 6.1 * cm, 6.7 * cm],
        ),
        Spacer(1, 0.12 * cm),
        _subsection("2.2", "核心大模型能力模块"),
        _flowable_text_table(
            [
                ["模块", "输入", "大模型处理", "输出与动作"],
                ["心理状态 AI 感知模块", "语音、人脸、文本、心理量表", "emotion2vec/FER 提取特征，qwen 做跨模态语义研判与规则加权", "输出 emotion、强度、风险，回写学生状态并触发预警"],
                ["AI 分级辅导模块", "谈心上下文、学生画像、风险等级、场景类型", "qwen 理解对话议题，按关注/高风险/紧急生成差异化话术并施加专业边界约束", "话术可点击填入，一键生成结构化谈心记录"],
                ["AI 数字人陪护模块", "老师离线状态、最近 8 轮、risk_level、emotion_status", "qwen 生成分级回复，采用三层危机分级与 LLM 语义兜底", "情绪化回复、TTS、SVG 头像；2 级预警，3 级危机工单与热线"],
                ["风险决策与预警闭环模块", "多来源风险证据、当前状态、处置操作", "规则聚合与 qwen 研判，执行“取最高不降级”和显式降级", "证据时间线、预警状态机、危机工单与复盘记录"],
            ],
            [1.9 * cm, 3.2 * cm, 5.3 * cm, 4.6 * cm],
        ),
        Spacer(1, 0.12 * cm),
        _subsection("2.3", "AI 数字人详细设计"),
        _body(
            "数字人状态包括“值班中、休息、生成中、朗读中、已接管”。当学生发送消息且老师离线、数字人开启时，"
            "系统异步构建最近 8 轮历史上下文，并将学生 risk_level 和 emotion_status 注入 student_context。"
            "高风险学生自动采用专业稳重风格、降低幽默程度；中等风险学生限制幽默等级。"
        ),
        _body(
            "危机识别采用三层策略：第一层紧急关键词返回 3 级；第二层扩展风险信号或 LLM 风险探测返回 2 级；"
            "第三层负面情绪返回 1 级，其余返回 0 级。0 为正常，1 为关注，2 为高风险，3 为紧急。"
            "2 级及以上生成预警，3 级生成危机工单并使用“停止幽默、立即联系、提供热线”的强干预回复。"
        ),
        _body(
            "老师上线后，值班日志按学生聚合展示：对话轮次、主要话题、关注数量、高风险数量、AI 回复后继续倾诉比例和建议跟进标记，"
            "老师可逐条标记已处理。前端 SVG 头像根据 mood 切换微笑、关切、思考和朗读口型，提升拟人体验。"
        ),
        _subsection("2.4", "关键数据结构"),
        _table(
            [
                ["实体", "关键字段", "说明"],
                ["DigitalHumanLog", "crisis, crisis_level, triggered_keywords, handled", "记录数字人回复与危机等级"],
                ["AlertLog", "risk_level, emotion_type, status, resolved_at", "预警流转和处置审计"],
                ["StudentRiskEvidence", "student_id, source, risk_level, evidence", "风险证据时间线"],
                ["Student", "risk_level, emotion_status, counselor_id", "学生画像和辅导员归属"],
                ["Message", "sender_type, content, created_at", "即时消息和短期记忆来源"],
            ],
            [4.4 * cm, 6.2 * cm, 4.4 * cm],
        ),
        _subsection("2.5", "安全与可解释性"),
        _bullet("采用签名令牌认证、退出黑名单、路由级角色控制、辅导员数据隔离和 IP 登录限流。"),
        _bullet("Markdown 内容统一经 DOMPurify 清洗后渲染，降低 XSS 风险。"),
        _bullet("情绪识别结果不直接作为医学诊断，只作为辅导员辅助研判信号，并在界面保留来源和证据。"),
        PageBreak(),
        _section("3", "测试方案与结果"),
        _subsection("3.1", "测试策略"),
        _body(
            "测试分为单元测试、接口测试、端到端闭环测试、前端页面冒烟测试和数据校验。"
            "后端使用 pytest 覆盖核心业务链路与权限边界；前端使用 Playwright 或 Edge headless 检查关键页面渲染；"
            "数据层使用确定性 seed 校验账号、外键关联、学生归属和统计数量。"
        ),
        _subsection("3.2", "测试环境与数据"),
        _table(
            [
                ["项目", "配置"],
                ["运行环境", "Python 3.10+ / Flask / SQLite / Vue 3"],
                ["浏览器", "Playwright / Edge headless"],
                ["演示数据", "12 名辅导员、600 名学生、1880 条情绪日志、146 条预警"],
                ["测试账号", "admin / liuxin / zhangwei / 20240001 等"],
            ],
            [3.4 * cm, 11.6 * cm],
        ),
        Spacer(1, 0.12 * cm),
        _subsection("3.3", "明星用例：风险状态闭环"),
        _body(
            "该用例覆盖“测评、谈心、预警、处置、复盘”完整链路，是验证系统设计严谨性的核心证据。"
            "被测对象为同一学生的风险状态与预警状态，测试逐步写入不同来源的风险证据，并断言系统状态符合预期。"
        ),
        _bullet("测评写入 high：系统将学生风险状态置为 high，并生成高风险预警。"),
        _bullet("谈心写入 medium：系统执行“取最高不降级”，状态仍保持 high，同时追加证据时间线。"),
        _bullet("辅导员显式降级：经人工确认后执行显式降级操作，预警进入已确认或已解决。"),
        _bullet("预警解决后重算：基于最新证据重新计算，学生状态回落到 low，处置过程完整留痕。"),
        Spacer(1, 0.12 * cm),
        _subsection("3.4", "执行结果汇总"),
        _bullet("自动化测试：python -m pytest tests/ -q，结果为 74 passed、0 failed。"),
        _bullet("账号与数据校验：python scripts/verify_test_accounts.py，结果为 61 项通过、0 项失败。"),
        _bullet("前端冒烟：python scripts/smoke_frontend.py，登录页、辅导员工作台、学生心理测评页均通过。"),
        _bullet("模型评测：文本情绪八分类基线评测 16 条样本，准确率 100.00%，宏平均 F1 100.00%。"),
        _bullet("数据清洗：python seed_v31.py 重置后为 146 条预警、1880 条情绪日志、600 名学生，测试学生脏预警为 0。"),
        _subsection("3.5", "测试用例矩阵"),
        _table(
            [
                ["用例分类", "重点内容", "结果"],
                ["工作台与待办", "辅导员工作台接口、学生统计、待办关系", "通过"],
                ["心理测评", "PHQ-9 第 9 项边界、高/中风险回写和预警", "通过"],
                ["预警闭环", "取最高不降级、显式降级、危机工单指派与关闭", "通过"],
                ["数字人危机", "紧急/高风险/关注/正常四级判定、回复落库与预警", "通过"],
                ["预约与档案", "确认预约生成待办、完成预约沉淀档案", "通过"],
                ["权限与安全", "辅导员跨学生访问隔离、登录鉴权", "通过"],
                ["前端冒烟", "登录页、工作台、心理测评页关键文本", "通过"],
                ["账号与数据", "61 项账号、学生归属、外键和统计校验", "通过"],
            ],
            [3.3 * cm, 8.1 * cm, 3.6 * cm],
        ),
        Spacer(1, 0.12 * cm),
        _subsection("3.6", "发现的问题与修复"),
        _table(
            [
                ["问题", "影响", "修复"],
                ["辅导员工作台接口崩溃", "默认页空白", "补充 Todo.student relationship，并增加工作台测试"],
                ["学生端测评/预约/个人中心空白", "三页不渲染", "补齐 studentChat 区域闭合标签，并增加冒烟测试"],
                ["index.html 主内容标签误闭合", "潜在 DOM 嵌套错误", "将错误 </div> 改为 </main>"],
                ["数字人危机仅有布尔值", "无法区分风险等级", "升级为 0-3 级语义分级，并落库与预警"],
                ["关键 API 静默失败", "用户无法感知失败", "增加关键路径白名单和 Toast 重试提示"],
            ],
            [5.6 * cm, 4.4 * cm, 5.0 * cm],
        ),
        Spacer(1, 0.12 * cm),
        _subsection("3.7", "残余风险与后续计划"),
        _bullet("情绪识别模型当前覆盖基础情绪类别，后续可接入更细粒度模型和真实标注样本。"),
        _bullet("视频通话中微表情与姿态融合仍以规则加权为主，需要更多端到端评测。"),
        _bullet("隐私增强方面，可引入本地化大模型，实现文本生成和知识检索的数据不出校。"),
        Spacer(1, 0.15 * cm),
        _section("4", "结论"),
        _body(
            "本方案已完成从教育管理需求分析、大模型能力模块设计、开发实现到测试验证的闭环。"
            "系统以通义千问大模型为核心，打通心理状态 AI 感知、AI 分级辅导、AI 数字人陪护和预警处置闭环，"
            "并形成可复现的演示数据、74/74 自动化测试和 61/61 数据校验基线，具备进入试点应用和后续扩展的基础。"
        ),
        Spacer(1, 0.2 * cm),
    ]
    _doc(
        path,
        cover_title,
        cover_sub,
        project_name,
        lambda c, d: _cover(c, d, cover_title, cover_sub, project_name),
        lambda c, d: _content_page(c, d, project_name),
        story,
    )
    return path


if __name__ == "__main__":
    overview = build_overview()
    design = build_design_doc()
    print(overview)
    print(design)
