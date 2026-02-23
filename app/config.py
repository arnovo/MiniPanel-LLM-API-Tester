from dataclasses import dataclass

APP_TITLE = "MiniPanel LLM API Tester (macOS/Windows)"
APP_VERSION = "0.1.0"
DEFAULT_BASE_URL = "https://integrate.api.nvidia.com"
DEFAULT_ENDPOINT = "/v1/chat/completions"
DEFAULT_MODEL = "meta/llama-3.1-70b-instruct"
DEFAULT_SYSTEM_PROMPT = "Eres un asistente util y conciso."
DEFAULT_USER_PROMPT = "Dime 5 ideas para testear una API de LLM."
CREATOR_NAME = "Alejandro Rodríguez"
GITHUB_NAME = "GitHub"
PROJECT_URL = "https://github.com/arnovo/MiniPanel-LLM-API-Tester"


@dataclass
class LLMRequestConfig:
    base_url: str
    endpoint: str
    api_key: str
    model: str
    system_prompt: str
    user_prompt: str
    temperature: float
    max_tokens: int
    top_p: float
    stop: str  # JSON list or empty
    timeout_s: int
    extra_headers: str  # JSON dict or empty
    stream: bool
