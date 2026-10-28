# Installing EditVideo Agent

This guide takes a clean machine to a working MCP server, a passing test suite and a first render. Windows 10/11 is
the tested platform. Linux runs the core in CI; macOS should work for the core but is untested. Vietnamese:
[INSTALL.vi.md](INSTALL.vi.md). What the system is: [docs/SPEC.md](docs/SPEC.md).

## 1. What you need

| Part | Needed for | Disk | Notes |
|---|---|---|---|
| Core (Python 3.11+, Node.js 22+, FFmpeg) | reading media, timelines, Remotion/HyperFrames renders, audits | ~2 GB with the engines' Chromium | no GPU needed |
| `-Vision` extras | SAM 2 masks, depth, LaMa inpainting, subject search | +~2.5 GB | NVIDIA GPU, CUDA 12.4 wheels |
| `-Temporal` extras | ProPainter video inpainting, local LTX footage | several GB | GPU with ≥ 8 GB VRAM; ProPainter is non-commercial |
| `-Voice` extras | offline Vietnamese narration (Piper) and word timing (Whisper small) | ~580 MB | Piper is GPL-3.0, run as a separate process |
| Beat This! (`requirements.music.txt`) | neural beats and downbeats in any metre | ~80 MB checkpoint | falls back to the built-in tracker without it |
| Blender 4.x/5.x | 3D terrain, maps, archive photos in 3D | — | headless; point `EDITVIDEO_BLENDER` at `blender.exe` if it is not found |
| MoGe-2 | archive photographs in 3D (`archive3d`) | ~1.3 GB | manual install (section 5.5) |
| Data directory | projects, caches, renders | grows with your media | put it on a drive with room (`EDITVIDEO_DATA`) |

## 2. Prerequisites

### Windows 10/11

Open PowerShell and install the tools with winget (or the installers from python.org, nodejs.org and ffmpeg.org):

```powershell
winget install -e --id Python.Python.3.11
winget install -e --id OpenJS.NodeJS.LTS
winget install -e --id Gyan.FFmpeg
winget install -e --id Git.Git
```

Close and reopen PowerShell, then check:

```powershell
python --version
node --version
ffmpeg -version
git --version
```

Expect Python 3.11 or newer, Node 22 or newer and FFmpeg 6.1 or newer (the tests pass with 6.1, 7.1 and 8.1). The
banding check of the delivery report needs an FFmpeg built with libvmaf: the gyan.dev builds that winget installs and
Homebrew's have it; Ubuntu's and Debian's packages do not, and the report then lists banding as `unmeasured`.

Keep the clone's path under ~100 characters (for example `C:\src\editvideo-agent`): installed files reach ~155
characters below it, and Windows refuses paths over 260 characters unless long paths are enabled. `setup.ps1` checks
this before it installs anything.

If PowerShell refuses to run scripts, allow local scripts for your user once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Linux (Debian/Ubuntu)

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv ffmpeg git   # Python 3.11 or newer
# Node.js 22 from nodesource or nvm
```

The apt FFmpeg has no libvmaf, so banding is reported as `unmeasured`. To measure it, put a static build with
libvmaf first on `PATH`. Check a build with `ffmpeg -hide_banner -filters | grep libvmaf`.

### macOS (untested)

```bash
brew install python@3.11 node@22 ffmpeg git
```

## 3. Get the code

```bash
git clone https://github.com/lamtung0487-droid/editvideo-agent.git
cd editvideo-agent
```

Put the clone on a drive with a few GB free. If your system drive is small, also set `EDITVIDEO_DATA` (section 6)
before the first run.

## 4. Core install

Windows:

```powershell
./setup.ps1
```

Linux/macOS:

```bash
sh setup.sh
```

The script:
1. creates `.venv` and installs the pinned Python packages (`requirements.lock.txt` on Windows, `requirements.txt`
   with `setup.sh`);
2. runs `npm ci` in `engines/` (Remotion, HyperFrames, React, three.js);
3. downloads Remotion's headless Chrome once (~120 MB, into `engines/node_modules/.remotion/`);
4. writes `.mcp.json` for this clone (from `.mcp.example.json`).

Slow or flaky networks are retried: pip waits 60 s and tries 5 times. You can override this with
`PIP_DEFAULT_TIMEOUT` and `PIP_RETRIES`. Behind a proxy, set `HTTPS_PROXY` before running the script.

## 5. Optional extras

### 5.1 Vision, temporal and voice

```powershell
./setup.ps1 -Vision    # SAM 2 (pinned commit), Depth Anything V2, LaMa, OWLv2/SigLIP on request; CUDA torch 2.6
./setup.ps1 -Temporal  # + ProPainter (non-commercial) and local LTX footage; implies the vision runtime
./setup.ps1 -Voice     # Piper vi_VN voice + Whisper small, for offline Vietnamese narration
```

On Linux, `sh setup.sh --voice` installs the voice extras. The vision and temporal extras on Linux follow the same
requirement files (`requirements.vision.txt`, `requirements.temporal.txt`) and the scripts `scripts/setup_vision.py`
and `scripts/setup_temporal.py`.

Model weights go into the installation's `data/models/`. They are never committed.

### 5.2 Beat This! (music)

Install the packages, then fetch the checkpoint once:

```powershell
.venv\Scripts\python -m pip install --no-deps -r requirements.music.txt
.venv\Scripts\python -c "from editvideo import music; print(music.fetch_beat_model())"
```

`--no-deps` keeps the CUDA torch you already have. Without the vision extras, install `torch` first (CPU is enough).

The checkpoint comes from the authors' host. If that host is down (it answered 500 on 2026-10-28), download
`final0.ckpt` by hand and set `EDITVIDEO_BEAT_CHECKPOINT` to its path. `music_structure` reports `tracker:
"beat_this"` once it is used.

### 5.3 Blender

Install Blender 4.x or 5.x from blender.org (the portable zip is fine) or from the Microsoft Store. The usual install
folders and the Store launcher are found automatically. Otherwise:

```powershell
$env:EDITVIDEO_BLENDER = 'C:\path\to\blender.exe'
```

### 5.4 GPU notes

- One heavy GPU job runs at a time: film renders, Blender, MoGe and local LTX share an admission slot. A job waiting
  longer than 30 s says on stderr who holds the slot.
- The vision wheels are built for CUDA 12.4 (`torch==2.6.0+cu124`). Use a matching NVIDIA driver.

### 5.5 MoGe-2 (archive photos in 3D, manual)

`archive3d` runs MoGe-2 in its own process. It looks for this layout, by default in `models/moge` next to the data
store or under `EDITVIDEO_MOGE`:

```
moge/
  code/moge/...            # the MoGe package (github.com/microsoft/MoGe, MIT)
  code/utils3d_moge/...    # its utils3d dependency (MIT), vendored under this name
  moge-2-vitl-normal/model.pt   # weights from huggingface.co/Ruicheng/moge-2-vitl-normal
```

It needs the vision extras' torch. Read the model card before commercial use.

## 6. Where your data goes

Projects, caches and renders live in `EDITVIDEO_DATA`, which defaults to `./data` inside the clone. To keep them on
another drive, set the variable for the MCP server (in `.mcp.json` under `env`) and in your shell:

```powershell
$env:EDITVIDEO_DATA = '<data drive>/EditVideo-data\store'
```

Installed models stay with the installation (`data/models`) and are found from a store on any drive.

## 7. Connect your AI client

**Claude Code.** Open the folder. `.mcp.json` registers the server, and the skill in
`.claude/skills/editvideo-agent/` is picked up. Approve the server when asked.

**Claude Desktop.** Add the server to `claude_desktop_config.json`. On Windows the file is
`%APPDATA%\Claude\claude_desktop_config.json`. Use your clone's absolute paths:

```json
{
  "mcpServers": {
    "editvideo": {
      "command": "C:\\path\\to\\editvideo-agent\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\editvideo-agent\\run.py"],
      "env": {"PYTHONIOENCODING": "utf-8"}
    }
  }
}
```

**Codex.** Add to `~/.codex/config.toml`; the skill is in `.agents/skills/editvideo-agent/`:

```toml
[mcp_servers.editvideo]
command = 'C:\path\to\editvideo-agent\.venv\Scripts\python.exe'
args = ['C:\path\to\editvideo-agent\run.py']
```

**Small-context hosts.** Add `"EDITVIDEO_TOOLSET": "compact"` to the server's `env`. That exposes 7 entry tools that
route to the rest; see `.mcp.compact.example.json`.

A session starts with `editvideo_bootstrap(task)`, then `editvideo_discover_tools(query, include_schema=true)`.

## 8. Verify the install

1. The server answers:

   ```powershell
   echo '{"tool":"editvideo_list_projects","arguments":{}}' | .venv\Scripts\python run.py --cli
   ```

2. The test suite: about 600 tests in about 15 minutes on CPU. Tests that need a GPU or downloaded models only run
   with `EDITVIDEO_RUN_RUNTIME_TESTS=1`.

   ```powershell
   .venv\Scripts\python -m pip install -r requirements-dev.txt
   .venv\Scripts\python -m pytest -q
   ```

   Media tests need ~2 GB free where pytest keeps its temporary folders. On a full system drive, use
   `--basetemp D:\tmp\pytest`.

3. A first render: a short Vietnamese explainer with diagrams, rendered with Remotion:

   ```powershell
   .venv\Scripts\python scripts\demo.py --render
   ```

   It prints the project id and the path of the MP4.

## 9. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ffmpeg` not found | Reopen the shell after installing; check `ffmpeg -version`; add FFmpeg's `bin` folder to `PATH`. |
| `setup.ps1` stops because the folder's path is too long, or pip/npm fail with `No such file or directory` on a long path | Windows' 260-character limit. Clone into a short path such as `C:\src\editvideo-agent`, or enable long paths once from an administrator PowerShell: `New-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force`, then `git config --global core.longpaths true`. |
| The delivery report lists `"unmeasured": ["banding"]` | This FFmpeg has no libvmaf (Ubuntu's and Debian's packages). Everything else is measured; install a build with libvmaf to measure banding. |
| `npm ci` fails | Node older than 22, or a proxy; check `node --version`; set `HTTPS_PROXY`. |
| A render stalls on "Downloading Chrome Headless Shell" | Setup fetches it once; if that was interrupted, run `node --input-type=module -e "const r = await import('@remotion/renderer'); await r.ensureBrowser()"` in `engines/`. |
| pip `ReadTimeoutError` | A slow mirror; the scripts already retry. Rerun `setup.ps1`, which keeps what was installed. |
| Tests refuse to run for lack of space | Free ~2 GB, or pass `--basetemp` on another drive. |
| `Blender not found` | Set `EDITVIDEO_BLENDER` to `blender.exe`. |
| `MoGe-2 is not installed` | Follow section 5.5, or set `EDITVIDEO_MOGE`. |
| `the GPU slot stayed busy` | Another render or model run holds the slot; the message names it. Wait, or cancel that job. |
| An AI host shows an old tool count | The host kept an old server process; restart the MCP connection. `editvideo_bootstrap` reports the server version. |

## 10. Updating

```bash
git pull
./setup.ps1   # or sh setup.sh: reinstalls changed pins and engines, keeps .mcp.json
```

Read the top of [CHANGELOG.md](CHANGELOG.md) for changes to tools or timeline contracts.
