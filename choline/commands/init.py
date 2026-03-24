
import argparse
import subprocess
import os
import sys
import json 
from pathlib import Path

import yaml 
import shutil
from datetime import datetime



from pathlib import Path
import yaml


import os
import fnmatch

CREDS_FILE = Path.home() / ".choline" / "creds.yaml"

def ensure_creds_file():
    """
    Ensure ~/.choline/creds.yaml exists with the required structure:

        git_username: bdytx5
        git_token: ghp_...
        API_KEYS:
          WANDB_API_KEY: ...
          HUGGINGFACE_API_KEY: ...
          CLAUDE_CODE_OAUTH_TOKEN: ...
    """
    CREDS_FILE.parent.mkdir(parents=True, exist_ok=True)

    if CREDS_FILE.exists():
        with open(CREDS_FILE, 'r') as f:
            creds = yaml.safe_load(f) or {}
    else:
        print(f"Creating {CREDS_FILE}...")
        creds = {}

    # --- migrate old flat keys into new structure ---
    if 'username' in creds and 'git_username' not in creds:
        creds['git_username'] = creds.pop('username')
    if 'github_token' in creds and 'git_token' not in creds:
        creds['git_token'] = creds.pop('github_token')
    if 'API_KEYS' not in creds:
        creds['API_KEYS'] = {}
    api_keys = creds['API_KEYS']
    # migrate old flat API keys
    for old_key, new_key in [('WANDB_API_KEY', 'WANDB_API_KEY'),
                              ('HUGGINGFACE_API_KEY', 'HUGGINGFACE_API_KEY'),
                              ('claude_code_token', 'CLAUDE_CODE_OAUTH_TOKEN')]:
        if old_key in creds and new_key not in api_keys:
            api_keys[new_key] = creds.pop(old_key)
        elif old_key in creds:
            creds.pop(old_key)

    changed = False

    # git creds
    if not creds.get('git_username'):
        creds['git_username'] = input("Enter your GitHub username: ")
        changed = True
    if not creds.get('git_token'):
        creds['git_token'] = input("Enter your GitHub token: ")
        changed = True

    # API keys — prompt for any missing ones
    known_api_keys = [
        ('WANDB_API_KEY', 'Weights & Biases API key'),
        ('HUGGINGFACE_API_KEY', 'Hugging Face API key'),
        ('CLAUDE_CODE_OAUTH_TOKEN', 'Claude Code OAuth token'),
    ]
    for key_name, display_name in known_api_keys:
        if key_name not in api_keys:
            val = input(f"Enter your {display_name} (or press Enter to skip): ").strip()
            if val:
                api_keys[key_name] = val
                changed = True

    # offer to add custom keys
    while True:
        custom = input("Add another API key? Enter name (e.g. OPENAI_API_KEY) or press Enter to skip: ").strip()
        if not custom:
            break
        val = input(f"Enter value for {custom}: ").strip()
        if val:
            api_keys[custom] = val
            changed = True

    if changed or not CREDS_FILE.exists():
        with open(CREDS_FILE, 'w') as f:
            yaml.dump(creds, f, default_flow_style=False)
        print(f"{CREDS_FILE} saved.")



import requests
from pathlib import Path
import yaml
# def ask_create_repo():
#     creds_file = Path.home() / ".choline" / "creds.yaml"
#     if not creds_file.exists():
#         raise FileNotFoundError("Credentials file not found. Please create ~/.choline/creds.yaml with the necessary Git credentials.")

#     with open(creds_file, 'r') as f:
#         creds = yaml.safe_load(f)

#     if 'username' not in creds or 'github_token' not in creds:
#         raise ValueError("Credentials file is missing necessary Git credentials. Please add 'username' and 'github_token' to ~/.choline/creds.yaml.")

#     git_username = creds['username']
#     github_token = creds['github_token']
    
#     # Check if any remote repository is set
#     try:
#         result = subprocess.run(["git", "config", "--get", "remote.origin.url"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#         remote_url = result.stdout.decode().strip()
#         if remote_url:
#             print(f"Remote repository is already set: {remote_url}")
#             return True
#         else:
#             print("No remote repository is set.")
#     except subprocess.CalledProcessError:
#         print("This directory is not a Git repository. You need to initialize a Git repository and set a remote URL.")
    
#     repo_name = input("Enter the name of the repository you want to create: ")
#     create_choice = input("Do you want to create a new repository? Enter 'p' for private, 'b' for public, or press Enter to exit: ").lower()
    
#     if create_choice == 'p':
#         repo_private = True
#     elif create_choice == 'b':
#         repo_private = False
#     else:
#         print("Exiting without creating a repository.")
#         return False

#     create_repo_payload = {
#         "name": repo_name,
#         "private": repo_private
#     }
    
#     create_response = requests.post(f"https://api.github.com/user/repos", auth=(git_username, github_token), json=create_repo_payload)
    
#     if create_response.status_code == 201:
#         print(f"Repository '{repo_name}' created successfully.")
#         return True
#     else:
#         print(f"Failed to create repository. Status code: {create_response.status_code}")
#         print(create_response.json())
#         return False

import subprocess
import requests
import yaml
import os
from pathlib import Path

def ask_create_repo():
    creds_file = Path.home() / ".choline" / "creds.yaml"
    if not creds_file.exists():
        raise FileNotFoundError("Credentials file not found. Please create ~/.choline/creds.yaml with the necessary Git credentials.")

    with open(creds_file, 'r') as f:
        creds = yaml.safe_load(f)

    git_username = creds.get('git_username') or creds.get('username')
    github_token = creds.get('git_token') or creds.get('github_token')

    if not git_username:
        git_username = input("Enter your GitHub username: ").strip()
        if not git_username:
            print("No username provided. Skipping repo creation.")
            return False
        creds['git_username'] = git_username

    if not github_token:
        github_token = input("Enter your GitHub token: ").strip()
        if not github_token:
            print("No token provided. Skipping repo creation.")
            return False
        creds['git_token'] = github_token

    # Save back to creds file so they don't have to enter again
    with open(creds_file, 'w') as f:
        yaml.dump(creds, f, default_flow_style=False)
    
    # Check if any remote repository is set
    try:
        result = subprocess.run(["git", "config", "--get", "remote.origin.url"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        remote_url = result.stdout.decode().strip()
        if remote_url:
            print(f"Remote repository is already set: {remote_url}")
            existing_repo_name = remote_url.rstrip('/').split('/')[-1].replace('.git', '')
            return existing_repo_name, git_username, github_token
        else:
            print("No remote repository is set.")
    except subprocess.CalledProcessError:
        print("This directory is not a Git repository. You need to initialize a Git repository and set a remote URL.")
    
    repo_name = input("Enter the name of the repository you want to create: ").strip().replace(" ", "-")
    create_choice = input("Do you want to create a new repository? Enter 'p' for private, 'b' for public, or press Enter to exit: ").lower()
    
    if create_choice == 'p':
        repo_private = True
    elif create_choice == 'b':
        repo_private = False
    else:
        print("Exiting without creating a repository.")
        return False

    create_repo_payload = {
        "name": repo_name,
        "private": repo_private
    }
    
    create_response = requests.post(f"https://api.github.com/user/repos", auth=(git_username, github_token), json=create_repo_payload)
    
    if create_response.status_code == 201:
        print(f"Repository '{repo_name}' created successfully.")
        
        # Initialize git repository if not already initialized
        subprocess.run(["git", "init"], check=True)
        
        # build .gitignore — always exclude choline internals + large files
        large_file_mb = input("Ignore files larger than how many MB? (default 1, press Enter to skip): ").strip()
        large_file_threshold = None
        try:
            large_file_threshold = float(large_file_mb) if large_file_mb else 1.0
        except ValueError:
            pass

        with open('.gitignore', 'a') as f:
            f.write("choline.yaml\n")
            f.write(".choline/\n")

        if large_file_threshold is not None:
            threshold_bytes = large_file_threshold * 1024 * 1024
            large_files = []
            for root, dirs, files in os.walk("."):
                dirs[:] = [d for d in dirs if d not in (".git",)]
                for fname in files:
                    fpath = os.path.join(root, fname)
                    try:
                        if os.path.getsize(fpath) > threshold_bytes:
                            rel = os.path.relpath(fpath, ".")
                            large_files.append(rel)
                    except OSError:
                        pass
            if large_files:
                print(f"Found {len(large_files)} file(s) over {large_file_threshold}MB — adding to .gitignore:")
                for lf in large_files:
                    print(f"  {lf}")
                with open('.gitignore', 'a') as f:
                    for lf in large_files:
                        f.write(lf + "\n")

        # find nested repos
        nested_repos = []
        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in (".git",)]
            for d in dirs:
                nested_git = os.path.join(root, d, ".git")
                if os.path.exists(nested_git):
                    nested_repos.append(os.path.join(root, d))

        if nested_repos:
            print("Found nested git repos:")
            for nr in nested_repos:
                print(f"  {nr}")
            flatten = input("Flatten them into this repo as plain directories? (y/n): ").strip().lower() == 'y'
            if flatten:
                import shutil
                for nr in nested_repos:
                    rel = os.path.relpath(nr, ".")
                    # remove from git index as submodule first, then re-add as plain dir
                    subprocess.run(["git", "rm", "--cached", rel], capture_output=True)
                    nested_git = os.path.join(nr, ".git")
                    shutil.rmtree(nested_git)
                    print(f"Removed .git from {nr}")

        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], check=True)

        remote_url = f"https://{git_username}:{github_token}@github.com/{git_username}/{repo_name}.git"
        subprocess.run(["git", "remote", "add", "origin", remote_url], check=True)
        push = subprocess.run(["git", "push", "-u", "origin", "main"])
        if push.returncode != 0:
            # try setting HEAD and pushing master->main
            subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"])
            push2 = subprocess.run(["git", "push", "-u", "origin", "main"])
            if push2.returncode != 0:
                print("Push failed. You may need to push manually: git push -u origin main")
                return False
        
        return repo_name, git_username, github_token
    else:
        print(f"Failed to create repository. Status code: {create_response.status_code}")
        print(create_response.json())
        return False
    
    # def ask_create_repo():
#     creds_file = Path.home() / ".choline" / "creds.yaml"
#     if not creds_file.exists():
#         raise FileNotFoundError("Credentials file not found. Please create ~/.choline/creds.yaml with the necessary Git credentials.")

#     with open(creds_file, 'r') as f:
#         creds = yaml.safe_load(f)

#     if 'username' not in creds or 'github_token' not in creds:
#         raise ValueError("Credentials file is missing necessary Git credentials. Please add 'username' and 'github_token' to ~/.choline/creds.yaml.")

#     git_username = creds['username']
#     github_token = creds['github_token']
    
#     repo_name = input("Enter the name of the repository you want to create or check: ")
#     repo_url = f"https://api.github.com/repos/{git_username}/{repo_name}"
    
#     response = requests.get(repo_url, auth=(git_username, github_token))
    
#     if response.status_code == 200:
#         print(f"The repository '{repo_name}' already exists.")
#     else:
#         print(f"The repository '{repo_name}' does not exist.")
#         create_choice = input("Do you want to create a new repository? Enter 'p' for private, 'b' for public, or press Enter to exit: ").lower()
        
#         if create_choice == 'p':
#             repo_private = True
#         elif create_choice == 'b':
#             repo_private = False
#         else:
#             print("Exiting without creating a repository.")
#             return

#         create_repo_payload = {
#             "name": repo_name,
#             "private": repo_private
#         }
        
#         create_response = requests.post(f"https://api.github.com/user/repos", auth=(git_username, github_token), json=create_repo_payload)
        
#         if create_response.status_code == 201:
#             print(f"Repository '{repo_name}' created successfully.")
#         else:
#             print(f"Failed to create repository. Status code: {create_response.status_code}")
#             print(create_response.json())

# # Example usage





def get_local_cuda_version():
    try:
        result = subprocess.run(["nvcc", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        result.check_returncode()
        version_line = result.stdout.decode().split("\n")[-2]
        local_cuda_version = version_line.split("_")[1].split(".r")[0]
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("CUDA not found. Using default version 12.0.")
        local_cuda_version = '12.0'
    return local_cuda_version

def get_python_version():
    return sys.version.split(' ')[0]


def get_conda_version():
    try:
        result = subprocess.run(["conda", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        result.check_returncode()
        conda_version = result.stdout.decode().strip().split(" ")[-1]
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Conda not found. Using 'latest' as default.")
        conda_version = 'latest'
    return conda_version



def get_requirements_list():
    result = subprocess.run(["pip", "freeze"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print("Error getting requirements. Using empty requirements.")
        return []
    return result.stdout.decode().split("\n")



def get_requirements_list():
    while True:
        use_req_txt = input("Do you want to supply the path to a requirements.txt file? (y/n): ").lower()
        
        if use_req_txt == 'y':
            req_path = input("Please enter the full path to your requirements.txt file: ")
            
            if os.path.exists(req_path):
                with open(req_path, 'r') as f:
                    return f.read().split("\n")
            else:
                print("The provided path does not exist.")
                
                while True:
                    continue_or_quit = input("Do you want to reenter the path or use pip freeze? (reenter/pip): ").lower()
                
                    if continue_or_quit == 'pip':
                        break
                    elif continue_or_quit == 'reenter':
                        break
                    else:
                        print("Invalid option. Please choose 'reenter' or 'pip'.")
                
                if continue_or_quit == 'pip':
                    break
        elif use_req_txt == 'n':
            break
        else:
            print("Invalid option. Please choose 'y' or 'n'.")
            continue
    
    result = subprocess.run(["pip", "freeze"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    if result.returncode != 0:
        print("Error getting requirements. Using empty requirements.")
        return []
    
    return result.stdout.decode().split("\n")


def get_python_version():
    return sys.version.split(' ')[0]


# def create_setup_script(wndb_key, hf_key, on_start_cmd):
#     setup_script_content = f'''#!/bin/bash
# # Download Miniconda installer
# # wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh
# # Install Miniconda
# # bash miniconda.sh -b -p $HOME/miniconda
# # Initialize conda
# # . $HOME/miniconda/bin/activate
# # conda init
# # Create environment
# # conda create --name choline python=3.10 -y
# # Activate environment
# # conda activate choline
# # Install vim
# export cholineremote=true
# sudo apt upgrade
# sudo apt install vim -y
# sudo apt install python3.9
# sudo apt install python-is-python3 -y
# sudo apt install python3-pip -y
# # Set Wandb API key without user interaction
# export WANDB_API_KEY={wndb_key}
# pip install huggingface || pip3 install huggingface -y\n
# # Log in to Hugging Face CLI
# echo '{hf_key}' | huggingface-cli login --stdin
# echo 'n' | huggingface-cli whoami
# '''

#     requirements = get_requirements_list()
#     for req in requirements:
        
#         if len(req) <= 1:
#             continue
#         if '@ file:' in req or 'pyobjc' in req:
#             print(f"Skipping {req}")
#             continue

#         setup_script_content += f'pip install {req} || pip3 install {req} -y\n'
#     setup_script_content += f'{on_start_cmd}\n'

#     return setup_script_content

import yaml
from pathlib import Path
import subprocess

def get_git_remote_url():
    try:
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        result = subprocess.run(["git", "config", "--get", "remote.origin.url"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        remote_url = result.stdout.decode().strip()
        if remote_url:
            return remote_url
        else:
            print("No remote URL is set for this Git repository. You need to set one.")
            
            return None
    except subprocess.CalledProcessError:
        print("This directory is not a Git repository. You need to initialize a Git repository and set a remote URL.")
        return None

# def create_setup_script(wndb_key, hf_key, on_start_cmd):
#     creds_file = Path.home() / ".choline" / "creds.yaml"
#     if not creds_file.exists():
#         raise FileNotFoundError("Credentials file not found. Please create ~/.choline/creds.yaml with the necessary Git credentials.")
    
#     with open(creds_file, 'r') as f:
#         creds = yaml.safe_load(f)
    
#     if 'username' not in creds or 'github_token' not in creds:
#         raise ValueError("Credentials file is missing necessary Git credentials. Please add 'username' and 'github_token' to ~/.choline/creds.yaml.")
    
#     git_username = creds['username']
#     github_token = creds['github_token']
    
#     remote_url = get_git_remote_url()
#     if remote_url is None:
#         raise ValueError("Git remote URL is not set. Please initialize a Git repository and set a remote URL.")

#     setup_script_content = f'''#!/bin/bash
# # Ensure Git is installed
# sudo apt update
# sudo apt install git -y

# # Download Miniconda installer
# # wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh
# # Install Miniconda
# # bash miniconda.sh -b -p $HOME/miniconda
# # Initialize conda
# # . $HOME/miniconda/bin/activate
# # conda init
# # Create environment
# # conda create --name choline python=3.10 -y
# # Activate environment
# # conda activate choline
# # Install vim
# export cholineremote=true
# sudo apt upgrade
# sudo apt install vim -y
# sudo apt install python3.9
# sudo apt install python-is-python3 -y
# sudo apt install python3-pip -y
# # Set Wandb API key without user interaction
# export WANDB_API_KEY={wndb_key}
# pip install huggingface || pip3 install huggingface -y
# # Log in to Hugging Face CLI
# echo '{hf_key}' | huggingface-cli login --stdin
# echo 'n' | huggingface-cli whoami

# # Set Git credentials
# git config --global user.name "{git_username}"
# git config --global user.email "{git_username}@users.noreply.github.com"
# git config --global credential.helper store
# sudo apt install git-lfs
# git lfs install --system
# echo "https://{git_username}:{github_token}@github.com" > ~/.git-credentials

# # Clone the repository
# git clone {remote_url} repo
# cd repo
# '''

#     requirements = get_requirements_list()
#     for req in requirements:
#         if len(req) <= 1:
#             continue
#         if '@ file:' in req or 'pyobjc' in req:
#             print(f"Skipping {req}")
#             continue
#         setup_script_content += f'pip install {req} || pip3 install {req} -y\n'
    
#     setup_script_content += "echo '0' > ~/.choline/setup_complete.txt\n" # setup is now complete 

#     # setup_script_content += f'{on_start_cmd}\n'
#     setup_script_content += f'''{on_start_cmd}
#     if [ $? -ne 0 ]; then
#         echo "Setup command failed with exit code $?" > ~/.choline/failed.txt
#     fi
#     ''' # track failures 

#     return setup_script_content

# from pathlib import Path
# import yaml

# def create_setup_script(wndb_key, hf_key, on_start_cmd):
#     creds_file = Path.home() / ".choline" / "creds.yaml"
#     if not creds_file.exists():
#         raise FileNotFoundError("Credentials file not found. Please create ~/.choline/creds.yaml with the necessary Git credentials.")
    
#     with open(creds_file, 'r') as f:
#         creds = yaml.safe_load(f)
    
#     if 'username' not in creds or 'github_token' not in creds:
#         raise ValueError("Credentials file is missing necessary Git credentials. Please add 'username' and 'github_token' to ~/.choline/creds.yaml.")
    
#     git_username = creds['username']
#     github_token = creds['github_token']
    
#     remote_url = get_git_remote_url()
#     if remote_url is None:
#         raise ValueError("Git remote URL is not set. Please initialize a Git repository and set a remote URL.")

#     setup_script_content = f'''#!/bin/bash
# set -euo pipefail

# mkdir -p $HOME/.choline
# export cholineremote=true

# sudo apt update
# sudo apt install -y wget bzip2 git vim git-lfs ca-certificates

# # Miniforge for a clean Python 3.10 with working ctypes
# ARCH=$(uname -m)
# if [ "$ARCH" = "x86_64" ]; then
#   MF_URL="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh"
# else
#   MF_URL="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-aarch64.sh"
# fi
# cd $HOME
# wget "$MF_URL" -O Miniforge.sh
# bash Miniforge.sh -b -p $HOME/miniforge
# . $HOME/miniforge/bin/activate

# conda config --set always_yes yes --set changeps1 no
# conda create -n choline python=3.10
# conda activate choline

# python -c "import _ctypes; print('ctypes ok')"
# python -m pip install -U pip setuptools wheel

# # Keys and tools inside the env
# export WANDB_API_KEY={wndb_key}
# python -m pip install huggingface
# echo '{hf_key}' | huggingface-cli login --stdin
# echo 'n' | huggingface-cli whoami

# # Git configuration
# git config --global user.name "{git_username}"
# git config --global user.email "{git_username}@users.noreply.github.com"
# git config --global credential.helper store
# git lfs install --system
# echo "https://{git_username}:{github_token}@github.com" > ~/.git-credentials

# # Clone the repository
# git clone {remote_url} repo
# cd repo
# '''

#     requirements = get_requirements_list()
#     for req in requirements:
#         if len(req) <= 1:
#             continue
#         if '@ file:' in req or 'pyobjc' in req:
#             print(f"Skipping {req}")
#             continue
#         setup_script_content += f'python -m pip install {req} || true\n'
    
#     setup_script_content += "echo '0' > ~/.choline/setup_complete.txt\n"

#     setup_script_content += f'''{on_start_cmd}
# if [ $? -ne 0 ]; then
#   echo "Setup command failed with exit code $?" > ~/.choline/failed.txt
# fi
# '''

#     return setup_script_content


from pathlib import Path
import yaml

def create_setup_script(on_start_cmd, skip_pip=False, dl_packages=None, **kwargs):
    """
    Generate the setup script that runs on the remote machine.
    Reads git creds from kwargs (yaml fields) first, falls back to ~/.choline/creds.yaml.
    Builds clone URL from repo_name/git_username/git_token if available,
    otherwise falls back to get_git_remote_url().
    """
    creds_file = Path.home() / ".choline" / "creds.yaml"
    creds = {}
    if creds_file.exists():
        with open(creds_file, 'r') as f:
            creds = yaml.safe_load(f) or {}

    # yaml fields override creds
    git_username = kwargs.get('git_username') or creds.get('git_username', creds.get('username', ''))
    git_token = kwargs.get('git_token') or creds.get('git_token', creds.get('github_token', ''))
    if not git_username or not git_token:
        raise ValueError("Missing git_username or git_token. Set in choline.yaml or ~/.choline/creds.yaml.")

    api_keys = creds.get('API_KEYS', {})

    # Build clone URL from repo fields if available, else fall back to local git remote
    repo_name = kwargs.get('repo_name', '')
    if repo_name and git_username and git_token:
        remote_url = f"https://{git_username}:{git_token}@github.com/{git_username}/{repo_name}.git"
    else:
        remote_url = get_git_remote_url()
        if remote_url is None:
            raise ValueError("No repo_name in yaml and no git remote URL set. Set repo_name/git_username/git_token in choline.yaml or initialize a git repo.")

    setup_script_content = f'''#!/bin/bash
set -uo pipefail

mkdir -p $HOME/.choline
export cholineremote=true

sudo apt update
sudo apt install -y git vim git-lfs curl build-essential \\
  zlib1g-dev libssl-dev libbz2-dev libreadline-dev libsqlite3-dev \\
  libffi-dev liblzma-dev uuid-dev tk-dev xz-utils ca-certificates

# pyenv install, no conda, no venv
if [ ! -d "$HOME/.pyenv" ]; then
  curl https://pyenv.run | bash
fi
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

PYVER=3.10.14
if ! pyenv versions --bare | grep -q "^$PYVER$"; then
  CFLAGS="-O2" pyenv install "$PYVER"
fi
pyenv global "$PYVER"
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

ln -sf "$PYENV_ROOT/versions/$PYVER/bin/python" /usr/local/bin/python
ln -sf "$PYENV_ROOT/versions/$PYVER/bin/python" /usr/local/bin/python3

# persist pyenv + claude in .bashrc
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> $HOME/.bashrc
echo 'export PATH="$PYENV_ROOT/bin:$HOME/.local/bin:$PATH"' >> $HOME/.bashrc
echo 'eval "$(pyenv init -)"' >> $HOME/.bashrc

python -c "import sys, _ctypes; print(sys.version); print('ctypes ok')"
python -m pip install -U pip setuptools wheel

# install claude code
curl -fsSL https://claude.ai/install.sh | bash || true
export PATH="$HOME/.local/bin:$PATH"

# install vastai cli (for self-destroy)
python -m pip install -q vastai || true

# Load all runtime config from choline_runtime.json
if [ -f ~/.choline/choline_runtime.json ] && [ -f ~/.choline/parse_runtime.py ]; then
  python ~/.choline/parse_runtime.py > /tmp/choline_runtime_env.sh
  set -a
  source /tmp/choline_runtime_env.sh
  set +a
fi

# git config
git config --global user.name "$GIT_USERNAME"
git config --global user.email "$GIT_USERNAME@users.noreply.github.com"
git config --global credential.helper store
echo "https://$GIT_USERNAME:$GIT_TOKEN@github.com" > "$HOME/.git-credentials"

git lfs install --skip-repo

# clone the repo
git clone --recurse-submodules "$CLONE_URL" repo
cd repo
'''

    # source custom env vars / aliases if present
    setup_script_content += '[ -f ~/.choline/custom_env.sh ] && source ~/.choline/custom_env.sh\n'
    setup_script_content += "echo '[ -f ~/.choline/custom_env.sh ] && source ~/.choline/custom_env.sh' >> ~/.bashrc\n"

    if not skip_pip:
        requirements = get_requirements_list()
        for req in requirements:
            if len(req) <= 1:
                continue
            if '@ file:' in req or 'pyobjc' in req:
                print(f"Skipping {req}")
                continue
            setup_script_content += f'python -m pip install {req} || true\n'

    if dl_packages:
        torch_pkgs = [p for p in dl_packages if p in ("torch", "torchvision", "torchaudio")]
        rest_pkgs = [p for p in dl_packages if p not in ("torch", "torchvision", "torchaudio", "flash-attn")]
        if torch_pkgs:
            setup_script_content += f'python -m pip install -q --no-cache-dir {" ".join(torch_pkgs)} || true\n'
        if rest_pkgs:
            setup_script_content += f'python -m pip install -q --no-cache-dir {" ".join(rest_pkgs)} || true\n'
        if "flash-attn" in dl_packages:
            setup_script_content += 'python -m pip install -q --no-cache-dir --no-build-isolation flash-attn || true\n'

    # huggingface login if key present (reads from env var set by api_keys.env)
    if api_keys.get('HUGGINGFACE_API_KEY'):
        setup_script_content += 'python -m pip install -q huggingface_hub\n'
        setup_script_content += 'python -c "import os; from huggingface_hub import login; login(os.environ[\'HUGGINGFACE_API_KEY\'])"\n'

    # If claude_prompt is set, write the Claude agent script BEFORE the onStart command
    claude_prompt = kwargs.get('claude_prompt', '')
    claude_auth_mode = kwargs.get('claude_auth_mode', 'oauth')  # 'oauth' or 'api_key'
    claude_code_token = api_keys.get('CLAUDE_CODE_OAUTH_TOKEN', kwargs.get('claude_code_token', ''))
    anthropic_api_key = api_keys.get('ANTHROPIC_API_KEY', '')

    # Determine if we have valid auth for either mode
    has_auth = False
    if claude_auth_mode == 'api_key' and anthropic_api_key:
        has_auth = True
    elif claude_auth_mode == 'oauth' and claude_code_token:
        has_auth = True

    if claude_prompt and has_auth:
        escaped_prompt = claude_prompt.replace("'", "'\\''")

        destroy_on_complete = kwargs.get('destroy_on_agent_complete', kwargs.get('auto_destroy', kwargs.get('shutdown_on_complete', False)))
        shutdown_line = ""
        if destroy_on_complete:
            shutdown_line = "'    echo \"Destroying instance...\"' '    vastai destroy instance $CONTAINER_ID --api-key $CONTAINER_API_KEY || true' "

        # max_life: background watchdog that force-kills instance after N minutes
        max_life = kwargs.get('max_life', 0)  # minutes, 0 = disabled

        # Auth block depends on mode
        if claude_auth_mode == 'api_key':
            # Simple: just export the API key, no .claude.json needed
            setup_script_content += """
# ---- Claude Code Agent (API key auth) ----
# ANTHROPIC_API_KEY is set by parse_runtime.py from choline_runtime.json
cd ~/repo
"""
        else:
            # OAuth mode: need token + .claude.json with oauthAccount
            claude_json_str = '{"hasCompletedOnboarding":true}'
            local_claude_json = Path.home() / ".claude.json"
            if local_claude_json.exists():
                import json as _json
                with open(local_claude_json) as _f:
                    _cj = _json.load(_f)
                headless_cfg = {"hasCompletedOnboarding": True}
                if "lastOnboardingVersion" in _cj:
                    headless_cfg["lastOnboardingVersion"] = _cj["lastOnboardingVersion"]
                if "oauthAccount" in _cj:
                    oa = _cj["oauthAccount"]
                    headless_cfg["oauthAccount"] = {
                        "accountUuid": oa.get("accountUuid", ""),
                        "emailAddress": oa.get("emailAddress", ""),
                        "organizationUuid": oa.get("organizationUuid", ""),
                    }
                claude_json_str = _json.dumps(headless_cfg).replace("'", "'\\''")

            setup_script_content += f"""
# ---- Claude Code Agent (OAuth auth) ----
# CLAUDE_CODE_OAUTH_TOKEN is set by parse_runtime.py from choline_runtime.json
mkdir -p ~/.claude
printf '%s' '{claude_json_str}' > ~/.claude.json
cd ~/repo
"""

        # Claude command — model flag from env var, prompt from env var
        # CHOLINE_CLAUDE_PROMPT is set by runtime yaml, falls back to baked-in prompt
        # CHOLINE_CLAUDE_MODEL is set by runtime yaml, empty string = no --model flag
        model_flag_snippet = 'MODEL_FLAG=""; if [ -n "${CHOLINE_CLAUDE_MODEL:-}" ]; then MODEL_FLAG="--model $CHOLINE_CLAUDE_MODEL"; fi'
        claude_cmd = f'{model_flag_snippet}; IS_SANDBOX=1 claude -p "$PROMPT. When you are done, write a file called complete.txt with a summary of what you did." $MODEL_FLAG --dangerously-skip-permissions --bare --output-format stream-json --verbose 2>&1 | tee -a ~/repo/chat_session.jsonl'

        # Build prompt block
        setup_script_content += "\n# Set prompt from runtime yaml env var, fall back to baked-in default\n"
        setup_script_content += 'if [ -n "${CHOLINE_CLAUDE_PROMPT:-}" ]; then\n'
        setup_script_content += '  export PROMPT="$CHOLINE_CLAUDE_PROMPT"\n'
        setup_script_content += "else\n"
        setup_script_content += f"  export PROMPT='{escaped_prompt}'\n"
        setup_script_content += "fi\n\n"

        # Build max-life watchdog block
        if max_life:
            sleep_seconds = int(max_life) * 60
            setup_script_content += f"""# Max-life watchdog — background process that kills instance after {max_life} minutes
cat > ~/max_life_watchdog.sh << 'WATCHDOG_EOF'
#!/bin/bash
sleep {sleep_seconds}
echo "max_life ({max_life}m) reached, force-killing instance..." | tee -a ~/repo/chat_session.txt
cd ~/repo
git add -A
git commit -m "claude-agent: max_life reached ({max_life}m)" || true
git push origin HEAD || true
vastai destroy instance $CONTAINER_ID --api-key $CONTAINER_API_KEY || true
WATCHDOG_EOF
chmod +x ~/max_life_watchdog.sh
nohup bash ~/max_life_watchdog.sh &
"""

        # Build run_claude.sh
        setup_script_content += "# Write the loop runner\n"
        setup_script_content += "printf '%s\\n' '#!/bin/bash' 'set -uo pipefail' '' 'cd ~/repo' "
        setup_script_content += "'export PATH=\"$HOME/.local/bin:$HOME/.pyenv/bin:$PATH\"' "
        setup_script_content += "'eval \"$(pyenv init -)\"' '' 'MAX_ATTEMPTS=10' 'ATTEMPT=0' '' "
        setup_script_content += "'while [ ! -f ~/repo/complete.txt ] && [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do' "
        setup_script_content += "'  ATTEMPT=$((ATTEMPT + 1))' "
        setup_script_content += "'  echo \"=== Claude Code attempt $ATTEMPT / $MAX_ATTEMPTS ===\" | tee -a ~/repo/chat_session.txt' '' "
        setup_script_content += f"'  {claude_cmd}' '' "
        setup_script_content += "'  # Convert JSONL to readable markdown' "
        setup_script_content += "'  python ~/.choline/format_session.py ~/repo/chat_session.jsonl ~/repo/chat_session.md 2>/dev/null || true' '' "
        setup_script_content += "'  # Copy full JSONL session data into repo' "
        setup_script_content += "'  cp -r ~/.claude/projects/ ~/repo/.claude_sessions/ 2>/dev/null || true' '' "
        setup_script_content += "'  if [ -f ~/repo/complete.txt ]; then' "
        setup_script_content += "'    echo \"complete.txt found, pushing results...\" | tee -a ~/repo/chat_session.txt' "
        setup_script_content += "'    cd ~/repo' '    git add -A' "
        setup_script_content += "'    git commit -m \"claude-agent: task complete\" || true' "
        setup_script_content += "'    git push origin HEAD || true' "
        setup_script_content += "'    echo \"Push complete.\" | tee -a ~/repo/chat_session.txt' "
        setup_script_content += shutdown_line
        setup_script_content += "'    break' '  fi' '' "
        setup_script_content += "'  echo \"No complete.txt yet, retrying in 10s...\" | tee -a ~/repo/chat_session.txt' "
        setup_script_content += "'  sleep 10' 'done' '' "
        setup_script_content += "'if [ ! -f ~/repo/complete.txt ]; then' "
        setup_script_content += "'  echo \"Claude agent did not produce complete.txt after $MAX_ATTEMPTS attempts.\" | tee -a ~/repo/chat_session.txt' "
        setup_script_content += "'  cd ~/repo' "
        setup_script_content += "'  cp -r ~/.claude/projects/ ~/repo/.claude_sessions/ 2>/dev/null || true' "
        setup_script_content += "'  git add -A' "
        setup_script_content += "'  git commit -m \"claude-agent: max attempts reached (no complete.txt)\" || true' "
        setup_script_content += "'  git push origin HEAD || true' "
        setup_script_content += shutdown_line
        setup_script_content += "'fi' > ~/run_claude.sh\n"
        setup_script_content += "chmod +x ~/run_claude.sh\n"

    # Now append the onStart command (runs after claude script is written to disk)
    setup_script_content += "echo '0' > ~/.choline/setup_complete.txt\n"
    setup_script_content += f'''{on_start_cmd}
if [ $? -ne 0 ]; then
  echo "Setup command failed with exit code $?" > ~/.choline/failed.txt
fi
'''

    return setup_script_content


# Example call to the function
# setup_script = create_setup_script('your_wandb_key', 'your_hf_key', 'your_start_cmd')
# print(setup_script)


def literal_str(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='')

yaml.add_representer(str, literal_str)

def create_choline_yaml(image_name, direct_copy_locations, start_cmd, gpu_name, disk_space, cpu_ram, ignore_list, num_gpus, skip_pip=False, dl_packages=None, claude_prompt='', shutdown_on_complete=False, repo_name='', repo_private=True, git_username='', git_token='', claude_auth_mode='oauth'):
    choline_yaml = {
        'image': image_name,
        'upload_locations': direct_copy_locations,
        'onStart': start_cmd,
        'local_cuda_version': get_local_cuda_version(),
        'python_version': get_python_version(),
        'conda_version': get_conda_version(),
        'hardware_filters': {'gpu_name': gpu_name, 'disk_space': disk_space, 'cpu_ram': cpu_ram},
        'ignore': ignore_list,
        'num_gpus': num_gpus,
    }
    if claude_prompt:
        choline_yaml['claude_prompt'] = claude_prompt
    if shutdown_on_complete:
        choline_yaml['destroy_on_agent_complete'] = True
    if repo_name:
        choline_yaml['repo_name'] = repo_name
        choline_yaml['repo_private'] = repo_private
    if claude_prompt:
        choline_yaml['claude_auth_mode'] = claude_auth_mode

    # Pull creds from creds.yaml into choline.yaml
    creds_file = Path.home() / ".choline" / "creds.yaml"
    if creds_file.exists():
        with open(creds_file, 'r') as cf:
            creds_data = yaml.safe_load(cf) or {}
        creds_api_keys = creds_data.get('API_KEYS', {})
        if creds_api_keys:
            choline_yaml['API_KEYS'] = dict(creds_api_keys)
        # Backfill git creds from creds.yaml
        if not git_username:
            git_username = creds_data.get('git_username') or creds_data.get('username', '')
        if not git_token:
            git_token = creds_data.get('git_token') or creds_data.get('github_token', '')

    if git_username:
        choline_yaml['git_username'] = git_username
    if git_token:
        choline_yaml['git_token'] = git_token

    choline_yaml_path = Path.cwd() / 'choline.yaml'

    with open(choline_yaml_path, 'w') as f:
        yaml.dump(choline_yaml, f, default_flow_style=False, indent=2)

        f.write("setup_script: |\n")

        setup_script_content = create_setup_script(
            start_cmd,
            skip_pip=skip_pip, dl_packages=dl_packages or [],
            claude_prompt=claude_prompt,
            shutdown_on_complete=shutdown_on_complete,
            repo_name=repo_name,
            git_username=git_username,
            git_token=git_token,
            claude_auth_mode=claude_auth_mode,
        )
        setup_script_content = '  ' + setup_script_content.replace('\n', '\n  ')
        f.write(setup_script_content)
        
def create_upload_dirs():
    # For checkpointed files
    # add_cwd_checkpoint = input("Add entire current working directory to checkpointed files? (y/n): ").strip().lower()
    # checkpoint_locations = []
    # if add_cwd_checkpoint == 'y':
    #     checkpoint_locations.append(os.getcwd())
    # additional_checkpoint_locations = input("Enter additional locations to upload as checkpointed (comma-separated, no spaces): ").split(',')
    # checkpoint_locations.extend(additional_checkpoint_locations)
    
    # For directly copied files
    add_cwd_copy = input("Add entire current working directory to directly copied files? (y/n): ").strip().lower()
    copy_locations = []
    if add_cwd_copy == 'y':
        copy_locations.append(os.getcwd())
    additional_copy_locations_input = input("Enter additional locations to upload as directly copied (comma-separated, no spaces): ")
    if additional_copy_locations_input.strip():
        additional_copy_locations = additional_copy_locations_input.split(',')
        copy_locations.extend(additional_copy_locations)
    
    return 0, copy_locations


def create_run_cmd():
    tr_command = input("Enter the train command after setting up your instance (or 'c' for Claude agent): ")
    if tr_command.strip().lower() == 'c':
        tr_command = 'bash ~/run_claude.sh'
        print(f"Using: {tr_command}")
    return tr_command


def ask_for_gpu_choice():
    gpu_choices = [
        'RTX_3060', 'H100', 'H100 PCIE', 'A100', 'RTX_3080', 'RTX_3090', 'A100 SXM4',
        'RTX_A5000', 'RTX_4090', 'RTX_3070', 'Tesla_V100', 'A401', 'RTX_3090',
        'RTX_A6000'
    ]
    print("Available GPUs:")
    for idx, choice in enumerate(gpu_choices):
        print(f"{idx}. {choice}")
    selected_idx = int(input("Enter the number corresponding to your choice: "))
    return gpu_choices[selected_idx]

def ask_for_image_choice():
    image_choices = [
        'pytorch/pytorch',
        'tensorflow/tensorflow',
        'nvidia/cuda:12.0.0-devel-ubuntu20.04',
        'ubuntu:latest',
        'alpine:latest'
    ]
    print("Available Images:")
    for idx, choice in enumerate(image_choices):
        print(f"{idx}. {choice}")
    selected_idx = int(input("Enter the number corresponding to your choice: "))
    return image_choices[selected_idx]



def ask_for_cpu_ram():
    disk_space = input("Enter the amount of CPU RAM needed (in GB): ")
    return f">{disk_space}"

def ask_for_num_gpus():
    while True:
        try:
            gpus = input("Enter the number of GPU's needed (1-128): ")
            gpus_int = int(gpus)  # Convert the input to an integer
            if 1 <= gpus_int <= 128:
                return f"{gpus_int}"
            else:
                print("Please enter a number between 1 and 128.")
        except ValueError:
            print("Invalid input. Please enter an integer.")


def ask_for_disk_space():
    disk_space = input("Enter the amount of disk space needed (in GB): ")
    return f">{disk_space}"


def ask_for_wandb_api_key():
    wandb_api_key = input("Enter your wandb API key: ")
    return wandb_api_key

import os
import fnmatch

def suggest_files_to_ignore(upload_locations):
    common_ignore_files = [
        '.DS_Store', '__pycache__', '*.pyc', '*.pyo', '*.egg-info/', 'env/', 
        '.ipynb_checkpoints/', '.git/', '*.swp', '*.swo', '.vscode/', '*.bak',
        '*.csv', '*.log', '*.tmp', '*.json', 'node_modules/', '.env', 'venv/',
        '.gitignore', '.dockerignore', '*.gz', '*.md', '*.rst'
    ]
    files_to_ignore = []
    ignore_dict = {}
    ignore_list = []
    pattern_count = {}
    
    for location in upload_locations:
        for root, _, files in os.walk(location):
            for file in files:
                for pattern in common_ignore_files:
                    if fnmatch.fnmatch(file, pattern):
                        full_path = os.path.join(root, file)
                        files_to_ignore.append(full_path)
                        pattern_count[pattern] = pattern_count.get(pattern, 0) + 1
    
    if files_to_ignore:
        print("Suggested files to ignore:")
        counter = 1
        for pattern, count in pattern_count.items():
            print(f"{counter}. {pattern} (all files with {pattern} pattern: {count} file(s))")
            ignore_dict[counter] = pattern
            counter += 1

        print("Individual files:")
        for idx, file in enumerate(files_to_ignore, counter):
            print(f"{idx}. {file}")
            ignore_dict[idx] = file

        selected_indices = input("Enter the numbers corresponding to the files or file types you want to ignore, or type 'all' (comma-separated): ")

        if selected_indices.strip().lower() == 'all':
            ignore_list = list(pattern_count.keys())
            print(f"Added all patterns to the ignore list: {ignore_list}")
        else:
            selected_indices = [int(idx.strip()) for idx in selected_indices.split(',') if idx.strip().isdigit()]
            for idx in selected_indices:
                if idx in ignore_dict:
                    print(f"Added {ignore_dict[idx]} to the ignore list.")
                    ignore_list.append(ignore_dict[idx])
                else:
                    print(f"Invalid index {idx}. Skipping.")
    
    return ignore_list




# def init_command():
#     image = ask_for_image_choice()
#     _, copy_locations = create_upload_dirs()
#     ignore_list = suggest_files_to_ignore(copy_locations)
#     start_cmd = create_run_cmd()
#     gpu_filters = ask_for_gpu_choice()
#     disk_space = ask_for_disk_space()

#     wdb_key = os.getenv("WANDB_API_KEY")
#     if wdb_key is None:
#         wdb_key = input("Enter your Weights & Biases API key: ")
#     else:
#         print("Using Weights & Biases API key from environment variable.")

#     hf_key = os.getenv("HUGGINGFACE_API_KEY")
#     if hf_key is None:
#         hf_key = input("Enter your Hugging Face API key: ")
#     else:
#         print("Using Hugging Face API key from environment variable.")

#     # Determine the shell configuration file based on the user's shell
#     shell = os.environ.get('SHELL', '')
#     if 'zsh' in shell:
#         config_file = '~/.zshrc'
#     else:
#         config_file = '~/.bashrc'

#     # Check if the API keys are already present in the shell configuration file
#     with open(os.path.expanduser(config_file), 'r') as f:
#         config_content = f.read()

#     # Echo the API keys to the shell configuration file if they are not already present
#     if f'export WANDB_API_KEY="{wdb_key}"' not in config_content:
#         with open(os.path.expanduser(config_file), 'a') as f:
#             f.write(f'\nexport WANDB_API_KEY="{wdb_key}"\n')

#     if f'export HUGGINGFACE_API_KEY="{hf_key}"' not in config_content:
#         with open(os.path.expanduser(config_file), 'a') as f:
#             f.write(f'export HUGGINGFACE_API_KEY="{hf_key}"\n')

#     # Source the shell configuration file
#     os.system(f'source {config_file}')

#     cpu_ram = ask_for_cpu_ram()
#     num_gpus = ask_for_num_gpus()

#     create_choline_yaml(
#         image,
#         copy_locations,
#         start_cmd,
#         gpu_filters,
#         disk_space,
#         wndb_key=wdb_key,
#         hf_key=hf_key,
#         cpu_ram=cpu_ram,
#         ignore_list=ignore_list,
#         num_gpus=num_gpus
#     )


# def init_command():
#     ensure_creds_file()
#     image = ask_for_image_choice()
#     _, copy_locations = create_upload_dirs()
#     ignore_list = suggest_files_to_ignore(copy_locations)
#     start_cmd = create_run_cmd()
#     gpu_filters = ask_for_gpu_choice()
#     disk_space = ask_for_disk_space()

#     creds_file = Path.home() / ".choline" / "creds.yaml"
#     if creds_file.exists():
#         with open(creds_file, 'r') as f:
#             creds = yaml.safe_load(f)
#     else:
#         creds = {}

#     if 'WANDB_API_KEY' in creds:
#         wdb_key = creds['WANDB_API_KEY']
#         print("Using Weights & Biases API key from creds.yaml.")
#     else:
#         wdb_key = input("Enter your Weights & Biases API key: ")
#         creds['WANDB_API_KEY'] = wdb_key

#     if 'HUGGINGFACE_API_KEY' in creds:
#         hf_key = creds['HUGGINGFACE_API_KEY']
#         print("Using Hugging Face API key from creds.yaml.")
#     else:
#         hf_key = input("Enter your Hugging Face API key: ")
#         creds['HUGGINGFACE_API_KEY'] = hf_key

#     with open(creds_file, 'w') as f:
#         yaml.dump(creds, f)

#     cpu_ram = ask_for_cpu_ram()
#     num_gpus = ask_for_num_gpus()

#     create_choline_yaml(
#         image,
#         copy_locations,
#         start_cmd,
#         gpu_filters,
#         disk_space,
#         wndb_key=wdb_key,
#         hf_key=hf_key,
#         cpu_ram=cpu_ram,
#         ignore_list=ignore_list,
#         num_gpus=num_gpus
#     )



PROFILES_DIR = Path.home() / ".choline" / "profiles"


def save_choline_profile(name):
    """Save the current choline.yaml as a named profile."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    src = Path.cwd() / 'choline.yaml'
    if not src.exists():
        print("No choline.yaml found to save.")
        return
    dest = PROFILES_DIR / f"{name}.yaml"
    import shutil
    shutil.copy2(src, dest)
    print(f"Profile '{name}' saved to {dest}")


def list_profiles():
    """Return list of saved profile names."""
    if not PROFILES_DIR.exists():
        return []
    return sorted([p.stem for p in PROFILES_DIR.glob("*.yaml")])


def load_profile(name):
    """Load a saved profile into the current directory's choline.yaml."""
    src = PROFILES_DIR / f"{name}.yaml"
    if not src.exists():
        print(f"Profile '{name}' not found.")
        return False
    dest = Path.cwd() / 'choline.yaml'
    import shutil
    shutil.copy2(src, dest)
    print(f"Loaded profile '{name}' into {dest}")
    return True


def init_command(skip_pip=False):
    ensure_creds_file()

    # Offer to load from a saved profile
    profiles = list_profiles()
    if profiles:
        print(f"\nSaved profiles: {', '.join(profiles)}")
        choice = input("Press 'p' to load a profile, or Enter to configure from scratch: ").strip().lower()
        if choice == 'p':
            for i, name in enumerate(profiles, 1):
                print(f"  {i}. {name}")
            sel = input("Select profile number: ").strip()
            try:
                idx = int(sel) - 1
                if 0 <= idx < len(profiles):
                    if load_profile(profiles[idx]):
                        print("Profile loaded. You can now run 'choline launch'.")
                        return
                else:
                    print("Invalid selection, continuing with fresh init.")
            except ValueError:
                print("Invalid input, continuing with fresh init.")

    # Only proceed if ask_create_repo returns repo info
    repo_result = ask_create_repo()
    if not repo_result:
        print("Repository creation unsuccessful.")
        return
    repo_name, git_username, git_token = repo_result

    image = ask_for_image_choice()
    _, copy_locations = create_upload_dirs()
    ignore_list = suggest_files_to_ignore(copy_locations)
    start_cmd = create_run_cmd()
    gpu_filters = ask_for_gpu_choice()
    disk_space = ask_for_disk_space()

    if not skip_pip:
        skip_pip = input("Skip pip requirements? (y/n): ").strip().lower() == 'y'

    DL_PACKAGES = [
        "torch", "torchvision", "torchaudio",
        "transformers", "datasets", "accelerate",
        "deepspeed", "peft", "trl",
        "wandb", "bitsandbytes", "sentencepiece",
        "einops", "flash-attn",
    ]
    print("Deep learning packages:")
    for p in DL_PACKAGES:
        print(f"  - {p}")
    include_dl = input("Add these to your setup? (y/n): ").strip().lower() == 'y'

    # Claude Code agent prompt (optional)
    claude_prompt = ''
    shutdown_on_complete = False
    claude_auth_mode = 'oauth'
    use_claude = input("Run a Claude Code agent on the remote machine? (y/n): ").strip().lower()
    if use_claude == 'y':
        print("Enter the prompt for Claude Code (what task should it perform?):")
        claude_prompt = input("> ").strip()
        auth_choice = input("Auth mode — 'api' for Anthropic API key, 'oauth' for Claude OAuth token (default oauth): ").strip().lower()
        if auth_choice == 'api':
            claude_auth_mode = 'api_key'
        shutdown_on_complete = input("Shutdown instance when complete? (y/n): ").strip().lower() == 'y'

    cpu_ram = ask_for_cpu_ram()
    num_gpus = ask_for_num_gpus()

    create_choline_yaml(
        image,
        copy_locations,
        start_cmd,
        gpu_filters,
        disk_space,
        cpu_ram=cpu_ram,
        ignore_list=ignore_list,
        num_gpus=num_gpus,
        skip_pip=skip_pip,
        dl_packages=DL_PACKAGES if include_dl else [],
        claude_prompt=claude_prompt,
        shutdown_on_complete=shutdown_on_complete,
        claude_auth_mode=claude_auth_mode,
        repo_name=repo_name,
        git_username=git_username,
        git_token=git_token,
    )

    # Offer to save as a profile
    save_profile = input("Save these settings as a profile? (y/n): ").strip().lower()
    if save_profile == 'y':
        profile_name = input("Profile name: ").strip()
        if profile_name:
            save_choline_profile(profile_name)



def reinit_command():
    """Re-run just the large-file ignore scan and add results to .gitignore."""
    large_file_mb = input("Ignore files larger than how many MB? (default 1, press Enter to skip): ").strip()
    large_file_threshold = None
    try:
        large_file_threshold = float(large_file_mb) if large_file_mb else 1.0
    except ValueError:
        print("Invalid input, skipping.")
        return

    threshold_bytes = large_file_threshold * 1024 * 1024
    large_files = []
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in (".git",)]
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                if os.path.getsize(fpath) > threshold_bytes:
                    rel = os.path.relpath(fpath, ".")
                    large_files.append(rel)
            except OSError:
                pass

    if not large_files:
        print(f"No files found over {large_file_threshold}MB.")
        return

    # read existing .gitignore to avoid duplicates
    gitignore_path = ".gitignore"
    existing = set()
    if os.path.exists(gitignore_path):
        with open(gitignore_path) as f:
            existing = {line.strip() for line in f}

    new_files = [f for f in large_files if f not in existing]
    if not new_files:
        print("All large files already in .gitignore.")
        return

    print(f"Found {len(new_files)} new file(s) over {large_file_threshold}MB:")
    for lf in new_files:
        print(f"  {lf}")
    confirm = input("Add to .gitignore? (y/n): ").strip().lower()
    if confirm == 'y':
        with open(gitignore_path, 'a') as f:
            for lf in new_files:
                f.write(lf + "\n")
        print(f"Added {len(new_files)} file(s) to .gitignore.")


def run():
    skip_pip = '--no-pip' in sys.argv
    init_command(skip_pip=skip_pip)


def run_reinit():
    reinit_command()


