# v0.2 — Bash Scripting: The Glue of DevOps

## What this version is about

Bash is the language that holds everything together. GitHub Actions pipelines are bash. Kubernetes init containers run bash. Dockerfile RUN commands are bash. Every time you SSH into a broken server, you fix it with bash. Every automation script in SRE work is bash.

This version also builds the bridge to v1. You will write `log_analyzer.sh` — a bash script that does log analysis the manual way. It will handle 5 patterns and miss everything else. When v1 arrives and Claude replaces it with one API call, you will understand exactly what changed and why it matters.

---

## Prerequisites

- v0.1 complete — you can navigate the terminal without hesitation
- The practice directory exists: `/workspaces/aois-system/practice/`
- A sample log file to work with (created in this version)

Verify:
```bash
ls /workspaces/aois-system/practice/
```
Expected: you see `sysinfo.sh` from v0.1.

---

## Learning goals

By the end of this version you will be able to:
- Write bash scripts from scratch
- Use variables, conditionals, loops, and functions correctly
- Process text with grep, awk, and sed
- Pass arguments to scripts and validate them
- Use exit codes to signal success and failure
- Write the patterns that appear in every CI/CD pipeline
- Understand exactly why bash log analysis fails and what AI solves

---

## Part 1 — The shebang and script basics

Every bash script starts with a shebang line:
```bash
#!/bin/bash
```
This tells the OS which interpreter to use when running the file. Without it, the OS might try to run it with sh (a simpler shell) and certain bash features will fail.

**How scripts execute:**

When you run `./script.sh`, the OS reads the shebang, finds `/bin/bash`, and passes the file to bash as input. Bash reads and executes each line in order.

When you run `bash script.sh`, you are explicitly telling bash to run it, so the shebang line is optional (but still good practice).

---

## Part 2 — Variables

```bash
#!/bin/bash

# Assign variables (no spaces around =)
name="collins"
count=0
log_file="/var/log/app.log"
max_errors=10

# Use variables with $
echo "Name: $name"
echo "Count: $count"
echo "Log file: $log_file"

# Always quote variables: "$name" not $name
# Without quotes, spaces in a variable break the command
file_with_spaces="my log file.txt"
cat $file_with_spaces     # WRONG: bash sees three arguments: my, log, file.txt
cat "$file_with_spaces"   # CORRECT: bash sees one argument: "my log file.txt"

# Arithmetic (must use $(( )) for math)
total=$((count + 5))
echo "Total: $total"

double=$((total * 2))
echo "Double: $double"

# String length
echo "Name length: ${#name}"      # 7

# Default value: use fallback if variable is unset or empty
port=${PORT:-8000}
environment=${ENV:-development}
echo "Port: $port"                 # 8000 if PORT not set in environment
```

Test this right now. Create and run it:
```bash
cat > /tmp/vars_test.sh << 'EOF'
#!/bin/bash
name="collins"
count=0
total=$((count + 5))
echo "Name: $name"
echo "Total: $total"
echo "Name length: ${#name}"
port=${PORT:-8000}
echo "Port: $port"
EOF
bash /tmp/vars_test.sh
```
Expected output:
```
Name: collins
Total: 5
Name length: 7
Port: 8000
```

---

## Part 3 — Conditionals

```bash
#!/bin/bash

severity="P1"

# Basic if/elif/else
if [ "$severity" = "P1" ]; then
    echo "CRITICAL — page the on-call engineer immediately"
elif [ "$severity" = "P2" ]; then
    echo "HIGH — respond within 1 hour"
elif [ "$severity" = "P3" ]; then
    echo "MEDIUM — address within 24 hours"
else
    echo "LOW — monitor, no immediate action"
fi
```

**Critical syntax rules:**
- Spaces inside `[ ]` are mandatory: `[ "$x" = "y" ]` not `["$x"="y"]`
- Quote variables inside conditions: `"$severity"` not `$severity`
- Semicolons after conditions: `if [ condition ]; then` — the `;` separates condition from `then`

**Comparison operators:**

String comparisons:
```bash
[ "$a" = "$b" ]     # equal
[ "$a" != "$b" ]    # not equal
[ -z "$a" ]         # true if a is empty (zero length)
[ -n "$a" ]         # true if a is not empty (non-zero length)
```

Number comparisons (use -eq -ne -gt -lt -ge -le, not = or !=):
```bash
[ $count -eq 0 ]    # equal to 0
[ $count -ne 0 ]    # not equal to 0
[ $count -gt 10 ]   # greater than 10
[ $count -lt 10 ]   # less than 10
[ $count -ge 10 ]   # greater than or equal to 10
[ $count -le 10 ]   # less than or equal to 10
```

File tests:
```bash
[ -f "file.txt" ]   # true if file exists and is a regular file
[ -d "dir/" ]       # true if directory exists
[ -r "file.txt" ]   # true if file is readable
[ -w "file.txt" ]   # true if file is writable
[ -x "script.sh" ]  # true if file is executable
[ ! -f ".env" ]     # true if .env does NOT exist (! inverts)
```

Combining conditions:
```bash
[ -f "main.py" ] && [ -r "main.py" ]    # both must be true (AND)
[ -f ".env" ] || [ -f ".env.example" ]  # either must be true (OR)
```

---

## Part 4 — Loops

### For loops

```bash
# Loop over a fixed list
for service in nginx redis postgres fastapi; do
    echo "Checking service: $service"
done
```
Expected output:
```
Checking service: nginx
Checking service: redis
Checking service: postgres
Checking service: fastapi
```

```bash
# Loop over files
for file in /workspaces/aois-system/curriculum/phase0/*/notes.md; do
    echo "Found: $file"
done

# Loop with counter
for ((i=1; i<=5; i++)); do
    echo "Attempt $i of 5"
done

# Loop over command output
for pid in $(pgrep python3); do
    echo "Python process: $pid"
done
```

### While loops

```bash
# Count down
count=3
while [ $count -gt 0 ]; do
    echo "Countdown: $count"
    count=$((count - 1))
done
echo "Done"
```
Expected:
```
Countdown: 3
Countdown: 2
Countdown: 1
Done
```

Read a file line by line (the correct pattern):
```bash
while IFS= read -r line; do
    echo "Line: $line"
done < /workspaces/aois-system/requirements.txt
```

`IFS=` prevents word splitting (treats each line as one unit even with spaces).
`-r` prevents backslash interpretation.
Without both of these, lines with spaces or backslashes behave unexpectedly.

---

## Part 5 — Functions

```bash
#!/bin/bash

# Define a function
check_port() {
    local port="$1"         # local: only exists inside this function
    local service="$2"

    if lsof -i ":$port" > /dev/null 2>&1; then
        echo "✓ $service is running on port $port"
        return 0    # success
    else
        echo "✗ $service is NOT running on port $port"
        return 1    # failure
    fi
}

# Call the function
check_port 8000 "FastAPI"
check_port 6379 "Redis"
check_port 5432 "Postgres"

# Use the return code
if check_port 8000 "FastAPI"; then
    echo "Server is healthy"
else
    echo "Server is down — investigate"
fi
```

**Why `local` matters:**
Without `local`, variables inside functions are global. They leak into the rest of the script and can overwrite variables with the same name, causing bugs that are very hard to find. Always use `local` for function variables.

**Return codes:**
- `return 0` = success (the function did what it was supposed to do)
- `return 1` = failure (anything non-zero means failure)
- `$?` holds the exit code of the last command

```bash
ls /nonexistent 2>/dev/null
echo "Exit code: $?"    # prints: Exit code: 2
```

---

## Part 6 — Script arguments

```bash
#!/bin/bash

# $0 = script name itself
# $1 = first argument
# $2 = second argument
# $# = number of arguments provided
# $@ = all arguments (each as separate item)

echo "Script: $0"
echo "First arg: $1"
echo "Second arg: $2"
echo "All args: $@"
echo "Count: $#"
```

Save as `/tmp/args_test.sh` and run:
```bash
bash /tmp/args_test.sh hello world foo
```
Expected:
```
Script: /tmp/args_test.sh
First arg: hello
Second arg: world
All args: hello world foo
Count: 3
```

Always validate arguments at the top of every script:
```bash
#!/bin/bash

LOG_FILE="$1"
THRESHOLD="${2:-10}"    # default to 10 if not provided

# Validate: require at least one argument
if [ $# -lt 1 ]; then
    echo "Usage: $0 <log_file> [error_threshold]"
    echo "Example: $0 /var/log/app.log 20"
    exit 1
fi

# Validate: the file must exist
if [ ! -f "$LOG_FILE" ]; then
    echo "Error: file not found: $LOG_FILE"
    exit 1
fi

echo "Analyzing: $LOG_FILE with threshold: $THRESHOLD"
```

A script that crashes with a cryptic error when called incorrectly wastes time. Print a clear usage message and `exit 1` immediately.

---

## Part 7 — Exit codes and &&/||

Exit codes are how processes communicate success or failure to the shell.

```bash
# && runs the next command ONLY if the previous succeeded (exit 0)
mkdir /tmp/testdir && cd /tmp/testdir && echo "Success"

# || runs the next command ONLY if the previous failed (non-zero exit)
mkdir /tmp/testdir 2>/dev/null || echo "Directory already exists"

# Chain them
git add . && git commit -m "message" && git push

# In scripts: exit with meaningful codes
exit 0    # success
exit 1    # general error
exit 2    # usage/argument error
```

The `&&` pattern is everywhere in shell scripts and Dockerfiles:
```dockerfile
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
```
If `apt-get update` fails, the install never runs. If the install fails, the cleanup never runs.

---

## Part 8 — Text processing: grep, awk, sed

These three tools process text. You will use them constantly.

### grep — find lines

```bash
# Filter log file to only error lines
grep "ERROR" /var/log/syslog

# Count how many errors
grep -c "ERROR" /var/log/syslog

# Case insensitive
grep -i "error" /var/log/syslog

# Show line numbers
grep -n "OOMKilled" /var/log/syslog

# Exclude lines (invert match)
grep -v "DEBUG" /var/log/syslog

# Match either of two patterns
grep -E "OOMKilled|CrashLoop" /var/log/syslog

# Show context lines around matches
grep -A 3 "ERROR" app.log    # 3 lines after
grep -B 2 "ERROR" app.log    # 2 lines before
grep -C 2 "ERROR" app.log    # 2 lines both sides
```

### awk — process columns

awk sees each line as columns separated by whitespace. `$1` is the first column, `$2` the second, etc.

```bash
# Print specific columns from ps output
ps aux | awk '{print $1, $2, $11}'    # user, PID, command

# Print lines where column 3 (CPU) is greater than 5
ps aux | awk '$3 > 5 {print $0}'

# Sum a column
awk '{sum += $2} END {print "Total:", sum}' data.txt

# Use different separator (colon for /etc/passwd)
awk -F: '{print $1}' /etc/passwd      # print just usernames

# Count total lines
awk 'END {print NR}' file.txt
```

Test it now:
```bash
ps aux | awk 'NR==1 || $3 > 0.1 {print $1, $2, $3, $11}' | head -10
```
This prints the header line (NR==1) plus any process using more than 0.1% CPU.

### sed — transform text

```bash
# Replace text
sed 's/ERROR/[ERROR]/g' app.log        # replace all occurrences on each line

# Delete lines matching pattern
sed '/DEBUG/d' app.log

# Print only specific line range
sed -n '10,20p' app.log                # lines 10 to 20

# Edit file in place (modify the actual file)
sed -i 's/localhost/0.0.0.0/g' config.txt

# Redact sensitive data
sed 's/password=[^ ]*/password=[REDACTED]/g' app.log
```

---

## Build: log_analyzer.sh

Now build the main script for this version.

### Step 1: Create a sample log file

```bash
cat > /tmp/sample_aois.log << 'EOF'
2026-04-17 09:00:01 INFO  pod/api-gateway started successfully
2026-04-17 09:00:45 ERROR pod/payment-service CrashLoopBackOff restarts=8
2026-04-17 09:01:02 ERROR pod/auth-service OOMKilled memory_limit=512Mi exit_code=137
2026-04-17 09:01:15 WARN  disk usage 87% on node/worker-1 filesystem=/var/lib/docker
2026-04-17 09:01:30 ERROR HTTP 503 service unavailable endpoint=/api/payment
2026-04-17 09:02:00 ERROR HTTP 503 service unavailable endpoint=/api/payment
2026-04-17 09:02:15 ERROR HTTP 503 service unavailable endpoint=/api/payment
2026-04-17 09:02:30 INFO  pod/cache-service healthy uptime=4d
2026-04-17 09:03:00 WARN  TLS certificate api.prod.company.com expires in 4 days
2026-04-17 09:03:30 ERROR pod/auth-service OOMKilled memory_limit=512Mi exit_code=137
2026-04-17 09:04:00 DEBUG pod/api-gateway processing request id=abc123
2026-04-17 09:04:15 INFO  autoscaler scaled payment-service from 2 to 4 replicas
EOF
```

Verify it was created:
```bash
wc -l /tmp/sample_aois.log
cat /tmp/sample_aois.log
```
Expected: 12 lines, showing all the log entries.

### Step 2: Create the analyzer script

```bash
cat > /workspaces/aois-system/practice/log_analyzer.sh << 'SCRIPT'
#!/bin/bash
# log_analyzer.sh — Pre-AI log analysis using pattern matching
# This is what log analysis looked like before LLMs.
# It handles the patterns it knows. It misses everything else.

# ---- Configuration ----
LOG_FILE="${1:-/tmp/sample_aois.log}"
ERROR_THRESHOLD="${2:-3}"

# ---- Argument validation ----
if [ ! -f "$LOG_FILE" ]; then
    echo "Error: Log file not found: $LOG_FILE"
    echo "Usage: $0 <log_file> [error_threshold]"
    exit 1
fi

# ---- Helper function ----
count_pattern() {
    local pattern="$1"
    local file="$2"
    grep -ciE "$pattern" "$file" 2>/dev/null || echo 0
}

contains_pattern() {
    local pattern="$1"
    local file="$2"
    grep -qiE "$pattern" "$file" 2>/dev/null
    return $?
}

# ---- Header ----
echo "=================================================="
echo "  AOIS Log Analyzer (Pre-AI Pattern Matching)"
echo "=================================================="
echo "Log file:  $LOG_FILE"
echo "Lines:     $(wc -l < "$LOG_FILE")"
echo "Threshold: $ERROR_THRESHOLD errors triggers P1"
echo "Analyzed:  $(date)"
echo ""

# ---- Summary counts ----
total_errors=$(count_pattern "ERROR" "$LOG_FILE")
total_warns=$(count_pattern "WARN" "$LOG_FILE")
total_info=$(count_pattern "INFO" "$LOG_FILE")

echo "=== Line Counts ==="
echo "  ERROR:    $total_errors"
echo "  WARN:     $total_warns"
echo "  INFO:     $total_info"
echo ""

# ---- Incident detection ----
echo "=== Incident Detection ==="

severity="P4"
reasons=""
detected_count=0

# Check for CrashLoopBackOff
if contains_pattern "CrashLoopBackOff" "$LOG_FILE"; then
    count=$(count_pattern "CrashLoopBackOff" "$LOG_FILE")
    echo "  [DETECTED] CrashLoopBackOff — $count occurrence(s)"
    severity="P1"
    reasons="CrashLoopBackOff detected"
    detected_count=$((detected_count + 1))
fi

# Check for OOMKilled
if contains_pattern "OOMKilled" "$LOG_FILE"; then
    count=$(count_pattern "OOMKilled" "$LOG_FILE")
    echo "  [DETECTED] OOMKilled — $count occurrence(s)"
    if [ "$severity" = "P4" ]; then
        severity="P2"
        reasons="OOMKilled detected"
    fi
    detected_count=$((detected_count + 1))
fi

# Check for repeated HTTP 503
count_503=$(count_pattern "503" "$LOG_FILE")
if [ "$count_503" -ge "$ERROR_THRESHOLD" ]; then
    echo "  [DETECTED] HTTP 503 errors — $count_503 occurrences (threshold: $ERROR_THRESHOLD)"
    if [ "$severity" = "P4" ] || [ "$severity" = "P3" ]; then
        severity="P1"
        reasons="$count_503 x HTTP 503 service unavailable"
    fi
    detected_count=$((detected_count + 1))
elif [ "$count_503" -gt 0 ]; then
    echo "  [INFO] HTTP 503 — $count_503 occurrence(s) (below threshold of $ERROR_THRESHOLD)"
fi

# Check for certificate expiry
if contains_pattern "cert.{0,30}expir|TLS.{0,30}expir" "$LOG_FILE"; then
    echo "  [DETECTED] Certificate expiry warning"
    if [ "$severity" = "P4" ]; then
        severity="P3"
        reasons="Certificate expiry warning"
    fi
    detected_count=$((detected_count + 1))
fi

# Check for high disk usage
if contains_pattern "disk.{0,20}[89][0-9]%" "$LOG_FILE"; then
    echo "  [DETECTED] High disk usage"
    if [ "$severity" = "P4" ]; then
        severity="P3"
        reasons="High disk usage"
    fi
    detected_count=$((detected_count + 1))
fi

if [ "$detected_count" -eq 0 ]; then
    echo "  No known incident patterns detected"
fi

echo ""

# ---- Assessment ----
echo "=== Assessment ==="
echo "  Severity: $severity"
echo "  Reason:   ${reasons:-No patterns matched}"
echo ""

# ---- Suggested action (canned responses per severity) ----
echo "=== Suggested Action ==="
case "$severity" in
    P1)
        echo "  IMMEDIATE ACTION REQUIRED"
        echo "  - Page the on-call engineer now"
        echo "  - Investigate pod crash logs: kubectl logs <pod> --previous"
        echo "  - Check service availability"
        ;;
    P2)
        echo "  RESPOND WITHIN 1 HOUR"
        echo "  - Review memory limits in pod spec"
        echo "  - Check: kubectl describe pod <pod-name>"
        echo "  - Consider increasing memory limits"
        ;;
    P3)
        echo "  ADDRESS WITHIN 24 HOURS"
        echo "  - Review and address before it escalates"
        ;;
    P4)
        echo "  LOW PRIORITY — monitor"
        echo "  - No immediate action required"
        ;;
esac

echo ""
echo "=== Error Lines (first 5) ==="
grep -iE "ERROR" "$LOG_FILE" | head -5 | sed 's/^/  /'

echo ""
echo "=================================================="
echo "  Confidence: NONE"
echo "  This is pattern matching. It matched or it did not."
echo "  No understanding of context, severity nuance, or"
echo "  anything outside the 5 patterns hardcoded above."
echo "=================================================="
SCRIPT
```

Make it executable:
```bash
chmod +x /workspaces/aois-system/practice/log_analyzer.sh
```

### Step 3: Run it

```bash
bash /workspaces/aois-system/practice/log_analyzer.sh /tmp/sample_aois.log
```

Expected output:
```
==================================================
  AOIS Log Analyzer (Pre-AI Pattern Matching)
==================================================
Log file:  /tmp/sample_aois.log
Lines:     12
Threshold: 3 errors triggers P1
Analyzed:  Thu Apr 17 12:30:00 UTC 2026

=== Line Counts ===
  ERROR:    6
  WARN:     2
  INFO:     3

=== Incident Detection ===
  [DETECTED] CrashLoopBackOff — 1 occurrence(s)
  [DETECTED] OOMKilled — 2 occurrence(s)
  [DETECTED] HTTP 503 errors — 3 occurrences (threshold: 3)
  [DETECTED] Certificate expiry warning
  [DETECTED] High disk usage

=== Assessment ===
  Severity: P1
  Reason:   CrashLoopBackOff detected

...
```

### Step 4: Test what it cannot handle

```bash
# A log with no known patterns — AOIS has no idea
echo "2026-04-17 10:00 ERROR payment service latency p99 jumped to 8 seconds, baseline 200ms" | \
  tee /tmp/latency_log.txt && \
  bash /workspaces/aois-system/practice/log_analyzer.sh /tmp/latency_log.txt
```

Expected: Severity P4, "No patterns matched." But that log describes a serious problem. The script has no idea.

```bash
# A staging OOMKill — not production, should be low severity
echo "2026-04-17 10:00 ERROR TEST pod/test-runner OOMKilled in staging environment" | \
  tee /tmp/staging_log.txt && \
  bash /workspaces/aois-system/practice/log_analyzer.sh /tmp/staging_log.txt
```

Expected: Severity P2. The script treats a staging test OOMKill exactly the same as a production OOMKill. The word "TEST" and "staging" mean nothing to regex.

These two failures are exactly what v1 solves.

---

## Troubleshooting

**Script runs but produces no output:**
```bash
bash -x /workspaces/aois-system/practice/log_analyzer.sh /tmp/sample_aois.log
```
`-x` enables trace mode — bash prints every command before running it. You can see exactly where it stops.

**"[: integer expression expected":**
You are using a numeric comparison (`-gt`, `-lt`) on a variable that is not a number. Check:
```bash
count=$(count_pattern "ERROR" "$LOG_FILE")
echo "Count value: '$count'"     # if empty, the function returned nothing
```

**"command not found: count_pattern":**
The function is defined after you try to call it. In bash, functions must be defined before use. Move the function definitions to the top of the script, before the code that calls them.

**Script exits with no error message:**
Check `$?` immediately after the problem:
```bash
bash log_analyzer.sh
echo "Exit code: $?"
```
A non-zero exit code means something failed. Add `set -e` at the top of the script to make it exit immediately on any error, then run with `-x` to trace.

**grep returns 0 matches but you can see the text:**
Check if there is a charset issue with your log file:
```bash
file /tmp/sample_aois.log     # should say "ASCII text"
cat -A /tmp/sample_aois.log   # shows hidden characters (^M = Windows line endings)
```
If you see `^M` at end of lines, convert with: `sed -i 's/\r//' file.txt`

---

## What bash cannot do — and why this matters

Read the bottom of the output you just produced:
```
Confidence: NONE
This is pattern matching. It matched or it did not.
No understanding of context, severity nuance, or
anything outside the 5 patterns hardcoded above.
```

Adding a new incident type to this script requires:
1. Writing a new regex pattern
2. Testing it against sample data
3. Deciding what severity and action to hardcode
4. Deploying the changed script

That is engineering work for every new incident type, every new log format, every new service. In a real environment with hundreds of services, thousands of log formats, and new failure modes appearing constantly, this approach does not scale.

v1 replaces `analyze_with_regex()` with `analyze_with_claude()`. The infrastructure stays identical. One function changes. And suddenly AOIS handles every log format it has ever seen.

---

## Connection to later phases

- **Phase 2 (v4)**: Dockerfile `RUN` commands are bash. You will use `&&` chaining, `||` fallbacks, and conditional logic inside Docker builds
- **Phase 3 (v6)**: Kubernetes readiness/liveness probe scripts are bash
- **Phase 3 (v8)**: ArgoCD hook scripts are bash
- **Phase 9 (v28)**: GitHub Actions `run:` steps are bash — every CI step you write uses these patterns
- **The pattern**: When you see a CI pipeline fail, you debug it by running the bash commands locally. This version gives you that skill.
