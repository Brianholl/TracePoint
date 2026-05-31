import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / '.env')

class Config:
    OPENROUTER_API_KEY: str = os.getenv('OPENROUTER_API_KEY', '')
    OPENROUTER_BASE_URL: str = 'https://openrouter.ai/api/v1'
    OPENROUTER_SITE_URL: str = os.getenv('OPENROUTER_SITE_URL', 'http://localhost:8000')
    OPENROUTER_SITE_NAME: str = os.getenv('OPENROUTER_SITE_NAME', 'TracePoint')

    OPENROUTER_MODEL_TEXT: str = os.getenv('OPENROUTER_MODEL_TEXT', 'deepseek/deepseek-v4-flash')
    OPENROUTER_MODEL_VISION: str = os.getenv('OPENROUTER_MODEL_VISION', 'google/gemini-3.5-flash')
    OPENROUTER_MODEL_EXTREME: str = os.getenv('OPENROUTER_MODEL_EXTREME', 'anthropic/claude-opus-4.7')

    DATABASE_URL: str = f'sqlite+aiosqlite:///{BASE_DIR / "data" / "osint.db"}'

    TOR_HOST: str = os.getenv('TOR_HOST', '127.0.0.1')
    TOR_PORT: int = int(os.getenv('TOR_PORT', '9050'))
    TOR_CONTROL_PORT: int = int(os.getenv('TOR_CONTROL_PORT', '9051'))
    TOR_PASSWORD: str = os.getenv('TOR_PASSWORD', '')

    HIBP_API_KEY: str = os.getenv('HIBP_API_KEY', '')

    SECRET_KEY: str = os.getenv('SECRET_KEY', 'change-this-secret-key')
    DEBUG: bool = os.getenv('DEBUG', 'false').lower() == 'true'

    REPORTS_DIR: Path = BASE_DIR / 'reports'
    UPLOADS_DIR: Path = BASE_DIR / 'uploads'

    MODEL_TEXT_LABEL: str = 'DeepSeek V4 Flash'
    MODEL_VISION_LABEL: str = 'Gemini 3.5 Flash'
    MODEL_EXTREME_LABEL: str = 'Claude Opus 4.7'

config = Config()
