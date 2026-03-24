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
    result = subprocess.run(
        ["vastai", "show", "instance", str(vastai_id), "--raw"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    d = json.loads(result.stdout)
    host = d.get("ssh_host")
    port = str(d.get("ssh_port"))
    return "root", host, port


def main():
    raw_info = subprocess.getoutput('vastai show instances')
    instance_ids = parse_instance_info(raw_info)
    if not instance_ids:
        print("No running instances found.")
        return

    choice = int(input("Select an instance by number: "))
    selected_instance_id = instance_ids[choice - 1]

    username, host, port = get_ssh_details_proxy(selected_instance_id)
    key_path = get_ssh_key()

    print(f"Connecting to instance {selected_instance_id} via SSH ({host}:{port})...")
    os.execvp("ssh", [
        "ssh",
        "-i", key_path,
        "-p", port,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=5",
        f"{username}@{host}"
    ])


def run():
    main()
