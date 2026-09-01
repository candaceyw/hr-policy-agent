from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "hr-policy-agent"
    app_env: str = "development"

    # LLM provider for text generation. "gemini" uses google-genai; "groq" and
    # "openai_compatible" use the OpenAI-style chat API (Groq, OpenRouter, Ollama).
    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gemini-3.6-flash", alias="LLM_MODEL")
    llm_base_url: str | None = Field(default=None, alias="LLM_BASE_URL")
    # Reserved output budget for the tool-calling chat model. Counts toward
    # provider TPM limits (Groq free tier = 8000 TPM), so keep it modest.
    llm_max_output_tokens: int = Field(default=2048, alias="LLM_MAX_OUTPUT_TOKENS")

    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")

    # Embeddings stay on Gemini's free tier (separate quota from generation).
    embedding_model: str = Field(default="gemini-embedding-001", alias="EMBEDDING_MODEL")
    embedding_dim: int = Field(default=768, alias="EMBEDDING_DIM")

    retrieval_k: int = Field(default=5, alias="RETRIEVAL_K")
    # Top-hit similarity below SCOPE_THRESHOLD -> out-of-corpus redirect (no LLM call).
    # Below ESCALATION_THRESHOLD but in scope -> answer, but flag "confirm with HR".
    scope_threshold: float = Field(default=0.55, alias="SCOPE_THRESHOLD")
    escalation_threshold: float = Field(default=0.60, alias="ESCALATION_THRESHOLD")
    chunk_size: int = Field(default=800, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=120, alias="CHUNK_OVERLAP")
    seed: int = Field(default=42, alias="SEED")
    # MCP transport. Unset MCP_SERVER_URL => the web app spawns the server over
    # stdio. MCP_TRANSPORT / MCP_HOST / MCP_PORT configure the server process when
    # it runs standalone over Streamable HTTP.
    mcp_server_url: str | None = Field(default=None, alias="MCP_SERVER_URL")
    mcp_transport: str = Field(default="stdio", alias="MCP_TRANSPORT")
    mcp_host: str = Field(default="127.0.0.1", alias="MCP_HOST")
    mcp_port: int = Field(default=8765, alias="MCP_PORT")
    max_tool_iterations: int = Field(default=8, alias="MAX_TOOL_ITERATIONS")
    project_root: str = "."

    # Evaluation LLM judge. Use a different model family than llm_model so the
    # judge does not grade its own output (self-preference bias). Default is
    # Groq gpt-oss (distinct from the qwen generator); Gemini is cleaner still
    # but its free tier caps at 20 requests/day. See .env.example.
    eval_judge_provider: str = Field(default="groq", alias="EVAL_JUDGE_PROVIDER")
    eval_judge_model: str = Field(default="openai/gpt-oss-20b", alias="EVAL_JUDGE_MODEL")
    # Seconds to sleep between judge calls, to stay under free-tier RPM limits.
    eval_judge_pace_seconds: float = Field(default=2.0, alias="EVAL_JUDGE_PACE_SECONDS")

    # Built SPA to serve from FastAPI. Unset => look for frontend/dist next to the
    # repo (dev/local); set in the container image to the copied dist path.
    static_dir: str | None = Field(default=None, alias="STATIC_DIR")

    @property
    def provider(self) -> str:
        return self.llm_provider.strip().lower()

    @property
    def resolved_llm_api_key(self) -> str | None:
        """The API key for the active generation provider."""
        if self.provider == "gemini":
            return self.gemini_api_key or None
        if self.provider == "groq":
            return (self.groq_api_key or self.llm_api_key) or None
        return (self.llm_api_key or self.groq_api_key) or None

    @property
    def resolved_llm_base_url(self) -> str | None:
        if self.llm_base_url:
            return self.llm_base_url
        if self.provider == "groq":
            return GROQ_BASE_URL
        return None


settings = Settings()
