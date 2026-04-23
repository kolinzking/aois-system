# v0.1 — Linux Essentials: Living in the Terminal
⏱ **Estimated time: 3–5 hours**

## What this version is about

Every server, container, cloud VM, and Kubernetes node you will ever touch runs Linux. You will never have a GUI. You will only have a terminal. This version builds the muscle memory to move around confidently without thinking about the commands.

The goal is not to memorise everything. It is to recognise patterns. After running these commands enough times, the right command appears naturally when you need it.

---

## Prerequisites

- A terminal open in your Codespace (or any Linux machine)
- Nothing else required — Linux is already there

Verify you have a Linux environment:
```bash
uname -a
```
Expected output (something like):
```
Linux codespace-xxx 6.8.0-1044-azure #46~22.04.1-Ubuntu SMP Mon Feb 10 01:07:36 UTC 2025 x86_64 x86_64 x86_64 GNU/Linux
```
If you see this, you are on Linux. Good.

---

## Learning goals

By the end of this version you will be able to:
- Navigate any filesystem without hesitation
- Read, create, move, copy, and delete files and directories
- Understand and change file permissions
- Find and kill any process
- Use environment variables correctly
- Pipe commands together to answer questions about your system
- Write and run a basic shell script
- Not be slowed down by the terminal

---

## Part 1 — The filesystem: where everything lives

Linux puts everything in one tree starting at `/` (called "root"). There is no C: drive or D: drive. One tree, everything hangs off it.

```
/
├── home/           user home directories
│   └── codespace/  your home directory (~ is a shortcut for this)
├── etc/            configuration files (nginx.conf, ssh config, etc.)
├── var/            variable data — logs live here
│   └── log/        system and application logs
├── tmp/            temporary files, deleted on reboot
├── proc/           virtual filesystem — running kernel and process info
├── usr/
│   ├── bin/        most user commands (python3, git, curl)
│   └── local/      software you installed yourself
├── bin/            essential commands (ls, bash, cat)
└── opt/            optional third-party software
```

Run this to see the top level:
```bash
ls /
```
Expected output:
```
bin  boot  dev  etc  home  lib  lib64  media  mnt  opt  proc  root  run  sbin  srv  sys  tmp  usr  var
```

Everything you need is in one of those directories. Nothing is random.

---

## Part 2 — Navigation

### Where am I?

```bash
pwd
```
Expected output:
```
/workspaces/aois-system
```
`pwd` = print working directory. Use it whenever you are disoriented.

### What is in this directory?

```bash
ls
```
Expected output (something like):
```
CLAUDE.md  Dockerfile  README.md  curriculum  docker-compose.yml  main.py  requirements.txt
```

### What is in this directory — full details (permissions, owner, size, date)

```bash
ls -la
```
Expected output:
```
total 64
drwxr-xr-x  8 codespace codespace 4096 Apr 17 12:00 .
drwxr-xr-x  3 root      root      4096 Apr 17 09:00 ..
-rw-r--r--  1 codespace codespace  832 Apr 17 12:00 CLAUDE.md
drwxr-xr-x  4 codespace codespace 4096 Apr 17 12:00 curriculum
-rw-r--r--  1 codespace codespace  123 Apr 17 11:00 main.py
```

Reading the `ls -la` output, column by column:
```
drwxr-xr-x   8   codespace  codespace   4096   Apr 17 12:00   curriculum
│            │   │           │           │       │              └─ name
│            │   │           │           │       └─ last modified
│            │   │           │           └─ size in bytes
│            │   │           └─ group owner
│            │   └─ user owner
│            └─ number of hard links
└─ permissions (d=directory, -=file, l=symlink | then 9 permission bits)
```

Flags that matter:
- `-l` = long format (shows permissions, owner, size, date)
- `-a` = all (includes hidden files starting with `.`)
- `-h` = human-readable sizes (4.0K instead of 4096)
- `-t` = sort by modification time (newest first)

### What is in this directory — full details with human-readable sizes

```bash
ls -lah
```
Expected output:
```
total 64K
drwxr-xr-x  8 codespace codespace 4.0K Apr 17 12:00 .
drwxr-xr-x  3 root      root      4.0K Apr 17 09:00 ..
-rw-r--r--  1 codespace codespace  832 Apr 17 12:00 CLAUDE.md
drwxr-xr-x  4 codespace codespace 4.0K Apr 17 12:00 curriculum
-rw-r--r--  1 codespace codespace  123 Apr 17 11:00 main.py
```

The only difference from `ls -la`: the size column reads `4.0K` instead of `4096`. For files in the megabyte or gigabyte range this matters — `1.2G` is instantly readable, `1287651328` is not. Use `ls -lah` when you care about sizes (checking a log file, a build artifact, a Docker layer). Use `ls -la` when you need the exact byte count.

You will use both constantly. Default to `ls -lah`.

### Moving around

```bash
cd curriculum           # go into curriculum directory (relative path)
pwd                     # confirm where you are
ls                      # see what's here
cd ..                   # go up one level
pwd                     # back where you started
cd /workspaces          # go to absolute path (always works regardless of where you are)
cd -                    # go back to where you just were
cd ~                    # go to your home directory
pwd                     # /home/codespace
cd /workspaces/aois-system   # back to the project
```

**Absolute vs relative paths:**
- Absolute path starts with `/` — works from anywhere: `cd /workspaces/aois-system`
- Relative path is relative to where you are now: `cd curriculum` (only works if curriculum is in current directory)

**Tip:** press Tab to autocomplete. Type `cd curr` then press Tab — it completes to `curriculum`. Press Tab twice to see all options if there are multiple matches.

---

## Part 3 — Reading files

```bash
cat main.py             # print entire file to terminal
head -20 main.py        # first 20 lines only
tail -20 main.py        # last 20 lines only
tail -f /var/log/syslog # follow file in real time (Ctrl+C to stop)
less main.py            # paginated viewer (scroll with arrows, q to quit, /text to search)
```

`tail -f` is one of the most-used SRE commands. When a service is misbehaving you run:
```bash
tail -f /var/log/service.log
```
And watch what it logs in real time while you reproduce the problem.

How many lines is a file — and how many words?

```bash
wc -l main.py
```
Expected output:
```
142 main.py
```
`wc` = word count. `-l` = count lines. The number on the left is the line count. Use this to quickly gauge how large a file is before opening it.

```bash
wc -w main.py
```
Expected output:
```
687 main.py
```
`-w` = count words (whitespace-separated tokens). Less useful for code, but essential when working with log files or text data where word frequency matters.

---

> **▶ STOP — do this now**
>
> Run these three commands and look carefully at the output:
> ```bash
> wc -l /workspaces/aois-system/main.py
> ```
> Expected output (your number will differ as the file grows):
> ```
> 142 /workspaces/aois-system/main.py
> ```
> This tells you the file is 142 lines long — small enough to read in full, large enough to be a real app.
>
> ```bash
> head -5 /workspaces/aois-system/main.py
> tail -5 /workspaces/aois-system/main.py
> ```
> `head` shows the imports at the top. `tail` shows the last function or route at the bottom.
> You are reading a real production file — the AOIS FastAPI app you will understand completely by v1.
> You do not need to understand the code yet — this is practice with the tools while looking at real code.

---

## Part 4 — Creating, copying, moving, deleting

```bash
# Create
mkdir practice              # create directory
mkdir -p a/b/c              # create nested directories all at once
touch notes.txt             # create empty file (or update timestamp if it exists)

# Verify creation
ls -la | grep practice      # confirm practice directory exists

# Copy
cp main.py main_backup.py   # copy file
cp -r curriculum/ backup/   # copy directory recursively (-r = recursive)

# Move / rename
mv main_backup.py old_main.py    # rename (move within same directory)
mv old_main.py practice/         # move to a different directory

# Confirm
ls practice/
```
Expected:
```
old_main.py
```

```bash
# Delete
rm practice/old_main.py         # delete a file (permanent — no trash)
rm -rf backup/                  # delete directory and everything in it (-r recursive, -f force)
rmdir practice/                 # delete empty directory only
```

**Warning:** `rm -rf` has no undo. There is no recycle bin. When you delete something it is gone. Before running `rm -rf`, confirm what directory you are in with `pwd` and confirm what you are deleting with `ls`.

---

## Part 5 — Permissions

Every file has three permission groups: **owner**, **group**, **others**. Each has three bits: **r** (read=4), **w** (write=2), **x** (execute=1).

```
-rwxr-xr-x
│├─┤├─┤├─┤
│ │  │  └─ others: r-x = read + execute = 5
│ │  └─── group:  r-x = read + execute = 5
│ └────── owner:  rwx = read + write + execute = 7
└──────── type:   - = file, d = directory, l = symlink
```

The three digits in `chmod 755` map to owner/group/others in octal:
- `7` = 4+2+1 = rwx (read, write, execute)
- `5` = 4+0+1 = r-x (read, execute, no write)
- `4` = 4+0+0 = r-- (read only)
- `6` = 4+2+0 = rw- (read, write, no execute)

Common permission patterns:
```bash
chmod 755 script.sh     # owner can do anything, others can read+execute (scripts)
chmod 644 config.txt    # owner can read+write, others can only read (config files)
chmod 600 .env          # only owner can read+write (secrets — no one else should see)
chmod +x script.sh      # add execute for everyone (shortcut for making scripts runnable)
chmod -x script.sh      # remove execute for everyone
```

When you see this error:
```
bash: ./script.sh: Permission denied
```
Fix it with:
```bash
chmod +x script.sh
```

Check permissions on a file:
```bash
ls -la script.sh
```
Expected after `chmod +x`:
```
-rwxr-xr-x 1 codespace codespace 245 Apr 17 12:00 script.sh
```
The `x` bits are now set.

---

> **▶ STOP — do this now**
>
> Create a test script, set permissions wrong, observe the error, then fix it:
> ```bash
> echo '#!/bin/bash
> echo "permissions work"' > /tmp/test_perms.sh
>
> # Try to run it without execute bit
> ls -la /tmp/test_perms.sh          # notice: no x bits
> /tmp/test_perms.sh                 # fails with Permission denied
>
> # Fix it
> chmod +x /tmp/test_perms.sh
> ls -la /tmp/test_perms.sh          # now shows x bits
> /tmp/test_perms.sh                 # works: "permissions work"
>
> # Check the .env file permissions
> ls -la /workspaces/aois-system/.env 2>/dev/null || echo "no .env yet"
> ```
> Every script you write in this curriculum needs `chmod +x` before it will run. Now you know why.

---

## Part 6 — Processes

A process is any running program. Your FastAPI server, Redis, Postgres, the shell you are typing in — all processes, all have a process ID (PID).

```bash
ps aux              # list all running processes
```
Expected output (abbreviated):
```
USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
root         1  0.0  0.0  20292  3584 ?        Ss   Apr17   0:00 /sbin/init
codespace 1234  0.2  1.1 456789 45000 ?       Sl   12:00   0:02 python3 main.py
codespace 5678  0.0  0.0  12345  2000 pts/0   S    12:05   0:00 bash
```

Column meanings:
- `PID` — process ID (unique number)
- `%CPU` — CPU usage percentage
- `%MEM` — memory usage percentage
- `COMMAND` — what is running

Filter to find a specific process:
```bash
ps aux | grep python        # find Python processes
ps aux | grep uvicorn       # find uvicorn (your FastAPI server)
```
Expected when server is running:
```
codespace 2345  0.3  2.0 789012 80000 pts/0   S+   12:05   0:01 uvicorn main:app --port 8000
```

Kill a process:
```bash
kill 2345               # send SIGTERM — politely asks process to stop
kill -9 2345            # send SIGKILL — force stop immediately (use when SIGTERM fails)
```

Find and kill whatever is using port 8000 (used throughout this project):
```bash
lsof -ti:8000           # get PID of process using port 8000
lsof -ti:8000 | xargs kill -9   # kill it immediately
```

`lsof -ti:8000` returns just the PID with no other text. `xargs` takes that PID and passes it to `kill -9`. If nothing is on port 8000, lsof returns nothing and xargs does nothing.

Run in background (get your terminal back):
```bash
uvicorn main:app --port 8000 &
```
The `&` sends the process to background. You see the PID printed, then get your prompt back:
```
[1] 3456
```
The `[1]` is the job number. `3456` is the PID.

---

## Part 7 — Environment variables

Environment variables are key=value pairs that any process can read. This is how API keys reach your application without being in the code.

```bash
echo $HOME              # print HOME variable
```
Expected:
```
/home/codespace
```

```bash
echo $PATH              # print PATH — list of directories bash searches for commands
```
Expected (something like):
```
/usr/local/bin:/usr/bin:/bin:/home/codespace/.local/bin
```

When you run `python3`, bash looks through each directory in `$PATH` until it finds a file named `python3`. If it is not in any of those directories, you get `command not found`.

```bash
export MY_VAR="hello"   # set a variable for this terminal session
echo $MY_VAR            # prints: hello
env | grep MY_VAR       # see it in the environment
unset MY_VAR            # remove it
echo $MY_VAR            # prints: (empty)
```

Variables set with `export` exist only for the current terminal session. If you open a new terminal, they are gone. To make them permanent, add them to `~/.bashrc`:
```bash
echo 'export MY_VAR="hello"' >> ~/.bashrc
source ~/.bashrc        # reload .bashrc without opening a new terminal
```

For AOIS, secrets are in `.env` and loaded by `python-dotenv`. You never need to export them manually — the library handles it.

---

> **▶ STOP — do this now**
>
> Test environment variable scoping:
> ```bash
> # Set a variable WITHOUT export
> MY_VAR="hello"
> bash -c 'echo "child sees: $MY_VAR"'    # child shell sees nothing
>
> # Set WITH export
> export MY_VAR="hello"
> bash -c 'echo "child sees: $MY_VAR"'    # child shell sees: hello
>
> # Now see what AOIS actually uses
> cat /workspaces/aois-system/.env 2>/dev/null | head -3 || echo "no .env yet"
> printenv | grep -i anthropic            # check if key is already in environment
> ```
> This is why `load_dotenv()` in Python exists — it reads the `.env` file and exports the variables so child processes (your FastAPI server) can access them. Without `load_dotenv()`, `os.getenv("ANTHROPIC_API_KEY")` returns `None`.

---

## Part 8 — stdin, stdout, stderr: the three streams

Every process has three open file descriptors by default. Understanding these is prerequisite to understanding pipes and redirection.

```
┌─────────────────────────────────────────────┐
│                  process                    │
│                                             │
│  fd 0: stdin  ←── keyboard / pipe / file   │  ← input stream
│  fd 1: stdout ──→ terminal / pipe / file   │  ← normal output
│  fd 2: stderr ──→ terminal / pipe / file   │  ← error output
│                                             │
└─────────────────────────────────────────────┘
```

- **stdin (fd 0)**: where the process reads input from. By default: your keyboard. Pipes redirect this.
- **stdout (fd 1)**: where the process writes normal output. By default: your terminal.
- **stderr (fd 2)**: where the process writes error messages. By default: also your terminal — which is why errors appear mixed with output. They are two separate streams that both happen to display on screen.

Why separate stdout and stderr? So you can redirect one without the other:
```bash
python3 app.py > output.txt       # stdout goes to file, errors still show on screen
python3 app.py 2> errors.txt      # errors go to file, output still shows on screen
python3 app.py > out.txt 2>&1     # both go to the same file
```

`2>&1` means "point file descriptor 2 at the same place file descriptor 1 currently points." The `&1` is "file descriptor 1", not a file named `1`.

Test it right now:
```bash
# python3 -c "import sys" succeeds silently — stdout has nothing, stderr has nothing
python3 -c "import sys"
echo "Exit: $?"    # 0 = success

# This fails — the error goes to stderr
python3 -c "import nonexistent_module" 2>/dev/null
echo "Exit: $?"    # non-zero = failure

# Now capture only stderr
python3 -c "import nonexistent_module" 2> /tmp/py_error.txt
cat /tmp/py_error.txt    # the error message is here
```

Expected from last command:
```
ModuleNotFoundError: No module named 'nonexistent_module'
```

This matters every time you debug a container or process. When you run `uvicorn main:app` and see startup errors on your screen, those are stderr. When you redirect logs, they may not include errors unless you merge with `2>&1`.

---

## Part 8 — Pipes and redirection

The shell's superpower: compose small tools into pipelines. Each tool does one thing well, pipes connect them.

```bash
command > file.txt          # redirect stdout to file (creates or overwrites)
command >> file.txt         # append stdout to file (adds to existing)
command 2> errors.txt       # redirect stderr to file
command 2>&1                # redirect stderr to wherever stdout goes (merge both)
command > out.txt 2>&1      # both stdout and stderr go to out.txt
command1 | command2         # pipe: stdout of command1 becomes stdin of command2
```

Real examples that you will use:
```bash
# Find Python processes
ps aux | grep python

# Count how many files are in a directory
ls | wc -l

# See last 20 error lines from a log file
cat /var/log/syslog | grep ERROR | tail -20

# Find which process is using the most CPU
ps aux | sort -k3 -rn | head -5

# See only the HTTP errors in your FastAPI logs
docker compose logs aois | grep "HTTP 5"
```

When a command produces too much output:
```bash
ps aux | head -20       # only show first 20 lines
ps aux | tail -20       # only show last 20 lines
ps aux | less           # paginate it (scroll with arrows, q to quit)
```

Silence output you do not care about:
```bash
mkdir logs 2>/dev/null || true      # suppress "already exists" error
command > /dev/null 2>&1            # discard all output completely
```

---

## Part 9 — Searching

```bash
grep "error" app.log                    # lines containing "error" (case sensitive)
grep -i "error" app.log                 # case insensitive
grep -n "error" app.log                 # show line numbers
grep -c "error" app.log                 # count matching lines (number only)
grep -v "DEBUG" app.log                 # invert: lines NOT containing DEBUG
grep -r "ANTHROPIC" /workspaces/        # search recursively in directory
grep -E "OOMKilled|CrashLoop" app.log   # regex: match either pattern
grep -A 3 "ERROR" app.log              # show 3 lines AFTER each match
grep -B 2 "ERROR" app.log              # show 2 lines BEFORE each match
grep -C 2 "ERROR" app.log              # show 2 lines BEFORE AND AFTER (context)
```

Test grep right now:
```bash
grep -r "def " /workspaces/aois-system/main.py
```
Expected: shows all function definitions in main.py.

```bash
grep -rn "ANTHROPIC" /workspaces/aois-system/ --include="*.py"
```
Expected: shows every line in every Python file that mentions ANTHROPIC, with line numbers.

Find files:
```bash
find /workspaces/aois-system -name "*.py"       # all Python files
find . -name "*.md" -newer CLAUDE.md            # .md files newer than CLAUDE.md
find /tmp -mtime +7 -delete                     # delete files older than 7 days
```

---

## Part 9.5 — Text processing: awk and sed

These two tools appear throughout this curriculum — in `sysinfo.sh`, in Dockerfiles, in CI scripts, in every environment where you need to extract or transform text. Understanding them removes a major source of "what does this line do?" confusion.

### awk: the column extractor and reporter

`awk` processes text line by line. Each line is split into fields by whitespace (or a delimiter you specify). Fields are numbered: `$1`, `$2`, `$3`, ... `$NF` is the last field. `NR` is the current line number.

The basic syntax:
```bash
awk 'pattern { action }' file
```
If pattern matches the current line, the action runs. If you omit the pattern, the action runs on every line.

**Field extraction — the most common use:**
```bash
echo "codespace 1234 0.2 1.1 python3 main.py" | awk '{print $1, $2}'
```
Output:
```
codespace 1234
```

**Real example — extract memory info from `free -h`:**
```bash
free -h
```
Output:
```
               total        used        free      shared  buff/cache   available
Mem:           7.7Gi       2.1Gi       3.9Gi        45Mi       1.7Gi       5.3Gi
Swap:          1.0Gi          0B       1.0Gi
```

The `Mem:` line is row 2 (NR==2). The fields are: `$1=Mem:`, `$2=7.7Gi`, `$3=2.1Gi`, `$4=3.9Gi`, `$5=45Mi`, `$6=1.7Gi`, `$7=5.3Gi`.

To print a formatted memory summary:
```bash
free -h | awk 'NR==2 {printf "Total: %s | Used: %s | Available: %s\n", $2, $3, $7}'
```
Output:
```
Total: 7.7Gi | Used: 2.1Gi | Available: 5.3Gi
```

This exact pattern is in `sysinfo.sh`. Now you can read it without confusion.

**`printf` formatting in awk:**
- `%s` — string
- `%d` — integer
- `%f` — float
- `\n` — newline
- `%-10s` — left-aligned, padded to 10 characters

**Filtering with pattern:**
```bash
ps aux | awk '$3 > 1.0 {print $1, $2, $3, $11}'
```
This prints user, PID, CPU%, and command for any process using more than 1% CPU. The pattern `$3 > 1.0` is a numeric comparison on the third field.

**Column formatting:**
```bash
ps aux | awk 'NR==1{print "USER       PID   CPU  MEM  CMD"} NR>1 && NR<=6 {printf "%-10s %-6s %4s %4s  %s\n", $1, $2, $3, $4, $11}'
```
- `NR==1` — print header on first line
- `NR>1 && NR<=6` — process lines 2-6 (top 5 processes)
- `%-10s` — left-justify in 10-char field
- `%4s` — right-justify in 4-char field

**Custom delimiter:**
```bash
awk -F: '{print $1, $3}' /etc/passwd    # -F: sets field separator to colon
```
Output: username and UID for every user in the system.

**Counting:**
```bash
awk 'END {print NR " lines"}' /var/log/syslog
```
`END` runs after all lines are processed. `NR` is the total line count.

**Arithmetic:**
```bash
# Calculate total size from du output
du -s /workspaces/aois-system/* | awk '{sum += $1} END {print sum " KB total"}'
```

---

### sed: the stream editor (find and replace at scale)

`sed` edits text streams. The most common use is substitution:

```bash
sed 's/old/new/' file              # replace first occurrence per line
sed 's/old/new/g' file             # replace ALL occurrences per line (g = global)
sed 's/old/new/gi' file            # case-insensitive replace all
sed -i 's/old/new/g' file          # edit the file in-place (modifies the actual file)
```

**Real example — change a version in requirements.txt:**
```bash
cat requirements.txt | grep fastapi
```
```
fastapi==0.104.1
```
```bash
sed -i 's/fastapi==0.104.1/fastapi==0.110.0/g' requirements.txt
```

**Deleting lines:**
```bash
sed '/DEBUG/d' app.log             # delete lines containing DEBUG
sed '/^$/d' file                   # delete empty lines (^ = start, $ = end, ^$ = empty line)
sed '1,5d' file                    # delete lines 1 through 5
```

**Printing specific lines:**
```bash
sed -n '10,20p' file               # print only lines 10-20 (-n suppresses default output, p = print)
sed -n '/ERROR/p' app.log          # print only lines containing ERROR
```

**Extracting values from config-style files:**
```bash
# Given a file: KEY=value
sed -n 's/^ANTHROPIC_API_KEY=//p' .env
```
This removes `ANTHROPIC_API_KEY=` from the start of matching lines and prints what remains — the value. Used in shell scripts to extract config values without loading the whole .env.

**Multiple substitutions:**
```bash
sed -e 's/ERROR/[ERROR]/g' -e 's/WARN/[WARN]/g' app.log
```

**Why sed over Python for this?** When processing millions of log lines, sed (written in C, operates on streams) is orders of magnitude faster than Python string processing. It is the right tool when transformation is simple and volume is high.

---

### When to use which tool

| Task | Tool |
|------|------|
| Extract specific columns/fields from text | `awk` |
| Count lines, sum values, format output | `awk` |
| Find and replace text | `sed` |
| Delete or print specific lines | `sed` |
| Search for matching lines | `grep` |
| Complex transformation with logic | `awk` or Python |

---

## Part 10 — Disk and memory

```bash
df -h               # disk usage by filesystem, human-readable
```
Expected output:
```
Filesystem      Size  Used Avail Use% Mounted on
overlay          32G  8.5G   22G  29% /
tmpfs            64M     0   64M   0% /dev
```
The first row is your main disk. `Use%` shows how full it is. When it hits 90%+, you have a problem.

```bash
du -sh /workspaces/aois-system/     # size of the project directory
du -sh *                             # size of everything in current directory
du -sh * | sort -h                   # sorted by size (smallest first)
free -h                              # memory usage
```
Expected `free -h`:
```
               total        used        free      shared  buff/cache   available
Mem:           7.7Gi       2.1Gi       3.9Gi        45Mi       1.7Gi       5.3Gi
Swap:          1.0Gi          0B       1.0Gi
```
`Mem: available` is what actually matters — how much memory processes can use right now.

---

## Part 11 — Useful shortcuts

```
Ctrl+C          kill the current running process
Ctrl+Z          pause current process (suspends it)
Ctrl+D          end of input (closes terminal if used at prompt)
Ctrl+L          clear the screen
Ctrl+A          jump to beginning of current line
Ctrl+E          jump to end of current line
Ctrl+R          search through command history (type to filter, Enter to run)
Tab             autocomplete (single press = complete, double press = show options)
!!              repeat the last command
!git            repeat last command that started with "git"
Up/Down arrows  cycle through command history
history         show full command history
history | grep docker    find all docker commands you've run
```

`Ctrl+R` is especially useful. Press it, start typing `uvicorn`, and it finds the last uvicorn command you ran. Press Enter to run it.

---

## Build: sysinfo.sh

Now build something. Create this file at `/workspaces/aois-system/practice/sysinfo.sh`.

First, create the practice directory if it does not exist:
```bash
mkdir -p /workspaces/aois-system/practice
```

Create the file:
```bash
cat > /workspaces/aois-system/practice/sysinfo.sh << 'EOF'
#!/bin/bash
# AOIS System Info Report

echo "========================================="
echo "  AOIS System Info"
echo "  Generated: $(date)"
echo "========================================="
echo ""

echo "--- Host ---"
echo "Hostname:  $(hostname)"
echo "OS:        $(grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '"')"
echo "Kernel:    $(uname -r)"
echo "Uptime:    $(uptime -p 2>/dev/null || uptime)"
echo ""

echo "--- CPU ---"
echo "Cores:     $(nproc)"
echo "Load avg:  $(cut -d' ' -f1-3 /proc/loadavg)"
echo ""

echo "--- Memory ---"
free -h | awk 'NR==2 {printf "Total: %s | Used: %s | Free: %s | Available: %s\n", $2, $3, $4, $7}'
echo ""

echo "--- Disk ---"
df -h / | awk 'NR==2 {printf "Total: %s | Used: %s | Free: %s | Usage: %s\n", $2, $3, $4, $5}'
echo ""

echo "--- Top 5 Processes (by CPU) ---"
ps aux --sort=-%cpu | awk 'NR==1{print "USER       PID   CPU  MEM  CMD"} NR>1 && NR<=6 {printf "%-10s %-6s %4s %4s  %s\n", $1, $2, $3, $4, $11}'
echo ""

echo "--- Ports Listening ---"
ss -tlnp 2>/dev/null | grep LISTEN | awk '{print "  " $4}' | head -10
echo ""

echo "--- Python Version ---"
python3 --version 2>/dev/null || echo "Python3 not found"
echo ""

echo "--- Project Size ---"
if [ -d "/workspaces/aois-system" ]; then
    du -sh /workspaces/aois-system/ 2>/dev/null
fi
echo ""
echo "========================================="
EOF
```

Make it executable:
```bash
chmod +x /workspaces/aois-system/practice/sysinfo.sh
```

Run it:
```bash
bash /workspaces/aois-system/practice/sysinfo.sh
```

Expected output (your values will differ):
```
=========================================
  AOIS System Info
  Generated: Thu Apr 17 12:30:00 UTC 2026
=========================================

--- Host ---
Hostname:  codespace-abc123
OS:        Ubuntu 22.04.4 LTS
Kernel:    6.8.0-1044-azure
Uptime:    up 3 hours, 12 minutes

--- CPU ---
Cores:     4
Load avg:  0.12 0.08 0.05

--- Memory ---
Total: 7.7Gi | Used: 2.1Gi | Free: 3.9Gi | Available: 5.3Gi

--- Disk ---
Total: 32G | Used: 8.5G | Free: 22G | Usage: 29%

--- Top 5 Processes (by CPU) ---
USER       PID   CPU  MEM  CMD
...
```

---

## Common Mistakes

**1. `rm -rf` with a trailing space**
Symptom: `rm -rf / home/user` deletes the entire filesystem instead of `/home/user`.
The space after `/` makes it two arguments: `/` (root) and `home/user`.
Fix: Always quote paths. Never run `rm -rf` as root without double-checking.
Trigger it safely:
```bash
echo rm -rf / home/user   # print the command first — never run it blind
```

**2. Forgetting `sudo` then piping**
Symptom:
```
$ cat /etc/shadow | grep root
cat: /etc/shadow: Permission denied
```
The pipe runs as your user, not root. `sudo cat /etc/shadow` works. `cat /etc/shadow | sudo grep root` does not — the `cat` still runs as you.
Fix:
```bash
sudo cat /etc/shadow | grep root   # correct — sudo the command that needs elevation
```

**3. Permissions octal confusion: `chmod 755` vs `chmod +x`**
Symptom: Script runs for owner but not for teammates.
`chmod +x script.sh` adds execute for owner, group, and others.
`chmod 700 script.sh` gives owner full access, everyone else nothing.
Trigger it:
```bash
chmod 700 test.sh && bash test.sh                 # works — you are the owner
chmod 700 test.sh && sudo -u nobody bash test.sh  # Permission denied
```
Fix: For shared scripts use `755`. For private scripts use `700`.

**4. `cd` in a subshell doesn't change your directory**
Symptom: Script runs `cd /tmp` but your terminal stays where it was.
Every script runs in a subshell. `cd` only affects that subshell — it exits and you're back.
Fix: Source the script if you need directory changes to persist:
```bash
source ./script.sh   # runs in current shell — cd takes effect
./script.sh          # runs in subshell — cd is lost on exit
```

**5. Overwriting a file with redirection**
Symptom: `echo "new content" > important.log` — all previous content gone.
`>` truncates first, then writes. Even `> file` with no command wipes the file completely.
Trigger it:
```bash
echo "original" > test.log
echo "new entry" > test.log   # original is gone
cat test.log                  # only: new entry
```
Fix: Use `>>` to append:
```bash
echo "new entry" >> test.log  # safe — appends, original preserved
```

---

## Troubleshooting

**"command not found" after installing something:**
```bash
which python3           # where is it?
echo $PATH              # is that directory in PATH?
hash -r                 # clear bash's command cache
```
If the directory is not in PATH, add it: `export PATH=$PATH:/path/to/dir`

**"Permission denied" running a script:**
```bash
ls -la script.sh        # check permissions
chmod +x script.sh      # add execute permission
```

**"No such file or directory" when you can see the file:**
```bash
pwd                     # are you where you think you are?
ls -la                  # is the file actually there?
ls -la | grep filename  # search for it exactly
```
Typos in filenames are the most common cause.

**Accidentally deleted something:**
There is no undo for `rm`. The file is gone. Prevention: always use `ls` to confirm what you are about to delete before running `rm -rf`.

**Terminal is frozen:**
- `Ctrl+C` — kills the current command
- `Ctrl+Z` then `kill %1` — kills a suspended job
- `q` — exits less, man, git log
- Close and reopen the terminal as a last resort

---

## Commands you will use every day in this project

```bash
ls -la                          # see what is here
pwd                             # where am I
cd /workspaces/aois-system      # go to the project
tail -f logs/app.log            # watch logs in real time
ps aux | grep python            # is my server running?
lsof -ti:8000 | xargs kill -9   # kill whatever is on port 8000
chmod +x script.sh              # make a script executable
grep -r "error" .               # search for errors in all files
df -h                           # is the disk full?
free -h                         # is memory low?
```

You do not need to memorise all of this at once. Run the commands. The muscle memory builds through repetition, not study.

---

## Connection to later phases

- **Phase 2 (v4)**: You will use `docker exec` to shell into containers and use these commands to debug what is happening inside
- **Phase 3 (v6)**: You will SSH into your Hetzner VPS and use all of this to configure k3s
- **Phase 6 (v16)**: `ps aux`, `top`, `df`, `free` become your first-response debugging tools before the observability stack is up
- **Phase 7 (v20)**: When you give AOIS tools like `get_pod_logs`, those tools shell out to Linux commands under the hood

---

## Mastery Checkpoint

These are not theoretical exercises. Run every one. Do not move to v0.2 until each of these works correctly and you understand why.

**1. Navigate without disorientation**
Open a fresh terminal. Without using `cd /workspaces/aois-system`, navigate to the curriculum directory and back to the project root using only relative paths. Then navigate to `/etc` using an absolute path and read the first 5 lines of `/etc/os-release`. Run `pwd` at each step to confirm where you are.

**2. Understand every line of sysinfo.sh output**
Run `sysinfo.sh`. For each line of output, identify exactly which command produced it and what each field means. Pay special attention to the lines that use `awk` — trace through the `NR==2 {printf...}` pattern and explain what `NR==2` does and why `$2`, `$3`, `$7` are the fields used.

**3. Use pipes to answer a real question**
Find the top 3 processes by memory usage on your system right now:
```bash
ps aux --sort=-%mem | head -4
```
Now understand every column in the output. What is `%MEM`? What is `VSZ` vs `RSS`? (RSS is the real physical memory used; VSZ includes virtual/mapped memory that may not be physically allocated.)

**4. Demonstrate permission understanding**
Create a file called `secret.txt` with some text in it. Set its permissions so only you (the owner) can read or write it, and absolutely no one else — not your group, not others. Verify with `ls -la`. Then add execute permission for yourself only. Verify again. Calculate the octal number for the final permission state.

**5. Prove you understand stderr vs stdout**
Run:
```bash
python3 -c "print('stdout message'); import sys; sys.stderr.write('stderr message\n')"
```
Now redirect stdout to `out.txt` and stderr to `err.txt` separately, in one command. Verify each file contains only the expected message. Then run again with both merged into a single file `combined.txt`.

**6. Build a live-monitoring one-liner**
Write a single pipe command (no scripts, just piped commands) that:
- Lists all processes using Python
- Shows only their PID and memory percentage
- Sorts by memory (highest first)
Expected format: two columns, PID and %MEM, for any Python process running.

**7. Use awk and sed on real data**
Run `free -h` and use `awk` to extract only the available memory value (the `available` column from the `Mem:` row). Print it as: `Available memory: X.XGi`.

Then: take the file `/etc/os-release` and use `sed` to print only the line containing `PRETTY_NAME`, with `PRETTY_NAME=` stripped from the start, leaving only the OS name string.

**8. Verify you can recover from common mistakes**
1. Run `lsof -ti:8000 | xargs kill -9` — what happens when nothing is on port 8000? (It should do nothing, not error)
2. Try to `rm -rf` a non-existent directory. What is the exit code? (`echo $?`)
3. Run a command that you know will fail, then use `|| echo "it failed"` to handle it gracefully

**9. The sysinfo.sh extension**
Add a new section to `sysinfo.sh` that shows the 5 largest files in the project directory, formatted as: `SIZE  FILENAME`. Use `du`, `sort`, and `head`. The output should be human-readable sizes.

**The mastery bar**: you are ready for v0.2 when you can run any Linux command in this file, read its output, understand every column, and know which flags to add to change the output. The terminal should feel like a tool, not a puzzle.

---

## 4-Layer Tool Understanding

*Every tool introduced in this version, understood at four levels. Read this after completing the exercises — it turns what you did into something you can explain.*

---

### Linux (the OS and shell environment)

| Layer | |
|---|---|
| **Plain English** | The operating system underneath every server, container, and cloud VM you will ever manage. If something is broken in production, this is the layer you land on. |
| **System Role** | Every service in AOIS — k3s, Kafka, FastAPI, Falco — runs as a Linux process. Understanding processes, files, permissions, and networking at this layer means you can diagnose anything above it. |
| **Technical** | A POSIX-compliant OS kernel managing hardware resources, processes, filesystems, and networking. The shell (bash) is the interface between you and the kernel. |
| **Remove it** | Without Linux fluency, you cannot read logs, inspect running processes, fix permission errors, or understand why a container behaves differently in prod than locally. You become dependent on tools you cannot debug. |

**Say it at three levels:**
- *Non-technical:* "Linux is the operating system that runs almost every server in the world. Learning it is like learning to drive before learning to build cars."
- *Junior engineer:* "Linux is the layer under every container and VM. Knowing it means I can SSH into a broken node, find the crashing process, read its logs, and fix it — without a GUI."
- *Senior engineer:* "Linux process model, file descriptor limits, cgroup resource isolation, and network namespace separation are what Docker and Kubernetes are built on. If a container OOMKills, I diagnose it with `dmesg` and `/proc`, not `kubectl describe`."

---

### SSH

| Layer | |
|---|---|
| **Plain English** | The secure tunnel that lets you control a remote server from your laptop, as if you were sitting in front of it. |
| **System Role** | Every Hetzner server, k3s node, and AWS instance is accessed via SSH. It is the entry point to every debugging session that happens outside of a cluster. |
| **Technical** | Secure Shell — an encrypted protocol using asymmetric key pairs (public key on server, private key on client) for authentication and an encrypted channel for all traffic. |
| **Remove it** | Without SSH, you have no access to a broken node. If a pod is crashing, you may need to SSH into the node itself to check `dmesg`, inspect containerd state, or fix a misconfigured kubelet. |

**Say it at three levels:**
- *Non-technical:* "SSH is how I log into a remote server securely. It's like having a secret key to a door that only I can open."
- *Junior engineer:* "SSH uses a key pair — my private key never leaves my machine, the server has my public key. The connection is encrypted end-to-end. I use it for every server operation."
- *Senior engineer:* "Ed25519 keys over password auth, `StrictHostKeyChecking`, jump hosts for bastion patterns, SSH agent forwarding. In a proper setup the private key is in an agent and rotated periodically — not static on disk with 600 perms."

---

### grep / awk / sed

| Layer | |
|---|---|
| **Plain English** | Tools for searching, filtering, and transforming text — the Swiss Army knife of log analysis before you had AI. |
| **System Role** | Used to parse raw log files, filter kubectl output, extract fields from JSON-ish text, and write the `log_analyzer.sh` that shows why static pattern matching fails for real incidents. |
| **Technical** | `grep` — regex-based line filter. `awk` — field-oriented text processor with a mini programming language. `sed` — stream editor for in-place substitution. All operate on stdin/stdout and compose via pipes. |
| **Remove it** | Without these, log analysis requires loading every file into a programming language. They are also the baseline for understanding why v1's AI approach is better — you need to see the regex approach fail before the LLM approach earns its place. |

**Say it at three levels:**
- *Non-technical:* "These tools search through huge text files in milliseconds. Think of grep as Ctrl+F for the entire system."
- *Junior engineer:* "`grep -i 'OOMKilled' /var/log/syslog` — instant results. `awk '{print $5}'` extracts the fifth field from every line. `sed 's/ERROR/CRITICAL/'` rewrites in place. Together they replace any quick Python script for text processing."
- *Senior engineer:* "grep is O(n) line scan; for repeated queries on large files, index with `ripgrep`. awk's field separator and BEGIN/END blocks handle 90% of log transformation tasks. The real value is composability — they pipe into each other without intermediate files."
