choline
=======
Launch GPU instances on VastAI, sync your code, and run autonomous Claude Code agents
-- all from a single YAML file or Python API.


WHAT THIS PACKAGE DOES
----------------------
Choline is a CLI tool and Python library that:
- Searches VastAI for the cheapest GPU instances matching your hardware requirements
- Launches instances, syncs your code and credentials via SCP
- Runs a setup script that installs dependencies, clones repos, and configures the environment
- Optionally runs a Claude Code agent autonomously on the remote machine with a prompt you define
- Monitors progress, streams logs, and auto-destroys instances when done
- Pushes results (code, logs, artifacts) to a GitHub repo

Flow:
  choline.yaml -> Search VastAI offers -> Launch instance -> SCP files -> Run setup -> Agent runs -> Push results -> Auto-destroy


PREREQUISITES
-------------
- VastAI CLI: pip install vastai, then: vastai set api-key YOUR_KEY
- SSH key: ~/.ssh/id_rsa must exist (used for SCP to remote instances)
- GitHub token: for creating repos and pushing results
- Python 3.8+ with pyyaml and requests

Install:
  cd choline_two_dev
  pip install -e .

Credentials Setup:
  Run `choline init` or manually create ~/.choline/creds.yaml:

    git_username: your-github-username
    git_token: ghp_xxxxxxxxxxxx
    API_KEYS:
      WANDB_API_KEY: your-wandb-key
      HUGGINGFACE_API_KEY: hf_xxxxxxxxxxxx
      CLAUDE_CODE_OAUTH_TOKEN: sk-ant-oat01-xxxxxxxxxxxx

  API keys are automatically injected as environment variables on the remote machine.


CHOLINE.YAML
------------
The single config file that defines your instance, environment, and agent behavior.

Minimal Example:
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

Agent Mode Example:
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

All Supported Keys:
  Key                              Description                                          Default
  ----                             -----------                                          -------
  image                            Docker image for the instance                        ubuntu:20.04
  hardware_filters.gpu_name        GPU model (RTX_4090, A100, any)                      any
  hardware_filters.cpu_ram         CPU RAM filter (e.g. >30)                            >16
  hardware_filters.disk_space      Disk space in GB (e.g. >50)                         >50
  num_gpus                         Number of GPUs                                       1
  repo_name                        GitHub repo for results                              --
  repo_private                     Make repo private                                    true
  git_username                     GitHub username (or from creds.yaml)                 --
  git_token                        GitHub token (or from creds.yaml)                    --
  upload_locations                 List of local paths to SCP to remote                 []
  ignore                           File patterns to skip during sync                    []
  setup_script                     Bash script run on remote after boot                 --
  API_KEYS                         Key-value pairs exported as env vars on remote       --
  --- Agent Mode Keys ---
  claude_prompt                    Task instructions for Claude Code agent               --
  claude_model                     Model override (e.g. claude-sonnet-4-5-20250514)     default
  destroy_on_agent_complete        Auto-destroy instance when agent writes complete.txt  false
  max_life                         Kill instance after N minutes regardless              0 (disabled)


CLI
---
  Command           Description
  -------           -----------
  choline init      Interactive setup -- prompts for GPU, image, API keys, creates choline.yaml
  choline launch    Launch instance(s) from choline.yaml, SCP files, start setup
  choline status    Check if remote setup is complete or failed
  choline stream    Tail the remote setup log in real-time
  choline code      Open VS Code via SSH to the running instance
  choline ssh       SSH directly into the running instance
  choline kill      Destroy running instance(s)
  choline sync      Re-sync local files to the remote instance
  choline ui        Manage custom env vars, aliases, functions for remote

Typical CLI Flow:
  # First time setup
  choline init

  # Launch and monitor
  choline launch
  choline stream      # watch setup progress
  choline status      # check if ready

  # Connect
  choline ssh         # or choline code for VS Code

  # Done
  choline kill


PYTHON API
----------
  from choline import Instance

  # Create instance from yaml, override any field
  inst = Instance("choline.yaml",
      claude_prompt="train a model on CIFAR-10",
      repo_name="cifar-experiment",
      gpu_name="RTX_4090",
      max_life=60,
      destroy_on_agent_complete=True,
  )

  # Create GitHub repo if needed
  inst.create_repo()

  # Launch (shotgun_count races N instances, keeps the fastest)
  cid = inst.launch(max_price=0.50, shotgun_count=3)

  # Wait for agent to finish (polls via SSH)
  result = inst.wait_for_complete(poll_interval=60, timeout=36000)
  print(result)  # contents of complete.txt

  # Or pull results from GitHub after instance self-destructs
  results = inst.get_results(files=[
      "complete.txt",
      "chat_session.md",
      "demo_log.txt",
      "demo.py",
  ])
  print(results["complete.txt"])

  # Verify remote instance is actually yours (by run_id)
  assert inst.verify_remote()

  # Monitor and connect
  inst.check_status()
  inst.stream_log()
  inst.ssh_details()

  # Cleanup
  inst.kill()

All Instance Methods:
  Method                                  Description
  ------                                  -----------
  create_repo()                           Create GitHub repo, returns clone URL
  launch(max_price, shotgun_count)        Launch instance(s), return winner contract_id
  wait_for_complete(poll_interval,        Poll SSH for complete.txt, return contents
    timeout)
  check_status()                          Dict: running, setup_complete, status_text, failed
  stream_log(log_path, lines)             Print tail of remote log file
  get_results(files, branch)              Fetch files from GitHub repo (works after instance dies)
  is_complete(branch)                     Quick check: returns complete.txt contents or None
  verify_remote(contract_id)              Confirm remote run_id matches local (prevents ID recycling)
  read_remote_file(remote_path)           Cat any file on the remote machine
  download_file(remote_path, local_path)  SCP a file from remote to local
  ssh_details(contract_id)               Returns {host, port, user}
  kill(contract_id)                       Destroy instance(s)

Standalone Functions:
  from choline.api import enforce_max_life

  # Scan choline_runs/ and kill any instances past their max_life
  killed = enforce_max_life(runs_dir="choline_runs", dry_run=False)


AGENT MODE
----------
Agent mode runs Claude Code autonomously on a remote GPU instance. You give it a prompt,
it does the work, pushes results to GitHub, and optionally self-destructs.

How It Works:
  1. Set claude_prompt in your choline.yaml (or pass as override via API)
  2. Choline launches an instance, installs Claude Code CLI on it
  3. A loop runner (run_claude.sh) invokes `claude -p "$PROMPT"` up to 10 times
  4. Claude works autonomously -- installing packages, writing code, debugging errors
  5. When done, Claude writes complete.txt with a summary
  6. The runner pushes all results to GitHub (git add -A && git push)
  7. If destroy_on_agent_complete: true, the instance self-destructs
  8. If max_life is set, a background watchdog kills the instance after N minutes regardless

What Gets Pushed to GitHub:
  File                  Description
  ----                  -----------
  complete.txt          Summary of what the agent did
  chat_session.jsonl    Raw Claude session log (JSON lines)
  chat_session.md       Human-readable markdown version of the session
  demo_log.txt          Output from demo/training scripts (if agent created one)
  (any agent files)     All code/files the agent created

Runtime Config Flow:
  All dynamic config flows through a single file: choline_runtime.json
    choline.yaml -> choline_runtime.json -> SCP to remote -> parse_runtime.py -> env vars
  parse_runtime.py is stdlib-only (no pip dependencies) so it runs before any packages are installed.

Run Auditing:
  Every launch creates a JSON log in choline_runs/ with:
  - Unique run_id (also written to remote via runtime json)
  - Contract ID, all launched instance IDs (for shotgun mode)
  - Offer details: machine_id, host_id, GPU, price
  - Repo name, max_life, destroy settings
  Use enforce_max_life() or `python enforce_lifetime.py` to scan runs and kill overdue instances.

Example: Batch Paper Reproduction:
  from choline import Instance

  papers = [
      {"title": "My Paper", "arxiv": "https://arxiv.org/abs/...", "github": "https://github.com/..."},
  ]

  for paper in papers:
      prompt = f"Reproduce a demo for: {paper['title']}\n..."

      inst = Instance("choline.yaml",
          claude_prompt=prompt,
          repo_name=f"demo-{paper['title'][:30]}",
          destroy_on_agent_complete=True,
          max_life=120,
      )
      inst.create_repo()
      inst.launch(max_price=0.50, shotgun_count=4)

      result = inst.wait_for_complete(timeout=36000)
      results = inst.get_results(files=["complete.txt", "demo.py", "chat_session.md"])

TIP: Use verify_remote() to confirm a running instance belongs to your run -- instance IDs
get recycled on VastAI, so contract_id alone isn't reliable for long-lived monitoring.
