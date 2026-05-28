#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${WIKIMAKER_REPO_ROOT:-$SCRIPT_DIR}"
CONDA_ENV="${WIKIMAKER_CONDA_ENV:-wikimaker}"
CORPUS_ROOT_DEFAULT="$HOME/extracts"
OUTPUT_ROOT_DEFAULT="$HOME/extracts/wiki-build/output"
STATE_ROOT_DEFAULT="$HOME/extracts/wiki-build/state"
TELEMETRY_ROOT_DEFAULT="$HOME/extracts/wiki-build/telemetry"
BASE_URL_DEFAULT="http://127.0.0.1:11434"
MODEL_DEFAULT="gemma4:e4b-mlx"
PID_FILE="/tmp/wikimaker.pid"
LOG_FILE="/tmp/wikimaker.log"
RESET_CONFIRMATION_PHRASE="RESET WIKIMAKER"

cmd="${1:-}"
shift || true

corpus_root="${WIKIMAKER_CORPUS_ROOT:-$CORPUS_ROOT_DEFAULT}"
output_root="${WIKIMAKER_OUTPUT_ROOT:-$OUTPUT_ROOT_DEFAULT}"
state_root="${WIKIMAKER_STATE_ROOT:-$STATE_ROOT_DEFAULT}"
telemetry_root="${WIKIMAKER_TELEMETRY_ROOT:-$TELEMETRY_ROOT_DEFAULT}"
base_url="${OPENAI_BASE_URL:-$BASE_URL_DEFAULT}"
model="${WIKIMAKER_ANALYSIS_MODEL:-$MODEL_DEFAULT}"
assume_yes="${WIKIMAKER_ASSUME_YES:-0}"

print_plan() {
  cat <<EOF
WikiMaker run plan
  conda env:  $CONDA_ENV
  corpus:     $corpus_root
  output:     $output_root
  state:      $state_root
  telemetry:  $telemetry_root
  local LLM:  $base_url
  model:      $model
EOF
}

print_status() {
  print_plan
  echo
  echo "Environment:"
  if conda env list | awk '{print $1}' | grep -qx "$CONDA_ENV"; then
    conda run -n "$CONDA_ENV" python --version
  else
    echo "  missing conda env: $CONDA_ENV"
  fi
  echo
  echo "Run state:"
  if is_running; then
    echo "  running: yes (pid $(cat "$PID_FILE"))"
  else
    echo "  running: no"
  fi
  echo "  pid file: $PID_FILE"
  echo "  log file: $LOG_FILE"
  if [[ -f "$LOG_FILE" ]]; then
    echo
    echo "Recent log:"
    tail -20 "$LOG_FILE"
  fi
  echo
  echo "Artifacts:"
  for artifact in \
    "$output_root/_privacy.md" \
    "$output_root/_llm_quality.md" \
    "$output_root/_health.md" \
    "$output_root/browser/index.html" \
    "$output_root/browser/data.json" \
    "$telemetry_root/latest.json"; do
    if [[ -f "$artifact" ]]; then
      echo "  ok:      $artifact"
    else
      echo "  missing: $artifact"
    fi
  done
}

run_wikimaker() {
  env -u OPENAI_API_KEY \
    OPENAI_BASE_URL="$base_url" \
    WIKIMAKER_PROVIDER="ollama" \
    WIKIMAKER_LLM_API_STYLE="ollama" \
    WIKIMAKER_ANALYSIS_MODEL="$model" \
    WIKIMAKER_GENERATION_MODEL="$model" \
    WIKIMAKER_REVIEW_MODEL="$model" \
    conda run -n "$CONDA_ENV" python "$REPO_ROOT/wikimaker.py" \
      --corpus-root "$corpus_root" \
      --output-root "$output_root" \
      --state-root "$state_root" \
      --telemetry-root "$telemetry_root" \
      "$@"
}

confirm_run() {
  if [[ "$assume_yes" == "1" ]]; then
    return 0
  fi
  if [[ ! -t 0 ]]; then
    echo "Non-interactive shell detected; set WIKIMAKER_ASSUME_YES=1 or use start."
    exit 1
  fi
  printf "Proceed with this run? [y/N] "
  read -r reply
  case "$reply" in
    y|Y|yes|YES)
      return 0
      ;;
    *)
      echo "Cancelled."
      exit 1
      ;;
  esac
}

resolve_path() {
  python3 - "$1" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).expanduser().resolve())
PY
}

build_parent_dir() {
  local resolved_output resolved_state resolved_telemetry
  resolved_output="$(resolve_path "$output_root")"
  resolved_state="$(resolve_path "$state_root")"
  resolved_telemetry="$(resolve_path "$telemetry_root")"

  if [[ "$(dirname "$resolved_output")" != "$(dirname "$resolved_state")" || "$(dirname "$resolved_output")" != "$(dirname "$resolved_telemetry")" ]]; then
    echo "Reset requires output/state/telemetry to share one parent build directory."
    echo "output:    $resolved_output"
    echo "state:     $resolved_state"
    echo "telemetry: $resolved_telemetry"
    exit 2
  fi

  printf '%s\n' "$(dirname "$resolved_output")"
}

safe_remove_tree() {
  local target="$1"
  local resolved_target resolved_corpus build_parent
  resolved_target="$(resolve_path "$target")"
  resolved_corpus="$(resolve_path "$corpus_root")"
  build_parent="$(build_parent_dir)"

  if [[ "$resolved_target" == "$resolved_corpus" ]]; then
    echo "Refusing to delete the corpus root: $resolved_target"
    exit 2
  fi

  case "$resolved_target" in
    "$build_parent"/*)
      ;;
    *)
      echo "Refusing to delete path outside the build directory: $resolved_target"
      echo "Build directory: $build_parent"
      exit 2
      ;;
  esac

  rm -rf -- "$resolved_target"
}

confirm_reset() {
  if [[ "$assume_yes" == "1" ]]; then
    return 0
  fi
  if [[ ! -t 0 ]]; then
    echo "Non-interactive shell detected; set WIKIMAKER_ASSUME_YES=1 to reset."
    exit 1
  fi
  printf "Type '%s' to delete generated wiki data: " "$RESET_CONFIRMATION_PHRASE"
  read -r reply
  if [[ "$reply" == "$RESET_CONFIRMATION_PHRASE" ]]; then
    return 0
  fi
  echo "Cancelled."
  exit 1
}

reset_wikimaker() {
  if is_running; then
    echo "WikiMaker is running; stopping it first."
    "$0" stop
  fi

  print_plan
  echo "Reset plan:"
  echo "  - delete output:    $output_root"
  echo "  - delete state:     $state_root"
  echo "  - delete telemetry: $telemetry_root"
  echo "  - preserve corpus:  $corpus_root"
  confirm_reset

  safe_remove_tree "$output_root"
  safe_remove_tree "$state_root"
  safe_remove_tree "$telemetry_root"
  rm -f "$PID_FILE"

  echo "Reset complete. Run '$0 run' or '$0 start' to build again."
}

preflight_run() {
  if [[ ! -d "$corpus_root" ]]; then
    echo "Corpus root not found: $corpus_root"
    exit 1
  fi
  mkdir -p "$output_root" "$state_root" "$telemetry_root"
  if [[ -n "${WIKIMAKER_CONNECTIVITY_CHECK_SCRIPT:-}" ]]; then
    echo "Preflight: verifying local model endpoint..."
    conda run -n "$CONDA_ENV" python "$WIKIMAKER_CONNECTIVITY_CHECK_SCRIPT" \
      --provider ollama \
      --base-url "$base_url" \
      --model "$model" \
      --timeout 60 \
      --prompt "Return exactly one word: OK."
  else
    echo "Preflight: skipping optional connectivity check. Set WIKIMAKER_CONNECTIVITY_CHECK_SCRIPT to enable it."
  fi
}

is_running() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(cat "$PID_FILE")"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

case "$cmd" in
  start)
    if is_running; then
      echo "WikiMaker already running (pid $(cat "$PID_FILE"))."
      exit 0
    fi
    mkdir -p "$(dirname "$LOG_FILE")"
    : > "$LOG_FILE"
    WIKIMAKER_ASSUME_YES=1 "$0" run "$@" >>"$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "Started WikiMaker (pid $(cat "$PID_FILE")). Log: $LOG_FILE"
    ;;
  run)
    print_plan
    confirm_run
    preflight_run
    run_wikimaker "$@"
    ;;
  stop)
    if ! [[ -f "$PID_FILE" ]]; then
      echo "WikiMaker is not running."
      exit 0
    fi
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" || true
      for _ in {1..20}; do
        if ! kill -0 "$pid" 2>/dev/null; then
          break
        fi
        sleep 0.2
      done
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" || true
      fi
      echo "Stopped WikiMaker (pid $pid)."
    else
      echo "WikiMaker pid file existed but process was gone."
    fi
    rm -f "$PID_FILE"
    ;;
  status)
    print_status
    ;;
  logs)
    if [[ ! -f "$LOG_FILE" ]]; then
      echo "No log file yet: $LOG_FILE"
      exit 1
    fi
    follow=0
    for arg in "$@"; do
      case "$arg" in
        -f|--follow)
          follow=1
          ;;
      esac
    done
    if [[ "$follow" == "1" ]]; then
      tail -n 200 -f "$LOG_FILE"
    else
      tail -n 200 "$LOG_FILE"
    fi
    ;;
  restart)
    "$0" stop
    "$0" start "$@"
    ;;
  reset)
    reset_wikimaker "$@"
    ;;
  rerun)
    reset_wikimaker "$@"
    "$0" run "$@"
    ;;
  fresh)
    reset_wikimaker "$@"
    "$0" run "$@"
    ;;
  rebuild)
    reset_wikimaker "$@"
    "$0" start "$@"
    ;;
  fresh-start)
    reset_wikimaker "$@"
    "$0" start "$@"
    ;;
  *)
    cat <<EOF
Usage: $0 {start|stop|status|restart|reset|rerun|fresh|rebuild|fresh-start|run|logs}

Modes:
  run     print the plan, ask for confirmation, and run in the foreground
  start   start in the background and write logs to $LOG_FILE
  logs    show the last 200 lines or follow with -f
  reset   stop the runner if needed, then delete output/state/telemetry only
  rerun   reset first, then run in the foreground
  fresh   alias for rerun
  rebuild reset first, then start in the background
  fresh-start alias for rebuild

Defaults:
  corpus:     $corpus_root
  output:     $output_root
  state:      $state_root
  telemetry:  $telemetry_root
  local LLM:  $base_url
  model:      $model
EOF
    exit 2
    ;;
esac
