# 聆心 · 高校辅导员 AI 减负与心理预警一体化平台

> 面向高校辅导员、学工处与学生的多模态心理辅助平台。平台把「谈心记录、视频情绪识别、风险预警、危机工单、AI 数字人、预约咨询」串成一条可追溯的闭环，让每一次学生状态变化都有证据、有通知、有处置。

## 核心功能

| 模块 | 能力 |
|---|---|
| 情绪网络图 | 以辅导员或全校视角展示学生情绪风险分布，按风险/班级/学院聚类，点击节点直达学生聊天 |
| 视频实时情绪 | 视频通话中融合微表情、语音韵律与后端模型，生成实时情绪和通话总结，并回写学生风险状态 |
| 数字人 | 老师离线时由 AI 分身幽默、亲切地回复学生；支持危机识别、AI 身份标注、TTS 朗读、值班日志流转 |
| 心理预警闭环 | 测评、谈心、视频、数字人、预警处置统一回写学生状态，取最高风险不降级，证据可溯源 |
| 危机工单 | 学工处/管理员可查看、指派、关闭跨角色危机工单，关闭后自动重算学生风险 |
| 知识库 | RAG 混合检索（向量 + BM25 + 新鲜度），文档上传/查看/删除 |
| 预约咨询 | 学生预约、老师确认后自动生成待办，完成后沉淀谈心记录 |
| 通讯与报告 | 师生消息、AI 谈心记录、班会策划、公文写作，Markdown 安全渲染与打印导出 |

## 技术架构

```mermaid
flowchart TB
    U[浏览器端 Vue 3 SPA] -->|REST / Socket.IO| F[Flask API]
    F --> DB[(SQLite + SQLAlchemy)]
    F --> AUTH[JWT 登录与角色权限]
    F --> DH[AI 数字人]
    F --> RAG[知识库 RAG]
    F --> EMO[情绪引擎]
    EMO --> SENSE[SenseVoice / emotion2vec]
    EMO --> VISION[face-api / YOLO]
    F --> LLM[DashScope / OpenAI]
    U --> NET[ECharts 情绪网络图]
    U --> RT[WebRTC 视频通话]
```

主要目录：

```text
api/routes.py              REST API、危机工单、Socket.IO 事件
core/database.py           SQLAlchemy 模型、状态聚合、风险证据
core/digital_human.py      数字人回复与危机识别
core/emotion_engine.py     语音情绪识别
core/rag_engine.py         知识库检索
static/js/app.js           前端主应用
static/js/network-graph.js 情绪网络图
static/js/realtime/*        实时情绪检测与融合
templates/index.html       Vue 3 单页界面
```

## 快速开始

### Windows 一键启动

双击 `演示一键启动.bat`，脚本会检查 Python/依赖、初始化数据库、必要时生成确定性演示数据，并打印访问地址和测试账号。

也可以使用原有入口 `启动平台.bat`。

### Linux / macOS

```bash
chmod +x run_demo.sh
./run_demo.sh
```

### 手动启动

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # 按需填写 DASHSCOPE_API_KEY
python app.py
```

访问 `http://127.0.0.1:5000`。

## 测试账号

种子数据为确定性数据，每名辅导员固定 50 名学生。角色和示例账号如下：

| 角色 | 账号 | 密码 |
|---|---|---|
| 超级管理员 | `admin` | `admin123` |
| 学工处 | `liuxin` | `staff123` |
| 学工处 | `student_affairs` | `staff123` |
| 辅导员 | `zhangwei`、`liuqiang`、`wangli`、`zhaolei`、`chenjing`、`yangfan`、`huangwei`、`zhoujie`、`sunpeng`、`wuxiaolin`、`zhengyu`、`tangli` | `counsel123` |
| 学生 | `20240001` 等，具体账号由 `seed_v31.py` 输出 | `123456` |

登录页会通过 `/system/test-accounts` 动态拉取完整账号，不依赖前端硬编码。

## 测试与验证

```bash
python -m pytest tests/ -q
python scripts/verify_test_accounts.py
python scripts/smoke_frontend.py
```

当前测试覆盖：

- 核心闭环：测评 high -> 谈心 medium -> 风险仍为 high -> 预警解决后重算；
- 数字人危机识别、AI 回复落库与预警生成；
- 预警状态机、危机工单指派与关闭；
- 测评边界、预约联动、权限隔离、风险证据时间线；
- 路由与前端页面冒烟。

## 安全说明

- Markdown 统一通过 `DOMPurify.sanitize(marked.parse(...))` 后再渲染；
- 密码使用 Werkzeug 哈希存储；
- `.env`、`data/*.db`、模型文件已加入 `.gitignore`；
- 关键 API 请求失败会触发前端 Toast，不再静默吞错。

## 更新记录

- `v3.2.1`：修复会话整理引擎未初始化（批量整理/上传文档 AI 整理失效）、视频通话拒绝无回执、语音情绪无 API key 时 500（改为声学保守判定兜底）、教师端未读徽标与知识库文档数占位；新增 `scripts/test_all_accounts.py` 全账号实测脚本；演示数据治理（清理测试残留与灌水、补录测评/预约/档案/危机工单/多源风险证据链）；
- `v3.2`：AI 数字人、危机工单、风险证据时间线、预约闭环、XSS 防护、测试补齐；
- `v3.1`：情绪网络图、实时情绪融合、在线状态；
- `v3.0`：深色模式、现代化 UI、响应式布局。
