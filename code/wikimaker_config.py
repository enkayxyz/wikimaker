from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import os
from typing import Any

LOCAL_OLLAMA_BASE_URL = "http://192.168.86.11:11434"


@dataclass(slots=True)
class WikiMakerConfig:
    corpus_root: Path
    output_root: Path
    state_root: Path
    telemetry_root: Path
    provider: str = "ollama"
    llm_api_style: str = "ollama"
    openai_base_url: str = LOCAL_OLLAMA_BASE_URL
    api_key: str = ""
    analysis_model: str = ""
    generation_model: str = ""
    review_model: str = ""
    use_adk: bool = False
    enable_adk_tracing: bool = True
    enable_adk_eval: bool = False
    adk_trace_db: str = ""
    adk_eval_dir: str = ""
    sample_files: int = 5
    progress_every: int = 100
    dry_run: bool = False

    @classmethod
    def from_env_and_args(cls, **overrides: Any) -> "WikiMakerConfig":
        env = os.environ

        def pick(name: str, fallback: str = "") -> str:
            if name in overrides and overrides[name] not in (None, ""):
                return str(overrides[name])
            return env.get(name, fallback)

        corpus_root_value = pick("WIKIMAKER_CORPUS_ROOT", pick("corpus_root", "")).strip()
        if not corpus_root_value:
            raise ValueError("Missing corpus root. Set WIKIMAKER_CORPUS_ROOT or pass --corpus-root.")

        corpus_root = Path(corpus_root_value).expanduser()
        output_root = Path(pick("WIKIMAKER_OUTPUT_ROOT", pick("output_root", str(corpus_root / "wiki-build" / "output")))).expanduser()
        state_root = Path(pick("WIKIMAKER_STATE_ROOT", pick("state_root", str(corpus_root / "wiki-build" / "state")))).expanduser()
        telemetry_root = Path(pick("WIKIMAKER_TELEMETRY_ROOT", pick("telemetry_root", str(corpus_root / "wiki-build" / "telemetry")))).expanduser()

        provider = pick("WIKIMAKER_PROVIDER", pick("provider", "ollama"))
        llm_api_style = pick("WIKIMAKER_LLM_API_STYLE", pick("llm_api_style", "ollama"))
        openai_base_url = pick("OPENAI_BASE_URL", pick("openai_base_url", LOCAL_OLLAMA_BASE_URL))
        api_key = pick("OPENAI_API_KEY", pick("OSAURUS_API_KEY", ""))

        analysis_model = pick("WIKIMAKER_ANALYSIS_MODEL", pick("analysis_model", env.get("OPENAI_MODEL", "")))
        generation_model = pick("WIKIMAKER_GENERATION_MODEL", pick("generation_model", analysis_model))
        review_model = pick("WIKIMAKER_REVIEW_MODEL", pick("review_model", analysis_model))
        use_adk = _boolish(pick("WIKIMAKER_USE_ADK", pick("use_adk", "0")))
        enable_adk_tracing = _boolish(pick("WIKIMAKER_ENABLE_ADK_TRACING", pick("enable_adk_tracing", "1")))
        enable_adk_eval = _boolish(pick("WIKIMAKER_ENABLE_ADK_EVAL", pick("enable_adk_eval", "0")))
        adk_trace_db = pick("WIKIMAKER_ADK_TRACE_DB", pick("adk_trace_db", str(telemetry_root / "adk_traces.sqlite3")))
        adk_eval_dir = pick("WIKIMAKER_ADK_EVAL_DIR", pick("adk_eval_dir", str(telemetry_root / "adk_eval")))
        sample_files = int(pick("WIKIMAKER_SAMPLE_FILES", pick("sample_files", "5")) or 5)
        progress_every = int(pick("WIKIMAKER_PROGRESS_EVERY", pick("progress_every", "100")) or 100)
        dry_run = _boolish(pick("WIKIMAKER_DRY_RUN", pick("dry_run", "0")))

        return cls(
            corpus_root=corpus_root,
            output_root=output_root,
            state_root=state_root,
            telemetry_root=telemetry_root,
            provider=provider,
            llm_api_style=llm_api_style,
            openai_base_url=openai_base_url,
            api_key=api_key,
            analysis_model=analysis_model,
            generation_model=generation_model,
            review_model=review_model,
            use_adk=use_adk,
            enable_adk_tracing=enable_adk_tracing,
            enable_adk_eval=enable_adk_eval,
            adk_trace_db=adk_trace_db,
            adk_eval_dir=adk_eval_dir,
            sample_files=sample_files,
            progress_every=progress_every,
            dry_run=dry_run,
        )

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("corpus_root", "output_root", "state_root", "telemetry_root"):
            data[key] = str(data[key])
        return data

    def telemetry_dict(self) -> dict[str, Any]:
        data = self.as_dict()
        data["api_key"] = "[redacted]"
        return data


def _boolish(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}
