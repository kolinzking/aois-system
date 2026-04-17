# v0.3 — Git & GitHub: Your Professional History

## What this version builds

This repo, committed properly. Real history. Meaningful commit messages. A .gitignore that actually protects you.

GitHub is your CV in this field. Recruiters and engineers look at the commit history, the progression, the consistency. Every version of AOIS committed properly is evidence of who you are as an engineer.

---

## The mental model — snapshots, not diffs

Git does not store changes. Git stores **snapshots** of your entire project at a point in time. Each commit is a complete snapshot, plus a pointer to the previous snapshot. The "diff" you see is computed on the fly by comparing two snapshots — it is not what git stores.

This matters because it changes how you think about branches, merges, and history. A branch is just a pointer to a commit. Merging is creating a new snapshot that has two parents. Checking out a branch is replacing your working files with the files from that snapshot.

```
Snapshot A --> Snapshot B --> Snapshot C  (main branch points here)
                    \
                     --> Snapshot D --> Snapshot E  (feature branch points here)
```

---

## The three areas

Git has three areas. Understanding these eliminates most git confusion.

```
Working directory          Staging area (index)          Repository (.git)
      |                           |                              |
   (your files)              (what will be                 (committed
   you edit here              in the next commit)           snapshots)
      |                           |                              |
      |------ git add ---------> |                              |
      |                           |------ git commit ---------> |
      |<----- git checkout ------|<-----------------------------|
```

`git add` moves changes from working directory to staging area.
`git commit` takes everything in staging and creates a snapshot.
`git checkout` replaces working directory files from a snapshot.

When `git status` shows "Changes not staged for commit" — that's the working directory.
When it shows "Changes to be committed" — that's the staging area.

---

## Setup

```bash
git config --global user.name "Collins"
git config --global user.email "your@email.com"
git config --global init.defaultBranch main
git config --list    # verify settings
```

These go into `~/.gitconfig` and apply to every repo on this machine.

---

## The daily workflow

```bash
git status                  # what's changed? always run this first
git diff                    # what exactly changed in files (unstaged)
git diff --staged           # what's in staging (will be committed)
git add main.py             # stage a specific file
git add curriculum/phase0/  # stage a whole directory
git add -p                  # interactive: choose which changes to stage
git commit -m "message"     # commit what's staged
git log                     # show commit history
git log --oneline           # compact view
git log --oneline --graph   # with branch graph
```

**Never use `git add .` blindly.** Run `git status` first. Know exactly what you are staging. One accidental commit of `.env` leaks your API keys into git history — even if you delete the file in the next commit, the keys are still in history and must be rotated.

---

## Commit messages

A commit message is a message to your future self and anyone who reads this repo. It should say **why**, not what. The diff already shows what changed.

Bad:
```
fixed bug
update main
changes
wip
asdf
```

Good:
```
v1: FastAPI + Claude tool use + OpenAI fallback
v2: LiteLLM gateway with 4 routing tiers and cost tracking
fix: handle Claude timeout on P1 incident analysis
docs: add v0.3 notes on git mental model
```

Convention for this project: `version: description` for version milestones, `type: description` for everything else. Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

---

## .gitignore — what never enters the repo

Create `/workspaces/aois-system/.gitignore` with:

```gitignore
# Secrets — never commit these
.env
.env.local
.env.*.local
*.pem
*.key
secrets/

# Python
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

# Node
node_modules/
npm-debug.log*

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/

# Docker
.docker/

# Terraform
*.tfstate
*.tfstate.backup
.terraform/
.terraform.lock.hcl
```

Check it works:
```bash
git status    # .env should NOT appear in the list
```

If `.env` appears, it is not in `.gitignore` properly. Fix it before anything else.

---

## Branches

```bash
git branch                     # list local branches
git branch -a                  # list all branches including remote
git checkout -b feature/kafka  # create and switch to new branch
git checkout main              # switch to existing branch
git merge feature/kafka        # merge feature into current branch
git branch -d feature/kafka    # delete branch after merging
```

**When to branch:** for anything that takes more than one commit. For version work: each version gets a branch, merged to main when done. For this learning project, working directly on main is fine until Phase 3 (GitOps).

---

## Remotes and GitHub

```bash
git remote -v                           # show configured remotes
git remote add origin git@github.com:user/repo.git   # add remote
git push -u origin main                 # push main branch, set upstream
git push                                # push after upstream is set
git pull                                # fetch + merge remote changes
git fetch                               # fetch without merging
git clone git@github.com:user/repo.git  # copy a repo locally
```

**origin** is the conventional name for your primary remote. When you run `git push`, git pushes to origin by default.

**SSH vs HTTPS for GitHub:**
- HTTPS: requires username + token on every push
- SSH: authenticate with a key pair, no password needed

Set up SSH authentication:
```bash
ssh-keygen -t ed25519 -C "your@email.com"   # generate key pair
cat ~/.ssh/id_ed25519.pub                     # copy this
# Paste it in GitHub → Settings → SSH and GPG keys → New SSH key
ssh -T git@github.com                         # test the connection
# Expected: "Hi username! You've successfully authenticated"
```

---

## Reading history

```bash
git log --oneline                      # compact history
git log --oneline --graph --all        # visual branch graph
git show abc1234                       # show a specific commit
git show HEAD                          # show latest commit
git diff HEAD~1 HEAD                   # diff last two commits
git blame main.py                      # who changed each line and when
git log --follow -p main.py            # full history of a file including renames
```

`HEAD` is a pointer to the current commit — wherever you are right now. `HEAD~1` means one commit before HEAD. `HEAD~3` means three before.

---

## Undoing things

```bash
git restore main.py             # discard changes in working directory (unstaged)
git restore --staged main.py    # unstage a file (keep changes in working dir)
git commit --amend              # modify the last commit message or add a file
                                # WARNING: only do this if you haven't pushed yet
git revert abc1234              # create a new commit that undoes a commit
                                # safe: works on pushed commits, preserves history
git reset --hard HEAD~1         # dangerous: delete last commit and discard changes
                                # never do this on pushed commits
```

**Rule of thumb:** if you haven't pushed yet, you can rewrite history freely. Once you've pushed, use `git revert` — it adds a new commit rather than rewriting history, which is safe for shared branches.

---

## What lives in .git/

```bash
ls -la .git/
```

```
HEAD        — pointer to current branch
config      — repo-level git config
objects/    — all commits, trees, blobs (the actual content)
refs/       — branches and tags (just files containing commit hashes)
hooks/      — scripts that run on git events (pre-commit, post-commit, etc.)
index       — the staging area
logs/       — history of where HEAD has pointed
```

`git reflog` shows everything HEAD has pointed to — useful if you lost a commit you thought was gone. Git almost never truly loses data.

---

## Committing this project properly

Check what exists:
```bash
cd /workspaces/aois-system
git status
git log --oneline
```

If the history looks like `checkpoint: 2026-04-17` entries from the auto-save hooks, that is fine. From here, every commit you make manually should be meaningful:

```bash
# Stage and commit Phase 0 notes
git add curriculum/phase0/
git commit -m "phase0: add foundation curriculum (v0.1-v0.7)"

# Or commit version by version as you go through them
git add curriculum/phase0/v0.1/
git commit -m "v0.1: Linux essentials notes and sysinfo.sh"
```

---

## The .git/hooks directory

This project already has post-commit hooks configured in `~/.claude/settings.json`. Those hooks commit automatically after Claude writes files. You can see them with:

```bash
cat ~/.claude/settings.json
```

Hooks are scripts that git runs at specific moments. `pre-commit` runs before a commit is created — useful for linting, running tests, blocking commits that contain secrets. `post-commit` runs after a commit is created. `pre-push` runs before a push — useful for running the full test suite.

You will write your own hooks in Phase 9 (v28, GitHub Actions + Dagger).

---

## GitHub as CV — what recruiters actually look at

1. **Commit frequency** — consistent daily activity shows you actually code
2. **Commit message quality** — `fix bug` vs `v3: Instructor validation with Langfuse tracing` tells them everything
3. **README** — does this repo explain what it is and why it exists?
4. **Progression** — v1 → v2 → v3 shows a build mindset, not just tutorial following
5. **Real tools** — Claude API, LangGraph, Temporal, k8s in the same repo signals you are ahead of the curve

Every version of AOIS committed properly is building this signal.
