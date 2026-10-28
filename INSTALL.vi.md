# Cài đặt EditVideo Agent

Hướng dẫn này đưa một máy mới cài đến lúc có MCP server chạy được, bộ test qua và một video render đầu tiên.
- Windows 10/11 là nền tảng đã kiểm thử.
- Linux chạy phần lõi trong CI.
- macOS có thể chạy phần lõi nhưng chưa được kiểm thử.

Bản tiếng Anh: [INSTALL.md](INSTALL.md). Đặc tả hệ thống: [docs/SPEC.md](docs/SPEC.md).

## 1. Cần những gì

| Thành phần | Dùng để | Dung lượng | Ghi chú |
|---|---|---|---|
| Lõi (Python 3.11+, Node.js 22+, FFmpeg) | đọc media, timeline, render bằng Remotion/HyperFrames, các phép kiểm tra | khoảng 2 GB, gồm Chromium của engine | không cần GPU |
| Gói `-Vision` | mask SAM 2, độ sâu, xóa vật thể LaMa, tìm đối tượng | thêm khoảng 2,5 GB | GPU NVIDIA, bản CUDA 12.4 |
| Gói `-Temporal` | xóa vật thể trong video bằng ProPainter, tạo footage bằng LTX chạy local | vài GB | GPU từ 8 GB VRAM; ProPainter chỉ dùng phi thương mại |
| Gói `-Voice` | lời dẫn tiếng Việt offline (Piper) và căn thời gian từng từ (Whisper small) | khoảng 580 MB | Piper theo GPL-3.0, chạy như tiến trình riêng |
| Beat This! (`requirements.music.txt`) | dò phách và phách mạnh bằng mạng neural, mọi loại nhịp | checkpoint khoảng 80 MB | thiếu thì hệ thống dùng bộ dò phách có sẵn |
| Blender 4.x/5.x | địa hình 3D, bản đồ, ảnh tư liệu dựng 3D | — | chạy không giao diện; nếu không tự tìm thấy thì đặt `EDITVIDEO_BLENDER` |
| MoGe-2 | ảnh tư liệu dựng 3D (`archive3d`) | khoảng 1,3 GB | cài tay (mục 5.5) |
| Thư mục dữ liệu | dự án, cache, video render | tăng theo lượng media | đặt trên ổ còn nhiều chỗ (`EDITVIDEO_DATA`) |

## 2. Cài công cụ nền

### Windows 10/11

Mở PowerShell rồi cài bằng winget. Cũng có thể dùng bộ cài từ python.org, nodejs.org và ffmpeg.org.

```powershell
winget install -e --id Python.Python.3.11
winget install -e --id OpenJS.NodeJS.LTS
winget install -e --id Gyan.FFmpeg
winget install -e --id Git.Git
```

Đóng PowerShell, mở lại rồi kiểm tra:

```powershell
python --version
node --version
ffmpeg -version
git --version
```

Cần Python 3.11 trở lên, Node 22 trở lên và FFmpeg 6.1 trở lên (bộ test chạy qua với 6.1, 7.1 và 8.1). Phép đo
banding trong báo cáo giao hàng cần FFmpeg có libvmaf. Bản gyan.dev mà winget cài và bản của Homebrew đều có. Gói của
Ubuntu và Debian thì không, nên báo cáo sẽ ghi banding là `unmeasured`.

Giữ đường dẫn thư mục clone dưới khoảng 100 ký tự (ví dụ `C:\src\editvideo-agent`). File cài đặt nằm sâu tới khoảng
155 ký tự bên dưới thư mục đó, mà Windows từ chối đường dẫn dài quá 260 ký tự nếu chưa bật long paths. `setup.ps1`
kiểm tra điều này trước khi cài.

Nếu PowerShell không cho chạy script, cho phép script local một lần cho tài khoản của bạn:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Linux (Debian/Ubuntu)

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv ffmpeg git   # Python 3.11 trở lên
# Node.js 22 cài qua nodesource hoặc nvm
```

FFmpeg cài bằng apt không có libvmaf, nên banding sẽ được ghi là `unmeasured`. Muốn đo banding, đặt một bản build
tĩnh có libvmaf lên đầu `PATH`. Kiểm tra bằng `ffmpeg -hide_banner -filters | grep libvmaf`.

### macOS (chưa kiểm thử)

```bash
brew install python@3.11 node@22 ffmpeg git
```

## 3. Lấy mã nguồn

```bash
git clone https://github.com/lamtung0487-droid/editvideo-agent.git
cd editvideo-agent
```

Đặt bản clone trên ổ còn vài GB trống. Nếu ổ hệ thống nhỏ, đặt luôn `EDITVIDEO_DATA` (mục 6) trước lần chạy đầu tiên.

## 4. Cài phần lõi

Windows:

```powershell
./setup.ps1
```

Linux/macOS:

```bash
sh setup.sh
```

Script sẽ:
1. tạo `.venv` và cài các gói Python đã ghim phiên bản (`requirements.lock.txt` trên Windows, `requirements.txt` khi
   dùng `setup.sh`);
2. chạy `npm ci` trong `engines/` (Remotion, HyperFrames, React, three.js);
3. tải Chrome chạy nền của Remotion một lần (khoảng 120 MB, vào `engines/node_modules/.remotion/`);
4. tạo `.mcp.json` cho bản clone này (từ `.mcp.example.json`).

Khi mạng chậm, pip chờ 60 giây và thử lại 5 lần. Có thể đổi bằng `PIP_DEFAULT_TIMEOUT` và `PIP_RETRIES`. Nếu dùng
proxy, đặt `HTTPS_PROXY` trước khi chạy script.

## 5. Gói tùy chọn

### 5.1 Vision, temporal và voice

```powershell
./setup.ps1 -Vision    # SAM 2 (ghim commit), Depth Anything V2, LaMa, OWLv2/SigLIP khi cần; torch CUDA 2.6
./setup.ps1 -Temporal  # thêm ProPainter (phi thương mại) và LTX chạy local; tự cài luôn phần vision
./setup.ps1 -Voice     # giọng Piper vi_VN và Whisper small, cho lời dẫn tiếng Việt offline
```

Trên Linux, `sh setup.sh --voice` cài gói giọng nói. Gói vision và temporal trên Linux dùng cùng các file requirements
(`requirements.vision.txt`, `requirements.temporal.txt`) và các script `scripts/setup_vision.py`,
`scripts/setup_temporal.py`.

Trọng số model được lưu trong `data/models/` của bản cài và không bao giờ được commit.

### 5.2 Beat This! (nhạc)

Cài các gói, rồi tải checkpoint một lần:

```powershell
.venv\Scripts\python -m pip install --no-deps -r requirements.music.txt
.venv\Scripts\python -c "from editvideo import music; print(music.fetch_beat_model())"
```

`--no-deps` giữ nguyên bản torch CUDA đã có. Nếu chưa cài gói vision, hãy cài `torch` trước (bản CPU là đủ).

Checkpoint được tải từ máy chủ của nhóm tác giả. Máy chủ này báo lỗi 500 ngày 28.10.2026; nếu nó không hoạt động,
hãy tải tay file `final0.ckpt` và đặt `EDITVIDEO_BEAT_CHECKPOINT` trỏ tới file đó. Khi đã dùng được, `music_structure`
trả về `tracker: "beat_this"`.

### 5.3 Blender

Cài Blender 4.x hoặc 5.x từ blender.org (bản zip portable cũng được) hoặc từ Microsoft Store. Hệ thống tự tìm trong
các thư mục cài đặt thông thường và qua launcher của bản Store. Nếu không tìm thấy:

```powershell
$env:EDITVIDEO_BLENDER = 'C:\duong\dan\blender.exe'
```

### 5.4 Lưu ý về GPU

- Mỗi lúc chỉ một việc nặng được dùng GPU: render phim, Blender, MoGe và LTX local dùng chung một suất. Việc nào phải
  chờ quá 30 giây sẽ ghi ra stderr tên việc đang giữ GPU.
- Các gói vision được build cho CUDA 12.4 (`torch==2.6.0+cu124`). Driver NVIDIA phải hỗ trợ phiên bản này.

### 5.5 MoGe-2 (ảnh tư liệu dựng 3D, cài tay)

`archive3d` chạy MoGe-2 trong tiến trình riêng. Nó tìm cấu trúc thư mục sau, mặc định ở `models/moge` cạnh kho dữ
liệu hoặc ở đường dẫn `EDITVIDEO_MOGE`:

```
moge/
  code/moge/...            # gói MoGe (github.com/microsoft/MoGe, MIT)
  code/utils3d_moge/...    # thư viện utils3d đi kèm (MIT), đặt dưới tên này
  moge-2-vitl-normal/model.pt   # trọng số từ huggingface.co/Ruicheng/moge-2-vitl-normal
```

MoGe-2 cần torch của gói vision. Đọc model card trước khi dùng cho mục đích thương mại.

## 6. Dữ liệu được lưu ở đâu

Dự án, cache và video render nằm trong `EDITVIDEO_DATA`, mặc định là `./data` trong bản clone. Để lưu sang ổ khác,
đặt biến này cho MCP server (trong `.mcp.json`, mục `env`) và cho shell:

```powershell
$env:EDITVIDEO_DATA = '<data drive>/EditVideo-data\store'
```

Model đã cài vẫn nằm cùng bản cài (`data/models`); kho dữ liệu đặt ở ổ nào cũng tìm thấy chúng.

## 7. Kết nối với AI

**Claude Code.** Mở thư mục repo. `.mcp.json` đăng ký server, và skill trong `.claude/skills/editvideo-agent/` được
tự nhận. Chấp nhận server khi được hỏi.

**Claude Desktop.** Thêm server vào `claude_desktop_config.json`. Trên Windows, file nằm ở
`%APPDATA%\Claude\claude_desktop_config.json`. Dùng đường dẫn tuyệt đối của bản clone:

```json
{
  "mcpServers": {
    "editvideo": {
      "command": "C:\\duong\\dan\\editvideo-agent\\.venv\\Scripts\\python.exe",
      "args": ["C:\\duong\\dan\\editvideo-agent\\run.py"],
      "env": {"PYTHONIOENCODING": "utf-8"}
    }
  }
}
```

**Codex.** Thêm vào `~/.codex/config.toml`; skill nằm trong `.agents/skills/editvideo-agent/`:

```toml
[mcp_servers.editvideo]
command = 'C:\duong\dan\editvideo-agent\.venv\Scripts\python.exe'
args = ['C:\duong\dan\editvideo-agent\run.py']
```

**AI có ngữ cảnh nhỏ.** Thêm `"EDITVIDEO_TOOLSET": "compact"` vào `env` của server. Khi đó chỉ còn 7 tool đầu vào,
các tool còn lại được gọi qua chúng (xem `.mcp.compact.example.json`).

Mỗi phiên làm việc bắt đầu bằng `editvideo_bootstrap(task)`, sau đó `editvideo_discover_tools(query,
include_schema=true)`.

## 8. Kiểm tra bản cài

1. Server trả lời được:

   ```powershell
   echo '{"tool":"editvideo_list_projects","arguments":{}}' | .venv\Scripts\python run.py --cli
   ```

2. Bộ test: khoảng 600 test, chạy khoảng 15 phút trên CPU. Các test cần GPU hoặc model đã tải chỉ chạy khi đặt
   `EDITVIDEO_RUN_RUNTIME_TESTS=1`.

   ```powershell
   .venv\Scripts\python -m pip install -r requirements-dev.txt
   .venv\Scripts\python -m pytest -q
   ```

   Các test media cần khoảng 2 GB trống ở nơi pytest đặt thư mục tạm. Nếu ổ hệ thống đầy, dùng
   `--basetemp D:\tmp\pytest`.

3. Render đầu tiên, một video giải thích ngắn bằng tiếng Việt có sơ đồ, render bằng Remotion:

   ```powershell
   .venv\Scripts\python scripts\demo.py --render
   ```

   Lệnh in ra mã dự án và đường dẫn file MP4.

## 9. Xử lý sự cố

| Hiện tượng | Nguyên nhân và cách xử lý |
|---|---|
| Không tìm thấy `ffmpeg` | Mở lại shell sau khi cài; chạy `ffmpeg -version`; thêm thư mục `bin` của FFmpeg vào `PATH`. |
| `setup.ps1` dừng vì đường dẫn thư mục quá dài, hoặc pip/npm báo `No such file or directory` với một đường dẫn dài | Giới hạn 260 ký tự của Windows. Clone vào đường dẫn ngắn như `C:\src\editvideo-agent`, hoặc bật long paths một lần trong PowerShell quyền quản trị: `New-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force`, rồi chạy `git config --global core.longpaths true`. |
| Báo cáo giao hàng ghi `"unmeasured": ["banding"]` | FFmpeg đang dùng không có libvmaf (gói của Ubuntu và Debian). Các phép đo khác vẫn chạy; muốn đo banding thì cài một bản có libvmaf. |
| `npm ci` lỗi | Node cũ hơn 22, hoặc do proxy; kiểm tra `node --version`; đặt `HTTPS_PROXY`. |
| Render đứng ở bước "Downloading Chrome Headless Shell" | Script cài đặt đã tải sẵn một lần; nếu lần đó bị ngắt, chạy `node --input-type=module -e "const r = await import('@remotion/renderer'); await r.ensureBrowser()"` trong `engines/`. |
| pip báo `ReadTimeoutError` | Mirror chậm; script đã tự thử lại. Chạy lại `setup.ps1`, các gói đã cài được giữ nguyên. |
| Test từ chối chạy vì thiếu chỗ | Dọn khoảng 2 GB, hoặc dùng `--basetemp` sang ổ khác. |
| `Blender not found` | Đặt `EDITVIDEO_BLENDER` trỏ tới `blender.exe`. |
| `MoGe-2 is not installed` | Làm theo mục 5.5, hoặc đặt `EDITVIDEO_MOGE`. |
| `the GPU slot stayed busy` | Một lượt render hay model khác đang giữ GPU, và thông báo ghi rõ tên việc đó. Chờ, hoặc hủy việc đó. |
| AI hiện số tool cũ | AI còn giữ tiến trình server cũ; khởi động lại kết nối MCP. `editvideo_bootstrap` báo phiên bản server. |

## 10. Cập nhật

```bash
git pull
./setup.ps1   # hoặc sh setup.sh: cài lại các gói đã đổi phiên bản và engine, giữ nguyên .mcp.json
```

Xem đầu file [CHANGELOG.md](CHANGELOG.md) để biết thay đổi về tool hoặc hợp đồng timeline.
