# 聆心 v3.0

> **高校辅导员AI减负与心理预警一体化平台**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-green.svg)](https://flask.palletsprojects.com)
[![License](https://img.shields.io/badge/License-MIT-orange.svg)](#)

---

## ✨ v3.0 新特性

- 🌙 **深色/浅色模式** - 支持一键切换深色和浅色主题，自动保存用户偏好
- 🎨 **现代化UI** - 全新设计的界面，采用渐变色彩和圆润卡片设计
- 📱 **响应式布局** - 适配不同屏幕尺寸，支持移动端访问
- 🚀 **性能优化** - 优化前端渲染和API响应速度

---

## 项目简介

**聆心** 是面向高校辅导员的 AI 辅助工作平台，基于 RAG 检索增强生成、语音情绪识别、多场景提示词工程等技术，为辅导员日常工作提供智能化支持。

### 核心功能

| 功能 | 说明 | 技术实现 |
|------|------|---------|
| **AI 谈心助手** | 自动生成结构化谈心记录，支持多种工作场景 | 多场景 Prompt |
| **语音情绪识别** | 上传音频自动识别学生情绪状态 | emotion2vec 模型 + 声学特征降级 |
| **RAG 知识库** | 基于学校规章制度文档的智能问答 | ChromaDB + BM25 混合检索 |
| **风险预警系统** | 自动识别高风险学生并生成预警 | 规则引擎 + AI 分析 |
| **数据可视化** | 情绪趋势、风险分布、工作统计等图表 | ECharts 可视化 |
| **权限管理** | 三级角色权限控制：管理员/学工/辅导员 | JWT 认证 |
| **深色模式** | 支持深色/浅色主题切换 | CSS变量 + localStorage |

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Node.js（仅开发环境需要）
- 有效的 DashScope API Key

### 安装步骤

```bash
# 1. 克隆项目
git clone <repo-url>
cd 聆心-代码文件

# 2. 创建虚拟环境
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Mac/Linux

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
copy .env.example .env
# 编辑 .env 文件配置 DASHSCOPE_API_KEY

# 5. 启动服务
python app.py
```

访问 http://localhost:5000

### Windows 快捷启动

双击 `启动平台.bat` 即可一键启动，自动检测环境并运行服务。

---

## 🔑 测试账号

| 角色 | 用户名 | 密码 | 权限范围 |
|------|--------|------|---------|
| 超级管理员 | admin | admin123 | 全部功能 |
| 学工处 | liuxin | staff123 | 学生管理+预警 |
| 辅导员 | zhangwei | counsel123 | 个人学生管理 |

---

## 📁 项目结构

```
聆心-代码文件/
├── app.py                 # Flask 应用入口
├── config/
│   └── config.py          # 统一配置模块
├── core/
│   ├── database.py        # 数据库模型与管理
│   ├── emotion_engine.py  # 情绪识别引擎
│   ├── prompt_engine.py   # 提示词工程引擎
│   └── rag_engine.py      # RAG 知识库引擎
├── api/
│   └── routes.py          # RESTful API 路由
├── templates/
│   └── index.html         # 前端单页应用（Vue 3 SPA）
├── static/                # 静态资源
├── data/                  # 数据库与向量库
├── docs/                  # 文档资料
├── requirements.txt       # Python 依赖
├── .env.example           # 环境变量模板
└── 启动平台.bat            # Windows 启动脚本
```

---

## 🎯 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                前端 (Vue 3 + ECharts)                       │
├─────────────────────────────────────────────────────────────┤
│              Flask RESTful API Layer                         │
├─────────────────────────────────────────────────────────────┤
│  Prompt    │  Emotion   │  RAG        │  Database           │
│  Engine    │  Engine    │  Engine     │  Manager            │
├─────────────────────────────────────────────────────────────┤
│  DashScope │ SenseVoice │ ChromaDB    │ SQLite/SQLAlchemy   │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 API 文档

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 用户登录 |
| GET | `/api/system/dashboard` | 仪表盘数据 |
| POST | `/api/conversation/organize` | AI整理谈心记录 |
| POST | `/api/conversation/recognize-image` | 截图识别 |
| POST | `/api/emotion/analyze` | 语音情绪分析 |
| GET | `/api/emotion/logs` | 情绪日志查询 |
| GET | `/api/alert/list` | 预警列表 |
| PUT | `/api/alert/:id/acknowledge` | 确认预警 |
| GET | `/api/knowledge/stats` | 知识库统计 |
| POST | `/api/knowledge/upload` | 上传知识文档 |
| POST | `/api/system/export` | 数据导出 |

---

## 🛠️ 核心技术

1. **多场景提示词引擎** - 谈心记录 + 班会策划 + 公文写作等多场景模板
2. **混合RAG检索** - 向量检索 + BM25关键词检索 + 时间新鲜度加权
3. **智能 AI 对话** - 基于大语言模型的自然语言处理，场景化 Prompt 管理
4. **语音情绪识别** - 真实开源模型（emotion2vec）本地推理，模型不可用时自动降级为声学特征 + LLM 研判，支持批量处理
5. **数据可视化** - ECharts 图表展示情绪趋势、风险分布等

---

## 📝 更新日志

### v3.0 (2026-07)
- ✨ 新增深色/浅色模式切换
- 🎨 全新现代化UI设计
- 📱 响应式布局优化
- 🚀 性能优化与bug修复

### v2.0
- 🎤 语音情绪识别功能
- 📚 RAG知识库系统
- 🚨 风险预警系统
- 📊 数据可视化看板

---

## License

MIT
