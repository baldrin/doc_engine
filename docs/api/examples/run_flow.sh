#!/usr/bin/env bash
# Run a published one-file flow on a file and print the results. Needs curl and jq.
#
#   ./run_flow.sh http://localhost:8000 medical-record-summary record.pdf
set -euo pipefail

base="$1"; flow="$2"; file="$3"

reply=$(curl -sS -X POST "$base/api/v1/flows/$flow/jobs" -F "file=@$file")
job=$(jq -r '.job_id // empty' <<<"$reply")
if [ -z "$job" ]; then
  echo "refused: $(jq -r '.error' <<<"$reply")" >&2
  exit 1
fi
echo "started $job" >&2

while true; do
  status=$(curl -sS "$base/api/v1/jobs/$job")
  state=$(jq -r '.status' <<<"$status")
  case "$state" in
    done) break ;;
    failed|cancelled) echo "$state: $(jq -r '.error' <<<"$status")" >&2; exit 1 ;;
  esac
  echo "  $state: $(jq -r '"\(.progress.calls_done) of \(.progress.calls_planned) calls so far"' <<<"$status")" >&2
  sleep 3
done

curl -sS "$base/api/v1/jobs/$job/results" | jq -r '.outputs[] | "=== \(.name) ===\n\(.text)\n"'
