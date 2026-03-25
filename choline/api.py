"""
Python API for choline.

Usage:
    from choline import Instance

    # Load yaml, override anything
    inst = Instance("choline.yaml",
        claude_prompt="train a model",
        gpu_name="RTX_4090",
        repo_name="my-experiment",
        repo_private=True,
    )
    # Create GitHub repo if it doesn't exist yet
    inst.create_repo()

    cid = inst.launch(max_price=0.50, shotgun_count=3)
    result = inst.wait_for_complete()
    print(result)  # contents of complete.txt
    inst.kill()
"""

import os
import re
import json
import yaml
import time
import uuid
import threading
import subprocess
import requests
from datetime import datetime, timezone
from pathlib import Path
from choline.utils import get_ssh_key


CREDS_FILE = Path.home() / ".choline" / "creds.yaml"


def _load_creds():
    """
    Load credentials from ~/.choline/creds.yaml.

    Expected structure:
        git_username: ...
        git_token: ...
        API_KEYS:
          WANDB_API_KEY: ...
          HUGGINGFACE_API_KEY: ...
          CLAUDE_CODE_OAUTH_TOKEN: ...

    Also handles legacy flat keys (username, github_token, etc).
    """
    if not CREDS_FILE.exists():
        return {}
    with open(CREDS_FILE, 'r') as f:
        creds = yaml.safe_load(f) or {}
    # handle legacy keys
    if 'username' in creds and 'git_username' not in creds:
        creds['git_username'] = creds['username']
    if 'github_token' in creds and 'git_token' not in creds:
        creds['git_token'] = creds['github_token']
    return creds


class Instance:
    def __init__(self, yaml_path, **overrides):
        """
        Load a choline.yaml and optionally override any field.

        Overrides: any key from the yaml. Hardware filter keys (gpu_name,
        disk_space, cpu_ram) are placed under hardware_filters automatically.

        Git repo fields (can be overridden or set in yaml):
            repo_name      - name of the GitHub repo
            repo_private   - True for private, False for public (default True)
            git_username   - GitHub username (defaults to creds.yaml username)
            git_token      - GitHub token (defaults to creds.yaml github_token)
        """
        self.yaml_path = os.path.abspath(yaml_path)
        self.work_dir = os.path.dirname(self.yaml_path)

        with open(self.yaml_path, 'r') as f:
            self.data = yaml.safe_load(f)

        hw_keys = {'gpu_name', 'disk_space', 'cpu_ram'}
        for k, v in overrides.items():
            if k in hw_keys:
                self.data.setdefault('hardware_filters', {})[k] = v
            else:
                self.data[k] = v

        # Backfill git creds from ~/.choline/creds.yaml if not provided
        creds = _load_creds()
        if 'git_username' not in self.data and 'username' in creds:
            self.data['git_username'] = creds['username']
        if 'git_token' not in self.data and 'github_token' in creds:
            self.data['git_token'] = creds['github_token']
        if 'repo_private' not in self.data:
            self.data['repo_private'] = True

        self._write_yaml()
        self.contract_ids = []
        self.winner_id = None
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]

    # ---- yaml / file helpers ----

    def _write_yaml(self):
        setup_script = self.data.pop('setup_script', None)
        with open(self.yaml_path, 'w') as f:
            yaml.dump(self.data, f, default_flow_style=False, indent=2)
            if setup_script:
                f.write("setup_script: |\n")
                f.write('  ' + setup_script.replace('\n', '\n  '))
        if setup_script:
            self.data['setup_script'] = setup_script

    def _ensure_choline_dir(self):
        choline_dir = os.path.join(self.work_dir, ".choline")
        os.makedirs(choline_dir, exist_ok=True)
        try:
            t = os.path.join(choline_dir, ".perm_test")
            with open(t, "w") as f:
                f.write("")
            os.remove(t)
        except PermissionError:
            print(f"WARNING: {choline_dir} is owned by root. Run: sudo chown -R $(whoami) {choline_dir}")
            raise
        return choline_dir

    def _generate_onstart_script(self):
        choline_dir = self._ensure_choline_dir()
        lines = [
            "#!/bin/bash",
            "mkdir -p ~/.choline",
            "echo '0' > ~/choline.txt",
            "while [ ! -f ~/.choline/choline_setup.sh ]; do",
            "  sleep 1",
            "done",
            "# Wait for runtime json too — SCP may deliver it after setup.sh",
            "for i in $(seq 1 30); do",
            "  [ -f ~/.choline/choline_runtime.json ] && break",
            "  sleep 1",
            "done",
            "sleep 3",
            "echo 'running setup script' > ~/choline.txt",
            ". ~/.choline/choline_setup.sh >> ~/.choline/choline_setup_log.txt 2>&1",
        ]
        path = os.path.join(choline_dir, "choline_onstart.sh")
        with open(path, "w") as f:
            f.write("\n".join(lines))
        return path

    def _write_setup_sh(self):
        choline_dir = self._ensure_choline_dir()
        path = os.path.join(choline_dir, "choline_setup.sh")
        with open(path, "w") as f:
            f.write(self.data.get('setup_script', ''))

        # Remove stale files from old format
        for stale in ('api_keys.env', 'repo_config.env', 'claude_prompt.txt',
                       'claude_model.txt', 'choline_runtime.yaml'):
            p = os.path.join(choline_dir, stale)
            if os.path.exists(p):
                os.remove(p)

        # Write choline_runtime.json — single file for all launch-time dynamic config
        runtime = {}

        # API keys (including CLAUDE_CODE_OAUTH_TOKEN — read from env on remote)
        api_keys = {}
        yaml_keys = self.data.get('API_KEYS', {})
        if yaml_keys:
            api_keys.update(yaml_keys)
        if api_keys:
            runtime['API_KEYS'] = api_keys

        # Claude prompt
        claude_prompt = self.data.get('claude_prompt', '')
        if claude_prompt:
            runtime['claude_prompt'] = claude_prompt

        # Claude model
        claude_model = self.data.get('claude_model', '')
        if claude_model:
            runtime['claude_model'] = claude_model

        # Run ID — unique identifier for this run, lives on remote too
        runtime['run_id'] = self.run_id

        # Destroy on agent complete
        destroy_on_complete = self.data.get('destroy_on_agent_complete', self.data.get('auto_destroy', self.data.get('shutdown_on_complete', False)))
        if destroy_on_complete:
            runtime['destroy_on_agent_complete'] = True

        # Max life in minutes — force-kill instance after this many minutes
        max_life = self.data.get('max_life', 0)
        if max_life:
            runtime['max_life'] = int(max_life)

        # Repo config
        git_username = self.data.get('git_username', '')
        git_token = self.data.get('git_token', '')
        repo_name = self.data.get('repo_name', '')
        if git_username and git_token and repo_name:
            runtime['git_username'] = git_username
            runtime['git_token'] = git_token
            runtime['repo_name'] = repo_name
            runtime['clone_url'] = f"https://{git_username}:{git_token}@github.com/{git_username}/{repo_name}.git"

        if runtime:
            runtime_path = os.path.join(choline_dir, "choline_runtime.json")
            with open(runtime_path, 'w') as f:
                json.dump(runtime, f, indent=2)

        # Copy helper scripts into .choline/ so they get SCP'd to remote
        import shutil
        for script_name in ("parse_runtime.py", "format_session.py"):
            src = os.path.join(os.path.dirname(__file__), script_name)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(choline_dir, script_name))

        return path

    # ---- git repo helpers ----

    def create_repo(self):
        """
        Create a GitHub repo using repo_name, git_username, git_token from
        the yaml/overrides. If the repo already exists, returns the clone URL.

        Returns:
            Clone URL string on success, None on failure.
        """
        repo_name = self.data.get('repo_name')
        git_username = self.data.get('git_username')
        git_token = self.data.get('git_token')
        repo_private = self.data.get('repo_private', True)

        if not repo_name:
            print("No repo_name set. Skipping repo creation.")
            return None
        if not git_username or not git_token:
            print("Missing git_username or git_token. Set them in yaml or ~/.choline/creds.yaml.")
            return None

        # Check if repo already exists
        check = requests.get(
            f"https://api.github.com/repos/{git_username}/{repo_name}",
            auth=(git_username, git_token)
        )
        if check.status_code == 200:
            clone_url = f"https://{git_username}:{git_token}@github.com/{git_username}/{repo_name}.git"
            print(f"Repo '{repo_name}' already exists.")
            return clone_url

        # Create it
        resp = requests.post(
            "https://api.github.com/user/repos",
            auth=(git_username, git_token),
            json={"name": repo_name, "private": repo_private}
        )
        if resp.status_code == 201:
            clone_url = f"https://{git_username}:{git_token}@github.com/{git_username}/{repo_name}.git"
            print(f"Created {'private' if repo_private else 'public'} repo '{repo_name}'.")
            return clone_url
        else:
            print(f"Failed to create repo: {resp.status_code} {resp.text}")
            return None

    def get_clone_url(self):
        """Build authenticated clone URL from yaml fields."""
        repo_name = self.data.get('repo_name')
        git_username = self.data.get('git_username')
        git_token = self.data.get('git_token')
        if not repo_name or not git_username or not git_token:
            return None
        return f"https://{git_username}:{git_token}@github.com/{git_username}/{repo_name}.git"

    # ---- run logging ----

    def _log_run(self, contract_id, offer=None, all_contract_ids=None):
        """
        Log a run to choline_runs/ with enough detail to identify and audit it
        even after instance IDs get recycled.
        """
        runs_dir = os.path.join(self.work_dir, "choline_runs")
        os.makedirs(runs_dir, exist_ok=True)

        run_log = {
            "run_id": self.run_id,
            "launched_at": datetime.now(timezone.utc).isoformat(),
            "contract_id": contract_id,
            "all_contract_ids": all_contract_ids or [contract_id],
            "repo_name": self.data.get("repo_name", ""),
            "git_username": self.data.get("git_username", ""),
            "image": self.data.get("image", ""),
            "gpu_name": self.data.get("hardware_filters", {}).get("gpu_name", ""),
            "num_gpus": self.data.get("num_gpus", "1"),
            "max_life": self.data.get("max_life", 0),
            "destroy_on_agent_complete": self.data.get("destroy_on_agent_complete", False),
            "claude_model": self.data.get("claude_model", ""),
            "claude_prompt_preview": (self.data.get("claude_prompt", "") or "")[:200],
        }

        if offer:
            run_log["offer_id"] = offer.get("id")
            run_log["machine_id"] = offer.get("machine_id")
            run_log["gpu_name_actual"] = offer.get("gpu_name", "")
            run_log["dph_base"] = offer.get("dph_base")
            run_log["host_id"] = offer.get("host_id")
            run_log["ssh_host"] = offer.get("public_ipaddr", "")

        fname = f"{self.run_id}.json"
        with open(os.path.join(runs_dir, fname), "w") as f:
            json.dump(run_log, f, indent=2)

        print(f"Run logged: choline_runs/{fname}")
        return self.run_id

    # ---- vastai helpers ----

    def _parse_hw_filters(self):
        hw = self.data.get('hardware_filters', {})
        cpu_ram_str = hw.get('cpu_ram', '>16')
        disk_space_str = hw.get('disk_space', '>50')
        gpu_name = hw.get('gpu_name', 'any')
        num_gpus = self.data.get('num_gpus', '1')
        image = self.data.get('image', 'ubuntu:20.04')

        m = re.match(r"([<>!=]+)(\d+)", cpu_ram_str)
        cpu_op, cpu_val = (m.group(1), int(m.group(2))) if m else ('>', 16)

        m = re.match(r"([<>!=]+)(\d+)", disk_space_str)
        disk_op, disk_val = (m.group(1), int(m.group(2))) if m else ('>', 50)

        return gpu_name, num_gpus, image, cpu_op, cpu_val, disk_op, disk_val

    def _search_offers(self, query=""):
        result = subprocess.run(
            ["vastai", "search", "offers", "--raw", query],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout = result.stdout.decode()
        if result.returncode != 0:
            print(f"Search error: {stdout or result.stderr.decode()}")
            return []
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return []

    def _sort_offers(self, offers, storage_gb, runtime_hr=2):
        def cost_key(o):
            dph = o['dph_base']
            storage_hr = (o['storage_cost'] / (30 * 24)) * storage_gb
            dl = storage_gb * o['inet_down_cost']
            ul = 1.0 * o['inet_up_cost']
            return (dph + storage_hr) * runtime_hr + dl + ul
        return sorted(offers, key=cost_key)

    def _create_instance(self, offer_id, options):
        cmd = ["vastai", "create", "instance", str(offer_id)] + options
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout = result.stdout.decode()
        if result.returncode != 0:
            print(f"Instance creation error: {stdout or result.stderr.decode()}")
            return None
        match = re.search(r"'new_contract': (\d+)", stdout)
        if match:
            return int(match.group(1))
        print(f"Could not parse contract ID from: {stdout}")
        return None

    def _get_instance_info(self, contract_id):
        """Get instance info from vastai. Returns dict or None."""
        result = subprocess.run(
            ["vastai", "show", "instance", str(contract_id), "--raw"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        try:
            return json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            return None

    def _check_machine_up(self, contract_id):
        d = self._get_instance_info(contract_id)
        if not d:
            return False
        host = d.get("ssh_host")
        port = str(d.get("ssh_port", ""))
        status = d.get("actual_status", "")
        if not host or not port or status != "running":
            return False

        ssh_key = get_ssh_key()
        r = subprocess.run(
            ["ssh", "-i", ssh_key, "-o", "StrictHostKeyChecking=no",
             "-o", "ConnectTimeout=10", "-p", port, f"root@{host}",
             "ls ~/choline.txt"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return r.returncode == 0 and "choline.txt" in r.stdout

    def _ssh_cmd(self, contract_id, cmd):
        """Run a command on the remote machine via SSH. Returns stdout."""
        d = self._get_instance_info(contract_id)
        if not d:
            return None
        host = d.get("ssh_host")
        port = str(d.get("ssh_port", ""))
        ssh_key = get_ssh_key()
        r = subprocess.run(
            ["ssh", "-i", ssh_key, "-o", "StrictHostKeyChecking=no",
             "-o", "ConnectTimeout=10", "-p", port, f"root@{host}", cmd],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return r.stdout if r.returncode == 0 else None

    def _scp_to_remote(self, contract_id, local_path, remote_path):
        """SCP a file/dir to the remote machine."""
        d = self._get_instance_info(contract_id)
        if not d:
            return False
        host = d.get("ssh_host")
        port = str(d.get("ssh_port", ""))
        ssh_key = get_ssh_key()
        flags = ["-i", ssh_key, "-o", "StrictHostKeyChecking=no", "-P", port]
        if os.path.isdir(local_path):
            flags.append("-r")
        r = subprocess.run(
            ["scp"] + flags + [local_path, f"root@{host}:{remote_path}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return r.returncode == 0

    def _scp_from_remote(self, contract_id, remote_path, local_path):
        """SCP a file from the remote machine to local."""
        d = self._get_instance_info(contract_id)
        if not d:
            return False
        host = d.get("ssh_host")
        port = str(d.get("ssh_port", ""))
        ssh_key = get_ssh_key()
        flags = ["-i", ssh_key, "-o", "StrictHostKeyChecking=no", "-P", port]
        r = subprocess.run(
            ["scp"] + flags + [f"root@{host}:{remote_path}", local_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return r.returncode == 0

    def _wait_and_sync(self, contract_id, max_checks=300, max_retries=3):
        """Wait for machine to come up, then SCP .choline dir to it with retry."""
        print(f"Waiting for instance {contract_id}...", flush=True)
        time.sleep(25)
        for _ in range(max_checks):
            if self._check_machine_up(contract_id):
                print(f"Instance {contract_id} is up. Syncing files.", flush=True)
                choline_dir = os.path.join(self.work_dir, ".choline")

                for attempt in range(1, max_retries + 1):
                    failed = []

                    # Ensure remote .choline dir exists
                    self._ssh_cmd(contract_id, "mkdir -p ~/.choline")

                    # SCP the .choline directory contents
                    for fname in os.listdir(choline_dir):
                        local = os.path.join(choline_dir, fname)
                        if os.path.isfile(local):
                            ok = self._scp_to_remote(contract_id, local, f"/root/.choline/{fname}")
                            if ok:
                                print(f"  Sent {fname}", flush=True)
                            else:
                                failed.append(fname)
                                print(f"  FAILED {fname}", flush=True)

                    # SCP upload_locations
                    for loc in self.data.get('upload_locations', []):
                        if os.path.exists(loc):
                            ok = self._scp_to_remote(contract_id, loc, "/root/")
                            if ok:
                                print(f"  Sent {loc}", flush=True)
                            else:
                                failed.append(loc)

                    # Transfer custom_env.sh if exists
                    custom_env = os.path.expanduser("~/.choline/custom_env.sh")
                    if os.path.exists(custom_env):
                        self._scp_to_remote(contract_id, custom_env, "/root/.choline/custom_env.sh")

                    # Verify critical files arrived
                    verify = self._ssh_cmd(contract_id, "ls ~/.choline/choline_setup.sh ~/.choline/choline_runtime.json 2>/dev/null")
                    setup_ok = verify is not None and "choline_setup.sh" in verify

                    if setup_ok and not failed:
                        print(f"Sync complete for {contract_id}.", flush=True)
                        return True

                    if attempt < max_retries:
                        print(f"  Sync incomplete (attempt {attempt}/{max_retries}), retrying in 5s...", flush=True)
                        time.sleep(5)

                # Final attempt failed
                if failed:
                    print(f"WARNING: Failed to send: {failed}", flush=True)
                if not setup_ok:
                    print(f"WARNING: choline_setup.sh not confirmed on remote", flush=True)
                # Still return True — onstart will wait for setup.sh
                print(f"Sync finished with warnings for {contract_id}.", flush=True)
                return True
            time.sleep(6)
        print(f"Instance {contract_id} failed to come up.", flush=True)
        return False

    # ---- public API ----

    def launch(self, max_price=None, shotgun_count=1):
        """
        Launch instance(s).

        Args:
            max_price: Max $/hr. If None, takes cheapest available.
            shotgun_count: Number of instances to race. First to come up wins,
                          rest get destroyed.

        Returns:
            contract_id of the winning instance, or None on failure.
        """
        orig_dir = os.getcwd()
        os.chdir(self.work_dir)

        try:
            gpu_name, num_gpus, image, cpu_op, cpu_val, disk_op, disk_val = self._parse_hw_filters()
            onstart_path = self._generate_onstart_script()
            self._write_setup_sh()

            if gpu_name.lower() != 'any':
                query = f"gpu_name={gpu_name} num_gpus>={num_gpus} disk_space {disk_op} {disk_val} cpu_ram {cpu_op} {cpu_val}"
            else:
                query = f"disk_space {disk_op} {disk_val} cpu_ram {cpu_op} {cpu_val}"

            print(f"Searching: {query}")
            offers = self._search_offers(query)
            offers = self._sort_offers(offers, disk_val)

            if not offers:
                print("No offers found.")
                return None

            if max_price is not None:
                offers = [o for o in offers if o['dph_base'] <= max_price]
                if not offers:
                    print(f"No offers under ${max_price}/hr.")
                    return None

            selected = offers[:shotgun_count]
            options = [
                "--image", image,
                "--disk", str(disk_val),
                "--onstart", onstart_path,
                "--env", "-e TZ=PDT -e XNAME=XX4 -p 22:22 -p 5000:5000",
            ]

            launched = []
            for offer in selected:
                cid = self._create_instance(offer["id"], options)
                if cid:
                    launched.append((cid, offer))
                    print(f"Launched contract {cid} (offer {offer['id']}, ${offer['dph_base']:.3f}/hr)")

            if not launched:
                print("All launches failed.")
                return None

            cids = [cid for cid, _ in launched]
            self.contract_ids = cids

            if len(cids) == 1:
                ok = self._wait_and_sync(cids[0])
                self.winner_id = cids[0] if ok else None
                if self.winner_id:
                    winner_offer = launched[0][1]
                    self._log_run(self.winner_id, offer=winner_offer,
                                  all_contract_ids=cids)
                return self.winner_id

            # Race mode
            print(f"Racing {len(cids)} instances...")
            winner = [None]
            lock = threading.Lock()

            def race(cid):
                for _ in range(300):
                    if winner[0] is not None:
                        return
                    if self._check_machine_up(cid):
                        break
                    time.sleep(10)
                else:
                    return

                with lock:
                    if winner[0] is not None:
                        subprocess.run(["vastai", "destroy", "instance", str(cid)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        return
                    winner[0] = cid

                for loser in cids:
                    if loser != cid:
                        print(f"Destroying loser {loser}")
                        subprocess.run(["vastai", "destroy", "instance", str(loser)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                self._wait_and_sync(cid)

            threads = [threading.Thread(target=race, args=(c,), daemon=True) for c in cids]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.winner_id = winner[0]
            if self.winner_id:
                # Find the offer that matched the winner
                winner_offer = next((o for c, o in launched if c == self.winner_id), None)
                self._log_run(self.winner_id, offer=winner_offer,
                              all_contract_ids=cids)
            return self.winner_id

        finally:
            os.chdir(orig_dir)

    def wait_for_complete(self, poll_interval=30, timeout=3600, completion_file="complete.txt", branch=None):
        """
        Poll the GitHub repo for the completion file.

        Args:
            poll_interval: Seconds between checks (default 30)
            timeout: Max seconds to wait (default 3600 = 1hr)
            completion_file: File to check for in the repo (default "complete.txt")
            branch: Git branch to check (default "main")

        Returns:
            String contents of the completion file on success, None on timeout.
        """
        repo_name = self.data.get('repo_name')
        git_username = self.data.get('git_username')
        git_token = self.data.get('git_token')

        if not repo_name or not git_username or not git_token:
            print("Missing repo_name, git_username, or git_token — cannot poll GitHub.")
            return None

        # Auto-detect default branch if none specified
        if branch is None:
            try:
                repo_url = f"https://api.github.com/repos/{git_username}/{repo_name}"
                resp = requests.get(repo_url, auth=(git_username, git_token))
                if resp.status_code == 200:
                    branch = resp.json().get("default_branch", "main")
                else:
                    branch = "main"
            except Exception:
                branch = "main"

        print(f"Monitoring repo {git_username}/{repo_name} ({branch}) for {completion_file}...", flush=True)
        elapsed = 0
        while elapsed < timeout:
            url = f"https://api.github.com/repos/{git_username}/{repo_name}/contents/{completion_file}?ref={branch}"
            try:
                resp = requests.get(url, auth=(git_username, git_token),
                                    headers={"Accept": "application/vnd.github.v3.raw"})
                if resp.status_code == 200 and len(resp.text.strip()) > 0:
                    contents = resp.text.strip()
                    print(f"{completion_file} found after {elapsed}s!")
                    print(f"Contents:\n{contents}")
                    return contents
            except Exception as e:
                print(f"  WARNING: GitHub API error: {e}", flush=True)

            time.sleep(poll_interval)
            elapsed += poll_interval
            if elapsed % 120 == 0:
                print(f"  Still waiting... ({elapsed}s elapsed)", flush=True)

        print(f"Timeout after {timeout}s. {completion_file} not found.")
        return None

    def check_status(self):
        """
        Check the current status of the remote machine.
        Reads ~/choline.txt and ~/.choline/setup_complete.txt to determine state.

        Returns:
            dict with keys: running, setup_complete, status_text, failed
        """
        cid = self.winner_id or (self.contract_ids[0] if self.contract_ids else None)
        if not cid:
            return {"running": False, "setup_complete": False, "status_text": "no instance", "failed": False}

        d = self._get_instance_info(cid)
        if not d:
            return {"running": False, "setup_complete": False, "status_text": "unreachable", "failed": False}

        actual_status = d.get("actual_status", "unknown")
        if actual_status != "running":
            return {"running": False, "setup_complete": False, "status_text": actual_status, "failed": False}

        status_text = self._ssh_cmd(cid, "cat ~/choline.txt 2>/dev/null") or "unknown"
        setup_done = self._ssh_cmd(cid, "cat ~/.choline/setup_complete.txt 2>/dev/null")
        failed = self._ssh_cmd(cid, "cat ~/.choline/failed.txt 2>/dev/null")

        return {
            "running": True,
            "setup_complete": setup_done is not None and setup_done.strip() == '0',
            "status_text": status_text.strip(),
            "failed": failed.strip() if failed else None,
        }

    def stream_log(self, log_path="~/.choline/choline_setup_log.txt", lines=50):
        """Print the last N lines of a remote log file."""
        cid = self.winner_id or (self.contract_ids[0] if self.contract_ids else None)
        if not cid:
            print("No instance.")
            return None
        out = self._ssh_cmd(cid, f"tail -n {lines} {log_path}")
        if out:
            print(out)
            return out
        else:
            print(f"Could not read {log_path}")
            return None

    def read_remote_file(self, remote_path):
        """Read any file from the remote machine. Returns contents or None."""
        cid = self.winner_id or (self.contract_ids[0] if self.contract_ids else None)
        if not cid:
            print("No instance.")
            return None
        return self._ssh_cmd(cid, f"cat {remote_path} 2>/dev/null")

    def download_file(self, remote_path, local_path):
        """Download a file from the remote machine via SCP."""
        cid = self.winner_id or (self.contract_ids[0] if self.contract_ids else None)
        if not cid:
            print("No instance.")
            return False
        return self._scp_from_remote(cid, remote_path, local_path)

    def kill(self, contract_id=None):
        """Destroy instance(s). If contract_id given, destroy just that one."""
        targets = [contract_id] if contract_id else self.contract_ids
        for cid in targets:
            print(f"Destroying instance {cid}")
            subprocess.run(["vastai", "destroy", "instance", str(cid)],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def get_results(self, files=None, branch="main"):
        """
        Pull result files from the GitHub repo after the agent has finished and pushed.

        Args:
            files: List of file paths to fetch from the repo. Defaults to
                   ["complete.txt", "chat_session.md", "demo_log.txt"].
            branch: Git branch to read from (default "main").

        Returns:
            dict mapping filename -> contents (str), or None if the file
            doesn't exist in the repo.
        """
        repo_name = self.data.get('repo_name')
        git_username = self.data.get('git_username')
        git_token = self.data.get('git_token')

        if not repo_name or not git_username or not git_token:
            print("Missing repo_name, git_username, or git_token.")
            return {}

        if files is None:
            files = ["complete.txt", "chat_session.md", "demo_log.txt"]

        results = {}
        for fname in files:
            url = f"https://api.github.com/repos/{git_username}/{repo_name}/contents/{fname}?ref={branch}"
            resp = requests.get(url, auth=(git_username, git_token),
                                headers={"Accept": "application/vnd.github.v3.raw"})
            if resp.status_code == 200:
                results[fname] = resp.text
            else:
                results[fname] = None

        return results

    def is_complete(self, branch="main"):
        """
        Check if the agent has finished by looking for complete.txt in the repo.

        Returns:
            String contents of complete.txt if done, None if not yet.
        """
        results = self.get_results(files=["complete.txt"], branch=branch)
        return results.get("complete.txt")

    def verify_remote(self, contract_id=None):
        """
        Check that the remote instance is actually running THIS run by comparing
        run_id in choline_runtime.json on the remote vs our local run_id.

        Returns:
            True if it matches, False if mismatch or unreachable.
        """
        cid = contract_id or self.winner_id or (self.contract_ids[0] if self.contract_ids else None)
        if not cid:
            return False
        out = self._ssh_cmd(cid, "cat ~/.choline/choline_runtime.json 2>/dev/null")
        if not out:
            return False
        try:
            remote_rt = json.loads(out)
            return remote_rt.get("run_id") == self.run_id
        except (json.JSONDecodeError, ValueError):
            return False

    def ssh_details(self, contract_id=None):
        """Get SSH connection details for an instance."""
        cid = contract_id or self.winner_id or (self.contract_ids[0] if self.contract_ids else None)
        if not cid:
            print("No instance.")
            return None
        d = self._get_instance_info(cid)
        if not d:
            print(f"Could not get info for instance {cid}")
            return None
        return {"host": d.get("ssh_host"), "port": d.get("ssh_port"), "user": "root"}


def enforce_max_life(runs_dir="choline_runs", dry_run=False):
    """
    Scan all run logs in choline_runs/, check which instances are still alive,
    and kill any that have exceeded their max_life.

    Prints a verbose summary of every run: alive/dead, time remaining, and
    whether it was killed.

    Args:
        runs_dir: Path to the choline_runs directory.
        dry_run: If True, print what would be killed but don't actually kill.

    Returns:
        List of run_ids that were killed.
    """
    if not os.path.isdir(runs_dir):
        print(f"No runs directory found at {runs_dir}")
        return []

    # Load all run logs
    runs = []
    for fname in sorted(os.listdir(runs_dir)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(runs_dir, fname)) as f:
            try:
                runs.append(json.load(f))
            except json.JSONDecodeError:
                continue

    if not runs:
        print("No runs found.")
        return []

    # Get all current vastai instances
    result = subprocess.run(
        ["vastai", "show", "instances", "--raw"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        live_instances = json.loads(result.stdout) if result.returncode == 0 else []
    except json.JSONDecodeError:
        live_instances = []

    live_ids = {inst.get("id") for inst in live_instances}

    now = datetime.now(timezone.utc)
    killed = []

    print(f"{'='*80}")
    print(f"CHOLINE RUN AUDIT — {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*80}\n")

    for run in runs:
        run_id = run.get("run_id", "???")
        contract_id = run.get("contract_id")
        all_cids = run.get("all_contract_ids", [contract_id])
        repo = run.get("repo_name", "???")
        max_life = run.get("max_life", 0)
        launched_at_str = run.get("launched_at", "")
        gpu = run.get("gpu_name_actual") or run.get("gpu_name", "???")
        dph = run.get("dph_base")
        price_str = f"${dph:.3f}/hr" if dph else "???"

        # Parse launch time
        try:
            launched_at = datetime.fromisoformat(launched_at_str)
            if launched_at.tzinfo is None:
                launched_at = launched_at.replace(tzinfo=timezone.utc)
            elapsed = now - launched_at
            elapsed_min = elapsed.total_seconds() / 60
        except (ValueError, TypeError):
            elapsed_min = None

        # Check if ANY of the contract IDs from this run are still alive
        live_cids = [c for c in all_cids if c in live_ids]
        alive = len(live_cids) > 0

        # Header
        status = "ALIVE" if alive else "DEAD"
        print(f"[{status}] {repo}")
        print(f"  run_id:      {run_id}")
        print(f"  winner:      {contract_id}")
        if len(all_cids) > 1:
            print(f"  all launched: {all_cids}")
            if alive:
                print(f"  still alive:  {live_cids}")
        print(f"  gpu:         {gpu}  price: {price_str}")

        if elapsed_min is not None:
            print(f"  launched:    {launched_at_str} ({elapsed_min:.0f}m ago)")
        else:
            print(f"  launched:    {launched_at_str}")

        if not alive:
            print(f"  status:      instance no longer running")
            print()
            continue

        if not max_life:
            print(f"  max_life:    not set (no limit)")
            print()
            continue

        remaining = max_life - (elapsed_min or 0)
        print(f"  max_life:    {max_life}m")

        if elapsed_min is not None and elapsed_min > max_life:
            overdue = elapsed_min - max_life
            print(f"  OVERDUE:     {overdue:.0f}m past max_life!")

            for cid in live_cids:
                if dry_run:
                    print(f"  action:      would kill {cid} (dry run)")
                else:
                    print(f"  action:      KILLING instance {cid}")
                    subprocess.run(
                        ["vastai", "destroy", "instance", str(cid)],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
            if not dry_run:
                killed.append(run_id)
        else:
            print(f"  remaining:   {remaining:.0f}m")

        print()

    print(f"{'='*80}")
    print(f"Total runs: {len(runs)}  |  Alive: {sum(1 for r in runs if r.get('contract_id') in live_ids)}  |  Killed: {len(killed)}")
    print(f"{'='*80}")

    return killed
