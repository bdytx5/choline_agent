#!/bin/bash
set -euo pipefail

mkdir -p $HOME/.choline
export cholineremote=true

sudo apt update
sudo apt install -y git vim git-lfs curl build-essential \
  zlib1g-dev libssl-dev libbz2-dev libreadline-dev libsqlite3-dev \
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

python -c "import sys, _ctypes; print(sys.version); print('ctypes ok')"
python -m pip install -U pip setuptools wheel

# keys and auth
export WANDB_API_KEY="${WANDB_API_KEY}"
python -c "from huggingface_hub import login; login('${HUGGINGFACE_API_KEY}')"

# git config without double dash flags
if [ ! -f "$HOME/.gitconfig" ]; then
  touch "$HOME/.gitconfig"
fi
awk 'BEGIN {print "[user]\n\tname = bdytx5\n\temail = bdytx5@users.noreply.github.com"}' >> "$HOME/.gitconfig"
git lfs install
echo "https://bdytx5:${GIT_TOKEN}@github.com" > "$HOME/.git-credentials"

# clone the repo
git clone https://github.com/bdytx5/choline.git repo
cd repo


echo '0' > ~/.choline/setup_complete.txt

if [ $? -ne 0 ]; then
  echo "Setup command failed with exit code $?" > ~/.choline/failed.txt
fi
