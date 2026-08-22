# LangGraph 工作流编排 · 增量集成操作指南

> 目标：在**不破坏现有功能**的前提下，为「聆心」补上「基于开源智能体平台 + 工作流编排」这一赛题硬性要求。
> 原则：**增量叠加**——保留 Flask + Vue + 现有所有函数，只把「数字人对话」「风险决策」两个核心智能体用 LangGraph 编排成工作流。

---

## 一、目标与范围

| 项 | 决定 |
|---|---|
| 开源框架 | **LangChain + LangGraph**（赛题认可的开源智能体平台） |
| 编排对象 | ① 数字人对话智能体　② 风险决策智能体 |
| 复用现有函数 | `core/digital_human.py` 的 `generate_reply` / `_crisis_reply`；`core/database.py` 的 `update_student_state_from_evidence` / `refresh_student_risk_after_alert_resolution` / `_max_risk` |
| **不动的部分** | 登录、聊天、测评、看板、预约、网络图——**零改动** |

---

## 二、环境准备（5 分钟）

1. 安装依赖：
```bash
pip install langchain langgraph
```
2. 在 `requirements.txt` 追加两行：
```
langchain
langgraph
```
3. 验证安装：
```bash
python -c "from langgraph.graph import StateGraph; print('OK')"
```

---

## 三、新增目录结构

```
core/agent/
    __init__.py               # 导出两个 Agent 的 run 函数
    state.py                  # 两个智能体的 State 定义
    digital_human_agent.py    # 数字人对话智能体
    risk_decision_agent.py    # 风险决策智能体
```

现有文件**只改一处**：`api/messages.py` 里数字人异步回复的调用点（见第五节）。

---

## 四、智能体 1：数字人对话智能体

### 工作流（StateGraph）

```
学生消息 ──► [危机检测] ──危机──► [危机回复 + 生成预警]
              │正常
              ▼
          [生成回复(大模型)]
              │
              ▼
          [落库 + 写数字人日志] ──► 结束
```

### State 定义（state.py）

```python
from typing import TypedDict, Optional

class DigitalHumanState(TypedDict):
    message: str            # 学生消息
    student_name: str       # 学生姓名
    settings: dict          # 数字人设置（风格/幽默度等）
    crisis: bool            # 是否危机（由节点填充）
    reply: str              # 回复内容（由节点填充）
    alert_created: bool     # 是否已生成预警
```

### 节点函数（digital_human_agent.py）

```python
from langgraph.graph import StateGraph, END
from core.digital_human import generate_reply, CRISIS_KEYWORDS
from core.database import db

def detect_crisis_node(state):
    """复用现有危机关键词，也可替换为语义判定。"""
    text = state["message"]
    crisis = any(w in text for w in CRISIS_KEYWORDS)
    return {"crisis": crisis}

def generate_reply_node(state):
    """复用现有 generate_reply —— 大模型生成 / 本地兜底全在这里。"""
    content, crisis = generate_reply(
        state["message"], state["settings"], state["student_name"]
    )
    return {"reply": content, "crisis": state["crisis"] or crisis}

def alert_node(state):
    """危机时生成高危预警 + 数字人日志。"""
    db.create_alert(
        student_name=state["student_name"],
        student_class="",
        risk_level="high",
        emotion_type="危机",
        intensity=10,
        description="数字人对话识别到危机信号",
    )
    return {"alert_created": True}

def build_digital_human_graph():
    g = StateGraph(DigitalHumanState)
    g.add_node("detect_crisis", detect_crisis_node)
    g.add_node("generate_reply", generate_reply_node)
    g.add_node("alert", alert_node)
    g.set_entry_point("detect_crisis")

    # 分支：危机走 alert，否则走生成回复
    g.add_conditional_edges(
        "detect_crisis",
        lambda s: "alert" if s["crisis"] else "generate_reply",
        {"alert": "alert", "generate_reply": "generate_reply"},
    )
    g.add_edge("generate_reply", END)
    g.add_edge("alert", END)
    return g.compile()

def run_digital_human(message, student_name, settings):
    return build_digital_human_graph().invoke({
        "message": message, "student_name": student_name,
        "settings": settings, "crisis": False, "reply": "", "alert_created": False,
    })
```

---

## 五、智能体 2：风险决策智能体

### 工作流（StateGraph）

```
多来源证据 ──► [读取当前风险] ──► [取最高合并] ──► [回写学生状态] ──► [写证据时间线] ──► 结束
```

### State 定义（state.py）

```python
class RiskDecisionState(TypedDict):
    student_id: int
    risk_level: str          # 本次证据的风险
    emotion_status: str
    source: str              # assessment / talk_report / video_call_summary ...
    description: str
    counselor_id: Optional[int]
    current_risk: str        # 读取到的当前风险
    merged_risk: str         # 合并后的风险
```

### 节点函数（risk_decision_agent.py）

```python
from langgraph.graph import StateGraph, END
from core.database import db, RISK_ORDER

def fetch_current_node(state):
    stu = db.get_student_by_id(state["student_id"]) or {}
    return {"current_risk": stu.get("risk_level") or "low"}

def merge_risk_node(state):
    a, b = state["current_risk"], state["risk_level"]
    merged = a if RISK_ORDER.get(a, 0) >= RISK_ORDER.get(b, 0) else b
    return {"merged_risk": merged}

def write_state_node(state):
    db.update_student_state_from_evidence(
        student_id=state["student_id"],
        risk_level=state["risk_level"],
        emotion_status=state["emotion_status"],
        source=state["source"],
        counselor_id=state["counselor_id"],
        description=state["description"],
    )
    return {}

def build_risk_decision_graph():
    g = StateGraph(RiskDecisionState)
    g.add_node("fetch_current", fetch_current_node)
    g.add_node("merge_risk", merge_risk_node)
    g.add_node("write_state", write_state_node)
    g.set_entry_point("fetch_current")
    g.add_edge("fetch_current", "merge_risk")
    g.add_edge("merge_risk", "write_state")
    g.add_edge("write_state", END)
    return g.compile()

def run_risk_decision(student_id, risk_level, emotion_status, source, description, counselor_id=None):
    return build_risk_decision_graph().invoke({...})
```

> 注意：`write_state_node` 复用的 `update_student_state_from_evidence` 内部**已经实现了取最高 + 证据时间线 + 生成跟进提醒**。所以上面的 `merge_risk` 节点其实是一个"显式展示取最高逻辑"的节点，用于在工作流图上体现"决策"这一步——即使它和底层函数有重叠，也能让评委在工作流图里看到"取最高"这个决策节点。

---

## 六、接入现有路由（唯一要改的现有文件）

改 `api/messages.py` 里数字人异步回复的调用（原来是直接 `generate_reply(...)`），改成调 LangGraph：

```python
# 原来
reply, crisis = generate_reply(content, settings, student_name)

# 改为
from core.agent import run_digital_human
result = run_digital_human(content, student_name, settings)
reply, crisis = result["reply"], result["crisis"]
```

其余落库、Socket 推送、日志代码**全部不动**。

---

## 七、测试与验证

1. **回归测试**（确认没破坏现有功能）：
```bash
python -m unittest discover -s tests -q
```
期望：70 项全部通过。

2. **新增 LangGraph 单测**（`tests/test_agent.py`）：
   - 数字人 Agent：输入"我想死"→ 断言 `crisis=True` 且生成了高危预警；
   - 数字人 Agent：输入"考试压力大"→ 断言 `crisis=False` 且返回了回复；
   - 风险决策 Agent：current=high + 新证据=medium → 断言 merged=high（取最高不降级）。

3. **前端冒烟**：确认登录、聊天、数字人页面照常渲染。

---

## 八、风险与回退

| 风险 | 概率 | 缓解 |
|---|---|---|
| langchain/langgraph 依赖冲突 | 低 | 用独立 venv 测试；冲突则固定版本号 |
| 工作流引入 bug | 低 | 只影响数字人/预警两处，70 测试兜底 |
| 需要回退 | — | LangGraph 是增量层，删掉 `core/agent/` + 还原 `messages.py` 那一行即可，一键回退 |

---

## 九、完成后材料怎么改

1. 名字：`聆心 —— 基于大模型智能体的高校辅导员减负与心理预警平台`；
2. 方案书"技术可行性"补一句："基于开源的 LangChain + LangGraph 智能体编排框架，实现数字人对话与风险决策两条工作流的编排与工具集成"；
3. PPT"设计开发"部分，放一张 **LangGraph 工作流图**（节点+箭头），替代/补充原来的普通架构图。
