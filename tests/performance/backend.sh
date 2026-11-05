#!/usr/bin/env bash
set -euo pipefail

URL="${1:-http://127.0.0.1:8080/captchaImage}"
CONCURRENCY="${CONCURRENCY:-50}"
REQUESTS="${REQUESTS:-2000}"
OUTDIR="${OUTDIR:-/tmp/hxjm-bench-$(date +%Y%m%d-%H%M%S)}"
RUNS="${RUNS:-1}"
SLEEP_BETWEEN="${SLEEP_BETWEEN:-2}"

mkdir -p "$OUTDIR"
BASE_OUTDIR="$OUTDIR"

PORT="$(echo "$URL" | sed -n 's#^[a-zA-Z]*://[^/:]*:\([0-9]\+\)/.*#\1#p')"
if [[ -z "$PORT" ]]; then
  PORT="$(echo "$URL" | sed -n 's#^[a-zA-Z]*://[^/:]*:\([0-9]\+\)$#\1#p')"
fi
if [[ -z "$PORT" ]]; then
  PORT="8080"
fi

JAVA_PID="${JAVA_PID:-}"
if [[ -z "${JAVA_PID}" ]]; then
  if command -v ss >/dev/null 2>&1; then
    JAVA_PID="$(ss -lptn "sport = :$PORT" 2>/dev/null | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | head -n 1 || true)"
  fi
fi
if [[ -z "${JAVA_PID}" ]]; then
  JAVA_PID="$(pgrep -f 'java.*hxjm|java.*spring|hxjm-admin' | head -n 1 || true)"
fi

echo "URL=$URL"
echo "PORT=$PORT"
echo "CONCURRENCY=$CONCURRENCY"
echo "REQUESTS=$REQUESTS"
echo "OUTDIR=$BASE_OUTDIR"
echo "RUNS=$RUNS"
echo "SLEEP_BETWEEN=$SLEEP_BETWEEN"
echo "JAVA_PID=${JAVA_PID:-<not found>}"

bench_once() {
  local RUN_OUTDIR="$1"
  mkdir -p "$RUN_OUTDIR"

  local PIDSTAT_PID=""
  if [[ -n "${JAVA_PID}" ]]; then
    pidstat -urd -p "$JAVA_PID" 1 > "$RUN_OUTDIR/pidstat.log" &
    PIDSTAT_PID=$!
  else
    echo "WARNING: JAVA_PID not found. pidstat will be skipped."
    echo "You can rerun with: JAVA_PID=<pid> $0 $URL"
  fi

  echo "Warmup 50 requests..."
  for _ in $(seq 1 50); do
    curl -s -o /dev/null --connect-timeout 2 --max-time 5 "$URL" || true
  done

  echo "Benchmarking..."
  local START_NS
  START_NS=$(date +%s%N)

  seq 1 "$REQUESTS" | xargs -I{} -P "$CONCURRENCY" bash -c '
    curl -s -o /dev/null \
      --connect-timeout 2 --max-time 5 \
      -w "%{time_total}\n" "'"$URL"'" || echo "5"
  ' > "$RUN_OUTDIR/times.txt"

  local END_NS
  END_NS=$(date +%s%N)
  local ELAPSED_MS
  ELAPSED_MS=$(( (END_NS - START_NS) / 1000000 ))

  if [[ -n "$PIDSTAT_PID" ]]; then
    kill "$PIDSTAT_PID" >/dev/null 2>&1 || true
  fi

  sort -n "$RUN_OUTDIR/times.txt" > "$RUN_OUTDIR/times.sorted"
  local COUNT
  COUNT=$(wc -l < "$RUN_OUTDIR/times.sorted")
  local P50_IDX P95_IDX P99_IDX
  P50_IDX=$(( (COUNT*50 + 99) / 100 ))
  P95_IDX=$(( (COUNT*95 + 99) / 100 ))
  P99_IDX=$(( (COUNT*99 + 99) / 100 ))

  local P50 P95 P99 AVG
  P50=$(awk "NR==$P50_IDX {print}" "$RUN_OUTDIR/times.sorted")
  P95=$(awk "NR==$P95_IDX {print}" "$RUN_OUTDIR/times.sorted")
  P99=$(awk "NR==$P99_IDX {print}" "$RUN_OUTDIR/times.sorted")
  AVG=$(awk '{sum+=$1} END{if(NR>0) printf("%.6f", sum/NR); else print "0"}' "$RUN_OUTDIR/times.txt")

  local ELAPSED_S QPS
  ELAPSED_S=$(awk "BEGIN {print $ELAPSED_MS/1000}")
  QPS=$(awk "BEGIN {if($ELAPSED_S>0) printf(\"%.2f\", $REQUESTS/$ELAPSED_S); else print \"0\"}")

  printf "%s\t%s\t%s\t%s\t%s\t%s\n" "$QPS" "$AVG" "$P50" "$P95" "$P99" "$ELAPSED_MS" > "$RUN_OUTDIR/result.tsv"

  echo
  echo "==== RESULT ===="
  echo "elapsed_ms=$ELAPSED_MS"
  echo "requests=$REQUESTS concurrency=$CONCURRENCY"
  echo "qps=$QPS"
  echo "avg_s=$AVG"
  echo "p50_s=$P50"
  echo "p95_s=$P95"
  echo "p99_s=$P99"
  echo
  echo "Artifacts:"
  echo "  $RUN_OUTDIR/times.txt"
  echo "  $RUN_OUTDIR/times.sorted"
  echo "  $RUN_OUTDIR/result.tsv"
  if [[ -f "$RUN_OUTDIR/pidstat.log" ]]; then
    echo "  $RUN_OUTDIR/pidstat.log"
  fi
}

median() {
  sort -n | awk '{a[NR]=$1} END{if(NR==0){print "0"; exit} if(NR%2==1){print a[(NR+1)/2]} else {print (a[NR/2]+a[NR/2+1])/2}}'
}

SUMMARY_FILE="$BASE_OUTDIR/summary.tsv"
: > "$SUMMARY_FILE"

if [[ "$RUNS" -le 1 ]]; then
  bench_once "$BASE_OUTDIR"
  cat "$BASE_OUTDIR/result.tsv" >> "$SUMMARY_FILE"
else
  for i in $(seq 1 "$RUNS"); do
    echo
    echo "==== RUN $i/$RUNS ===="
    RUN_OUTDIR="$BASE_OUTDIR/run-$i"
    bench_once "$RUN_OUTDIR"
    cat "$RUN_OUTDIR/result.tsv" >> "$SUMMARY_FILE"
    if [[ "$i" -lt "$RUNS" ]]; then
      sleep "$SLEEP_BETWEEN"
    fi
  done

  MED_QPS=$(awk '{print $1}' "$SUMMARY_FILE" | median)
  MED_AVG=$(awk '{print $2}' "$SUMMARY_FILE" | median)
  MED_P50=$(awk '{print $3}' "$SUMMARY_FILE" | median)
  MED_P95=$(awk '{print $4}' "$SUMMARY_FILE" | median)
  MED_P99=$(awk '{print $5}' "$SUMMARY_FILE" | median)
  MED_ELAPSED_MS=$(awk '{print $6}' "$SUMMARY_FILE" | median)

  echo
  echo "==== SUMMARY (median of $RUNS runs) ===="
  echo "elapsed_ms=$MED_ELAPSED_MS"
  echo "requests=$REQUESTS concurrency=$CONCURRENCY"
  echo "qps=$MED_QPS"
  echo "avg_s=$MED_AVG"
  echo "p50_s=$MED_P50"
  echo "p95_s=$MED_P95"
  echo "p99_s=$MED_P99"
  echo
  echo "Summary:"
  echo "  $SUMMARY_FILE"
fi
