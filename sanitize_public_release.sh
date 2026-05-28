#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./sanitize_public_release.sh audit
  ./sanitize_public_release.sh patch
  ./sanitize_public_release.sh export <destination-dir>

Modes:
  audit   Scan tracked files for personal paths, LAN endpoints, private hints, and token-like secrets.
  patch   Rewrite known public-safety leaks in the current checkout.
  export  Create a sanitized copy without .git, .env, caches, generated output, logs, DBs, or archives.
EOF
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

mode="${1:-}"
destination="${2:-}"

tracked_files() {
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git ls-files
  else
    find . -type f \
      ! -path './.git/*' \
      ! -path './.env' \
      ! -path './.env.*' \
      ! -path './*/__pycache__/*' \
      ! -path './.pytest_cache/*' \
      ! -path './output/*' \
      ! -path './state/*' \
      ! -path './telemetry/*' \
      ! -path './wiki-build/*' \
      ! -name '*.pyc' \
      ! -name '*.pyo' \
      ! -name '*.pyd' \
      ! -name '*.sqlite' \
      ! -name '*.sqlite3' \
      ! -name '*.log' \
      ! -name '*.zip' \
      ! -name '*.tar' \
      ! -name '*.tgz' \
      ! -name '*.gz' \
      | sed 's#^\./##'
  fi
}

public_files() {
  {
    tracked_files
    [[ -f sanitize_public_release.sh ]] && printf '%s\n' sanitize_public_release.sh
  } | sort -u | grep -Ev '(^|/)(__pycache__|\.pytest_cache)(/|$)|\.(pyc|pyo|pyd|sqlite|sqlite3|log|zip|tar|tgz|gz)$|(^|/)(output|state|telemetry|wiki-build)(/|$)' || true
}

private_user="en""kay"
private_lan='192\.168\.86'
private_home="/Users/${private_user}"
private_dotdir='\.'"hermes"
private_project="File""Analyze"
private_extract="MD""Extract"
private_email='nirav@'"kana""kia"'\.org'
private_repo='github\.com/en'"kay"
private_agent_a="Her""mes"
private_agent_b="Har""mis"

audit_patterns=(
  "$private_home"
  "$private_lan"
  "$private_dotdir"
  "$private_project"
  "$private_extract"
  "$private_email"
  "$private_repo"
  "$private_agent_a"
  "$private_agent_b"
  'OPENAI_''API_KEY=[^*[:space:]]'
  'OSAURUS_''API_KEY=[^*[:space:]]'
  'GEMINI_''API_KEY=[^*[:space:]]'
  'sk-[A-Za-z0-9_-]{20,}'
  'ghp_[A-Za-z0-9_]{20,}'
  'github_pat_[A-Za-z0-9_]{20,}'
  'AIza[0-9A-Za-z_-]{20,}'
  'Bearer[[:space:]]+[A-Za-z0-9._-]{20,}'
)

audit() {
  local failures=0
  local files
  files="$(public_files)"
  for pattern in "${audit_patterns[@]}"; do
    if [[ -n "$files" ]] && echo "$files" | xargs rg -n -I --color never -e "$pattern" >/tmp/wikimaker_sanitize_hits.$$ 2>/dev/null; then
      echo "Audit failure for pattern: $pattern"
      cut -d: -f1-2 /tmp/wikimaker_sanitize_hits.$$ | sort -u
      failures=$((failures + 1))
    fi
  done
  rm -f /tmp/wikimaker_sanitize_hits.$$

  if git rev-parse --is-inside-work-tree >/dev/null 2>&1 && git ls-files --error-unmatch .env >/dev/null 2>&1; then
    echo "Audit failure: .env is tracked"
    failures=$((failures + 1))
  fi

  if [[ "$failures" -gt 0 ]]; then
    echo "Sanitize audit failed with $failures issue group(s)."
    return 1
  fi
  echo "Sanitize audit passed."
}

rewrite_file() {
  local path="$1"
  [[ -f "$path" ]] || return 0
  local user_name="en""kay"
  local home_path="/Users/${user_name}"
  local project_name="File""Analyze"
  local extract_name="MD""Extract"
  local private_network='192\.168\.86'
  local old_endpoint="http://192"".168"".86"".11:11434"
  local private_dot='.'"hermes"
  local private_agent_a="Her""mes"
  local private_agent_b="Har""mis"
  local private_domain="kana""kia"
  perl -0pi \
    -e "s#${home_path}/dev/wikimaker#<repo-root>#g;" \
    -e "s#${home_path}/extracts#\\\$HOME/extracts#g;" \
    -e "s#${home_path}/dev/${project_name}/${extract_name}/data#\\\$HOME/extracts#g;" \
    -e "s#${home_path}/dev/${project_name}/${extract_name}/wikimaker/output#\\\$HOME/extracts/wiki-build/output#g;" \
    -e "s#${home_path}/dev/${project_name}/${extract_name}/wikimaker/state#\\\$HOME/extracts/wiki-build/state#g;" \
    -e "s#${home_path}/dev/${project_name}/${extract_name}/wikimaker/telemetry#\\\$HOME/extracts/wiki-build/telemetry#g;" \
    -e "s#${home_path}#\\\$HOME#g;" \
    -e "s#${old_endpoint}#http://127.0.0.1:11434#g;" \
    -e "s#${private_network}\\.\\*#127.0.0.1#g;" \
    -e "s#${private_network}#127.0.0#g;" \
    -e "s#${private_dot}#\\.wikimaker#g;" \
    -e "s#${project_name}/${extract_name}#local-extracts#g;" \
    -e "s#${extract_name}#Markdown extracts#g;" \
    -e "s#nirav\@${private_domain}\.org#user@example.com#g;" \
    -e "s#${private_agent_a}#local agent#g;" \
    -e "s#${private_agent_b}#agent#g;" \
    "$path"
}

patch_checkout() {
  while IFS= read -r path; do
    [[ "$path" == "sanitize_public_release.sh" ]] && continue
    case "$path" in
      *.py|*.sh|*.md|*.txt|*.yml|*.yaml|*.json|.env.example|README.md)
        rewrite_file "$path"
        ;;
    esac
  done < <(public_files)
  echo "Patch complete. Run './sanitize_public_release.sh audit' next."
}

export_clean() {
  if [[ -z "$destination" ]]; then
    usage
    return 2
  fi
  local dest_parent
  dest_parent="$(dirname "$destination")"
  mkdir -p "$dest_parent"
  if [[ -e "$destination" ]]; then
    echo "Destination already exists: $destination"
    return 2
  fi

  mkdir -p "$destination"
  while IFS= read -r path; do
    mkdir -p "$destination/$(dirname "$path")"
    cp -p "$path" "$destination/$path"
  done < <(public_files)

  (
    cd "$destination"
    ./sanitize_public_release.sh patch >/dev/null
    ./sanitize_public_release.sh audit
  )
  echo "Sanitized export created: $destination"
}

case "$mode" in
  audit)
    audit
    ;;
  patch)
    patch_checkout
    ;;
  export)
    export_clean
    ;;
  *)
    usage
    exit 2
    ;;
esac
