"""聚合注册入口：所有业务路由拆分到 api/*.py，行为保持兼容。"""
from api import common as _common
from api.common import api, set_socketio, init_services  # noqa: F401
from api import (
    alert,
    appointments,
    assessment,
    auth,
    conversation,
    emotion,
    knowledge,
    messages,
    network,
    realtime,
    student,
    system,
    workplan,
)  # noqa: F401


def __getattr__(name):
    """Keep `from api.routes import db` compatible after service init."""
    if name == "db":
        return _common.db
    raise AttributeError(name)
