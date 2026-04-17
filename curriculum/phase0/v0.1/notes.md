# v0.1 — Linux Essentials: Living in the Terminal

## What this version builds

A `sysinfo.sh` script that reports hostname, OS, CPU, memory, disk usage, and top processes. Simple output. The point is not the script — it is building the muscle memory to move around a Linux system without thinking.

Every server, every container, every cloud VM you will ever touch runs Linux. This is the OS of your career.

---

## The filesystem — where everything lives

```
/               root of the entire filesystem
├── home/       user home directories (/home/codespace is yours)
├── etc/        configuration files (nginx.conf, ssh/sshd_config, hosts)
├── var/        variable data — logs live here (/var/log/)
├── tmp/        temporary files, cleared on reboot
├── proc/       virtual filesystem — running kernel and process info
├── usr/        user programs and libraries (/usr/bin, /usr/local/bin)
├── bin/        essential command binaries (ls, cp, bash)
└── opt/        optional/third-party software
```

Nothing is random. If you wonder where a config file is, it is in `/etc`. If you wonder where logs are, they are in `/var/log`. This structure is consistent across every Linux distribution.

---

## Navigation

```bash
pwd                    # print working directory — where am I right now
ls                     # list files in current directory
ls -la                 # list all files including hidden, long format
ls -lah                # same, but human-readable file sizes (KB/MB/GB)
cd /workspaces         # change to absolute path
cd aois-system         # change to relative path
cd ..                  # go up one level
cd ~                   # go to home directory
cd -                   # go back to previous directory
```

`ls -la` output explained:
```
drwxr-xr-x  3 codespace codespace 4096 Apr 17 12:00 curriculum
-rw-r--r--  1 codespace codespace  832 Apr 17 12:00 main.py
```
- First character: `d` = directory, `-` = file, `l` = symlink
- Next 9 characters: permissions in three groups (owner, group, others)
- Number after permissions: hard link count
- Next two: owner and group
- Number: file size in bytes
- Date and time: last modified
- Name

---

## Files — creating, reading, moving, deleting

```bash
mkdir logs                         # create a directory
mkdir -p a/b/c                     # create nested directories at once
touch file.txt                     # create an empty file
cat file.txt                       # print entire file to terminal
head -20 file.txt                  # first 20 lines
tail -20 file.txt                  # last 20 lines
tail -f /var/log/syslog            # follow a log in real time (Ctrl+C to stop)
less file.txt                      # paginated viewer (q to quit, / to search)
cp file.txt backup.txt             # copy file
cp -r dir/ backup_dir/             # copy directory recursively
mv file.txt newname.txt            # rename or move
rm file.txt                        # delete file (no recycle bin — gone)
rm -rf directory/                  # delete directory and everything in it (be careful)
```

`tail -f` is one of the most-used commands in SRE work. When a service is misbehaving you run `tail -f /var/log/service.log` and watch what happens in real time.

---

## Permissions

Every file has three permission sets: **owner**, **group**, **others**. Each set has three bits: **read (r=4)**, **write (w=2)**, **execute (x=1)**.

```bash
chmod 755 script.sh       # owner: rwx (7), group: r-x (5), others: r-x (5)
chmod 644 file.txt        # owner: rw- (6), group: r-- (4), others: r-- (4)
chmod +x script.sh        # add execute permission for everyone
chmod -x script.sh        # remove execute permission
chown codespace file.txt  # change owner
chown codespace:codespace file.txt  # change owner and group
```

Why this matters: when a script fails with "Permission denied", the file is not executable. `chmod +x script.sh` fixes it. When a web server can't read a config file, it's a permissions problem. When a container won't start, it's often a permissions problem.

---

## Processes

A process is a running program. Every running thing on your system — your FastAPI server, Redis, Postgres, the kernel itself — is a process with a process ID (PID).

```bash
ps aux                    # list all running processes
ps aux | grep python      # find python processes specifically
top                       # live view of processes (q to quit)
htop                      # better version of top (install with: apt install htop)
kill 1234                 # send SIGTERM (graceful stop) to PID 1234
kill -9 1234              # send SIGKILL (force stop) — use when SIGTERM fails
lsof -i :8000             # what process is using port 8000
lsof -ti:8000 | xargs kill -9   # kill whatever is on port 8000
```

The `lsof -ti:8000 | xargs kill -9` command is used throughout this project. When you need to restart your FastAPI server after a code change, you kill the old process first. `lsof -ti:8000` returns just the PID. `xargs` takes that PID and passes it to `kill -9`.

---

## Background processes

```bash
uvicorn main:app &        # run in background, get your terminal back
jobs                      # list background jobs
fg                        # bring last background job to foreground
fg %1                     # bring job 1 to foreground
Ctrl+C                    # kill foreground process
Ctrl+Z                    # pause foreground process (send to background)
bg                        # resume paused process in background
nohup uvicorn main:app &  # run in background, survives terminal close
```

---

## Environment variables

Environment variables are key=value pairs available to any process on the system. This is how API keys reach your application without being hardcoded.

```bash
echo $HOME                     # print HOME variable
echo $PATH                     # print PATH — where bash looks for commands
export MY_VAR="hello"          # set a variable for this session
echo $MY_VAR                   # prints: hello
env                            # list all environment variables
printenv MY_VAR                # print one variable
unset MY_VAR                   # remove a variable
```

`$PATH` is a colon-separated list of directories. When you type `python`, bash looks in each directory in $PATH for a file named `python`. If it's not there, you get "command not found". When you install something and it's not found, the binary is not in a directory in $PATH.

---

## Pipes and redirection

The shell's superpower is composing small tools into pipelines.

```bash
command > file.txt         # redirect output to file (overwrites)
command >> file.txt        # redirect output to file (appends)
command 2> errors.txt      # redirect stderr to file
command 2>&1               # merge stderr into stdout
command < file.txt         # feed file as input to command
command1 | command2        # pipe: output of command1 becomes input of command2
```

Real examples:
```bash
ps aux | grep python           # list processes, filter to python ones
cat /var/log/syslog | grep ERROR | tail -20   # last 20 error lines from syslog
ls -la | wc -l                 # count files in directory
echo "hello" > /tmp/test.txt   # write to file
cat /dev/null > file.txt       # empty a file without deleting it
```

---

## Searching

```bash
grep "error" file.txt              # find lines containing "error"
grep -i "error" file.txt           # case insensitive
grep -r "error" /var/log/          # search recursively in directory
grep -n "error" file.txt           # show line numbers
grep -v "debug" file.txt           # invert — show lines NOT containing "debug"
grep -E "error|warning" file.txt   # regex — error OR warning

find /etc -name "*.conf"           # find files by name pattern
find . -name "*.py" -newer main.py # find .py files newer than main.py
find /tmp -mtime +7 -delete        # find and delete files older than 7 days
```

---

## Disk and memory

```bash
df -h                    # disk usage by filesystem, human readable
du -sh directory/        # disk usage of a specific directory
du -sh * | sort -h       # size of everything in current dir, sorted
free -h                  # memory usage (total, used, free, cache)
```

---

## Useful shortcuts

```bash
Ctrl+C     # kill current process
Ctrl+Z     # pause current process
Ctrl+D     # end of input (like typing exit)
Ctrl+L     # clear screen (same as clear command)
Ctrl+A     # go to beginning of line
Ctrl+E     # go to end of line
Ctrl+R     # search command history
!!         # repeat last command
!grep      # repeat last command starting with "grep"
history    # show command history
```

---

## Package management

```bash
apt update                      # refresh package list
apt install htop                # install a package
apt remove htop                 # remove a package
apt list --installed            # list installed packages
which python3                   # find where a command lives
python3 --version               # check version
```

---

## SSH

SSH (Secure Shell) is how you connect to remote servers. Every Hetzner VPS, every AWS EC2 instance, every cloud machine you manage will be accessed via SSH.

```bash
ssh user@ip_address              # connect to server
ssh -i ~/.ssh/key.pem user@ip    # connect with a specific private key
ssh-keygen -t ed25519            # generate a new key pair
cat ~/.ssh/id_ed25519.pub        # your public key — this goes on the server
```

Key pairs: you keep the private key (`~/.ssh/id_ed25519`), you put the public key on the server (`~/.ssh/authorized_keys`). The server encrypts a challenge with your public key. Only your private key can decrypt it. That's the authentication.

Never share or copy your private key. If a server is compromised, you rotate keys — you do not reuse them.

---

## Build: sysinfo.sh

Create this file at `/workspaces/aois-system/practice/sysinfo.sh`:

```bash
#!/bin/bash

echo "=== AOIS System Info ==="
echo ""

echo "Hostname:    $(hostname)"
echo "OS:          $(cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '"')"
echo "Kernel:      $(uname -r)"
echo "Uptime:      $(uptime -p)"
echo ""

echo "=== CPU ==="
echo "Cores:       $(nproc)"
echo "Load avg:    $(cat /proc/loadavg | awk '{print $1, $2, $3}')"
echo ""

echo "=== Memory ==="
free -h | awk 'NR==2 {printf "Total: %s | Used: %s | Free: %s\n", $2, $3, $4}'
echo ""

echo "=== Disk ==="
df -h / | awk 'NR==2 {printf "Total: %s | Used: %s | Free: %s | Usage: %s\n", $2, $3, $4, $5}'
echo ""

echo "=== Top 5 Processes by CPU ==="
ps aux --sort=-%cpu | awk 'NR<=6 {printf "%-10s %-8s %-8s %s\n", $1, $2, $3, $11}'
echo ""

echo "=== Network Ports in Use ==="
ss -tlnp | grep LISTEN | awk '{print $4, $6}' | head -10
```

Make it executable and run it:
```bash
chmod +x /workspaces/aois-system/practice/sysinfo.sh
bash /workspaces/aois-system/practice/sysinfo.sh
```

Each line teaches a command. Read the script after running it, then modify it — add your Python version, add a check for whether port 8000 is in use.

---

## Commands you will use daily throughout this project

```bash
tail -f logs            # watch logs in real time
ps aux | grep python    # is my server running?
lsof -ti:8000 | xargs kill -9   # kill the server on port 8000
chmod +x script.sh      # make a script executable
grep -r "error" .       # search for errors in all files
df -h                   # is the disk full?
free -h                 # is memory full?
```

You do not need to memorise all of this. Run the commands. The muscle memory builds itself.
