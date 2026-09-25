from vera.config import Settings
from vera.errors import ConfigurationError
from vera.providers.base import ModelProvider
from vera.providers.deterministic import DeterministicProvider
from vera.providers.http import GeminiProvider, OpenAICompatibleProvider


def build_provider(settings: Settings) -> ModelProvider:
    if settings.llm_provider == "deterministic":
        return DeterministicProvider()
    if settings.llm_provider == "gemini":
        if settings.gemini_api_key is None:
            raise ConfigurationError("VERA_GEMINI_API_KEY is required for Gemini")
        return GeminiProvider(
            settings.llm_model,
            settings.gemini_api_key.get_secret_value(),
            settings.request_timeout_seconds,
        )
    api_key = (
        settings.llm_api_key.get_secret_value() if settings.llm_api_key is not None else None
    )
    return OpenAICompatibleProvider(
        settings.llm_provider,
        settings.llm_model,
        settings.llm_base_url,
        api_key,
        settings.request_timeout_seconds,
    )
