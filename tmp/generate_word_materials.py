# -*- coding: utf-8 -*-
"""Generate the two Chinese Word deliverables for the LingXin project."""

import os
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


NAVY = RGBColor(0x1F, 0x38, 0x64)
BLUE = RGBColor(0x2E, 0x74, 0xB5)
DARK_BLUE = RGBColor(0x1F, 0x4D, 0x78)
BLACK = RGBColor(0x00, 0x00, 0x00)
MUTED = RGBColor(0x55, 0x55, 0x55)
TABLE_HEADER_FILL = "F2F4F7"
TABLE_ALT_FILL = "F8FAFC"
EAST_ASIAN_FONT = "微软雅黑"
LATIN_FONT = "Calibri"


def set_run_font(run, size=11, color=BLACK, bold=False, italic=False,
                 east_asia=EAST_ASIAN_FONT, latin=LATIN_FONT):
    run.font.name = latin
    run._element.get_or_add_rPr()
    rfonts = run._element.rPr.get_or_add_rFonts()
    rfonts.set(qn("w:ascii"), latin)
    rfonts.set(qn("w:hAnsi"), latin)
    rfonts.set(qn("w:eastAsia"), east_asia)
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold
    run.font.italic = italic


def set_style_font(style, size=11, color=BLACK, bold=False,
                   east_asia=EAST_ASIAN_FONT, latin=LATIN_FONT):
    style.font.name = latin
    style.font.size = Pt(size)
    style.font.color.rgb = color
    style.font.bold = bold
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:ascii"), latin)
    rfonts.set(qn("w:hAnsi"), latin)
    rfonts.set(qn("w:eastAsia"), east_asia)


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(table, top=80, start=120, bottom=80, end=120):
    tbl_pr = table._tbl.tblPr
    cell_mar = tbl_pr.find(qn("w:tblCellMar"))
    if cell_mar is None:
        cell_mar = OxmlElement("w:tblCellMar")
        tbl_pr.append(cell_mar)
    for margin_name, value in (("top", top), ("start", start),
                               ("bottom", bottom), ("end", end)):
        node = cell_mar.find(qn(f"w:{margin_name}"))
        if node is None:
            node = OxmlElement(f"w:{margin_name}")
            cell_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_table_geometry(table, widths_in, indent_in=0.083):
    total_dxa = int(sum(widths_in) * 1440)
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    tbl_pr = table._tbl.tblPr

    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(total_dxa))
    tbl_w.set(qn("w:type"), "dxa")

    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), str(int(indent_in * 1440)))
    tbl_ind.set(qn("w:type"), "dxa")

    grid = table._tbl.find(qn("w:tblGrid"))
    if grid is not None:
        table._tbl.remove(grid)
    grid = OxmlElement("w:tblGrid")
    table._tbl.insert(1, grid)
    for width_in in widths_in:
        grid_col = OxmlElement("w:gridCol")
        grid_col.set(qn("w:w"), str(int(width_in * 1440)))
        grid.append(grid_col)

    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            cell.width = Inches(widths_in[idx])
            tc_w = cell._tc.get_or_add_tcPr().find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                cell._tc.get_or_add_tcPr().append(tc_w)
            tc_w.set(qn("w:w"), str(int(widths_in[idx] * 1440)))
            tc_w.set(qn("w:type"), "dxa")

    set_cell_margins(table)


def set_repeat_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def add_page_number_field(paragraph, prefix="第 ", suffix=" 页"):
    run = paragraph.add_run(prefix)
    set_run_font(run, size=9, color=MUTED)

    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")

    field_run = paragraph.add_run()
    field_run._r.append(fld_begin)
    field_run._r.append(instr)
    field_run._r.append(fld_end)
    set_run_font(field_run, size=9, color=MUTED)

    run = paragraph.add_run(suffix)
    set_run_font(run, size=9, color=MUTED)


def configure_document(doc, footer_label):
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)
    section.different_first_page_header_footer = True

    styles = doc.styles
    normal = styles["Normal"]
    set_style_font(normal, size=11, color=BLACK, bold=False)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.1

    h1 = styles["Heading 1"]
    set_style_font(h1, size=16, color=BLUE, bold=True)
    h1.paragraph_format.space_before = Pt(16)
    h1.paragraph_format.space_after = Pt(8)
    h1.paragraph_format.keep_with_next = True

    h2 = styles["Heading 2"]
    set_style_font(h2, size=13, color=BLUE, bold=True)
    h2.paragraph_format.space_before = Pt(12)
    h2.paragraph_format.space_after = Pt(6)
    h2.paragraph_format.keep_with_next = True

    h3 = styles["Heading 3"]
    set_style_font(h3, size=12, color=DARK_BLUE, bold=True)
    h3.paragraph_format.space_before = Pt(8)
    h3.paragraph_format.space_after = Pt(4)
    h3.paragraph_format.keep_with_next = True

    footer = section.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    run = p.add_run(footer_label + "  |  ")
    set_run_font(run, size=9, color=MUTED)
    add_page_number_field(p)

    first_footer = section.first_page_footer
    first_footer.is_linked_to_previous = False
    first_footer.paragraphs[0].text = ""


def add_cover(doc, title, subtitle, meta_rows):
    for _ in range(3):
        spacer = doc.add_paragraph()
        spacer.paragraph_format.space_before = Pt(0)
        spacer.paragraph_format.space_after = Pt(0)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(8)
    run = p.add_run("聆心")
    set_run_font(run, size=12, color=MUTED, bold=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(title)
    set_run_font(run, size=26, color=NAVY, bold=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(18)
    run = p.add_run(subtitle)
    set_run_font(run, size=13, color=MUTED, bold=False)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(20)
    p_pr = p._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "B8C4D2")
    p_bdr.append(bottom)
    p_pr.append(p_bdr)

    meta = doc.add_table(rows=0, cols=2)
    meta.alignment = WD_TABLE_ALIGNMENT.CENTER
    for label, value in meta_rows:
        row = meta.add_row().cells
        row[0].width = Inches(1.2)
        row[1].width = Inches(3.6)
        row[0].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        row[1].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p0 = row[0].paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p0.paragraph_format.space_after = Pt(5)
        p0.paragraph_format.space_before = Pt(5)
        r0 = p0.add_run(label)
        set_run_font(r0, size=10.5, color=BLACK, bold=True)
        p1 = row[1].paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p1.paragraph_format.space_after = Pt(5)
        p1.paragraph_format.space_before = Pt(5)
        r1 = p1.add_run(value)
        set_run_font(r1, size=10.5, color=BLACK, bold=False)

    set_table_geometry(meta, [1.2, 3.6], indent_in=0.25)
    doc.add_page_break()


def add_heading(doc, text, level=1):
    p = doc.add_heading("", level=level)
    run = p.add_run(text)
    if level == 1:
        set_run_font(run, size=16, color=BLUE, bold=True)
    elif level == 2:
        set_run_font(run, size=13, color=BLUE, bold=True)
    else:
        set_run_font(run, size=12, color=DARK_BLUE, bold=True)
    p.paragraph_format.keep_with_next = True
    return p


def add_para(doc, text, size=11, color=BLACK, bold=False, italic=False,
             align=WD_ALIGN_PARAGRAPH.LEFT, after=6, before=0, line=1.1):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = line
    run = p.add_run(text)
    set_run_font(run, size=size, color=color, bold=bold, italic=italic)
    return p


def add_label_para(doc, label, text, after=4):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.15
    r = p.add_run(label + "：")
    set_run_font(r, size=11, color=BLACK, bold=True)
    r = p.add_run(text)
    set_run_font(r, size=11, color=BLACK, bold=False)
    return p


def add_bullets(doc, items, style="List Bullet", size=10.5, after=3):
    for item in items:
        p = doc.add_paragraph(style=style)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(after)
        p.paragraph_format.line_spacing = 1.15
        if isinstance(item, tuple):
            r = p.add_run(item[0])
            set_run_font(r, size=size, color=BLACK, bold=True)
            r = p.add_run(item[1])
            set_run_font(r, size=size, color=BLACK, bold=False)
        else:
            r = p.add_run(item)
            set_run_font(r, size=size, color=BLACK, bold=False)
        p.style.font.name = LATIN_FONT
        rpr = p.style.element.get_or_add_rPr()
        rfonts = rpr.get_or_add_rFonts()
        rfonts.set(qn("w:ascii"), LATIN_FONT)
        rfonts.set(qn("w:hAnsi"), LATIN_FONT)
        rfonts.set(qn("w:eastAsia"), EAST_ASIAN_FONT)


def add_table(doc, headers, rows, widths, font_size=10, align_center_cols=None,
              caption=None, caption_before=True):
    if caption:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.0
        r = p.add_run(caption)
        set_run_font(r, size=9, color=MUTED, italic=False)
        if caption_before is False:
            p._element.getparent().remove(p._element)

    table = doc.add_table(rows=1, cols=len(headers))
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    set_table_geometry(table, widths)

    hdr = table.rows[0]
    set_repeat_header(hdr)
    for idx, header in enumerate(headers):
        cell = hdr.cells[idx]
        set_cell_shading(cell, TABLE_HEADER_FILL)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.05
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if (
            align_center_cols is None or idx in align_center_cols
        ) else WD_ALIGN_PARAGRAPH.LEFT
        r = p.add_run(header)
        set_run_font(r, size=font_size, color=BLACK, bold=True)

    for row_idx, row_data in enumerate(rows):
        row = table.add_row().cells
        for idx, value in enumerate(row_data):
            cell = row[idx]
            if row_idx % 2 == 1:
                set_cell_shading(cell, TABLE_ALT_FILL)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(3)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.08
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if (
                align_center_cols is not None and idx in align_center_cols
            ) else WD_ALIGN_PARAGRAPH.LEFT
            r = p.add_run(str(value))
            set_run_font(r, size=font_size, color=BLACK, bold=False)

    if caption and caption_before is False:
        cp = doc.add_paragraph()
        cp.paragraph_format.space_before = Pt(4)
        cp.paragraph_format.space_after = Pt(6)
        cp.paragraph_format.line_spacing = 1.0
        r = cp.add_run(caption)
        set_run_font(r, size=9, color=MUTED, italic=False)
    return table


def add_caption(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.0
    r = p.add_run(text)
    set_run_font(r, size=9, color=MUTED, italic=False)
    return p


def build_overview():
    doc = Document()
    configure_document(doc, "聆心平台项目概要介绍")
    add_cover(
        doc,
        "聆心平台项目概要介绍",
        "高校辅导员 AI 减负与心理预警一体化平台",
        [
            ("项目名称", "聆心平台"),
            ("文档类型", "项目概要介绍"),
            ("版本状态", "v1.0 / 评审稿"),
            ("编制日期", "2026-08-21"),
        ],
    )

    add_heading(doc, "一、项目介绍", 1)
    add_para(
        doc,
        "聆心是面向高校辅导员、学工处和学生的多模态心理辅助平台，将谈心记录、视频情绪识别、"
        "风险预警、危机工单、AI数字人、预约咨询和知识库串联为可追溯的闭环。项目聚焦辅导员文书"
        "负担重、学生心理风险发现不及时、跨角色处置不闭环三类问题，以“让辅导员把时间从写材料还给"
        "见学生”为目标，提供主动预警和规范处置能力。"
    )

    add_heading(doc, "二、核心功能", 1)
    add_bullets(
        doc,
        [
            ("心理预警闭环：", "测评、谈心、视频、数字人和预警处置统一回写学生状态，采用“取最高风险不降级”策略，形成风险证据时间线。"),
            ("多模态情绪识别：", "融合文本语义、语音韵律、人脸表情和量表结果，实时视频通话中形成连续情绪研判。"),
            ("AI数字人：", "老师离线时提供有温度的学生陪伴，支持危机识别、AI身份标注、TTS朗读和值班日志流转。"),
            ("危机工单中心：", "学工处可查看、指派和关闭跨角色危机工单，关闭后自动重新计算学生风险。"),
            ("情绪网络图：", "按风险、班级、学院聚类展示学生情绪分布，节点点击可直达学生聊天。"),
            ("预约咨询与待办：", "学生预约、老师确认后自动生成待办，完成后沉淀谈心记录。"),
            ("知识库问答：", "采用向量检索、BM25关键词和时间新鲜度混合检索，支撑规章制度与知识问答。"),
            ("通讯与文书：", "提供师生消息、谈心记录、班会策划和公文写作，Markdown安全渲染并支持打印导出。"),
        ],
    )

    add_heading(doc, "三、技术路线", 1)
    add_para(
        doc,
        "系统采用“浏览器SPA + Flask API + 多模型引擎 + SQLite”分层架构。前端使用Vue 3、ECharts、"
        "Socket.IO和WebRTC；后端使用Flask、SQLAlchemy、JWT与RBAC权限体系；情绪引擎融合emotion2vec"
        "语音情绪、YOLOv8-face人脸检测、transformers FER人脸表情和文本语义分析；生成式能力接入通义"
        "千问qwen-plus、qwen-vl-plus；知识库采用ChromaDB混合检索。核心链路为数据采集、情绪研判、风险"
        "聚合、预警工单、处置复核、证据归档，并通过pytest自动化回归和headless Edge前端冒烟测试保障质量。"
    )

    add_heading(doc, "四、预期成果", 1)
    add_para(
        doc,
        "项目形成可运行、可演示、可部署的心理健康一体化平台，覆盖17个主要功能页面。核心心理预警闭环"
        "完整可用；70项pytest自动化测试全部通过；61项账号与数据完整性校验通过；前端冒烟测试覆盖登录、"
        "辅导员工作台和学生测评三个关键页面。项目同时提供确定性演示数据、一键启动脚本、部署指南与安全"
        "指南，可在高校场景中进一步试点并采集辅导员工时节约、预警响应时效和危机干预闭环率等效果指标。"
    )

    add_heading(doc, "五、创新性说明", 1)
    add_bullets(
        doc,
        [
            ("多模态同源融合：", "将面部表情、语音韵律、文本语义和量表结果置于同一时间轴融合，降低单一模态误报。"),
            ("风险状态聚合取最高：", "持续保留危机信号，避免后续低风险记录覆盖此前的关键预警。"),
            ("AI数字人安全兜底：", "明确标注AI身份，危机语义识别后自动进入预警和工单，并由人工接管。"),
            ("跨角色危机工单闭环：", "将预警从“看到”延伸到“指派、处置、复核”，实现责任可追踪。"),
            ("本地优先隐私设计：", "语音情绪模型支持本地推理，音频数据不离开服务器，减少敏感数据外传。"),
        ],
    )

    add_heading(doc, "六、应用价值说明", 1)
    add_bullets(
        doc,
        [
            ("对辅导员：", "减少谈心记录、班会策划、公文写作等重复性工作，提升重点关注学生的识别效率。"),
            ("对学工处：", "形成跨学院风险总览和可追踪的危机工单，增强协同处置与审计能力。"),
            ("对学生：", "提供7×24陪伴、心理测评、预约咨询和主动求助入口，降低求助门槛。"),
            ("对学校：", "推动心理健康工作从经验驱动转向数据支撑、闭环留痕，提升风险防控与合规水平。"),
        ],
    )

    out = os.path.join(OUTPUT_DIR, "聆心平台项目概要介绍.docx")
    doc.save(out)
    return out


def build_design_book():
    doc = Document()
    configure_document(doc, "聆心平台设计方案书")
    add_cover(
        doc,
        "聆心平台设计方案书",
        "高校辅导员 AI 减负与心理预警一体化平台",
        [
            ("项目名称", "聆心平台"),
            ("文档版本", "v1.0"),
            ("文档状态", "评审稿"),
            ("编制日期", "2026-08-21"),
            ("适用对象", "评审、立项、实施与验收"),
        ],
    )

    add_heading(doc, "文档修订记录", 1)
    add_table(
        doc,
        ["版本", "日期", "修订说明", "编制"],
        [
            ["v1.0", "2026-08-21", "形成设计方案书初稿，覆盖需求、设计与测试结果。", "项目组"],
        ],
        widths=[0.8, 1.2, 3.5, 1.0],
        align_center_cols={0, 1, 3},
    )

    add_heading(doc, "目录", 1)
    toc_items = [
        "1 项目概述",
        "2 需求分析报告",
        "2.1 建设背景与问题分析",
        "2.2 用户角色与核心诉求",
        "2.3 功能需求",
        "2.4 非功能需求",
        "2.5 关键业务流程",
        "2.6 需求验收标准",
        "3 设计说明书",
        "3.1 设计原则",
        "3.2 总体架构",
        "3.3 技术选型",
        "3.4 功能模块设计",
        "3.5 数据模型设计",
        "3.6 接口与消息设计",
        "3.7 安全与合规设计",
        "3.8 前端与交互设计",
        "4 测试方案与结果",
        "4.1 测试策略",
        "4.2 测试环境",
        "4.3 功能测试用例与结果",
        "4.4 自动化测试结果",
        "4.5 情绪识别专项评测",
        "4.6 安全与兼容性测试",
        "4.7 缺陷回归说明",
        "4.8 测试结论",
        "5 部署与运行",
        "6 风险与改进路线",
        "7 结论",
    ]
    for item in toc_items:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.15
        r = p.add_run(item)
        set_run_font(r, size=10.5, color=BLACK, bold=False)

    doc.add_page_break()

    add_heading(doc, "1 项目概述", 1)
    add_label_para(doc, "系统定位", "面向高校辅导员、学工处、学生和超级管理员的AI减负与心理预警一体化平台。")
    add_label_para(doc, "建设目标", "实现辅导员文书减负、学生心理风险主动预警、跨角色危机工单闭环，以及工程可交付、可演示、可测试。")
    add_label_para(doc, "建设范围", "覆盖17个主要功能页面，包含师生通讯、谈心记录、班会策划、公文写作、情绪网络图、视频实时情绪、AI数字人、心理测评、预约咨询、风险预警和危机工单等。")
    add_label_para(doc, "关键说明", "系统定位为心理健康教育、陪伴与预警辅助工具，不替代心理咨询师或医生的专业诊断。")

    doc.add_page_break()
    add_heading(doc, "2 需求分析报告", 1)

    add_heading(doc, "2.1 建设背景与问题分析", 2)
    add_para(
        doc,
        "高校心理健康工作强调“预防为主、及时干预、规范处置”。实际工作中，辅导员既要处理大量谈心记录、"
        "班会策划和行政文书，又要从分散的谈话、测评、聊天和视频通话中识别潜在风险。传统方式存在四类问题："
    )
    add_bullets(
        doc,
        [
            "文书负担重：谈心、班会、公文等重复性材料耗费大量时间，压缩面对面陪伴。",
            "风险线索分散：测评、聊天、语音、表情和谈话记录各自独立，难以形成完整风险画像。",
            "危机处置不闭环：发现问题后，跨部门指派、处置和复核缺乏统一载体，责任边界不清。",
            "数据与安全要求高：心理健康数据属于敏感个人信息，需要权限隔离、访问审计和隐私保护。",
        ],
    )

    add_heading(doc, "2.2 用户角色与核心诉求", 2)
    add_table(
        doc,
        ["角色", "核心诉求", "主要关注点"],
        [
            ["超级管理员", "系统运行、账号与权限、全局监控", "安全、审计、数据一致性与可维护性"],
            ["学工处", "全校风险总览、危机工单分派、处置闭环", "跨学院协同、责任追踪、处理时效"],
            ["辅导员", "学生状态掌握、文书减负、主动预警", "本人学生范围、风险优先级、待办提醒"],
            ["学生", "便捷求助、测评预约、离线和危机陪伴", "可用性、隐私、及时响应"],
        ],
        widths=[1.1, 2.5, 2.9],
        align_center_cols={0},
    )
    add_caption(doc, "表2-1 用户角色与核心诉求")

    add_heading(doc, "2.3 功能需求", 2)
    add_table(
        doc,
        ["模块", "功能需求", "优先级"],
        [
            ["身份与权限", "多角色登录、JWT认证、辅导员数据隔离、操作审计", "高"],
            ["心理测评", "PHQ-9、GAD-7、ISI三量表，自动计分分级，第9项高危预警", "高"],
            ["风险预警", "多源风险回写、状态聚合取最高、证据时间线、预警状态机", "高"],
            ["危机工单", "跨角色查看、指派、关闭，关闭后重算风险", "高"],
            ["视频实时情绪", "WebRTC通话、人脸/语音/文本融合、通话总结回写", "高"],
            ["AI数字人", "离线回复、危机识别、AI身份标注、TTS、值班日志", "高"],
            ["情绪网络图", "按学院/班级/风险聚类、搜索筛选、节点跳转", "中"],
            ["预约咨询", "预约、确认、待办生成、完成沉淀谈心记录", "中"],
            ["知识库", "混合RAG检索、文档上传/查看/删除", "中"],
            ["通讯与文书", "师生消息、谈心记录、班会策划、公文写作、打印导出", "中"],
        ],
        widths=[1.2, 4.4, 0.9],
        align_center_cols={0, 2},
    )
    add_caption(doc, "表2-2 主要功能需求与优先级")

    add_heading(doc, "2.4 非功能需求", 2)
    add_bullets(
        doc,
        [
            ("安全：", "密码哈希、令牌黑名单、登录限流、RBAC权限、XSS防护、文件类型白名单。"),
            ("隐私：", "语音情绪模型支持本地推理，视频与音频默认不落盘，敏感数据最小化授权。"),
            ("性能：", "常规页面和接口响应满足演示与校内试点需求，关键操作失败时前端明确提示。"),
            ("可用性：", "模型或外部API不可用时自动降级，核心业务不因单个模型缺失而中断。"),
            ("可测试：", "核心闭环、权限、边界和前端关键页面均可自动化验证。"),
            ("可部署：", "提供一键启动、确定性演示数据、环境变量配置和部署安全说明。"),
        ],
    )

    add_heading(doc, "2.5 关键业务流程", 2)
    add_para(
        doc,
        "平台的核心业务闭环如下："
    )
    steps = [
        "采集：学生完成心理测评、发起聊天或视频通话，系统同步采集量表答案、文本、语音和面部表情。",
        "研判：情绪引擎对多模态信号进行识别，输出情绪类型、置信度、强度和风险等级。",
        "聚合：测评、谈心、视频、数字人和预警处置统一回写学生风险，采用取最高风险不降级策略。",
        "预警：达到高危阈值时生成预警记录，形成风险证据时间线，支持待处理、已确认、已解决状态流转。",
        "危机处置：自伤、自杀等高危线索进入危机工单中心，由学工处查看、指派和关闭。",
        "复核归档：处置完成后重新计算学生风险，所有操作与证据可追溯。",
    ]
    for idx, text in enumerate(steps, 1):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.15
        r = p.add_run(f"{idx}. ")
        set_run_font(r, size=10.5, color=BLACK, bold=True)
        r = p.add_run(text)
        set_run_font(r, size=10.5, color=BLACK, bold=False)

    add_heading(doc, "2.6 需求验收标准", 2)
    add_bullets(
        doc,
        [
            "核心闭环可从测评、谈心、视频、数字人到危机工单完整走通。",
            "辅导员只能访问本人管辖学生，跨学生访问被拒绝或返回空数据。",
            "PHQ-9第9项得分达到阈值时自动生成高危预警；未命中第9项但量表总分偏高时按规则生成中风险。",
            "预警状态机、危机工单指派与关闭、预约联动待办等关键业务通过自动化回归。",
            "登录页、辅导员工作台、学生测评等核心页面渲染成功，无白屏。",
            "登录账号、学生数量、网络图统计和数据库外键完整性校验全部通过。",
        ],
    )

    doc.add_page_break()
    add_heading(doc, "3 设计说明书", 1)

    add_heading(doc, "3.1 设计原则", 2)
    add_bullets(
        doc,
        [
            ("安全保守：", "心理风险研判采用宁高勿漏策略，风险只向更高级别聚合。"),
            ("可追溯：", "关键操作写入审计日志，风险变化保存证据来源、操作人和时间。"),
            ("角色隔离：", "权限控制同时覆盖接口层和数据层，避免越权访问。"),
            ("降级可用：", "外部模型不可用时以规则、声学特征或可理解回复兜底。"),
            ("模块化：", "前后端按业务域拆分，降低维护和回归风险。"),
        ],
    )

    add_heading(doc, "3.2 总体架构", 2)
    add_table(
        doc,
        ["层级", "技术/组件", "主要职责"],
        [
            ["表现层", "Vue 3 SPA、ECharts、Socket.IO、WebRTC", "页面交互、数据可视化、实时通讯、视频通话"],
            ["接口层", "Flask REST API、Socket.IO事件、RBAC装饰器", "业务路由、鉴权、参数校验、实时事件分发"],
            ["服务层", "prompt_engine、emotion_engine、rag_engine、digital_human、realtime_emotion", "文本生成、情绪识别、知识检索、数字人与实时融合"],
            ["数据层", "SQLAlchemy、SQLite、ChromaDB、文件存储", "业务数据持久化、向量索引、模型与文件管理"],
            ["模型层", "通义千问、emotion2vec、YOLOv8-face、transformers FER", "大模型生成、语音情绪、人脸检测与表情识别"],
        ],
        widths=[0.9, 2.7, 2.9],
        align_center_cols={0},
    )
    add_caption(doc, "表3-1 系统分层架构")

    add_heading(doc, "3.3 技术选型", 2)
    add_table(
        doc,
        ["类别", "选型", "选择理由"],
        [
            ["后端", "Python 3.10+ / Flask 3 / SQLAlchemy 2", "开发效率高、组件成熟、便于快速构建REST API"],
            ["前端", "Vue 3 + ECharts + Socket.IO + WebRTC", "SPA交互流畅，支持网络图、实时状态和视频通话"],
            ["数据存储", "SQLite + SQLAlchemy + ChromaDB", "演示部署轻量，向量检索支撑知识库"],
            ["大模型", "通义千问 qwen-plus / qwen-vl-plus", "中文能力稳定，支持文本生成与图片理解"],
            ["语音情绪", "emotion2vec_plus_large / FunASR", "开源本地推理，减少音频外传"],
            ["人脸情绪", "YOLOv8n-face + transformers FER", "兼顾人脸检测速度与表情分类"],
            ["测试", "pytest + headless Edge", "后端回归与前端页面冒烟双重保障"],
        ],
        widths=[1.0, 2.4, 3.1],
        align_center_cols={0},
    )
    add_caption(doc, "表3-2 技术选型")

    add_heading(doc, "3.4 功能模块设计", 2)
    add_table(
        doc,
        ["模块", "关键功能", "数据交互"],
        [
            ["认证与权限", "登录、登出、令牌黑名单、角色与数据隔离", "users、token_blacklist、system_logs"],
            ["心理测评", "PHQ-9/GAD-7/ISI自动计分与风险回写", "assessment_results、students、alert_logs"],
            ["预警管理", "风险聚合、证据时间线、预警状态机", "student_risk_evidence、alert_logs、students"],
            ["危机工单", "查看、指派、升级、关闭、关闭后重算", "alert_logs、students、system_logs"],
            ["视频实时情绪", "WebRTC信令、多模态融合、通话总结", "emotion_logs、students、reminders"],
            ["AI数字人", "离线回复、危机识别、TTS、值班日志", "digital_human_settings、digital_human_logs、messages"],
            ["预约与待办", "预约确认、待办生成、谈心记录沉淀", "appointments、todos、student_profiles"],
            ["知识库", "文档管理、向量+BM25+新鲜度检索", "ChromaDB、knowledge_documents"],
        ],
        widths=[1.2, 2.8, 2.5],
        align_center_cols={0},
    )
    add_caption(doc, "表3-3 功能模块设计")

    add_heading(doc, "3.5 数据模型设计", 2)
    add_para(
        doc,
        "数据库包含用户、学生、风险证据、情绪日志、预警、测评、预约、待办、消息、数字人和审计等14类核心表。"
        "学生风险不单独依赖单一记录，而由student_risk_evidence按来源聚合，保留来源、等级、描述、操作人和时间。"
    )
    add_table(
        doc,
        ["数据域", "主要数据表", "关键说明"],
        [
            ["用户与权限", "users、students、user_presence", "三级教师角色、学生归属辅导员、在线状态"],
            ["风险评估", "student_risk_evidence、alert_logs、emotion_trackers", "多源证据、风险聚合、预警审计"],
            ["业务协同", "messages、appointments、reminders、todos", "师生消息、预约、提醒与待办联动"],
            ["心理测评", "assessment_results", "PHQ-9、GAD-7、ISI分数与等级"],
            ["谈话与档案", "conversation_records、student_profiles", "谈心记录、结构化总结与跟进档案"],
            ["数字人", "digital_human_settings、digital_human_logs", "人格化设置、AI回复与危机日志"],
            ["安全审计", "system_logs、token_blacklist", "操作日志与登出令牌"],
        ],
        widths=[1.1, 2.7, 2.7],
        align_center_cols={0},
    )
    add_caption(doc, "表3-4 核心数据域")

    add_heading(doc, "3.6 接口与消息设计", 2)
    add_para(
        doc,
        "平台采用REST JSON接口处理业务请求，Socket.IO处理在线状态、消息、预警和视频通话信令。接口统一使用"
        "JWT鉴权，敏感操作增加角色校验与数据归属校验。代表性接口如下："
    )
    add_table(
        doc,
        ["接口", "方法", "说明"],
        [
            ["/api/auth/login", "POST", "用户登录并返回令牌"],
            ["/api/assessment/submit", "POST", "提交测评并计算等级与风险"],
            ["/api/alert/list", "GET", "按角色返回预警列表"],
            ["/api/alert/acknowledge", "POST", "确认预警"],
            ["/api/alert/resolve", "POST", "解决预警并重算风险"],
            ["/api/crisis/list", "GET", "危机工单列表"],
            ["/api/crisis/assign", "POST", "指派危机工单"],
            ["/api/conversation/generate-report", "POST", "生成结构化谈心报告"],
            ["/api/knowledge/search", "GET", "知识库混合检索"],
            ["/api/system/dashboard", "GET", "工作台汇总数据"],
        ],
        widths=[2.6, 0.8, 3.1],
        align_center_cols={1},
    )
    add_caption(doc, "表3-5 代表性接口")

    add_heading(doc, "3.7 安全与合规设计", 2)
    add_bullets(
        doc,
        [
            "密码采用pbkdf2:sha256加盐哈希，登出令牌进入黑名单。",
            "路由级RBAC装饰器与数据级辅导员归属隔离双重控制。",
            "登录失败基于IP进行限流，关键操作写入system_logs。",
            "Markdown通过DOMPurify清理后渲染，防止XSS。",
            "生产环境强制配置SECRET_KEY和HTTPS，敏感数据导出建议脱敏。",
            "明确知情同意、目的限制、危机干预义务和数据删除权。",
        ],
    )

    add_heading(doc, "3.8 前端与交互设计", 2)
    add_bullets(
        doc,
        [
            "工作台优先展示学生总数、风险分布、待办和日历，便于辅导员快速进入处置。",
            "情绪网络图以颜色编码风险，按学院、班级聚类，点击节点直达学生聊天。",
            "学生端以测评、预约、个人中心和联系老师为主路径，移动端重点保证可用性。",
            "数字人回复明确标注AI身份，危机内容使用强提醒并进入人工处置。",
            "关键操作失败通过Toast提示，轮询和上传等非关键请求保持静默。",
        ],
    )

    doc.add_page_break()
    add_heading(doc, "4 测试方案与结果", 1)

    add_heading(doc, "4.1 测试策略", 2)
    add_para(
        doc,
        "测试采用风险导向与分层验证相结合：自动化pytest覆盖后端核心闭环、权限、边界和异常；前端冒烟覆盖"
        "关键页面渲染；专项脚本验证账号、数据完整性和情绪识别基线。功能测试与回归测试作为评审交付依据。"
    )

    add_heading(doc, "4.2 测试环境", 2)
    add_table(
        doc,
        ["项目", "环境/版本"],
        [
            ["操作系统", "Windows 10/11"],
            ["验证Python", "Python 3.13.9（项目要求Python 3.10+）"],
            ["后端", "Flask 3、SQLAlchemy 2、SQLite、ChromaDB"],
            ["浏览器", "Microsoft Edge headless"],
            ["自动化", "pytest 8、scripts/verify_test_accounts.py、scripts/smoke_frontend.py"],
            ["情绪评测", "tools/benchmark_emotion.py（文本关键词基线）"],
        ],
        widths=[1.2, 5.3],
        align_center_cols={0},
    )
    add_caption(doc, "表4-1 测试环境")

    add_heading(doc, "4.3 功能测试用例与结果", 2)
    add_table(
        doc,
        ["测试项", "验证内容", "结果"],
        [
            ["登录鉴权", "未登录访问受保护接口返回401；登录成功返回令牌", "通过"],
            ["权限隔离", "辅导员访问非本人学生返回拒绝或空数据", "通过"],
            ["测评高危", "PHQ-9第9项得分达到阈值生成high风险与预警", "通过"],
            ["测评中风险", "PHQ-9总分≥10但第9项未命中，生成medium风险", "通过"],
            ["预警状态机", "待处理→已确认→已解决，重复确认返回400", "通过"],
            ["危机工单", "查看、指派、关闭，关闭后重新计算风险", "通过"],
            ["数字人危机", "危机语义识别后生成预警并进入值班日志", "通过"],
            ["预约联动", "预约确认生成待办，完成生成谈心记录", "通过"],
            ["学生工作台", "辅导员工作台显示学生总数、待办和日历", "通过"],
            ["前端关键页", "登录、辅导员工作台、学生测评页面正常渲染", "通过"],
        ],
        widths=[1.1, 4.3, 1.1],
        align_center_cols={0, 2},
    )
    add_caption(doc, "表4-2 功能测试用例与结果")

    add_heading(doc, "4.4 自动化测试结果", 2)
    add_table(
        doc,
        ["测试项", "结果", "说明"],
        [
            ["pytest后端回归", "70 passed，0 failed", "耗时34.72s，覆盖闭环、权限、边界和路由"],
            ["账号与数据校验", "61项通过，0项失败", "覆盖账号、学生数量、密码、外键和网络图统计"],
            ["前端冒烟", "3项关键页面通过", "登录页、辅导员工作台、学生测评页均渲染成功"],
            ["控制台提示", "1项非阻断提示", "页面请求返回401，未影响核心页面验证"],
        ],
        widths=[1.4, 1.8, 3.3],
        align_center_cols={0, 1},
    )
    add_caption(doc, "表4-3 自动化测试结果")

    add_heading(doc, "4.5 情绪识别专项评测", 2)
    add_para(
        doc,
        "文本情绪关键词基线评测覆盖8类情绪、16个样本，结果如下。该结果用于验证文本基线规则的一致性，"
        "不代表真实语音或视频情绪模型在开放数据上的最终准确率。"
    )
    add_table(
        doc,
        ["指标", "结果"],
        [
            ["评测模式", "文本情绪（关键词基线）"],
            ["样本数量", "16"],
            ["情绪类别", "低落、压抑、恐惧、悲伤、愤怒、正常、焦虑、高兴，共8类"],
            ["准确率", "100.00%"],
            ["宏F1", "100.00%"],
        ],
        widths=[1.5, 5.0],
        align_center_cols={0},
    )
    add_caption(doc, "表4-4 文本情绪识别基线评测")

    add_heading(doc, "4.6 安全与兼容性测试", 2)
    add_bullets(
        doc,
        [
            "XSS防护：Markdown内容经DOMPurify清理后渲染。",
            "密码安全：密码哈希、登录限流和登出令牌黑名单均已实现。",
            "文件上传：限制大小与类型，超出大小返回413。",
            "响应式：桌面端主要页面正常，移动端重点支持学生聊天与测评。",
            "降级能力：外部模型不可用时核心页面仍可访问，情绪识别返回可说明的降级结果。",
        ],
    )

    add_heading(doc, "4.7 缺陷回归说明", 2)
    add_para(
        doc,
        "历史开发中曾出现辅导员工作台接口崩溃和学生端测评、预约、个人中心空白两类P0缺陷，根因分别为待办"
        "数据模型缺少学生关系映射、前端模板缺少闭合标签。修复后已纳入回归测试与前端冒烟，当前相关页面与"
        "接口均通过验证。"
    )

    add_heading(doc, "4.8 测试结论", 2)
    add_para(
        doc,
        "当前版本达到评审与演示验收条件：核心心理预警闭环可完整走通，权限隔离、危机工单、预约联动和前端"
        "关键页面均有自动化或脚本化证据。后端70项测试全绿，账号与数据完整性61项校验通过，未发现阻断性"
        "缺陷。后续在真实高校试点阶段需补充真机兼容、多用户并发、真实音频/视频样本和第三方安全测评。"
    )

    doc.add_page_break()
    add_heading(doc, "5 部署与运行", 1)
    add_bullets(
        doc,
        [
            "安装依赖并配置.env中的SECRET_KEY与DASHSCOPE_API_KEY。",
            "运行演示一键启动.bat或run_demo.sh，初始化数据库并生成确定性演示数据。",
            "访问http://127.0.0.1:5000，使用管理员、学工处、辅导员或学生测试账号登录。",
            "运行python -m pytest tests/ -q、python scripts/verify_test_accounts.py和python scripts/smoke_frontend.py进行回归验证。",
            "生产环境启用HTTPS，修改默认口令，配置WebRTC所需的TURN服务器，并做好数据库备份。",
        ],
    )

    add_heading(doc, "6 风险与改进路线", 1)
    add_table(
        doc,
        ["风险/局限", "影响", "缓解与改进"],
        [
            ["情绪识别模型类别映射损失", "中文细粒度情绪识别能力受限", "接入SenseVoice或细粒度中文情绪模型"],
            ["人脸表情依赖首次联网下载", "无网环境可能返回未知", "模型预置、离线缓存和明确降级提示"],
            ["实时微表情/姿态为规则加权", "开放场景泛化需验证", "采集真实标注样本并开展第三方评测"],
            ["文本内容需经云端API", "数据完全不出校尚需补强", "引入本地化LLM部署"],
            ["缺乏真实试点数据", "效果指标有待验证", "与高校合作试点，统计减负与干预指标"],
        ],
        widths=[1.8, 1.8, 2.9],
        align_center_cols={0, 1},
    )
    add_caption(doc, "表6-1 风险与改进路线")

    add_heading(doc, "7 结论", 1)
    add_para(
        doc,
        "聆心平台将AI文书辅助、多模态心理预警、数字人陪伴和危机工单处置整合为统一闭环，兼顾辅导员减负、"
        "学生关怀和学校合规管理。当前版本已完成需求分析、架构设计、功能实现、自动化测试与关键专项评测，"
        "具备进入演示、评审和高校试点的条件。后续将围绕真实数据验证、模型细粒度提升、本地化部署与效果"
        "评估持续迭代。"
    )

    out = os.path.join(OUTPUT_DIR, "聆心平台设计方案书.docx")
    doc.save(out)
    return out


def main():
    overview_path = build_overview()
    design_path = build_design_book()
    print(overview_path)
    print(design_path)


if __name__ == "__main__":
    main()
