# v0.3 — Git & GitHub: Your Professional History
⏱ **Estimated time: 2–3 hours**

## What this version is about

GitHub is your CV in this field. When an engineer or recruiter looks at your profile, they see the commit history. The progression from v0.1 to v34 — committed consistently, with meaningful messages — is evidence that you build things rather than just read about them.

Beyond the career angle: git is how every real team manages code. Every company uses it. Understanding it deeply eliminates the fear that makes people do things wrong (force pushing main, losing work, confused merges). By the end of this version, git has no mystery.

---

## Prerequisites

- v0.1 and v0.2 complete — you can use the terminal fluently
- Git is installed (it is in Codespaces)

Verify git is installed and configured:
```bash
git --version
```
Expected:
```
git version 2.43.0
```

Check if it is configured:
```bash
git config --list | grep user
```
Expected:
```
user.name=Collins
user.email=gspice1@proton.me
```
If you see nothing, configure it now:
```bash
git config --global user.name "Collins"
git config --global user.email "gspice1@proton.me"
git config --global init.defaultBranch main
git config --global core.editor "nano"    # use nano as default editor (simpler than vim)
```

---

## Learning goals

By the end of this version you will:
- Understand git's mental model (snapshots, not diffs)
- Know the three areas and how changes move between them
- Use the daily git workflow without thinking: status, add, commit, log, diff
- Write meaningful commit messages
- Use branches correctly
- Connect a local repo to GitHub and push/pull
- Understand .gitignore and what never enters a repo
- Know how to undo mistakes safely

---

## Part 1 — The mental model: snapshots, not diffs

Most people think of git as tracking changes. This leads to confusion. The accurate mental model is different.

**Git stores snapshots.** Each commit is a complete snapshot of your entire project at that moment — every file, every directory. Not what changed from the last commit. The whole thing.

When you see a "diff" in git, git is computing it on the fly by comparing two snapshots. The diff is not stored — the snapshots are.

```
time →

Commit A          Commit B          Commit C
(snapshot)   →   (snapshot)   →   (snapshot)
                                        ↑
                                     HEAD (where you are now)
                                     main (branch pointer)
```

A **branch** is just a pointer (a text file containing a commit hash) to a specific commit. Creating a branch is instantaneous — it just creates a new pointer.

`HEAD` is a pointer to the branch you are currently on. When you commit, the branch pointer advances to the new commit, and HEAD follows.

```
Before commit:    main → Commit C ← HEAD
After commit:     main → Commit D ← HEAD
```

This model makes operations like branching, merging, and rebasing conceptually simple — they are all just moving pointers around or creating new snapshots.

---

## Part 2 — The three areas

Understanding these three areas eliminates 90% of git confusion.

```
┌─────────────────────┐    git add     ┌──────────────────┐    git commit    ┌──────────────┐
│   Working Directory  │ ─────────────→ │   Staging Area   │ ───────────────→ │  Repository  │
│                     │                │    (Index)       │                  │   (.git/)    │
│  Files you edit     │ ←───────────── │                  │ ←─────────────── │              │
│  on disk            │  git checkout  │  What the next   │  git checkout    │  Committed   │
│                     │                │  commit will     │                  │  snapshots   │
└─────────────────────┘                │  contain         │                  └──────────────┘
                                       └──────────────────┘
```

- **Working directory**: your files as they are on disk right now. This is where you edit.
- **Staging area (index)**: a "preview" of the next commit. `git add` moves changes here.
- **Repository (.git/)**: the database of all committed snapshots.

What `git status` shows:
- "Changes not staged for commit" = changes in working directory not yet in staging
- "Changes to be committed" = changes in staging area, will be in next commit
- "Untracked files" = new files git has never seen (not in working directory tracking, not staged)

---

> **▶ STOP — do this now**
>
> Run `git status` right now in your AOIS repo and interpret every line:
> ```bash
> cd /workspaces/aois-system
> git status
> ```
> For each line of output, identify which of the three areas it describes (working directory, staging, or repository). If the output says "nothing to commit, working tree clean" — that means all three areas are in sync. If you see modified files — those are in the working directory, not yet staged.
>
> Now check the log to see the snapshot history:
> ```bash
> git log --oneline -10
> ```
> Each line is a snapshot. The hash on the left uniquely identifies that exact state of every file in the project.

---

## Part 3 — Daily workflow

### Check what state everything is in

Always start here:
```bash
cd /workspaces/aois-system
git status
```
Expected (clean repo):
```
On branch main
nothing to commit, working tree clean
```

After making a change (edit any file):
```bash
echo "# test" >> README.md
git status
```
Expected:
```
On branch main
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)

        modified:   README.md

no changes added to commit (use "git add" or "git commit -a")
```

### See exactly what changed

```bash
git diff            # changes in working directory not yet staged
git diff --staged   # changes in staging area (what will be in the next commit)
git diff HEAD       # all changes since last commit (staged + unstaged)
```

Expected `git diff` output:
```diff
diff --git a/README.md b/README.md
index abc1234..def5678 100644
--- a/README.md
+++ b/README.md
@@ -1,3 +1,4 @@
 # AOIS
+# test
```
Lines starting with `+` are additions. Lines starting with `-` are deletions. Lines with no prefix are context (unchanged).

### Stage changes

```bash
git add README.md               # stage a specific file
git add curriculum/phase0/      # stage an entire directory
git add -p                      # interactive: choose which changes to stage (hunk by hunk)
git add .                       # stage everything in current directory (careful — read below)
```

**Warning about `git add .`:** it stages everything, including files you may not want to commit. Always run `git status` after `git add .` to see exactly what got staged. Better to be explicit and name files.

After staging:
```bash
git status
```
Expected:
```
On branch main
Changes to be committed:
  (use "git restore --staged <file>..." to unstage)

        modified:   README.md
```

### Commit

```bash
git commit -m "docs: update README with test line"
```
Expected:
```
[main abc1234] docs: update README with test line
 1 file changed, 1 insertion(+)
```

The output tells you: branch name, commit hash (first 7 characters), message, and what changed.

### View history

```bash
git log                     # full log with author, date, message
git log --oneline           # compact: one line per commit
git log --oneline --graph   # with ASCII branch graph
git log --oneline -10       # last 10 commits only
```

Expected `git log --oneline`:
```
abc1234 docs: update README with test line
2305c5d checkpoint: 2026-04-17 15:09
5b40d7f checkpoint: 2026-04-17 12:13
```

The first 7 characters (`abc1234`) are the commit hash — a unique identifier for that snapshot. You can reference any commit by its hash.

---

> **▶ STOP — do this now**
>
> Make a real change, go through the full add → commit cycle, then look at the result:
> ```bash
> cd /workspaces/aois-system
> echo "# v0.3 practice" >> /tmp/practice_v03.txt
> # (don't actually commit random files — instead, look at the diff on something that already changed)
> git diff                    # see what changed since last commit
> git log --oneline -5        # see the 5 most recent snapshots
> git show HEAD               # see exactly what the last commit changed
> ```
> `git show HEAD` shows the diff for the most recent commit. This is how you read git history — not just the message, but the actual change. In a team setting, `git show <hash>` is how you investigate why a line of code was written.

---

## Part 4 — .gitignore: what never enters the repo

The `.gitignore` file lists patterns of files and directories that git should never track.

Check the current `.gitignore`:
```bash
cat /workspaces/aois-system/.gitignore
```

It should contain `.env` at minimum. If it does not, your API keys are at risk.

A complete `.gitignore` for this project:
```bash
cat > /workspaces/aois-system/.gitignore << 'EOF'
# === Secrets — NEVER commit these ===
.env
.env.local
.env.*.local
*.pem
*.key
secrets/
credentials.json

# === Python ===
__pycache__/
*.py[cod]
*.pyo
.Python
venv/
env/
.venv/
*.egg-info/
dist/
build/
.pytest_cache/
.mypy_cache/
.ruff_cache/

# === Node ===
node_modules/
npm-debug.log*

# === IDE ===
.vscode/settings.json
.idea/
*.swp
*.swo

# === OS ===
.DS_Store
Thumbs.db

# === Logs ===
*.log
logs/

# === Docker ===
.docker/

# === Terraform ===
*.tfstate
*.tfstate.backup
.terraform/
.terraform.lock.hcl

# === Kubernetes ===
kubeconfig
*.kubeconfig
EOF
```

Verify that `.env` is protected:
```bash
git status
```
`.env` should NOT appear in the untracked files list. If it does, `.gitignore` is not set up correctly — stop immediately and fix it before doing anything else.

**What happens if you accidentally commit `.env`:**
The API keys are now in git history. Even if you delete the file and commit again, the keys are still visible in previous commits. They must be rotated immediately:
1. Generate new keys from console.anthropic.com and platform.openai.com
2. Update `.env` with new keys
3. Remove the file from tracking:
   ```bash
   git rm --cached .env
   git commit -m "remove .env from tracking"
   ```
The old keys are still in history, but they no longer work, so the damage is contained.

---

## Part 5 — Commit messages that mean something

A commit message is a message to your future self and to anyone who reads this repo. It should say **why**, not what. The diff already shows what changed.

**Bad messages:**
```
fix bug
update main
changes
wip
added stuff
asdf
```

**Good messages:**
```
v1: FastAPI + Claude tool use + OpenAI fallback
v2: LiteLLM gateway with 4 routing tiers and cost tracking per call
fix: handle Claude timeout on P1 incident analysis gracefully
docs: add v0.3 notes covering git mental model and daily workflow
refactor: extract sanitize_log into separate validation module
chore: pin jaraco.context>=6.1.0 to fix Trivy CVE
```

The pattern for this project: `type: description`
- `feat:` or `vN:` — new version or feature
- `fix:` — bug fix
- `docs:` — documentation only
- `refactor:` — code change that does not add features or fix bugs
- `chore:` — maintenance (dependency updates, config changes)
- `test:` — adding or updating tests

Keep the first line under 72 characters. If you need more detail, leave a blank line and add a body:
```bash
git commit -m "v5: rate limiting, payload limits, prompt injection defence

Implements four security layers as specified in OWASP LLM Top 10:
- Input: sanitize_log() strips injection patterns, caps at 5KB
- Prompt: SECURITY paragraph in system prompt
- Output: validate_output() blocks destructive suggestions
- Transport: slowapi rate limiting at 10/minute per IP"
```

---

> **▶ STOP — do this now**
>
> Read 5 recent commit messages from this repo and rate them:
> ```bash
> git log --oneline -10
> ```
> For each message, ask: does it tell you what changed AND why? Does it use a conventional prefix (feat:, fix:, chore:)? Would you understand it 6 months from now without looking at the diff?
>
> Then look at a full commit with body:
> ```bash
> git log --format="%H %s" -5 | head -1 | cut -d' ' -f1 | xargs git show --stat
> ```
> See the files changed and the commit message together. This is what a recruiter sees when they browse your GitHub. Message quality matters.

---

## Part 6 — Branches

A branch is an independent line of development. Use it when you want to try something without affecting the main codebase.

```bash
git branch                      # list local branches
git branch -a                   # list all branches including remote-tracking
```
Expected:
```
* main
```
The `*` marks the current branch.

Create and switch to a new branch:
```bash
git checkout -b feature/test-branch
git branch                      # verify you are on the new branch
```
Expected:
```
* feature/test-branch
  main
```

Make a change, commit it:
```bash
echo "test content" > /tmp/test_file.txt
cp /tmp/test_file.txt /workspaces/aois-system/practice/test_file.txt
git add practice/test_file.txt
git commit -m "test: add test file on feature branch"
```

Switch back to main:
```bash
git checkout main
ls practice/     # test_file.txt is NOT here — it is on the feature branch
```

Merge the feature branch into main:
```bash
git merge feature/test-branch
ls practice/     # now test_file.txt IS here
```

Delete the branch (clean up after merging):
```bash
git branch -d feature/test-branch
git branch      # confirms it is gone
```

Clean up the test file:
```bash
rm /workspaces/aois-system/practice/test_file.txt
git add practice/test_file.txt
git commit -m "chore: remove test file"
```

**For this learning project:** working directly on `main` is fine until Phase 3 (GitOps). When ArgoCD watches main and auto-deploys on every push, you will use branches properly. For now, commit directly to main.

---

## Part 7 — Remotes and GitHub

A remote is a copy of the repository somewhere else (GitHub, GitLab, your own server).

```bash
git remote -v           # show configured remotes
```
Expected (if the repo is connected to GitHub):
```
origin  https://github.com/kolinzking/aois-system.git (fetch)
origin  https://github.com/kolinzking/aois-system.git (push)
```

`origin` is the conventional name for the primary remote.

```bash
git push                # push current branch to its upstream remote
git push -u origin main # push and set upstream (first time for a new branch)
git pull                # fetch from remote and merge into current branch
git fetch               # fetch from remote without merging (safe to run anytime)
```

`git fetch` vs `git pull`:
- `git fetch` just downloads new commits from the remote into your local repository. Your working directory is unchanged.
- `git pull` = `git fetch` + `git merge`. It fetches AND merges remote changes into your current branch.

When in doubt, use `git fetch` first to see what changed, then decide whether to merge.

**SSH authentication for GitHub (recommended over HTTPS):**
```bash
ssh-keygen -t ed25519 -C "gspice1@proton.me"    # generate key pair
# When asked for a file, press Enter to use the default
# When asked for a passphrase, press Enter for none (or set one for extra security)

cat ~/.ssh/id_ed25519.pub                         # your public key
```
Copy the output (starts with `ssh-ed25519 ...`), go to GitHub → Settings → SSH and GPG keys → New SSH key, paste it.

Test the connection:
```bash
ssh -T git@github.com
```
Expected:
```
Hi kolinzking! You've successfully authenticated, but GitHub does not provide shell access.
```

---

## Part 8 — Reading history and finding information

```bash
git log --oneline --graph --all     # full visual history of all branches

git show abc1234                    # show a specific commit (what changed, message, author)
git show HEAD                       # show the most recent commit
git show HEAD~1                     # show one commit before HEAD
git show HEAD~3                     # show three commits before HEAD

git diff HEAD~1 HEAD                # what changed in the last commit
git diff abc1234 def5678            # what changed between two specific commits

git blame main.py                   # who last changed each line and when
git log --follow -p main.py         # full history of changes to one file

git log --oneline --author="Collins"    # commits by a specific person
git log --oneline --since="2026-04-01" # commits since a date
git log --oneline --grep="v3"          # commits with "v3" in the message
```

`git blame` is useful when you find something surprising in the code:
```bash
git blame main.py | head -20
```
Expected:
```
abc1234 (Collins 2026-04-17 12:00:00 +0000  1) from fastapi import FastAPI
abc1234 (Collins 2026-04-17 12:00:00 +0000  2) from pydantic import BaseModel
```
Shows who wrote each line and when.

---

## Part 9 — Undoing mistakes

```bash
# Discard changes in working directory (before staging)
git restore main.py             # discard all changes to main.py
git restore .                   # discard all changes to all files

# Remove from staging area (keep changes in working directory)
git restore --staged main.py    # unstage main.py but keep the edits

# Fix the last commit message (before pushing)
git commit --amend -m "corrected message"
# WARNING: only do this if you have NOT pushed yet

# Safely undo a commit (creates a new commit that reverses it)
git revert HEAD                 # undo last commit
git revert abc1234              # undo a specific commit
# This is SAFE — it does not rewrite history, works on pushed commits

# Nuclear option: delete last commit and discard all changes
git reset --hard HEAD~1
# WARNING: data is GONE. Only use on commits you have not pushed.
```

**The rule:**
- Before pushing: you can rewrite history freely with `--amend` and `reset`
- After pushing: use `git revert` only — it adds a new commit, never rewrites history

**Recovering "lost" work:**
Almost nothing in git is truly lost. `git reflog` shows every place HEAD has pointed:
```bash
git reflog | head -20
```
Expected:
```
abc1234 HEAD@{0}: commit: v5: security hardening
bcd2345 HEAD@{1}: commit: v4: Docker multi-stage build
cde3456 HEAD@{2}: checkout: moving from feature to main
```
If you accidentally reset or deleted a branch, the commit hash is still in reflog. You can recover it:
```bash
git checkout -b recovery-branch abc1234     # create branch pointing to "lost" commit
```

---

## Part 10 — Committing this project properly

Now commit Phase 0 notes:
```bash
cd /workspaces/aois-system
git status
```

You should see the new Phase 0 files:
```
Untracked files:
    curriculum/phase0/
    practice/sysinfo.sh
    practice/log_analyzer.sh
```

Stage and commit:
```bash
git add curriculum/phase0/
git add practice/
git commit -m "phase0: add foundation curriculum v0.1-v0.7"
```

Verify:
```bash
git log --oneline -5
```
Expected: your new commit at the top.

```bash
git show HEAD --stat
```
Expected: shows which files were added and how many lines.

---

## Troubleshooting

**"Your branch is behind 'origin/main'":**
```bash
git pull
```
Someone (or a hook) pushed to the remote and you have not pulled yet. Pull before pushing.

**"Please commit your changes or stash them before merge":**
```bash
git stash              # temporarily save working directory changes
git pull               # pull the remote changes
git stash pop          # restore your saved changes
```

**"Merge conflict" after pull:**
Git shows conflicted files in `git status` with "both modified". Open the file and look for:
```
<<<<<<< HEAD
your version
=======
their version
>>>>>>> origin/main
```
Edit the file to keep what you want, remove the marker lines, then:
```bash
git add conflicted_file.py
git commit -m "resolve merge conflict in conflicted_file.py"
```

**"fatal: not a git repository":**
```bash
pwd                     # are you in the right directory?
ls -la | grep ".git"    # is there a .git directory here?
cd /workspaces/aois-system
```

**Accidentally staged .env:**
```bash
git restore --staged .env       # unstage it without discarding content
git status                      # verify it is no longer staged
```
Then add `.env` to `.gitignore` before anything else.

---

## Connection to later phases

- **Phase 3 (v8)**: ArgoCD watches the git repo. Every `git push` to main triggers a deployment. This is GitOps — git IS the source of truth for the cluster state.
- **Phase 9 (v28)**: GitHub Actions runs on every push. The pipeline builds, tests, scans, and deploys automatically. Every workflow you write runs bash commands in response to git events.
- **The CV angle**: By Phase 10, the commit history shows 34 versions of progressive complexity. That history is the evidence of your skills — more credible than any resume line.

---

## Mastery Checkpoint

Git has no mystery after these exercises. Run every one before moving to v0.4.

**1. Prove you understand the three areas**
Make a change to any file. Run `git status` and identify which area it is in. Stage it with `git add`. Run `git status` again — what changed in the output? Now run `git restore --staged <file>` to unstage without discarding. Verify the change is still in the working directory. This cycle — working directory → staging area → commit — is the foundation of every git operation.

**2. Understand what a commit actually contains**
Run `git log --oneline -5`. Pick any commit. Run `git show <hash>`. Read the full output: who committed, when, the message, and the diff showing exactly what changed. Now run `git show <hash> --stat` to see just the file list and change counts. This is how you investigate "what changed in that deploy?"

**3. The .gitignore must be airtight**
Run `git status` and verify `.env` does not appear anywhere. Now temporarily add `.env` to staging (`git add -f .env`) — see how `-f` forces it past `.gitignore`. Immediately unstage it (`git restore --staged .env`). The `-f` exists for legitimate reasons but is also how accidents happen.

**4. Write a commit message for every version you have built**
Look at the current `git log --oneline`. If any commits say "checkpoint" or have unhelpful messages, practice writing what the message SHOULD have been. Use the format: `type: description of the change and its purpose`. Write at least 5 hypothetical commit messages for things you have built so far.

**5. Use git log to answer a question**
Answer these without running any commands other than git:
- When was the last change made to `main.py`? (`git log --oneline -- main.py`)
- What was changed in the most recent commit? (`git show HEAD`)
- How many commits have been made since the beginning? (`git log --oneline | wc -l`)

**6. Create a branch, make a change, merge it back**
Create a branch called `test/mastery-check`. Add a file called `practice/mastery_note.txt` with any content. Commit it on the branch. Switch back to main and verify the file is gone. Merge the branch into main. Verify the file appears. Delete the branch. Delete the file and commit the cleanup. The entire cycle in one session.

**7. Recover from a "mistake"**
On main, make a change to any file and commit it. Then use `git revert HEAD` to create a reversal commit. Check `git log --oneline` — you should see two new commits: the change and its reversal. Your history is preserved; the mistake is undone. This is the safe way to undo on a shared branch.

**8. Read git blame on main.py**
Run `git blame main.py | head -30`. For each line shown: you can see the commit hash, author, date, and line number. This is how you answer "who changed this line and when?" in a production incident.

**The mastery bar**: git should feel like a superpower, not a danger. You commit cleanly, you can undo safely, you can investigate history, and your `.gitignore` is protecting your secrets. The engineers who lose work or accidentally commit credentials are the ones who never understood the three areas and the safety rules.
