import subprocess
import os
from choline.utils import get_ssh_key
import re
import json


def parse_instance_info(raw_info):
    instance_ids = []
    pattern = r"\n(\d+)"
    matches = re.findall(pattern, raw_info)
    for i, instance_id in enumerate(matches):
        print(f"{i+1}. Instance ID: {instance_id}")
        instance_ids.append(instance_id)
    return instance_ids


def get_ssh_details_proxy(vastai_id):
    """Use show instance --raw to get proxy host/port (same as monitor uses)."""
    result = subprocess.run(
        ["vastai", "show", "instance", str(vastai_id), "--raw"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    d = json.loads(result.stdout)
    host = d.get("ssh_host")
    port = str(d.get("ssh_port"))
    return "root", host, port


def write_ssh_config_entry(alias, host, port, key_path):
    """Upsert a Host block in ~/.ssh/config for the given alias."""
    ssh_config = os.path.expanduser("~/.ssh/config")
    block = (
        f"Host {alias}\n"
        f"    HostName {host}\n"
        f"    Port {port}\n"
        f"    User root\n"
        f"    IdentityFile {key_path}\n"
        f"    StrictHostKeyChecking no\n"
        f"    ServerAliveInterval 30\n"
        f"    ServerAliveCountMax 5\n"
    )

    existing = ""
    if os.path.exists(ssh_config):
        with open(ssh_config) as f:
            existing = f.read()

    # remove old block for this alias if present
    existing = re.sub(
        rf"Host {re.escape(alias)}\n(?:[ \t]+.*\n)*",
        "",
        existing
    )

    with open(ssh_config, "w") as f:
        f.write(existing.rstrip("\n") + "\n\n" + block)

    os.chmod(ssh_config, 0o600)
    print(f"SSH config updated: Host {alias} -> {host}:{port}")


def open_in_vscode(alias, open_repo=False):
    folder = "/root/repo" if open_repo else "/root"
    vscode_command = f"code --folder-uri=vscode-remote://ssh-remote+{alias}{folder}"
    result = subprocess.run(vscode_command, shell=True)
    if result.returncode == 0:
        print("VS Code opened successfully.")
    else:
        print("Failed to open VS Code.")


def main(open_repo=False):
    raw_info = subprocess.getoutput('vastai show instances')
    instance_ids = parse_instance_info(raw_info)
    choice = int(input("Select an instance by number: "))
    selected_instance_id = instance_ids[choice - 1]

    username, host, port = get_ssh_details_proxy(selected_instance_id)
    key_path = get_ssh_key()

    alias = f"choline-{selected_instance_id}"
    write_ssh_config_entry(alias, host, port, key_path)

    print(f"Opening VSCode via SSH host alias: {alias}")
    open_in_vscode(alias, open_repo=open_repo)


def run():
    import sys
    open_repo = len(sys.argv) > 2 and sys.argv[2] == 'repo'
    main(open_repo=open_repo)
