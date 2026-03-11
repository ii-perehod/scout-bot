import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Schedule: auto-scan every N hours
SCAN_INTERVAL_HOURS = int(os.getenv("SCAN_INTERVAL_HOURS", "12"))

# Keywords: tools, platforms, patterns
DEFAULT_KEYWORDS = [
    # Direct tool indicators
    "github.com", "open source", "бесплатно", "инструмент", "скилл",
    "утилита", "расширение", "плагин", "шаблон", "фреймворк",
    "генератор", "конструктор", "сервис", "тул", "tool",
    # Dev platforms & tools
    "cursor", "make.com", "n8n", "zapier", "vercel", "supabase",
    "netlify", "railway", "render", "heroku", "firebase",
    "notion", "airtable", "figma", "miro",
    # AI & LLM
    "gpt", "claude", "gemini", "midjourney", "stable diffusion",
    "нейросет", "llm", "chatgpt", "openai", "anthropic",
    "langchain", "llamaindex", "autogen", "crewai",
    "openrouter", "groq", "ollama", "huggingface",
    # Code & automation
    "api", "скрипт", "парсер", "бот", "автоматизация",
    "python", "javascript", "node.js", "docker",
    # SEO & marketing
    "seo", "аналитик", "метрик", "трафик", "выдач",
    # Action words (tool posts often contain these)
    "репозиторий", "установи", "npm install", "pip install",
    "git clone", "попробуй", "подборка", "топ-", "список",
]

DB_PATH = os.path.join(os.path.dirname(__file__), "scout.db")
