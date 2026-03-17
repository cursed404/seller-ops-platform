from app.infrastructure.llm.base import ChatModel
from app.infrastructure.llm.mock import MockChatModel
from app.infrastructure.llm.openai import OpenAIChatModel
from app.settings import Settings


def build_chat_model(settings: Settings) -> ChatModel:
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return OpenAIChatModel(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.request_timeout_seconds,
        )
    return MockChatModel()

