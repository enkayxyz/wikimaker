from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import os
from typing import Any

LOCAL_OLLAMA_BASE_URL = "http://127.0.0.1:11434"


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
    use_adk: bool = True
    enable_adk_tracing: bool = True
    enable_adk_eval: bool = False
    adk_trace_db: str = ""
    adk_eval_dir: str = ""
    sample_files: int = 50
    llm_batch_size: int = 50
    test_limit: int = 0
    card_mode: str = "metadata"
    llm_debug: bool = False
    llm_preflight_timeout: int = 20
    llm_file_timeout: int = 120
    llm_batch_timeout: int = 180
    llm_global_timeout: int = 300
    llm_quality_timeout: int = 120
    progress_every: int = 100
    dry_run: bool = False
    allow_remote_llm: bool = False
    prompt_profile_path: str = ""
    synthesis_mode: str = "adk_workflow"
    force_reprocess: bool = False
    force_paths: list[str] | None = None
    enable_quality_judge: bool = True
    quality_judge_model: str = ""

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
        use_adk = _boolish(pick("WIKIMAKER_USE_ADK", pick("use_adk", "1")))
        enable_adk_tracing = _boolish(pick("WIKIMAKER_ENABLE_ADK_TRACING", pick("enable_adk_tracing", "1")))
        enable_adk_eval = _boolish(pick("WIKIMAKER_ENABLE_ADK_EVAL", pick("enable_adk_eval", "0")))
        adk_trace_db = pick("WIKIMAKER_ADK_TRACE_DB", pick("adk_trace_db", str(telemetry_root / "adk_traces.sqlite3")))
        adk_eval_dir = pick("WIKIMAKER_ADK_EVAL_DIR", pick("adk_eval_dir", str(telemetry_root / "adk_eval")))
        sample_files = int(pick("WIKIMAKER_SAMPLE_FILES", pick("sample_files", "50")) or 50)
        llm_batch_size = int(pick("WIKIMAKER_LLM_BATCH_SIZE", pick("llm_batch_size", "50")) or 50)
        test_limit = int(pick("WIKIMAKER_TEST_LIMIT", pick("test_limit", "0")) or 0)
        card_mode = pick("WIKIMAKER_CARD_MODE", pick("card_mode", "metadata")).strip().lower() or "metadata"
        if card_mode not in {"metadata", "sampled", "deep", "original"}:
            raise ValueError("WIKIMAKER_CARD_MODE must be metadata, sampled, deep, or original.")
        llm_debug = _boolish(pick("WIKIMAKER_LLM_DEBUG", pick("llm_debug", "0")))
        llm_preflight_timeout = int(pick("WIKIMAKER_LLM_PREFLIGHT_TIMEOUT", pick("llm_preflight_timeout", "20")) or 20)
        llm_file_timeout = int(pick("WIKIMAKER_LLM_FILE_TIMEOUT", pick("llm_file_timeout", "120")) or 120)
        llm_batch_timeout = int(pick("WIKIMAKER_LLM_BATCH_TIMEOUT", pick("llm_batch_timeout", "180")) or 180)
        llm_global_timeout = int(pick("WIKIMAKER_LLM_GLOBAL_TIMEOUT", pick("llm_global_timeout", "300")) or 300)
        llm_quality_timeout = int(pick("WIKIMAKER_LLM_QUALITY_TIMEOUT", pick("llm_quality_timeout", "120")) or 120)
        progress_every = int(pick("WIKIMAKER_PROGRESS_EVERY", pick("progress_every", "100")) or 100)
        dry_run = _boolish(pick("WIKIMAKER_DRY_RUN", pick("dry_run", "0")))
        allow_remote_llm = _boolish(pick("WIKIMAKER_ALLOW_REMOTE_LLM", pick("allow_remote_llm", "0")))
        prompt_profile_path = pick("WIKIMAKER_PROMPT_PROFILE", pick("prompt_profile_path", ""))
        synthesis_mode = pick("WIKIMAKER_SYNTHESIS_MODE", pick("synthesis_mode", "adk_workflow")).strip() or "adk_workflow"
        if synthesis_mode not in {"adk_workflow", "map_reduce", "llm_only", "coverage_fallback"}:
            raise ValueError("WIKIMAKER_SYNTHESIS_MODE must be adk_workflow, map_reduce, llm_only, or coverage_fallback.")
        force_reprocess = _boolish(pick("WIKIMAKER_FORCE_REPROCESS", pick("force_reprocess", "0")))
        force_paths_raw: str | list[Any]
        if isinstance(overrides.get("force_paths"), list):
            force_paths_raw = overrides["force_paths"]
        else:
            force_paths_raw = pick("WIKIMAKER_FORCE_PATHS", pick("force_paths", ""))
        if isinstance(force_paths_raw, list):
            force_paths = [str(item).strip() for item in force_paths_raw if str(item).strip()]
        else:
            force_paths = [item.strip() for item in str(force_paths_raw).split(",") if item.strip()]
        enable_quality_judge = _boolish(pick("WIKIMAKER_ENABLE_QUALITY_JUDGE", pick("enable_quality_judge", "1")))
        quality_judge_model = pick("WIKIMAKER_QUALITY_JUDGE_MODEL", pick("quality_judge_model", review_model))

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
            llm_batch_size=llm_batch_size,
            test_limit=test_limit,
            card_mode=card_mode,
            llm_debug=llm_debug,
            llm_preflight_timeout=llm_preflight_timeout,
            llm_file_timeout=llm_file_timeout,
            llm_batch_timeout=llm_batch_timeout,
            llm_global_timeout=llm_global_timeout,
            llm_quality_timeout=llm_quality_timeout,
            progress_every=progress_every,
            dry_run=dry_run,
            allow_remote_llm=allow_remote_llm,
            prompt_profile_path=prompt_profile_path,
            synthesis_mode=synthesis_mode,
            force_reprocess=force_reprocess,
            force_paths=force_paths,
            enable_quality_judge=enable_quality_judge,
            quality_judge_model=quality_judge_model,
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
