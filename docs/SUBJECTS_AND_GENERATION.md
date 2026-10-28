# Đọc, tách, chỉnh chủ thể và sinh footage

Claude thao tác qua MCP, không mở studio. `editvideo_media_capabilities` cho biết backend/model thực có trên máy; `probe_local=true` kiểm tra ComfyUI. Xem `editvideo://schemas` cho toàn bộ tham số.

## Tracking và segmentation chạy local

Đã tích hợp [SAM 2](https://github.com/facebookresearch/sam2), pin commit `2b90b9f5ceec907a1c18123530e92e794ad901a4`, checkpoint SAM2.1 Hiera Tiny. Dùng predictor có bộ nhớ video, box và điểm dương/âm; mỗi frame đều có mask PNG, box chuẩn hoá, diện tích và ảnh overlay để Claude đọc lại. Nhãn chủ thể do Claude cung cấp; không có model phát hiện bằng văn bản hoặc bằng chứng danh tính tự động.

Máy hiện tại đã cài Torch CUDA và hai checkpoint; thử thật trên RTX 3060 12GB. Máy mới chạy `./setup.ps1 -Vision` (tải Torch khoảng 2.5GB và model). Setup cơ bản không buộc tải phần này. Không cần CUDA compiler: tắt extension SAM2 và postprocessing phụ thuộc extension trên Windows. CPU cũng chạy được nhưng chậm. `requirements.vision.txt` tách khỏi dependency cơ bản; model hashes lưu trong `data/models/vision-models.json`.

1. `inspect_window`/`crop_detail`: nhìn footage và chọn chủ thể. Box/points chuẩn hoá **theo toàn bộ frame nguồn**, không lấy toạ độ crop làm toạ độ nguồn.
2. `track_subject(request={path,start,end,fps:30,width:640,prompts:[{object_id:1,label,frame:0,box:[l,t,r,b]}]})`. Đoạn ≤15 giây và ≤450 frame; `frame` tính từ đầu đoạn. Mỗi object cần prompt ở frame 0. Chia video dài thành các đoạn có mốc chồng để quan sát/chỉnh; chưa có stitching tự động.
3. Poll `get_media_task(task_id)`, rồi `read_subject(task_id,object_id,frames=[0,30,59])`: pixel overlay/mask thật và tracks phân trang. Không dùng `visible=true` như confidence: nó chỉ cho biết mask dự đoán không rỗng.
4. `refine_subject(task_id,prompts=[{object_id:1,frame:30,box,points:[[x,y],...],labels:[1,0,...]}])`: prompt mới thay toàn bộ prompt cũ tại object/frame tương ứng, giữ các frame khác, tạo task bất biến mới. Gửi đủ box/click muốn giữ. Có thể thêm object mới với prompt frame 0. Quan sát lại chỗ che khuất, motion blur, cảnh cắt và chủ thể giống nhau.

SAM2 xử lý thay đổi hình dạng/chuyển động tốt hơn tracker dịch chuyển vùng cũ; không bảo đảm re-identification sau mất dấu dài. Không gọi mask là ground truth. `track_region` vẫn hữu ích cho feature tracking nhẹ và keyframe x/y; hai công cụ có hợp đồng khác nhau.

## Chỉnh vùng đã tách

`edit_subject(request={subject_task_id,object_ids:[1],operation,...})` tạo clip local. Giữ audio đoạn nguồn với các thao tác xuất MP4; foreground alpha giữ hình, âm thanh đặt riêng trong timeline.

| Operation | Kết quả và tham số |
|---|---|
| `remove` | Xoá vùng bằng ProPainter temporal, LaMa từng frame, Telea hoặc clean plate. `backend`, `dilation`, `feather`; các tham số temporal bên dưới |
| `foreground` | VP9 WebM có alpha và chuỗi RGBA PNG; đặt làm video layer trên bất kỳ background nào |
| `replace_background` | Giữ chủ thể, thay bằng ảnh/video local `background_path`; video nền lặp và resize theo mask |
| `blur` | Làm mờ vùng mask; `invert=true` làm mờ nền; `blur_radius` |
| `color_grade` | Brightness/saturation riêng vùng; các pixel ngoài vùng được giữ trước encode |
| `spotlight` | Làm tối nền để nhấn chủ thể; `strength` |
| `outline` | Viền chủ thể theo mask; `tint`, `strength` |
| `reframe` | Crop bám tâm chủ thể, output ngang/dọc tuỳ `output_width/output_height`, `zoom`, `follow_smoothing`; giữ tâm cuối khi mask rỗng; lưu crop track |

`invert` đảo mask; `dilation` nới vùng theo pixel ở độ phân giải mask; `feather` làm mềm biên (được scale theo frame nguồn). Mặc định `resolution="source"` decode PNG ở kích thước footage gốc rồi upscale mask, giữ chi tiết ngoài vùng sửa trước encode. `resolution="mask"` là lựa chọn nhanh ở kích thước mask. LaMa giới hạn suy luận theo `inpaint_max_size` (mặc định cạnh dài 1024), kết quả vùng lấp được scale về gốc; không hứa tái tạo chi tiết gốc của vùng đã xoá. Mask/manifest có hashes; mỗi edit kiểm tra nguồn không đổi và mask chưa sửa ngoài session. Có thể sửa mask bằng prompt rồi chạy lại operation.

[LaMa](https://github.com/advimman/lama) dùng [TorchScript checkpoint do IOPaint phân phối](https://github.com/Sanster/IOPaint/blob/main/iopaint/model/lama.py), checksum MD5 upstream và SHA256 local được lưu. Đây là **inpainting theo từng frame**. `temporal_strength` pha kết quả trước được warp theo flow, mặc định 0; không phải model video-inpainting theo thời gian. LaMa có thể bịa texture, rung/flicker hoặc xoá nhầm vùng chủ thể khác khi mask chạm nhau. Clean plate phải khớp vị trí/kích thước edit (source mặc định, hoặc mask khi chọn resolution=mask); chưa có đăng ký camera tự động. Với vùng lớn, inspect và chỉnh mask/plate thay vì tuyên bố đã khôi phục nền thật.

## Inpainting theo thời gian

`backend="propainter"` dùng [ProPainter](https://github.com/sczhou/ProPainter) tại commit `e870e79321c31b733e2031af5aa2fb1fe3ac7eec`: RAFT hai chiều → hoàn thiện optical flow → truyền nền từ nhiều frame → temporal sparse transformer. Wrapper chạy code upstream trong process riêng; không đưa source/model upstream vào gói hệ thống. Cài `./setup.ps1 -Temporal`, hoặc sau runtime CUDA chạy `pip install -r requirements.temporal.txt` và `python scripts/setup_temporal.py --backend propainter`. Giấy phép upstream **S-Lab 1.0, phi thương mại**; bản checkout giữ LICENSE nguyên gốc.

```json
{"subject_task_id":"SESSION","object_ids":[2],"operation":"remove","backend":"propainter","dilation":5,"feather":3,"temporal_max_size":512,"temporal_window":60,"temporal_overlap":12,"temporal_neighbors":6}
```

`temporal_max_size` chỉ giới hạn độ phân giải suy luận. Kết quả vùng lấp ghép về PNG nguồn gốc, các pixel ngoài mask/feather giữ nguyên trước encode. Cửa sổ chồng và pha ở biên giữ RAM/VRAM có giới hạn. Model dùng cả frame trước/sau **trong cùng cảnh**: tự phát hiện hard cut theo thay đổi màu/pixel, `scene_cuts:[30,...]` bổ sung mốc Claude đã quan sát; không truyền hay blend qua cut. Phát hiện cut là heuristic, không nhận biết ngữ nghĩa. Frame cô lập dùng bản sao của chính nó để cấp một cặp cho flow. `temporal_neighbors` phải chẵn; overlap nhỏ hơn nửa cửa sổ. Không dùng `temporal_strength` với ProPainter vì model đã có temporal propagation.

Manifest ghi cut/window, kích thước suy luận, checkpoint hashes và revision. Mẫu thật có 60 frame, working 512×288, output 960×540; xem `outputs/subject-temporal-inpaint.mp4`, `outputs/temporal-comparison.jpg`, `outputs/temporal-verification.json`. Không hứa khôi phục nền thật tại vùng chưa từng xuất hiện hoặc xoá hoàn hảo khi mask chạm chủ thể giữ lại.

## Sinh footage không khoá vào nhà cung cấp

Ba backend dùng chung task → clip đo/probe/decode → attach → edit/render. `local_ltx` chạy model CUDA có cache sẵn; ComfyUI và Runway vẫn là adapter tuỳ chọn đã kiểm giao thức, chưa xác nhận bằng live API. Không yêu cầu người dùng chọn nhà cung cấp trước khi thử tạo video local.

**LTX-Video local:** [Lightricks LTX-Video](https://github.com/Lightricks/LTX-Video), checkpoint 2B 0.9.8 distilled pin revision, Diffusers 0.35.2. Prompt hoặc `reference_image` frame đầu; tám bước với lịch noise distilled, guidance 1, decode timestep .05/noise .025. CPU offload và VAE tiling giảm VRAM. Bộ T5 XXL mặc định là [FP8 checkpoint do maintainer ComfyUI phân phối](https://huggingface.co/comfyanonymous/flux_text_encoders), pin revision/hash, giữ linear weights FP8, đổi sang BF16 theo từng module để tính trên RTX 3060 (embedding/norm BF16); không cần FP8 GEMM phần cứng và không bung toàn encoder thành bản BF16 10GB trong RAM; đây là encoder lượng tử hoá, không phải encoder nguyên FP32. Có lựa chọn `--text-encoder fp32` để tải encoder gốc từ PixArt. Model LTX có [giấy phép open weights riêng](https://huggingface.co/Lightricks/LTX-Video); T5 checkpoint Apache 2.0. Setup lưu provenance/full hash/size/mtime. Inference kiểm size/mtime trước và sau, dùng hash đã xác minh để tránh đọc lại hàng GB trên HDD; không ngầm tải model.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.temporal.txt
.\.venv\Scripts\python.exe scripts/setup_temporal.py --backend ltx
```

```json
{"provider":"local_ltx","prompt":"A calm documentary shot of sunrise in a green forest, leaves gently swaying, smooth slow camera motion, warm natural light.","width":512,"height":320,"fps":24,"duration":3,"frame_count":73,"seed":1729,"timeout":1800}
```

Chỉ truyền provider local_ltx và prompt sẽ dùng 512×320, 24fps, 73 frame; duration thiếu frame_count được làm tròn về số frame hợp lệ gần nhất và ghi số thực vào request. Kích thước bội 32, cạnh dài ≤768, diện tích ≤393216; số frame `8*n+1`, tối đa 161. 73 frame/24fps thực dài khoảng 3.04s, không giả định đúng 3s. Chia phim dài thành shot; upscale không tạo thêm chi tiết nguồn. Backend distilled không có negative prompt/mask/workflow; đặt các ý định trong prompt và tinh chỉnh hậu kỳ. `model` được ghi `ltx-2b-distilled`. Prompt encoder tối đa 256 token, manifest báo nếu bị cắt. GPU lock chung tránh model segmentation/inpainting/generation cạnh tranh với nhau. Task local dùng checkpoint cache, tắt HF network, có timeout/cancel và sống qua việc đóng MCP client. Không có API key/cước provider cho local inference. Trên Windows, đặt EDITVIDEO_MODEL_PREFETCH=1 để thử nạp trước checkpoint sắp dùng qua [PrefetchVirtualMemory](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-prefetchvirtualmemory), theo vùng 64MiB để giảm page fault nhỏ khi đọc HDD. Đây là cache hint, không bảo đảm tăng tốc; mặc định tắt và có thể tắt lại bằng EDITVIDEO_MODEL_PREFETCH=0. Không sao chép model hay sửa thiết lập hệ điều hành.

`scripts/verify_generation.py` gửi yêu cầu qua MCP rồi đóng client, chờ worker và kiểm clip thực; kết quả live chỉ được ghi khi model hoàn tất trong `outputs/local-generation-verification.json`. Theo dõi `media_capabilities` và task result, không suy từ việc model đã cài thành chất lượng output.

**ComfyUI local/server:** cấu hình `EDITVIDEO_COMFY_URL` (mặc định `http://127.0.0.1:8188`), key riêng `EDITVIDEO_COMFY_API_KEY` nếu server yêu cầu. [API server chính thức](https://docs.comfy.org/development/comfyui-server/comms_routes) cho phép discovery node, graph API, queue/history và lấy artifact. `generation_nodes(query="Wan")` hoặc `query="SaveVideo"` trả đúng node/input có trên server. Claude có thể xây hoặc chỉnh graph không dùng UI. Cần checkpoint và graph sinh video chạy được trên server; không đặt tên model/node giả.

`register_generation_workflow(name,graph,bindings,output_node)` lưu graph **API format**, không phải JSON canvas UI. Ví dụ binding:

```json
{"prompt":[{"node":"6","input":"text"}],"seed":[{"node":"3","input":"seed"}]}
```

Thêm binding `negative_prompt,width,height,frames,fps,reference_image,reference_mask` theo input của node thực. Tham số không binding giữ giá trị graph và được báo ở kết quả; duration/fps request không tự đổi graph không có binding tương ứng. `frame_count` ghi số frame chính xác cho model yêu cầu dạng 4n+1, ví dụ 81 frame/16fps; mặc định dùng duration×fps. Chọn node saver thực trả MP4/WebM/MOV. Task giữ snapshot graph và ảnh tham chiếu để thay workflow/file sau đó không đổi task đã gửi. Có upload ảnh đầu cho image-to-video; `reference_mask` upload như ảnh grayscale, graph cần node chuyển IMAGE thành MASK khi cần. Workflow nâng cao điều khiển motion/camera/model qua graph, không có nút studio.

**Runway:** key riêng `EDITVIDEO_RUNWAY_API_KEY`, không dùng key OpenAI hoặc biến khác. Adapter [API chính thức](https://docs.dev.runwayml.com/api/) theo schema [SDK chính thức](https://github.com/runwayml/sdk-python): Gen4.5 text-to-video/image-to-video (2–10 giây), Gen4 Turbo image-to-video (5/10 giây). Prompt ≤1000 UTF-16 units; tỷ lệ được kiểm theo mode. Ảnh local ≤5MB; gửi data URI đến provider, API key không được chuyển sang host tải clip. Chưa xác nhận bằng live API; backend/model/chi phí thuộc dịch vụ được cấu hình.

`generate_footage(request={provider,prompt,workflow?,model?,reference_image?,seed,width,height,duration,fps})` trả task ID ngay. Không tự gọi provider khác khi lỗi. Tác vụ có timeout, cancel, provenance và clip chuẩn hoá fps/audio; kích thước/thời lượng thực được đo, không suy từ request. Clip AI là reconstruction/illustration, không là footage chứng cứ.

`import_media(...,preserve_plan=true,base_revision=REV)` cũng có thể thêm local footage/audio sau khi plan đã khoá: trả `{asset,revision,plan_preserved}`, giữ voice/timeline. Import mặc định vẫn làm plan stale. Không cần tạo lại giọng chỉ để thêm B-roll.

## Ghép vào video kiến thức

Viết prompt cho **một shot có ý định**: nội dung giải thích, chủ thể/hành động, bố cục, camera, ánh sáng, style tham chiếu và mốc vào/ra. Ví dụ: minh hoạ dòng nước đi từ rễ lên lá, camera macro cố định, nền đơn giản, dành bên phải cho nhãn do code vẽ. Dựng chữ/diagram bằng React/HTML để sửa chính xác; sinh footage giúp minh hoạ chuyển động, không thay thế kiểm tra nội dung kiến thức.

`attach_media_result(task_id,project_id,base_revision,output="video")` copy artifact bất biến, lưu provenance và tăng revision **mà giữ narration/timeline/plan hiện có**. Trả asset ID; patch `update_shot` hoặc `upsert_layer`, đọc revision mới. Không tự thay shot. `overlay` là clip kiểm tra mask của subject task, không footage sạch. Engine scaffold mới truyền alpha đến Remotion decoder; Hyperframes dùng alpha video của Chromium. Source cũ được giữ theo hợp đồng v2: bổ sung `transparent={asset.alpha||false}` vào `OffthreadVideo` nếu cần, hoặc export lại có chủ đích.

Task chạy bằng process riêng, lưu SQLite + artifacts; giữ kết quả khi đóng MCP. Windows khởi chạy process ẩn qua WMI/pywin32 để worker không thuộc Job Object bị MCP client dọn khi đóng phiên; không tạo service hay lịch tự động. POSIX dùng process session riêng. Nếu worker bị dừng, task báo interrupted; không xuất partial result. Cancel dừng local tại biên frame/decoder, Runway theo task ID, ComfyUI xoá đúng queue item. Không interrupt toàn server: bật `EDITVIDEO_COMFY_TARGETED_INTERRUPT=1` chỉ sau khi xác nhận server hỗ trợ `prompt_id`; mặc định task đang chạy remote có thể tiếp tục. `get_media_task` khai trạng thái remote khi huỷ.

Thử thực tế: `scripts/verify_subjects.py`, kết quả `outputs/subject-verification.json` và clip composite của hai engine. Test HTTP dùng server/mock để xác nhận request, output, cancel và key isolation; không coi mock output là video do model sinh.


## Image-to-video và temporal reading mở rộng

Xem [guide mới](IMAGE_VIDEO_AND_TEMPORAL_READING.md) cho nhiều ảnh neo, strength/fit/crop/noise, preset, cache prompt/posterior, refine_footage, dense flow/camera/residual/FFT và temporal lens. Các giới hạn model/dependency/licensing phía trên vẫn áp dụng.
