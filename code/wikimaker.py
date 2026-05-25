from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from wikimaker_config import WikiMakerConfig
from wikimaker_runner import run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WikiMaker alpha v0001 scaffold")
    parser.add_argument("--corpus-root", type=Path, help="Root folder containing Markdown source files")
    parser.add_argument("--output-root", type=Path, help="Output root for generated wiki artifacts")
    parser.add_argument("--state-root", type=Path, help="Persistent state directory")
    parser.add_argument("--telemetry-root", type=Path, help="Telemetry directory")
    parser.add_argument("--provider", help="LLM provider name, e.g. ollama")
    parser.add_argument("--analysis-model", help="Model used for corpus analysis")
    parser.add_argument("--generation-model", help="Model used for wiki generation")
    parser.add_argument("--review-model", help="Model used for verification/review")
    parser.add_argument("--use-adk", action=argparse.BooleanOptionalAction, default=None, help="Retained orchestration flag")
    parser.add_argument("--enable-adk-tracing", action=argparse.BooleanOptionalAction, default=None, help="Enable ADK/OpenTelemetry tracing")
    parser.add_argument("--enable-adk-eval", action=argparse.BooleanOptionalAction, default=None, help="Retained compatibility flag")
    parser.add_argument("--adk-trace-db", help="SQLite DB path for ADK trace storage")
    parser.add_argument("--adk-eval-dir", help="Directory for ADK eval artifacts")
    parser.add_argument("--sample-files", type=int, help="Maximum number of files to include in the model prompt sample window")
    parser.add_argument("--progress-every", type=int, help="Print a scan progress line every N files")
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=None, help="Run without future write actions")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = WikiMakerConfig.from_env_and_args(
            corpus_root=args.corpus_root,
            output_root=args.output_root,
            state_root=args.state_root,
            telemetry_root=args.telemetry_root,
            provider=args.provider,
            analysis_model=args.analysis_model,
            generation_model=args.generation_model,
            review_model=args.review_model,
            use_adk=args.use_adk,
            enable_adk_tracing=args.enable_adk_tracing,
            enable_adk_eval=args.enable_adk_eval,
            adk_trace_db=args.adk_trace_db,
            adk_eval_dir=args.adk_eval_dir,
            sample_files=args.sample_files,
            progress_every=args.progress_every,
            dry_run=args.dry_run,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not config.corpus_root.exists():
        print(f"Corpus root does not exist: {config.corpus_root}", file=sys.stderr)
        return 2
    result = run(config)
    print("WikiMaker run complete")
    print(f"- files scanned: {result['scan']['total_files']}")
    print(f"- added: {result['scan']['added']}, changed: {result['scan']['changed']}, removed: {result['scan']['removed']}")
    print(f"- LLM used: {result['llm']['used']}")
    eval_result = result.get("observability", {}).get("evaluation", {})
    if eval_result.get("used"):
        eval_runs = eval_result.get("eval_results", [])
        if eval_runs:
            first = eval_runs[0]
            metric_results = first.get("metric_results", [])
            if metric_results:
                metric = metric_results[0]
                print(f"- eval: {metric.get('metric')}={metric.get('score')} ({metric.get('status')})")
            else:
                print(f"- eval: {first.get('status', 'unknown')}")
        else:
            print("- eval: ran")
    else:
        print(f"- eval: skipped ({eval_result.get('error') or 'disabled'})")
    print(f"- report: {result['paths']['report']}")
    print(f"- dashboard: {result['paths'].get('dashboard', '')}")
    print(f"- stats: {result['paths'].get('stats', '')}")
    print(f"- search: {result['paths'].get('search', '')}")
    print(f"- graph: {result['paths'].get('graph', '')}")
    print(f"- telemetry: {result['paths']['telemetry']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
