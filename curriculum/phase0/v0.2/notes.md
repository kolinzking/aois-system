# v0.2 — Bash Scripting: The Glue of DevOps

## What this version builds

`log_analyzer.sh` — a bash script that reads a log file, detects incident patterns, counts errors and warnings, and outputs a summary report.

It will handle maybe 5 patterns. It will miss everything it wasn't explicitly written for. It will break on log formats it didn't expect. It will take 80 lines to do what v1 does in one Claude API call.

That is the point. Build this, feel the limitation, then watch v1 replace it.

---

## Why bash matters even in an AI-heavy stack

Bash is the glue. GitHub Actions workflows are bash. Kubernetes init containers run bash. Dockerfile RUN commands are bash. Helm chart hooks are bash. Terraform provisioners are bash. Every time you ssh into a server and something is broken, you fix it with bash.

You will write bash for the rest of your career. This version teaches you to write it properly.

---

## Variables

```bash
#!/bin/bash

name="collins"
count=0
log_file="/var/log/app.log"

echo "Name: $name"
echo "Count: $count"
echo "File: $log_file"

# Arithmetic
total=$((count + 1))
echo "Total: $total"

# String length
len=${#name}
echo "Length: $len"

# Default value: use "default" if VAR is unset or empty
port=${PORT:-8000}
echo "Port: $port"
```

**Always quote variables:** `"$name"` not `$name`. Without quotes, a variable containing spaces breaks the command. `rm $file` where `$file` is `"my file.txt"` becomes `rm my file.txt` — two arguments. `rm "$file"` handles it correctly.

---

## Conditionals

```bash
severity="P1"

if [ "$severity" = "P1" ]; then
    echo "CRITICAL — page the on-call"
elif [ "$severity" = "P2" ]; then
    echo "HIGH — respond within 1 hour"
else
    echo "Lower severity"
fi

# File tests
if [ -f "/etc/hosts" ]; then echo "file exists"; fi
if [ -d "/var/log" ]; then echo "directory exists"; fi
if [ -r "file.txt" ]; then echo "file is readable"; fi
if [ ! -f ".env" ]; then echo "WARNING: .env file missing"; fi

# Numeric comparisons
count=15
if [ $count -gt 10 ]; then echo "count exceeds threshold"; fi
if [ $count -eq 0 ]; then echo "count is zero"; fi
# -gt greater than, -lt less than, -ge greater or equal, -le less or equal, -eq equal, -ne not equal

# String comparisons
if [ -z "$var" ]; then echo "var is empty"; fi
if [ -n "$var" ]; then echo "var is not empty"; fi
```

`[` is actually a command, not special syntax. The spaces around `[` and before `]` are required. `[ "$x" = "y"]` fails. `[ "$x" = "y" ]` works.

---

## Loops

```bash
# Loop over a list
for service in nginx redis postgres; do
    echo "Checking: $service"
done

# Loop over files
for file in /var/log/*.log; do
    echo "Processing: $file"
done

# C-style loop
for ((i=1; i<=5; i++)); do
    echo "Attempt $i"
done

# While loop
count=0
while [ $count -lt 3 ]; do
    echo "Try $count"
    count=$((count + 1))
done

# Read lines from a file
while IFS= read -r line; do
    echo "Line: $line"
done < /var/log/app.log

# Read output of a command line by line
ps aux | grep python | while IFS= read -r line; do
    echo "Process: $line"
done
```

`IFS= read -r line` is the correct way to read lines in bash. `IFS=` prevents word splitting. `-r` prevents backslash interpretation. Without these, lines with spaces or backslashes behave unexpectedly.

---

## Functions

```bash
# Define a function
check_service() {
    local service_name="$1"    # local: variable only exists inside this function
    local port="$2"
    
    if lsof -i ":$port" > /dev/null 2>&1; then
        echo "✓ $service_name is running on port $port"
        return 0    # success exit code
    else
        echo "✗ $service_name is NOT running on port $port"
        return 1    # failure exit code
    fi
}

# Call it
check_service "FastAPI" 8000
check_service "Redis" 6379
check_service "Postgres" 5432

# Check if last command succeeded
if check_service "FastAPI" 8000; then
    echo "All good"
else
    echo "FastAPI is down — investigate"
fi
```

`local` is critical. Without it, variables inside functions are global and leak into the rest of the script, causing subtle bugs.

`return 0` = success. `return 1` (or any non-zero) = failure. This is how bash communicates success/failure between commands and scripts. `$?` holds the exit code of the last command.

---

## Script arguments

```bash
#!/bin/bash

# $0 = script name
# $1 = first argument
# $2 = second argument
# $# = number of arguments
# $@ = all arguments as separate words
# $* = all arguments as one word

script_name="$0"
log_file="$1"
threshold="${2:-10}"    # default to 10 if not provided

if [ $# -lt 1 ]; then
    echo "Usage: $0 <log_file> [error_threshold]"
    echo "Example: $0 /var/log/app.log 20"
    exit 1
fi

if [ ! -f "$log_file" ]; then
    echo "Error: file not found: $log_file"
    exit 1
fi

echo "Analyzing: $log_file"
echo "Threshold: $threshold"
```

Always validate arguments. A script that crashes with a cryptic error when called wrong is a bad script. Print usage and exit 1 if the input is wrong.

---

## Exit codes

```bash
command && echo "success"       # run echo only if command succeeded (exit 0)
command || echo "failed"        # run echo only if command failed (non-zero exit)
command1 && command2 && command3   # chain: stop at first failure

# In a script: exit with a code
exit 0    # success
exit 1    # general error
exit 2    # usage error

# Check exit code
ls /nonexistent 2>/dev/null
echo "Exit code: $?"   # prints: Exit code: 2
```

`&&` and `||` are how you write conditional logic in one-liners. `mkdir logs && cd logs` creates the directory and enters it, but only if mkdir succeeded.

---

## Text processing — the triad

Three tools you will use constantly: `grep`, `awk`, `sed`.

### grep — filter lines
```bash
grep "ERROR" app.log                     # lines containing ERROR
grep -c "ERROR" app.log                  # count matching lines
grep -i "error" app.log                  # case insensitive
grep -v "DEBUG" app.log                  # exclude DEBUG lines
grep -E "ERROR|WARN" app.log             # regex: ERROR or WARN
grep -E "OOMKilled|CrashLoop" app.log    # find k8s incidents
grep -n "ERROR" app.log                  # show line numbers
grep -A 3 "ERROR" app.log               # show 3 lines after each match
grep -B 2 "ERROR" app.log               # show 2 lines before each match
```

### awk — process columns
```bash
# awk sees each line as fields separated by whitespace ($1, $2, ...)
ps aux | awk '{print $1, $2, $11}'          # print user, PID, command
awk '{print $1}' access.log                 # print first field of every line
awk -F: '{print $1}' /etc/passwd            # use : as separator, print first field
awk '$3 > 50 {print $0}' metrics.log        # print lines where field 3 > 50
awk 'END {print NR}' file.txt               # print total line count (NR = number of records)
awk '{sum += $2} END {print sum}' data.txt  # sum column 2
```

### sed — edit/transform text
```bash
sed 's/ERROR/[ERROR]/g' app.log             # replace ERROR with [ERROR] everywhere
sed 's/password=[^ ]*/password=[REDACTED]/g' log   # redact passwords
sed '/DEBUG/d' app.log                      # delete DEBUG lines
sed -n '10,20p' app.log                     # print only lines 10-20
sed -i 's/localhost/0.0.0.0/g' config.txt   # edit file in place
```

---

## Build: log_analyzer.sh

Save this at `/workspaces/aois-system/practice/log_analyzer.sh`.

First, create a sample log to test with:
```bash
cat > /tmp/sample.log << 'EOF'
2026-04-17 09:00:01 INFO  pod/payment-service started
2026-04-17 09:00:45 ERROR pod/payment-service CrashLoopBackOff restarts=8
2026-04-17 09:01:02 ERROR pod/auth-service OOMKilled memory_limit=512Mi
2026-04-17 09:01:15 WARN  disk usage at 87% on node/worker-1
2026-04-17 09:01:30 ERROR HTTP 503 service unavailable — payment endpoint
2026-04-17 09:02:00 ERROR HTTP 503 service unavailable — payment endpoint
2026-04-17 09:02:15 ERROR HTTP 503 service unavailable — payment endpoint
2026-04-17 09:02:30 INFO  pod/cache-service healthy
2026-04-17 09:03:00 WARN  TLS certificate expires in 4 days
2026-04-17 09:03:30 ERROR pod/auth-service OOMKilled memory_limit=512Mi
EOF
```

Now the analyzer:
```bash
#!/bin/bash

# log_analyzer.sh — pre-AI log analysis
# Shows what pattern matching looks like before intelligence

LOG_FILE="${1:-/tmp/sample.log}"
ERROR_THRESHOLD="${2:-3}"

if [ ! -f "$LOG_FILE" ]; then
    echo "Error: log file not found: $LOG_FILE"
    echo "Usage: $0 <log_file> [error_threshold]"
    exit 1
fi

echo "================================================"
echo "  AOIS Log Analyzer v0 — Pattern Matching Mode"
echo "================================================"
echo "File:      $LOG_FILE"
echo "Lines:     $(wc -l < "$LOG_FILE")"
echo "Analyzed:  $(date)"
echo ""

# --- Counts ---
total_errors=$(grep -c "ERROR" "$LOG_FILE" 2>/dev/null || echo 0)
total_warns=$(grep -c "WARN" "$LOG_FILE" 2>/dev/null || echo 0)

echo "=== Summary ==="
echo "Errors:    $total_errors"
echo "Warnings:  $total_warns"
echo ""

# --- Severity assignment (the brittle part) ---
echo "=== Incident Detection ==="

severity="P4"
reason="No critical patterns detected"

if grep -q "OOMKilled" "$LOG_FILE"; then
    echo "[DETECTED] OOMKilled — container exceeded memory limit"
    severity="P2"
    reason="OOMKilled detected"
fi

if grep -q "CrashLoopBackOff" "$LOG_FILE"; then
    echo "[DETECTED] CrashLoopBackOff — pod repeatedly crashing"
    severity="P1"
    reason="CrashLoopBackOff detected"
fi

if grep -q "503" "$LOG_FILE"; then
    count_503=$(grep -c "503" "$LOG_FILE")
    echo "[DETECTED] HTTP 503 errors: $count_503 occurrences"
    if [ "$count_503" -ge "$ERROR_THRESHOLD" ]; then
        severity="P1"
        reason="$count_503 x HTTP 503 — service unavailable"
    fi
fi

if grep -qE "cert.*expires|TLS.*expires" "$LOG_FILE"; then
    echo "[DETECTED] Certificate expiry warning"
    if [ "$severity" = "P4" ]; then
        severity="P3"
        reason="Certificate expiry detected"
    fi
fi

if grep -qE "disk.*[89][0-9]%|disk.*100%" "$LOG_FILE"; then
    echo "[DETECTED] High disk usage"
    if [ "$severity" = "P4" ]; then
        severity="P3"
        reason="High disk usage"
    fi
fi

echo ""
echo "=== Assessment ==="
echo "Severity:  $severity"
echo "Reason:    $reason"
echo ""

# --- Suggested action (hardcoded per pattern) ---
echo "=== Suggested Action ==="
case "$severity" in
    P1)
        echo "IMMEDIATE: Page on-call. Investigate pod restarts and service availability."
        ;;
    P2)
        echo "URGENT: Increase memory limits or optimize pod memory usage within 1 hour."
        ;;
    P3)
        echo "WARNING: Address within 24 hours. Review cert renewal or disk cleanup."
        ;;
    P4)
        echo "LOW: Monitor. No immediate action required."
        ;;
esac

echo ""
echo "=== Raw Error Lines ==="
grep "ERROR" "$LOG_FILE" | head -5

echo ""
echo "================================================"
echo "  Confidence: unknown (pattern matching has no"
echo "  concept of confidence — it either matches or"
echo "  it doesn't)"
echo "================================================"
```

Run it:
```bash
chmod +x /workspaces/aois-system/practice/log_analyzer.sh
bash /workspaces/aois-system/practice/log_analyzer.sh /tmp/sample.log
```

Now read the script and ask yourself:
- What happens with a log format this script has never seen?
- What if an OOMKill is actually low severity in context?
- How does this handle multiple simultaneous incidents?
- What does "confidence" even mean here?

The answers are: it fails, it can't tell, it can't, and it has no concept of confidence.

That is what v1 replaces with one API call.

---

## What you can and cannot do in bash

| Good for | Bad for |
|----------|---------|
| File operations | Complex data structures |
| Running other programs | Reliable string parsing |
| System administration | Numeric precision |
| Glue between tools | Multi-step reasoning |
| Quick automation | Error context awareness |
| CI/CD pipelines | Understanding log meaning |

Bash is powerful for what it is designed for. Log *intelligence* is not what it is designed for. That is why AOIS exists.
