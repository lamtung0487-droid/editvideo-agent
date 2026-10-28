# Image-to-video và đọc chuyển động cho Claude

Hệ thống MCP cung cấp dữ liệu và thao tác để Claude quan sát → tạo cảnh → nhận ra lỗi cụ thể → tạo phiên bản tinh chỉnh → đưa cảnh đã chọn vào timeline/source. Runtime không xây studio hay tự phán xét thẩm mỹ bằng điểm số.

## Điều khiển ảnh tham chiếu

Đọc `editvideo://schemas` và `editvideo_media_capabilities` trước. Backend local đã cài là **LTX-Video 2B 0.9.8 distilled**, không phải dòng LTX-2 mới hơn. Model/checkpoint/config tiếp tục được pin; không nâng dependency hoặc tải model âm thầm trong lúc dựng.

```json
{
  "provider": "local_ltx",
  "prompt": "A peaceful sunlit forest. The camera drifts very slowly forward; foreground leaves move gently in a breeze. One continuous shot.",
  "reference_image": "F:/images/forest.png",
  "reference_strength": 1.0,
  "reference_fit": "cover",
  "reference_frames": [
    {"path": "F:/images/forest-end.png", "frame_index": 72, "strength": 0.4}
  ],
  "image_cond_noise_scale": 0.025,
  "width": 512,
  "height": 320,
  "frame_count": 73,
  "fps": 24,
  "seed": 2317
}
```

- `reference_image` neo ở frame 0; `reference_frames` thêm tối đa 4 ảnh ở vị trí bất kỳ trong clip. Index không được trùng, phải nằm trong số frame đầu ra. Mỗi ảnh có `strength` trong `(0,1]`.
- `cover` crop giữa giữ tỷ lệ; `contain` giữ toàn ảnh, thêm nền `#101820`; `stretch` có thể méo ảnh. `reference_crop=[left,top,right,bottom]` chuẩn hóa trong ảnh đã sửa EXIF, áp dụng trước fit. Mỗi task lưu ảnh đã chuẩn bị, crop pixel và SHA256; alpha dùng matte cố định, không tự làm ảnh trong suốt thành nền đen.
- Mỗi tham chiếu được copy vào task trước khi worker chạy. Chỉnh file gốc sau submit không đổi kết quả đang chờ.
- Preset `draft`: 384×256/49 frame, `standard`: 512×320/73 frame, `detail`: 768×448/121 frame. FPS mặc định 24; giá trị width/height/frame_count tự khai ưu tiên hơn preset. Tất cả vẫn chạy lịch distilled 8 bước; draft giảm không gian/thời gian, không bỏ tùy tiện các bước denoise.
- Strength cao ở nhiều ảnh giống nhau có thể làm cảnh gần như đứng yên. Hai ảnh khác xa có thể gây chuyển cảnh đột ngột; cần quan sát khoảng giữa, không chỉ đầu/cuối. Đây là hướng dẫn conditioning, không bảo đảm danh tính/bố cục chính xác.
- Prompt tiếng Anh phù hợp model hiện tại; chữ, biểu đồ và chú thích chính xác dựng bằng React/HTML. Crop/strength/noise/seed là điều khiển đã tích hợp; semantic re-identification, depth/pose conditioning và latent video-to-video chưa được công bố là chạy được.

Các tham số conditioning theo hợp đồng [Diffusers LTXConditionPipeline](https://huggingface.co/docs/diffusers/v0.35.1/en/api/pipelines/ltx_video), đối chiếu source 0.35.2 đã cài. [Model card Lightricks](https://huggingface.co/Lightricks/LTX-Video) hướng dẫn nhiều ảnh/video neo và giới hạn ảnh khác nhau. Model này có giấy phép upstream riêng, không thay giấy phép bằng Apache.

## Tinh chỉnh và tốc độ local

`editvideo_refine_footage(task_id,changes)` tạo **task mới** từ một task local đã hoàn thành, giữ seed/prompt/ảnh snapshot nếu không đổi. Task cha và video cũ giữ nguyên. Có lineage SHA video cha, tên tham số đổi và trạng thái giữ seed; Claude có thể so hai phiên bản và attach bản phù hợp. Đây là một lượt diffusion mới, chưa phải sửa trực tiếp latent của video cha.

Hai cache tránh việc tính lại dữ liệu không đổi:

1. **Prompt embeddings**: khóa theo prompt hash, SHA bộ mã hóa/tokenizer/config, precision và phiên bản thuật toán. BF16 lưu lossless qua float32 NumPy; shape, dtype, finite, size và SHA được kiểm trước dùng; phiên bản runtime tham gia khóa để nâng dependency không dùng nhầm cache cũ. Không dùng pickle. Cache giới hạn 128MB; cùng prompt có thể đổi seed/kích thước/ảnh mà không nạp lại T5 4,9GB.
2. **Posterior ảnh tham chiếu**: khóa theo pixel sau EXIF/crop/fit, SHA checkpoint VAE/config và thiết lập tiling/runtime. Lưu tham số phân phối VAE **trước** bước lấy mẫu; generator vẫn lấy noise theo seed/thứ tự của pipeline. Seed/strength/noise/frame index không làm mất cache ảnh không đổi. Nếu toàn bộ ảnh cache hit, encoder VAE được bỏ trước thiết lập offload, giảm weights cần đọc/chuyển và VRAM. Tối đa 128 entry nhỏ. Cache hỏng/khác shape trở thành miss.

Cache không tái sử dụng các lớp attention/denoising gần đúng. [Diffusers caching](https://huggingface.co/docs/diffusers/optimization/cache) nêu tradeoff về interval/threshold và chất lượng; với lịch 8 bước, nút thắt thực tế ở máy này là đọc weights trên HDD. Tối ưu hiện tại giữ toàn bộ bước transformer, dùng CUDA SDPA, BF16, CPU offload và VAE tiling đã kiểm. Không bật TeaCache/torch.compile chỉ để có tên công nghệ, không chép model lớn sang SSD đang ít chỗ trống, không giữ worker ngốn GPU khi user dùng app khác.

Metadata tách prompt/model load, vòng conditioning–denoise–decode, decode sau bước cuối, export/encode và import runtime. `seconds` là phần sau import; `worker_wall_seconds` bao gồm khởi động/import/thoát process, chưa tính queue/GPU lock. Peak allocated là bộ nhớ cấp phát của process Torch, không phải tổng VRAM hệ thống. Thời gian đo trong một cấu hình/cache/ảnh cụ thể, không hứa tốc độ giống nhau trên mọi máy.

## Đọc video vượt việc xem ở tốc độ thường

`editvideo_analyze_motion(path,start,end,region,sampling_fps,width,evidence_frames)` đọc tối đa 15s/240 sample, CPU, không tải model. Nó cung cấp:

- Dense Farneback hai chiều; kiểm consistency forward/backward và biên ảnh để loại các correspondence nghi lỗi.
- Sparse LK + RANSAC affine để ước lượng chuyển động chung. Cần đủ feature và phủ rộng ảnh. Trả matrix previous→current, tỉ lệ inlier và số feature; có thể không ước lượng được.
- Chuyển động còn lại sau trừ affine; raw RGB change và residual sau warp theo dense flow. Chuyển động camera và thay đổi texture/ánh sáng không còn bị gộp thành một con số pixel thô.
- Trace ROI cố định: luma, Laplacian variance, vùng tối/sáng clipping; FFT Hann với tần số, độ phân giải và Nyquist rõ ràng.
- Chọn frame đầu/cuối và các thời điểm sai khác nổi bật, gửi pixel thật + flow/residual heatmap inline. Bản kê đầy đủ phân trang bằng `editvideo_read_motion`; Claude dùng timestamp để crop, thêm mask/cut hay tinh chỉnh cảnh.

Đây là các tín hiệu có thể tính trên từng khoảng thời gian và vùng ảnh; không khẳng định thấy thông tin camera chưa ghi lại. Reliability không phải identity confidence; affine có thể bị chủ thể lớn/parallax đánh lừa; residual gồm đổi sáng, nội suy, biến dạng và lỗi codec. Sharpness proxy không đo thẩm mỹ. ROI cố định trong khung, chưa tự đi theo SAM2 mask. Các cut chỉ là ứng viên pixel, chưa phải hiểu scene về ngữ nghĩa. Sampling dùng CFR grid resample, chưa bảo tồn native VFR PTS.

Ví dụ: `sampling_fps=24,width=384` trên clip 3s xem được mỗi bước native của footage 24fps; đoạn 15s phải giảm fps hoặc chia cửa sổ. FPS thấp có thể alias; cần xem clip liên tục khi đánh giá động tác. Motion đo bằng pixel ở ảnh sample/mỗi interval, không tự chuyển thành vận tốc vật lý.

[OpenCV optical flow](https://docs.opencv.org/4.x/d4/dee/tutorial_optical_flow.html) giải thích Farneback/LK; [estimateAffinePartial2D](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html) là phép ước lượng robust dùng trong hệ thống. Không gọi các kỹ thuật đã có này là phát minh mới.

`editvideo_temporal_lens` tạo split video original/derived để khuếch đại dải tần RGB trong ROI cố định. FFT bandpass theo thời gian, gain 1..10; low<high<Nyquist, ≥16 sample, xử lý block nhỏ, không giữ model/GPU. Có ảnh inline và tỷ lệ channel bị clipping. Đây là biến đổi phân tích pixel, **không phải phase-based motion magnification**, không ổn định camera hay suy ra sinh lý/sự thật vật lý. Chuyển động, noise và ringing tại biên FFT cũng được khuếch đại. Luôn giữ hình original cạnh bản derived. Ý tưởng đọc biến thiên nhỏ có tiền lệ trong [Eulerian Video Magnification, MIT](https://people.csail.mit.edu/mrub/evm/); bản tích hợp này là phép bandpass RGB đơn giản và có giới hạn riêng.

## Vòng thao tác Claude

1. Index video dài; chọn cửa sổ và xem audio/frame/crop theo ý tưởng nội dung.
2. Khi cần tìm chuyển động/đổi màu/nhấp nháy khó thấy, dùng analyze_motion → read_motion. Đối chiếu heatmap với pixel thật và clip phát thường; temporal_lens chỉ là view hỗ trợ.
3. Tạo một shot có hành động/camera/ánh sáng/bố cục rõ; ảnh neo là chuẩn thị giác, không dùng prompt để dựng chữ chính xác.
4. Quan sát đầu–giữa–cuối và thời điểm residual lớn; mô tả lỗi với timestamp/vùng ảnh. Ví dụ lá rời khung quá nhanh → giảm chuyển động hoặc thêm ảnh neo cuối với strength vừa phải.
5. Refine giữ seed để so điều khiển; giữ prompt nếu chỉ đổi conditioning để dùng lại cache. Đổi seed có thể tạo motion mới nhưng không giữ latent video cũ.
6. Attach artifact đã chọn bằng revision mới nhất; patch shot/layer hoặc custom source, snapshot rồi render. Voice/timeline đã khóa được giữ. Chất lượng do nội dung, bố cục, nhịp và quan sát kết quả, không phải số lượng effect/model.

Hệ thống tích hợp các khả năng đã cài và đã kiểm, không cam kết “mọi kỹ thuật thị trường chưa có”. Các hướng mở rộng như semantic embedding retrieval, depth/pose/video conditioning, spatial latent upscaler và tracking danh tính sau occlusion cần model phù hợp, hợp đồng tool và chạy thử thực tế trước khi ghi là sẵn dùng.


## Bằng chứng chạy thực tế

Xem [verification](VERIFICATION.md): năm lượt image-conditioned, 73 frame mỗi clip, seed giữ nguyên qua refinement. Toàn bộ 73 PNG và hai MP4 của replay cache khớp; peak Torch GPU giảm 6.13→3.80 GiB. Phần prompt từ 32.45s xuống khoảng 0.1s khi hit. Worker wall 68.58→106.55s trong cặp posterior miss/hit, do đọc model trên HDD vẫn biến động; không ghi speedup tổng. Hai ảnh neo khác nhau cho cảnh có chuyển động; cùng ảnh neo mạnh làm cảnh gần đứng yên. MCP trả pixel thực cho motion/lens; bản so sánh đã render Remotion kèm editable ZIP.
