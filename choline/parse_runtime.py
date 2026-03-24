#!/usr/bin/env python
"""
Reads ~/.choline/choline_runtime.json and prints shell export statements.
Called by the setup script on the remote machine BEFORE pip packages are installed,
so this uses only stdlib (json, os). No pyyaml dependency.

Output is sourced as: python parse_runtime.py > /tmp/env.sh && source /tmp/env.sh
"""
import json
import os

RUNTIME_PATH = os.path.expanduser("~/.choline/choline_runtime.json")

# OAuth token stored separately so it never ends up in choline_runtime.json / git
AUTH_PATH = os.path.expanduser("~/.choline/claude_auth.json")
if os.path.exists(AUTH_PATH):
    with open(AUTH_PATH) as f:
        auth = json.load(f)
    for k, v in auth.items():
        print(f'export {k}="{v}"')

if not os.path.exists(RUNTIME_PATH):
    exit(0)

with open(RUNTIME_PATH) as f:
    rt = json.load(f)

# API keys
for k, v in rt.get('API_KEYS', {}).items():
    print(f'export {k}="{v}"')

# Repo config
for k in ('git_username', 'git_token', 'repo_name', 'clone_url'):
    if k in rt:
        print(f'export {k.upper()}="{rt[k]}"')

# Claude prompt
if 'claude_prompt' in rt:
    p = rt['claude_prompt'].replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    print(f'export CHOLINE_CLAUDE_PROMPT="{p}"')

# Claude model
if 'claude_model' in rt:
    print(f'export CHOLINE_CLAUDE_MODEL="{rt["claude_model"]}"')

# Run ID — unique identifier written by the launching machine
if 'run_id' in rt:
    print(f'export CHOLINE_RUN_ID="{rt["run_id"]}"')

# Destroy on agent complete
if rt.get('destroy_on_agent_complete'):
    print('export CHOLINE_DESTROY_ON_COMPLETE="1"')

# Max life in minutes
if rt.get('max_life'):
    print(f'export CHOLINE_MAX_LIFE="{rt["max_life"]}"')
