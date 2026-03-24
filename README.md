# choline_agent

**Launch GPU instances on VastAI, sync your code, and run autonomous Claude Code agents — all from a single YAML file or Python API.**

---

## What It Does

- Searches VastAI for the cheapest GPU instances matching your hardware requirements
- Launches instances and syncs your code + credentials via SCP
- Runs a setup script that installs dependencies, clones repos, and configures the environment
- Optionally runs a **Claude Code agent** autonomously on the remote machine with a prompt you define
- Monitors progress, streams logs, and auto-destroys instances when done
- Pushes results (code, logs, artifacts) to a GitHub repo

```
choline.yaml → Search VastAI → Launch → SCP files → Run setup → Agent runs → Push results → Auto-destroy
```

---

## Prerequisites

- **VastAI CLI** — `pip install vastai` then `vastai set api-key YOUR_KEY`
- **SSH key** — `~/.ssh/id_rsa` must exist
- **GitHub token** — for creating repos and pushing results
- **Python 3.8+** with `pyyaml` and `requests`

### Install

```bash
pip install git+https://github.com/bdytx5/choline_agent.git
```

### Credentials Setup

Run `choline init` or manually create `~/.choline/creds.yaml`:

```yaml
git_username: your-github-username
git_token: ghp_xxxxxxxxxxxx
API_KEYS:
  WANDB_API_KEY: your-wandb-key
  HUGGINGFACE_API_KEY: hf_xxxxxxxxxxxx
  CLAUDE_CODE_OAUTH_TOKEN: sk-ant-oat01-xxxxxxxxxxxx
```

API keys are automatically injected as environment variables on the remote machine.

---

## choline.yaml

The single config file that defines your instance, environment, and agent behavior.

### Minimal Example

```yaml
image: nvidia/cuda:12.0.0-devel-ubuntu20.04
hardware_filters:
  gpu_name: RTX_4090
  cpu_ram: '>30'
  disk_space: '>50'
num_gpus: '1'
repo_name: my-experiment
repo_private: true
setup_script: |
  #!/bin/bash
  pip install torch transformers
  python train.py
```

### Agent Mode Example

```yaml
image: nvidia/cuda:12.0.0-devel-ubuntu20.04
hardware_filters:
  gpu_name: RTX_3060
  cpu_ram: '>30'
  disk_space: '>50'
num_gpus: '1'
repo_name: my-agent-run
destroy_on_agent_complete: true
max_life: 120
claude_prompt: |
  Clone the repo, install deps, get training running.
  Write complete.txt when done.
```

### All Supported Keys

| Key | Description | Default |
|-----|-------------|---------|
| `image` | Docker image for the instance | `ubuntu:20.04` |
| `hardware_filters.gpu_name` | GPU model (`RTX_4090`, `A100`, `any`) | `any` |
| `hardware_filters.cpu_ram` | CPU RAM filter (e.g. `>30`) | `>16` |
| `hardware_filters.disk_space` | Disk space in GB (e.g. `>50`) | `>50` |
| `num_gpus` | Number of GPUs | `1` |
| `repo_name` | GitHub repo for results | — |
| `repo_private` | Make repo private | `true` |
| `git_username` | GitHub username (or from creds.yaml) | — |
| `git_token` | GitHub token (or from creds.yaml) | — |
| `upload_locations` | List of local paths to SCP to remote | `[]` |
| `ignore` | File patterns to skip during sync | `[]` |
| `setup_script` | Bash script run on remote after boot | — |
| `API_KEYS` | Key-value pairs exported as env vars on remote | — |
| **Agent Mode** | | |
| `claude_prompt` | Task instructions for Claude Code agent | — |
| `claude_model` | Model override (e.g. `claude-sonnet-4-5-20250514`) | default |
| `destroy_on_agent_complete` | Auto-destroy instance when agent writes `complete.txt` | `false` |
| `max_life` | Kill instance after N minutes regardless | `0` (disabled) |

---

## CLI

| Command | Description |
|---------|-------------|
| `choline init` | Interactive setup — prompts for GPU, image, API keys, creates choline.yaml |
| `choline launch` | Launch instance(s) from choline.yaml, SCP files, start setup |
| `choline status` | Check if remote setup is complete or failed |
| `choline stream` | Tail the remote setup log in real-time |
| `choline code` | Open VS Code via SSH to the running instance |
| `choline ssh` | SSH directly into the running instance |
| `choline kill` | Destroy running instance(s) |
| `choline sync` | Re-sync local files to the remote instance |
| `choline ui` | Manage custom env vars, aliases, functions for remote |

### Typical Flow

```bash
# First time setup
choline init

# Launch and monitor
choline launch
choline stream    # watch setup progress
choline status    # check if ready

# Connect
choline ssh       # or: choline code (VS Code)

# Done
choline kill
```

---

## Python API

```python
from choline import Instance

inst = Instance("choline.yaml",
    claude_prompt="train a model on CIFAR-10",
    repo_name="cifar-experiment",
    gpu_name="RTX_4090",
    max_life=60,
    destroy_on_agent_complete=True,
)

inst.create_repo()

# shotgun_count races N instances, keeps the fastest
cid = inst.launch(max_price=0.50, shotgun_count=3)

# Poll SSH until agent writes complete.txt
result = inst.wait_for_complete(poll_interval=60, timeout=36000)
print(result)

# Pull results from GitHub (works even after instance self-destructs)
results = inst.get_results(files=["complete.txt", "chat_session.md", "demo_log.txt", "demo.py"])
print(results["complete.txt"])

inst.kill()
```

### Instance Methods

| Method | Description |
|--------|-------------|
| `create_repo()` | Create GitHub repo, returns clone URL |
| `launch(max_price, shotgun_count)` | Launch instance(s), return winner contract_id |
| `wait_for_complete(poll_interval, timeout)` | Poll SSH for `complete.txt`, return contents |
| `check_status()` | Returns dict: `running`, `setup_complete`, `status_text`, `failed` |
| `stream_log(log_path, lines)` | Print tail of remote log file |
| `get_results(files, branch)` | Fetch files from GitHub repo |
| `is_complete(branch)` | Quick check — returns `complete.txt` contents or `None` |
| `verify_remote(contract_id)` | Confirm remote `run_id` matches local |
| `read_remote_file(remote_path)` | Read any file on the remote machine |
| `download_file(remote_path, local_path)` | SCP a file from remote to local |
| `ssh_details(contract_id)` | Returns `{host, port, user}` |
| `kill(contract_id)` | Destroy instance(s) |

### Standalone Functions

```python
from choline.api import enforce_max_life

# Scan choline_runs/ and kill any instances past their max_life
killed = enforce_max_life(runs_dir="choline_runs", dry_run=False)
```

---

## Agent Mode

Agent mode runs Claude Code autonomously on a remote GPU instance. Give it a prompt, it does the work, pushes results to GitHub, and optionally self-destructs.

### How It Works

1. Set `claude_prompt` in `choline.yaml` (or pass as override via API)
2. Choline launches an instance and installs Claude Code CLI
3. A loop runner (`run_claude.sh`) invokes `claude -p "$PROMPT"` up to 10 times
4. Claude works autonomously — installing packages, writing code, debugging errors
5. When done, Claude writes `complete.txt` with a summary
6. Results are pushed to GitHub (`git add -A && git push`)
7. If `destroy_on_agent_complete: true`, the instance self-destructs
8. If `max_life` is set, a watchdog kills the instance after N minutes regardless

### What Gets Pushed to GitHub

| File | Description |
|------|-------------|
| `complete.txt` | Summary of what the agent did |
| `chat_session.jsonl` | Raw Claude session log (JSON lines) |
| `chat_session.md` | Human-readable session transcript |
| `demo_log.txt` | Output from demo/training scripts |
| *(any agent files)* | All code and files the agent created |

### Example: Batch Paper Reproduction

```python
from choline import Instance

papers = [
    {"title": "My Paper", "arxiv": "https://arxiv.org/abs/...", "github": "https://github.com/..."},
]

for paper in papers:
    inst = Instance("choline.yaml",
        claude_prompt=f"Reproduce a demo for: {paper['title']}\n...",
        repo_name=f"demo-{paper['title'][:30]}",
        destroy_on_agent_complete=True,
        max_life=120,
    )
    inst.create_repo()
    inst.launch(max_price=0.50, shotgun_count=4)
    result = inst.wait_for_complete(timeout=36000)
    results = inst.get_results(files=["complete.txt", "demo.py", "chat_session.md"])
```

> **Tip:** Use `verify_remote()` to confirm a running instance belongs to your run — instance IDs get recycled on VastAI, so `contract_id` alone isn't reliable for long-lived monitoring.
