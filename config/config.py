"""聆心 - 高校辅导员 AI 辅助平台
应用配置模块
"""

import os
import secrets

from dotenv import load_dotenv

load_dotenv()


class ApplicationConfig:
    APP_NAME: str = "聆心"
    VERSION: str = "3.2"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    DATABASE_URI: str = os.getenv("DATABASE_URI", "sqlite:///data/campus_mind.db")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "5000"))


class LLMConfig:
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
    BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DEFAULT_MODEL: str = "qwen-plus"
    TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "2000"))


class RAGConfig:
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 100
    TOP_K: int = 3
    EMBEDDING_MODEL: str = "text-embedding-v2"
    PERSIST_DIR: str = "./data/chroma_db"
    COLLECTION_NAME: str = "school_knowledge"


class EmotionConfig:
    MODEL_ID: str = "iic/SenseVoiceSmall"
    SAMPLE_RATE: int = 16000
    HIGH_RISK_EMOTIONS: list = ["焦虑", "压抑", "恐惧", "愤怒", "悲伤"]
    HIGH_RISK_THRESHOLD: int = 7
    # 实时分析配置
    REALTIME_CHUNK_DURATION: float = 2.0       # 每段音频时长(秒)
    REALTIME_CONSECUTIVE_ALERT_THRESHOLD: int = 3  # 连续高风险才触发告警
    REALTIME_MIN_CONFIDENCE_LLM: float = 0.65  # 低于此置信度调用LLM


class AgoraConfig:
    APP_ID: str = os.getenv("AGORA_APP_ID", "")
    TOKEN: str = os.getenv("AGORA_TOKEN", "")
    APP_CERT: str = os.getenv("AGORA_APP_CERT", "")
    TOKEN_EXPIRE_HOURS: int = int(os.getenv("AGORA_TOKEN_EXPIRE_HOURS", "24"))


class SecurityConfig:
    ROLES: list = ["super_admin", "student_affairs", "counselor"]
    TOKEN_EXPIRE_HOURS: int = 24
    LOG_RETENTION_DAYS: int = 90


def load_config():
    return {
        "app": ApplicationConfig(),
        "llm": LLMConfig(),
        "rag": RAGConfig(),
        "emotion": EmotionConfig(),
        "agora": AgoraConfig(),
        "security": SecurityConfig(),
    }


# --- Flat imports for backward compatibility ---
DASHSCOPE_API_KEY = LLMConfig.DASHSCOPE_API_KEY
OPENAI_API_KEY = LLMConfig.DASHSCOPE_API_KEY
API_KEY = LLMConfig.DASHSCOPE_API_KEY
OPENAI_BASE_URL = LLMConfig.BASE_URL
API_BASE_URL = LLMConfig.BASE_URL
OPENAI_MODEL = LLMConfig.DEFAULT_MODEL
DEFAULT_MODEL = LLMConfig.DEFAULT_MODEL
TEMPERATURE = LLMConfig.TEMPERATURE
MAX_TOKENS = LLMConfig.MAX_TOKENS

CHUNK_SIZE = RAGConfig.CHUNK_SIZE
CHUNK_OVERLAP = RAGConfig.CHUNK_OVERLAP
EMBEDDING_MODEL = RAGConfig.EMBEDDING_MODEL
CHROMA_PERSIST_DIR = RAGConfig.PERSIST_DIR
COLLECTION_NAME = RAGConfig.COLLECTION_NAME

AGORA_APP_ID = AgoraConfig.APP_ID
AGORA_TOKEN = AgoraConfig.TOKEN
AGORA_APP_CERT = AgoraConfig.APP_CERT

SECRET_KEY = ApplicationConfig.SECRET_KEY
DEBUG = ApplicationConfig.DEBUG
LOG_LEVEL = "INFO"


class Config:
    SQLALCHEMY_DATABASE_URI = ApplicationConfig.DATABASE_URI
    SQLALCHEMY_ECHO = ApplicationConfig.DEBUG
    SECRET_KEY = ApplicationConfig.SECRET_KEY
    DASHSCOPE_API_KEY = LLMConfig.DASHSCOPE_API_KEY
    BASE_URL = LLMConfig.BASE_URL
    MODEL = LLMConfig.DEFAULT_MODEL
    AGORA_APP_ID = AgoraConfig.APP_ID
    AGORA_TOKEN = AgoraConfig.TOKEN
    AGORA_APP_CERT = AgoraConfig.APP_CERT
    AGORA_TOKEN_EXPIRE_HOURS = AgoraConfig.TOKEN_EXPIRE_HOURS
