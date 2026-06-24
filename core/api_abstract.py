"""API 抽象层 —— 统一 LLM 调用接口，切换提供商只需改环境变量"""
import os
from openai import OpenAI
from core.config import LLM_PROVIDER, TAOTOKEN_API_KEY, TAOTOKEN_BASE_URL, OPENAI_API_KEY, OPENAI_BASE_URL, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL


class LLMProvider:
    """LLM 提供商抽象基类"""

    def chat(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 2048) -> str:
        raise NotImplementedError

    def chat_json(self, messages: list[dict], temperature: float = 0.3, max_tokens: int = 1024) -> str:
        """要求 JSON 格式返回"""
        raise NotImplementedError


class TaoTokenProvider(LLMProvider):
    def __init__(self):
        self.model = os.getenv("TAOTOKEN_MODEL", "taotoken-chat")
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            if not TAOTOKEN_API_KEY:
                raise RuntimeError("TAOTOKEN_API_KEY 未设置")
            self._client = OpenAI(api_key=TAOTOKEN_API_KEY, base_url=TAOTOKEN_BASE_URL)

    def chat(self, messages, temperature=0.7, max_tokens=2048):
        self._ensure_client()
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content

    def chat_json(self, messages, temperature=0.3, max_tokens=1024):
        messages.append({"role": "system", "content": "请严格以 JSON 格式输出，不要包含任何其他文本。"})
        return self.chat(messages, temperature, max_tokens)


class OpenAIProvider(LLMProvider):
    def __init__(self):
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            if not OPENAI_API_KEY:
                raise RuntimeError("OPENAI_API_KEY 未设置")
            self._client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)

    def chat(self, messages, temperature=0.7, max_tokens=2048):
        self._ensure_client()
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content

    def chat_json(self, messages, temperature=0.3, max_tokens=1024):
        messages.append({"role": "system", "content": "请严格以 JSON 格式输出，不要包含任何其他文本。"})
        return self.chat(messages, temperature, max_tokens)


class DeepSeekProvider(LLMProvider):
    """DeepSeek API 提供者 —— 兼容 OpenAI 格式"""

    def __init__(self):
        self.model = DEEPSEEK_MODEL
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            if not DEEPSEEK_API_KEY:
                raise RuntimeError("DEEPSEEK_API_KEY 未设置")
            self._client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    def chat(self, messages, temperature=0.7, max_tokens=2048):
        self._ensure_client()
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content

    def chat_json(self, messages, temperature=0.3, max_tokens=1024):
        messages.append({"role": "system", "content": "请严格以 JSON 格式输出，不要包含任何其他文本。"})
        return self.chat(messages, temperature, max_tokens)


class MockProvider(LLMProvider):
    """Mock 提供者 —— 用于无 API Key 时的开发测试"""

    def chat(self, messages, temperature=0.7, max_tokens=2048):
        last_msg = messages[-1]["content"] if messages else ""
        return f"[Mock LLM] 收到消息: {last_msg[:100]}..."

    def chat_json(self, messages, temperature=0.3, max_tokens=1024):
        return '{"logic": 7.0, "completeness": 7.5, "organization": 7.0, "match": 7.0, "comment": "Mock评分"}'


_providers = {
    "taotoken": TaoTokenProvider,
    "openai": OpenAIProvider,
    "deepseek": DeepSeekProvider,
    "mock": MockProvider,
}


def get_llm() -> LLMProvider:
    """获取LLM提供商。若API Key未设置，自动降级为Mock模式。"""
    provider_name = LLM_PROVIDER
    if provider_name == "taotoken" and not TAOTOKEN_API_KEY:
        print("[警告] TAOTOKEN_API_KEY 未设置，使用 Mock 模式")
        provider_name = "mock"
    elif provider_name == "openai" and not OPENAI_API_KEY:
        print("[警告] OPENAI_API_KEY 未设置，使用 Mock 模式")
        provider_name = "mock"
    elif provider_name == "deepseek" and not DEEPSEEK_API_KEY:
        print("[警告] DEEPSEEK_API_KEY 未设置，使用 Mock 模式")
        provider_name = "mock"
    return _providers.get(provider_name, MockProvider)()
