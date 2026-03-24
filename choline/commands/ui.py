import os
import re
import subprocess
from pathlib import Path

CUSTOM_ENV_FILE = Path.home() / ".choline" / "custom_env.sh"


def get_current_env_vars():
    return dict(os.environ)


def _zsh_run(cmd):
    """Run a command in an interactive zsh so it sources .zshrc."""
    return subprocess.run(
        ["zsh", "-i", "-c", cmd],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

# Prefixes of zsh/conda/nvm internal functions to hide
_FUNC_SKIP_PREFIXES = (
    "__", "_S", "_bash", "_call", "_pylog", "_comp",
    "nvm", "conda", "compdef", "compdump", "bashcompinit",
    "compinit", "compgen", "complete",
)


def get_bash_aliases():
    aliases = {}
    result = _zsh_run("alias")
    raw = result.stdout.decode()
    # strip zsh session restore noise
    raw = re.sub(r'^Restored session:.*\n?', '', raw)
    # zsh alias output: name=value, possibly multiline $'...' values
    # split on lines that begin a new name= entry
    entries = re.split(r'\n(?=[a-zA-Z0-9_]+=)', raw)
    for entry in entries:
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        name, _, val = entry.partition("=")
        name = name.strip()
        # strip outer quotes/ansi-c quoting
        val = val.strip()
        if val.startswith("$'") and val.endswith("'"):
            val = val[2:-1]
        elif val.startswith(("'", '"')) and val.endswith(val[0]):
            val = val[1:-1]
        aliases[name] = val
    return aliases


def get_bash_functions():
    """Returns dict of name -> body from zsh typeset -f, filtering internals."""
    functions = {}
    result = _zsh_run("typeset -f")
    output = result.stdout.decode()
    # Each block starts with: name ()
    blocks = re.split(r'\n(?=[a-zA-Z_][a-zA-Z0-9_]* \(\))', output)
    for block in blocks:
        block = block.strip()
        m = re.match(r'^(\w+) \(\)', block)
        if not m:
            continue
        name = m.group(1)
        if any(name.startswith(p) for p in _FUNC_SKIP_PREFIXES):
            continue
        if "# undefined" in block:
            continue
        functions[name] = block
    return functions


def load_saved_entries():
    """
    Parse custom_env.sh into list of {type, name, value} dicts.
    Functions are stored as:
      # __func__ name
      <body lines>
      # __endfunc__
    """
    entries = []
    if not CUSTOM_ENV_FILE.exists():
        return entries

    lines = CUSTOM_ENV_FILE.read_text().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("export "):
            rest = line[7:]
            name, _, value = rest.partition("=")
            entries.append({"type": "env", "name": name.strip(), "value": value.strip().strip("'\"")})
        elif line.startswith("alias "):
            rest = line[6:]
            name, _, value = rest.partition("=")
            entries.append({"type": "alias", "name": name.strip(), "value": value.strip().strip("'\"")})
        elif line.startswith("# __func__ "):
            name = line[len("# __func__ "):].strip()
            body_lines = []
            i += 1
            while i < len(lines) and lines[i].strip() != "# __endfunc__":
                body_lines.append(lines[i])
                i += 1
            entries.append({"type": "function", "name": name, "value": "\n".join(body_lines)})
        i += 1
    return entries


def _bash_quote(s):
    """Single-quote a value for bash — safe for any content."""
    return "'" + s.replace("'", "'\\''") + "'"


def save_entries(entries):
    CUSTOM_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = ["#!/bin/bash", "# choline custom env - auto-generated", ""]
    for e in entries:
        if e["type"] == "env":
            lines.append(f"export {e['name']}={_bash_quote(e['value'])}")
        elif e["type"] == "alias":
            lines.append(f"alias {e['name']}={_bash_quote(e['value'])}")
        elif e["type"] == "function":
            lines.append(f"# __func__ {e['name']}")
            lines.extend(e["value"].splitlines())
            lines.append("# __endfunc__")
        lines.append("")
    CUSTOM_ENV_FILE.write_text("\n".join(lines) + "\n")


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Choline UI</title>
<style>
  body {{ font-family: monospace; background: #0f0f0f; color: #e0e0e0; margin: 0; padding: 20px; }}
  h1 {{ color: #7ec8e3; margin-bottom: 4px; }}
  h2 {{ color: #a0d8a0; margin-top: 28px; margin-bottom: 8px; }}
  .subtitle {{ color: #888; margin-bottom: 24px; font-size: 12px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 16px; }}
  th {{ background: #1a1a2e; color: #7ec8e3; text-align: left; padding: 6px 10px; font-size: 12px; }}
  td {{ padding: 4px 10px; font-size: 12px; border-bottom: 1px solid #222; vertical-align: top; word-break: break-all; max-width: 500px; }}
  tr:hover td {{ background: #1a1a1a; }}
  .add-btn {{ background: #2a6496; color: white; border: none; padding: 4px 10px; cursor: pointer; font-size: 12px; border-radius: 3px; white-space: nowrap; }}
  .add-btn:hover {{ background: #3a74a6; }}
  .del-btn {{ background: #8b2020; color: white; border: none; padding: 3px 8px; cursor: pointer; font-size: 11px; border-radius: 3px; }}
  .del-btn:hover {{ background: #ab3030; }}
  .saved-section {{ background: #111; border: 1px solid #333; padding: 16px; border-radius: 6px; margin-bottom: 24px; }}
  .add-form {{ display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; align-items: flex-start; }}
  .add-form input, .add-form select, .add-form textarea {{
    background: #1a1a1a; color: #e0e0e0; border: 1px solid #444;
    padding: 5px 8px; font-size: 12px; border-radius: 3px; font-family: monospace;
  }}
  .add-form input[name=name] {{ width: 160px; }}
  .add-form input[name=value] {{ flex: 1; min-width: 200px; }}
  .add-form textarea[name=value] {{ flex: 1; min-width: 300px; height: 80px; resize: vertical; }}
  .badge {{ font-size: 10px; padding: 2px 6px; border-radius: 3px; margin-left: 4px; }}
  .badge-env {{ background: #1a3a5c; color: #7ec8e3; }}
  .badge-alias {{ background: #1a3a1a; color: #a0d8a0; }}
  .badge-function {{ background: #3a1a3a; color: #d8a0d8; }}
  .filter-bar {{ margin-bottom: 8px; }}
  .filter-bar input {{ background: #1a1a1a; color: #e0e0e0; border: 1px solid #444; padding: 5px 8px; font-size: 12px; border-radius: 3px; width: 300px; }}
  .flash {{ background: #1a3a1a; border: 1px solid #2a5a2a; color: #a0d8a0; padding: 8px 14px; border-radius: 4px; margin-bottom: 16px; font-size: 13px; }}
  pre {{ margin: 0; white-space: pre-wrap; font-size: 11px; color: #bbb; }}
  .type-toggle {{ display: flex; gap: 6px; margin-bottom: 8px; }}
  .type-toggle button {{ background: #222; color: #888; border: 1px solid #444; padding: 4px 12px; cursor: pointer; border-radius: 3px; font-size: 12px; }}
  .type-toggle button.active {{ background: #2a6496; color: white; border-color: #2a6496; }}
</style>
</head>
<body>
<h1>choline ui</h1>
<div class="subtitle">manage env vars, aliases &amp; functions transferred to your remote machine</div>

{flash}

<div class="saved-section">
  <h2>saved to ~/.choline/custom_env.sh <span style="font-size:11px;color:#666">(transferred on launch)</span></h2>
  {saved_table}

  <div class="type-toggle">
    <button class="active" onclick="setType('env', this)">export</button>
    <button onclick="setType('alias', this)">alias</button>
    <button onclick="setType('function', this)">function</button>
  </div>
  <form method="post" action="/add" id="addForm">
    <div class="add-form">
      <input type="hidden" name="type" id="typeInput" value="env">
      <input name="name" id="nameInput" placeholder="NAME" required>
      <input name="value" id="valueInput" placeholder="value" required>
      <button type="submit" class="add-btn">+ add</button>
    </div>
  </form>
</div>

<h2>current env vars</h2>
<div class="filter-bar"><input id="envFilter" placeholder="filter..." oninput="filterTable('envTable', this.value)"></div>
<table id="envTable">
  <tr><th>name</th><th>value</th><th></th></tr>
  {env_rows}
</table>

<h2>bash aliases</h2>
<div class="filter-bar"><input id="aliasFilter" placeholder="filter..." oninput="filterTable('aliasTable', this.value)"></div>
<table id="aliasTable">
  <tr><th>name</th><th>value</th><th></th></tr>
  {alias_rows}
</table>

<h2>bash functions</h2>
<div class="filter-bar"><input id="funcFilter" placeholder="filter..." oninput="filterTable('funcTable', this.value)"></div>
<table id="funcTable">
  <tr><th>name</th><th>body</th><th></th></tr>
  {func_rows}
</table>

<script>
function filterTable(tableId, query) {{
  const rows = document.getElementById(tableId).querySelectorAll('tr:not(:first-child)');
  const q = query.toLowerCase();
  rows.forEach(r => {{ r.style.display = r.innerText.toLowerCase().includes(q) ? '' : 'none'; }});
}}

function setType(type, btn) {{
  document.querySelectorAll('.type-toggle button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('typeInput').value = type;
  const valueArea = document.getElementById('valueInput');
  const nameInput = document.getElementById('nameInput');
  const addForm = document.querySelector('.add-form');

  if (type === 'function') {{
    nameInput.placeholder = 'function_name';
    // swap input for textarea
    if (valueArea.tagName === 'INPUT') {{
      const ta = document.createElement('textarea');
      ta.name = 'value';
      ta.id = 'valueInput';
      ta.placeholder = 'my_func () {{\\n  echo hello\\n}}';
      ta.required = true;
      valueArea.replaceWith(ta);
    }}
  }} else {{
    nameInput.placeholder = type === 'alias' ? 'alias_name' : 'VAR_NAME';
    if (valueArea.tagName === 'TEXTAREA') {{
      const inp = document.createElement('input');
      inp.name = 'value';
      inp.id = 'valueInput';
      inp.placeholder = type === 'alias' ? 'command --flags' : 'value';
      inp.required = true;
      valueArea.replaceWith(inp);
    }}
  }}
}}
</script>
</body>
</html>"""


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_saved_table(entries):
    if not entries:
        return '<p style="color:#666;font-size:12px;">nothing saved yet — add something below</p>'
    rows = ""
    for i, e in enumerate(entries):
        badge = f'<span class="badge badge-{e["type"]}">{e["type"]}</span>'
        val_display = f'<pre>{_esc(e["value"][:300])}</pre>' if e["type"] == "function" else _esc(e["value"])
        rows += (
            f'<tr><td>{_esc(e["name"])} {badge}</td>'
            f'<td>{val_display}</td>'
            f'<td><form method="post" action="/delete/{i}" style="margin:0">'
            f'<button class="del-btn">✕</button></form></td></tr>'
        )
    return f'<table><tr><th>name</th><th>value</th><th></th></tr>{rows}</table>'


def _hidden(name, value, use_textarea=False):
    """Hidden form field — use textarea for multiline/special-char values."""
    if use_textarea or any(c in value for c in ('"', "'", '<', '>', '\n', '\\')):
        # textarea content must NOT be _esc'd — browser submits it raw
        # only escape the closing tag to prevent injection
        safe = value.replace("</textarea>", "<\\/textarea>")
        return f'<textarea name="{name}" style="display:none">{safe}</textarea>'
    return f'<input type="hidden" name="{name}" value="{_esc(value)}">'


def build_env_rows(env_vars, saved_names):
    rows = ""
    for k, v in sorted(env_vars.items()):
        label = "✓" if k in saved_names else "save"
        rows += (
            f'<tr><td>{_esc(k)}</td><td>{_esc(v[:200])}</td>'
            f'<td><form method="post" action="/add_quick" style="margin:0">'
            f'<input type="hidden" name="type" value="env">'
            f'<input type="hidden" name="name" value="{_esc(k)}">'
            f'{_hidden("value", v)}'
            f'<button class="add-btn">{label}</button></form></td></tr>'
        )
    return rows


def build_alias_rows(aliases, saved_names):
    rows = ""
    for k, v in sorted(aliases.items()):
        label = "✓" if k in saved_names else "save"
        rows += (
            f'<tr><td>{_esc(k)}</td><td>{_esc(v)}</td>'
            f'<td><form method="post" action="/add_quick" style="margin:0">'
            f'<input type="hidden" name="type" value="alias">'
            f'<input type="hidden" name="name" value="{_esc(k)}">'
            f'{_hidden("value", v)}'
            f'<button class="add-btn">{label}</button></form></td></tr>'
        )
    return rows


def build_func_rows(functions, saved_names):
    rows = ""
    for k, body in sorted(functions.items()):
        label = "✓" if k in saved_names else "save"
        rows += (
            f'<tr><td>{_esc(k)}</td>'
            f'<td><pre>{_esc(body[:400])}</pre></td>'
            f'<td><form method="post" action="/add_quick" style="margin:0">'
            f'<input type="hidden" name="type" value="function">'
            f'<input type="hidden" name="name" value="{_esc(k)}">'
            f'{_hidden("value", body, use_textarea=True)}'
            f'<button class="add-btn">{label}</button></form></td></tr>'
        )
    return rows


def run():
    try:
        from flask import Flask, request, redirect
    except ImportError:
        print("Flask is required for choline ui. Install it with: pip install flask")
        return

    app = Flask(__name__)
    _flash = {"msg": ""}

    def render(flash=""):
        entries = load_saved_entries()
        saved_names = {e["name"] for e in entries}
        flash_html = f'<div class="flash">{_esc(flash)}</div>' if flash else ""
        html = HTML_TEMPLATE.format(
            flash=flash_html,
            saved_table=build_saved_table(entries),
            env_rows=build_env_rows(get_current_env_vars(), saved_names),
            alias_rows=build_alias_rows(get_bash_aliases(), saved_names),
            func_rows=build_func_rows(get_bash_functions(), saved_names),
        )
        return html

    @app.route("/")
    def index():
        msg = _flash["msg"]
        _flash["msg"] = ""
        return render(flash=msg)

    @app.route("/add", methods=["POST"])
    @app.route("/add_quick", methods=["POST"])
    def add():
        entry_type = request.form.get("type", "env")
        name = request.form.get("name", "").strip()
        value = request.form.get("value", "").strip()
        if name:
            entries = load_saved_entries()
            entries = [e for e in entries if e["name"] != name]
            entries.append({"type": entry_type, "name": name, "value": value})
            save_entries(entries)
            _flash["msg"] = f"saved: {entry_type} {name}"
        return redirect("/")

    @app.route("/delete/<int:idx>", methods=["POST"])
    def delete(idx):
        entries = load_saved_entries()
        if 0 <= idx < len(entries):
            removed = entries.pop(idx)
            save_entries(entries)
            _flash["msg"] = f"removed: {removed['name']}"
        return redirect("/")

    import webbrowser
    import threading
    port = 5199
    print(f"choline ui running at http://localhost:{port}")
    threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    app.run(port=port, debug=False)
