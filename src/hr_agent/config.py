from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "hr-policy-agent"
    app_env: str = "development"
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    llm_model: str = Field(default="gemini-2.0-flash", alias="LLM_MODEL")
    embedding_model: str = Field(default="text-embedding-004", alias="EMBEDDING_MODEL")
    retrieval_k: int = Field(default=5, alias="RETRIEVAL_K")
    chunk_size: int = Field(default=800, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=120, alias="CHUNK_OVERLAP")
    seed: int = Field(default=42, alias="SEED")
    mcp_server_url: str | None = Field(default=None, alias="MCP_SERVER_URL")
    mcp_port: int = Field(default=8765, alias="MCP_PORT")
    max_tool_iterations: int = Field(default=8, alias="MAX_TOOL_ITERATIONS")
    project_root: str = "."


settings = Settings()
