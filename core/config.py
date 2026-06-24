"""全局配置"""
import os

# LLM 提供商选择
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
TAOTOKEN_API_KEY = os.getenv("TAOTOKEN_API_KEY", "")
TAOTOKEN_BASE_URL = os.getenv("TAOTOKEN_BASE_URL", "https://api.taotoken.com/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 语音配置
STT_PROVIDER = os.getenv("STT_PROVIDER", "taotoken")
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "taotoken")

# 服务器
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# 数据库 —— 基于 main.py 所在目录解析相对路径
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", os.path.join(_BASE_DIR, "chroma_db"))
QUESTIONS_FILE = os.getenv("QUESTIONS_FILE", os.path.join(_BASE_DIR, "database", "questions.json"))

# 存储路径
AUDIO_DIR = os.getenv("AUDIO_DIR", os.path.join(_BASE_DIR, "audio"))
RECORDS_DIR = os.getenv("RECORDS_DIR", os.path.join(_BASE_DIR, "records"))
CHECKPOINTS_DIR = os.getenv("CHECKPOINTS_DIR", os.path.join(_BASE_DIR, "checkpoints"))

# 面试参数默认值
DEFAULT_QUESTION_COUNT = 5
DEFAULT_TIME_LIMIT = 180  # 秒
MAX_FOLLOWUP_ROUNDS = 2
PRESSURE_TTS_SPEED = 1.3
SCORE_THRESHOLD_WRONG = 6.0

# 场景列表
SCENES = {
    "tech": {"name": "大厂技术岗", "categories": ["算法", "项目经历", "系统设计", "行为面试", "技术视野"]},
    "civil": {"name": "公务员结构化面试", "categories": ["综合分析", "组织协调", "应急处理", "人际关系", "岗位认知"]},
    "postgrad": {"name": "考研复试", "categories": ["英文自我介绍", "专业基础", "研究计划", "导师匹配", "综合素养"]},
}
