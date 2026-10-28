# Kiểm tra EditVideo Agent — 12/10/2026

## HDR/LUT, depth, 3D và giao diện model — bản hiện tại

- **(Số liệu của bản kiểm định v0.2; số hiện tại: README và `scripts/repo_facts.py`.) 64 MCP tools, 7 entry tools trong compact mode, 69 hiệu ứng, 14 loại layer.** Thư viện hiện có 16 font families/23 faces, 24 bảng màu, 16 style kits; bổ sung 6 LUT nguyên bản và 4 preset cảnh 3D. [Hướng dẫn model](MODEL_INTEGRATION.md) ghi nguồn nghiên cứu Claude/Codex/OpenAI, transport, creative brief và quy trình đọc/sửa theo cửa sổ.
- Compact giữ registry SDK thật, schema/annotations và image/audio blocks. Thử MCP stdio trực tiếp trên dự án: bootstrap, edit context, đọc 3 cặp depth trả 9 ImageContent, đọc HDR scope trả ảnh thật. `outputs/advanced-live-mcp.json`. Definitions 49.208 → 4.964 ký tự, giảm 89,91%; không phải benchmark token, latency, chi phí hoặc chất lượng model.
- **Depth chạy model thật trên CUDA:** Depth Anything V2 Small HF pin revision 5426e4f0f36572d16453bbda7a8389317b1bef99, safetensors SHA 3152477ce0d8d6978d76b995120de97cb5b928701fd0f817769f59e249a16b70. Video 24 frame/512×288/12fps; ảnh 768×448. Có raw float, 16-bit depth, cut-reset affine/flow stabilization, preview và SHA. Focus blur/parallax đã chạy và xem output; relative depth không phải mét, Gaussian blur không phải optical bokeh, parallax 2.5D không khôi phục phần bị che.
- **Màu chạy thật:** float linear zscale, HDR tonemap, LUT display BT.709, HEVC 10-bit BT.2020/PQ. Fixture gốc có 20/100/400/1000 nit, native HDR p99 khoảng 1004 nit sau codec, SDR tonemap p99 khoảng 100 nit. Test exposure +1 kiểm vùng khoảng 2000 nit. Đã sửa scope resize để không clamp float ở 100 nit. Không bịa mastering metadata; peak là giá trị khai báo/fixture, không MaxCLL của cả phim. `outputs/color-live-verification.json` và `color-lut-atlas.json`.
- **3D thật ở cả hai engine:** `outputs/scene3d-remotion.mp4` và `scene3d-hyperframes.mp4`, mỗi bản 90 frame/3s/Full HD/30fps. Native meshes/material/lights/shadows, camera và pose theo frame, projected labels. Hyperframes lint 0 errors/0 warnings. Chuyển TEMP/TMP của riêng subprocess sang F: sau lần render thiếu dung lượng C:, không đổi môi trường hệ điều hành hoặc xóa dữ liệu ngoài tác vụ. Cập nhật camera matrix trước khi chiếu label; bản phim cuối dùng cập nhật này. Hai proof 3D trước đó vẫn giữ nguyên SHA lịch sử.
- **Phim thuyết minh mới hoàn chỉnh:** “Chiều sâu giúp hình ảnh kể chuyện thế nào?”, `outputs/advanced-narrated-video.mp4`. Project a22bf22f-2d12-4c65-b037-f7e757a528fc, final job 917b6d03-5d81-4d1a-8550-2f9969889719. 2360 frame, 78,67s, 1920×1080/30fps/AAC48kHz. Đã full decode -xerror; SHA 24d53dc368dc5043ab001af1ec4006c8f83cdc2af3a41aebb98d79013c646dfc. Metadata thực yuv420p/limited/BT.709. **Đây là phim SDR**; native HDR xử lý ở pipeline media riêng.
- Narration mới 7 đoạn/246 word units, timing từ Edge TTS thực; không chia đều theo số chữ. Voice SHA 696d65f52535975f68a1c5f8f6f26071be94b059380adbb6c54a9d8e8198501f giữ nguyên qua edit/render. Toàn phim đo −16,0 LUFS, true peak −3,78 dBFS, range 1,6 LU. ASR small trên bản xuất trước có lỗi nhận dạng từ; không coi là WER hoặc xác nhận từng chữ. PCM decode mono16k của bản trước và cuối khớp hash, nên evidence ASR được giữ đúng nguồn cũ và đối chiếu qua `advanced-film-audio-equivalence.json`.
- Đã xem ảnh thật từ MP4 ở giữa cả 7 đoạn; sửa nhãn 3D theo projection, thay depth still bằng video đồng bộ, trình bày LUT và HDR proxy đúng miền màu, giữ chữ/caption đọc được. Storyboard là ảnh mẫu theo thời điểm, không chứng minh mọi frame hoặc thẩm mỹ cho mọi thiết bị. Nguồn AI/depth/HDR fixture được ghi rõ trên hình.
- **Regression 61 passed, 2 skipped** trong 63,24s; skip là 2 test runtime Torch tùy chọn. 5 test advanced chạy lại sau tinh chỉnh cuối đều qua. GPU depth vẫn được kiểm thực độc lập. Skill mirrors đã validate; CLI async dispatch và MCP stdio đã chạy thật. Chưa gọi trực tiếp API Claude/OpenAI trả phí hoặc cấu hình remote MCP/tunnel.
- Source system ZIP chứa code, locks, skill references, fonts/licenses và LUT cube; không chứa model weights, caches, keys hoặc dự án người dùng. Video ZIP chứa media, narration, timeline/captions, source và video xuất. Bản kê cuối: `outputs/advanced-upgrade-verification.json`. [Hợp đồng kỹ thuật và giới hạn](COLOR_DEPTH_3D.md).

Các phần dưới là lịch sử kiểm tra; số tool/layer/test trong từng mục là tại thời điểm tương ứng.

## Thư viện typography/color/graphic — 12/10/2026

- **50 MCP tools,69 effects,13 layer kinds.**16 font families/23faces offline,24 role palettes,16 style kits,10 typography roles,12 motion directions,10 executable graphic components,12 procedural SVG patterns và24 original icons. Có5 HSL harmony modes × dark/light, glyph/advance/bounds measurement và variable axes có kiểm range. Nghiên cứu/cách phối trong [DESIGN_LIBRARY](DESIGN_LIBRARY.md); không làm điểm đẹp/cổng duyệt.
- Font pin google/fonts bd8f81ddb5c74d5c8897b36ad88b440266245103,12,578,148bytes. Kiểm SHA/font/license; tất cả23faces có U+1EA0–U+1EF9 và ĐđƠơƯư. Không có font hệ điều hành trong gói;15familyOFL1.1,RobotoSlabApache2.0/copyright. DM Sans ở revision khảo sát thiếu chữ nên không vào registry.
- **Chromium thật:** outputs/design-font-browser-proof.json:23FontFace loaded,16family có glyph advances khác monospace fixture fallback; NotoSans wdth75 hẹp hơn100 trong DOM. Kiểm native loaded status và local asset requests, không chỉ document.fonts.check. Đây không phải chứng minh mọi ngôn ngữ/glyph đều có.
- **Hai MP4 thật60s**: outputs/design-library-remotion.mp4 và design-library-hyperframes.mp4,1920×1080/1800frame/30fps/AAC48kHz. Atlas30pages=16styles+10components+4graphics pages; đầu ra im lặng, mục đích xem thư viện. Decode -xerror qua. Đọc lại từngpage từMP4, so sánh Remotion/Hyperframes, sửa blank-scene title và khoảng trống/inset/height của lower-third để cả detail nằm trong plate. Font/semantic-role/PILmetrics và actualChromiumlayout được phân biệt rõ.
- Source/render evidence: outputs/design-atlas.json,design-verification.json,design-engine-comparison.json. Rendered normal font/type/palette kits; browser riêng kiểm variable width. Mẫu không đo toàn bộ tiêu chuẩn điện ảnh/khả năng đọc trên mọi thiết bị.
- **Atlas69effects**: outputs/effects-remotion.mp4/effects-hyperframes.mp4,14s/420frames/7pages;7new effects được xem ởpage6. Full decode cả hai qua. Font/palette previews là glyph/swatch sheets; style/component/pattern/icon previews lấy từMP4 thực và được read_design_preview trả inline.
- **53 passed,2 skipped** full regression; skips là optional Torch runtime. MCP stdio gọi thật catalog/measure/apply_design/compose_graphic/derive_palette/inline preview/runtime resource. Tests kiểm glyph/licenseSHA/contrast, atomic rollback/revision/voice/source preservation, fitting lower-third, grapheme/escape/determinism và validated axes. pipcheck sạch.
- Source system ZIP có open font assets/licenses; outputs/design-library-demo.zip có mẫu/preview và hai sourceZIP thực, chưa chứa model weights/API key. Source tùy chỉnh cũ cần deliberate font-loader/type resolver merge, không bị ghi đè ngầm. Simple FFmpeg renderer không thực thi DOM/font widgets. Source paths/hashes trong JSON là máy hiện tại; ZIP chứa preview/source để chuyển máy.

Các mục dưới là lịch sử các đợt trước; con số atlas/tool ở đó mô tả thời điểm thử, atlas hiện tại là69.

## Dựng chuyên nghiệp TikTok/YouTube — 12/10/2026

Đã nghiên cứu và chuyển thành [professional playbook](PROFESSIONAL_VIDEO_PLAYBOOK.md): ma trận story/promise/payoff, footage, continuity, composition, typography/caption, motion, màu, dialogue/music/SFX, cấu trúc/chapter và adaptation. Nguồn chính thức TikTok/YouTube/Adobe/Blackmagic/Remotion/FFmpeg có phạm vi rõ; không làm beauty/virality score hay approval gate.

- **44 MCP tools,62 effects,11 layer kinds,16 executable recipes.** Compose theo revision, kiểm source handles, giữ voice/timebase; dùng cùng id thay cả namespace để không để lại role/caption/card cũ. Dry-run là tùy chọn inspection. Runtime templates cung cấp code hiện tại để merge source cũ bằng hash/backup, không ghi đè entry tùy chỉnh ngầm.
- Caption có2000 pages trong một layer; controlled test1001 pages qua. TTS thực được map sang cue và frame, hoặc caller cung cấp ASR word_timings đúng narration. Không chia đều timing theo số chữ. Caption không có page hoạt động ẩn cả background; không hiện đôi với caption mặc định.
- Callout SVG neo theo target_keyframes và giữ label tại vị trí đọc được. Bản mẫu dùng SAM2 session đã có, map lại điểm sau viewport/crop/speed. Tỷ lệ/coordinates là canvas, không nhận source bbox như canvas bbox.
- **Hai video mẫu hoàn chỉnh:** outputs/professional-tiktok.mp4 và professional-youtube.mp4,1585 frames/30fps,52.833333s,AAC48kHz. TikTok1080×1920;YouTube1920×1080. Bản ngang là mẫu53s theo bố cục YouTube, chưa phải một benchmark phim dài30 phút. SourceZIP tương ứng gồm code/timeline/media/voice/mix/locks/hash. Source footage2–3s được dùng với rate chậm cho minh họa; footage AI native512×320, không giả là nativeFullHD generation.
- Narration PCM được so với bản TTS gốc trước khi tái sử dụng word timing; file voice giữ SHA trước/sau recipe và render. Hai bản chỉ khác framing/layout, cùng phần narration/mix; kiểm full decode -xerror qua. **Đo toàn bộ MP4**: integrated−16.0LUFS,truepeak−3.53dBFS,range2.1LU. Target master−16LUFS/−1.5dBTP; target không được ghi thay measurement.
- Đã xem source snapshots và MP4 thực ở2.3/10/20/27/38/48.3s. Sửa blank caption background, marker theo chữ, lower-third theo độ dài text, viewport lớn hơn ở dọc và label không đè mặt. Rectangle/spotlight SVG stretch đúng bounds; Hyperframes visual-content được đặt width/height100% để tránh auto SVG aspect làm lệch hình. Native font/antialias có thể khác hai engine; không hứa pixel-bit-identical.
- **Portable widgets chạy thật**: outputs/professional-widgets-remotion.mp4 và professional-widgets-hyperframes.mp4,3s/90frames. Real TTS excerpt, caption active-word và điểm đồ họa chuyển có leader. Sau fix Hyperframes container, đo tâm điểm tại1.5s từ ảnh1280px: lệch hai engine khoảng0.04px. Đây là kỹ thuật portability, không semantic tracking hay chất lượng toàn video. outputs/professional-widgets-verification.json.
- **Atlas đợt dựng chuyên nghiệp đủ62 effects ở cả hai engine**,420frames/14s/1920×1080, seven pages. Xem outputs/effect-atlas.json/effects-remotion.mp4/effects-hyperframes.mp4. Đã xem page5/6 và sửa foreground/background marker/outline để preview đọc được. Full decode -xerror qua; audio là signal fixture.
- Sound reader: actual acoustic onset/quiet interval và LUFS/peak/range, không beat/BPM/semantic detector. Controlled1s/2.5s pulse test khớp<50ms; procedural WAV cùng seed có SHA giống nhau,48kHz/gain bound. Master trước đây đã có2-pass−16LUFS; phần mới cho chỉnh target/truepeak/LRA và per-clip/music duck threshold/ratio/attack/release. J-cut handles được kiểm, L-cut/source audio không tự xóa/double narration.
- Regression cuối: **50passed,2skipped**,51.12s; hai skip là optional Torch runtime không đổi trong đợt này. Sau chỉnh numeric zero/caption effect validation:5 test liên quan qua. MCP stdio gọi thật toolkit,compose/schema/resource,sound generation/audio packet; không chỉ kiểm tên. Pipcheck qua. Source/ZIP integrity được kiểm khi đóng gói.

Bằng chứng: outputs/professional-verification.json (MP4/audio/PCM/probe), professional-demo-projects.json (project/jobs/observations), professional-widgets-verification.json, effect-atlas.json. Các đoạn bên dưới ghi lịch sử trước nâng cấp; atlas file hiện trỏ bản62.

## Image-to-video, cache và đọc video — nâng cấp tiếp theo 12/10/2026

- **Sinh model thật**: task ảnh đầu `8368d415-929a-416b-a0ab-9565f715bb07`; thêm ảnh neo giống nhau `3d76be21-aac3-4a9b-af1c-1d88c0754fb9`; giảm strength `b6376f82-9e95-429a-8598-a39e7f2ad7a6`; replay cache `070bce22-6cc5-430f-a8b5-5f8c9fcdd7dd`; hai ảnh khác nhau `f287193b-2ed6-4a71-90ce-330653dc5b87`. Mỗi clip 512×320,73 frame,24fps,3.041667s,8 bước distilled. Refine được gửi qua MCP rồi đóng client; worker vẫn hoàn thành. Có ảnh prepared/crop/strength/frame index/hash, lineage giữ seed2317, model/source checksums. Xem outputs/image-to-video-*-verification.json.
- Đã xem pixel đầu/giữa/cuối của các phiên bản. Ảnh neo giống nhau strength0.85 gần như đóng băng cảnh; strength0.4 giữ chuyển động rất nhỏ. Hai ảnh đầu/cuối khác nhau cho lá tiền cảnh chuyển động, cây/ánh nắng tiếp tục liên hệ. Cảnh có texture mềm theo model2B và chuyển động chưa được coi là vật lý/danh tính hoàn hảo. Không lấy residual thấp nhất làm phán quyết chất lượng.
- Prompt cache lần miss32.453s,hit0.078–0.141s; bỏ nạp4,893,934,904byte T5 trên hit. Đây là timing phần prompt, không phải thời gian cả clip. Cache cuối có thêm runtime-version identity; khi nâng runtime sẽ miss đúng thiết kế.
- Cache posterior VAE trước sampling: lượt miss có1 miss/1 hit cho hai ảnh giống nhau; replay2 hit/0 miss,encoder omitted. **Tất cả 73 PNG frame,provider MP4 và normalized MP4 giống hệt**. outputs/image-cache-equivalence.json ghi đầy đủ. Peak allocated Torch6,584,967,168→4,078,135,808byte (6.13→3.80 GiB); không phải tổng GPU memory. Worker wall miss68.578s,replay106.547s do import/decoder đọc HDD chậm trong replay; không tuyên bố speedup tổng từ cặp này. Cache vẫn giảm công việc encoder và VRAM. Không bật approximate attention caching hay bỏ bước denoise.
- **Reader chạy MCP thật trên footage thật**: 40 tool,analyze_motion trả7 ảnh inline (6 original+diagnostic),read_motion phân trang,temporal_lens trả3 ảnh và split MP4. outputs/temporal-reader-mcp-verification.json,outputs/temporal-lens-forest.mp4. ROI cố định bên phải; FFT/flow/affine/residual có đơn vị và giới hạn. Full decode -xerror qua.
- Controlled tests: chuyển texture3px/2px → affine trong0.3px,residual căn chỉnh<20%raw; đổi sáng10luma vẫn được đo khoảng8–12; cut đổi độ sáng hoặc hue cùng luma reset correspondence; tín hiệu3Hz/24fps/4s tìm đúng3Hz,frequencyresolution0.25Hz; lens gain3 tăng temporalstd>2.5lần,zero channel clipping trong fixture. Không gọi đây là semantic/aesthetic score.
- **Remotion thật qua MCP**: project d2764ec3-decc-40ee-85b4-2bf14fb6d48a,job586b5c57-5cf3-4f71-b0fa-875455b2be3b. Attach/import giữ voice SHA trước/sau,patch/writecode bằnghash,snapshot0/45/90 rồirender. outputs/image-to-video-comparison.mp4:1920×1080,91frames/30fps,3.033333s; source footage vẫn512×320/24fps. Comparison im lặng,sourceZIP outputs/image-to-video-comparison.zip. Đã xem MP4 frame0/1.5/3s: tiêu đề,hai panel và ảnh neo rõ,không chồng text. Full decode qua. outputs/image-director-demo.json và image-comparison-observation.json lưu kết quả.
- Full regression **46 passed, 2 skipped** trong 50.69s (hai test optional Torch). Optional runtime tests chạy riêng: T5BF16/FP8 và posterior cache giữ RNG sampling đều qua. MCP tests gọi thật analyze/read/lens và nhận pixel,không chỉ kiểm tên tool. pipcheck/compileall qua. Không có live remote API mới.

Bản kiểm tra cơ bản phía dưới là lịch sử đợt trước, không phủ định khả năng image-to-video đã có bằng chứng ở đây. [Hợp đồng và nghiên cứu kỹ thuật](IMAGE_VIDEO_AND_TEMPORAL_READING.md).

## Video hoàn chỉnh đã render — 12/10/2026

Project 2824c0e3-88de-4cf8-8b6b-266bd5d283f6, final job bc6b6d4a-5904-473c-81c2-c88cdadf8def. scripts/demo_temporal.py author qua MCP: attach inpaint/footage thật giữ plan, thêm nhạc, sửa cue theo timing TTS, viết React bằng hash, snapshot rồi render Remotion.

- outputs/ai-video-complete.mp4: **1920×1080, 1585 frame, 30fps, 52.833333s**, AAC 48kHz/52.824s. Full decode -xerror qua. SHA256 3d821e4669a1bd9d031e1ebc01af13a3f5d7afd219ae352eb9222616b50112c9.
- Voice tiếng Việt HoaiMy giữ nguyên trước/sau attach/patch/render: SHA256 4a78dc8cbc417c2fc71c6a569ad0cf82e2020d547aefeaadc871d3481e80bf59. 20 cue từ TTS word boundaries, nhạc synth gốc có ducking. Loudness MP4 -16.01 LUFS, true peak -3.52dBTP. Audio chênh duration video 9ms.
- outputs/ai-video-complete.zip chứa MP4, timeline/SRT/words, voice/mix WAV, source React, video/music assets và locks/hashes. ZIP integrity qua; voice trong ZIP khớp plan. Public source có cả asset nhạc, không mất khi export custom code.
- Xem source snapshots và frame từ MP4 cuối ở 1.5/8.5/16/24/32.2/38.5/45.7/52.4s. Sửa khoảng cách tiêu đề mở đầu và không tách cụm dễ đọc. Footage gốc 768×448 được scale/crop trong bố cục Full HD; không gọi đó là footage sinh native Full HD.
- ASR small local CPU int8 đọc track audio của **MP4 cuối**, outputs/complete-video-asr.json. Nhận được sáu đoạn và ý chính; vẫn nhầm vài âm Việt như che khuất/liền mạch/ảnh tĩnh. Không coi transcript ASR là bản xác minh từng từ, không ghi accuracy/WER hoặc thay subtitle TTS bằng suy đoán ASR.

outputs/complete-video-verification.json ghi kỹ thuật/hash/audio; outputs/complete-video-observation.json ghi frame thực. Contact sheet nhận đúng tỷ lệ ngang/dọc, tăng diện tích hình cho AI đọc thay vì đặt video ngang trong ô dọc lớn. outputs/ai-video-storyboard.jpg dùng bản này. Test regression liên quan sau sửa cuối: 23 passed; hai test MCP/perception sau đổi contact sheet và director guide qua. Dependency pip check và skill quick_validate qua; hai skill Claude/Codex cùng nội dung.

## Footage local sinh thật — 12/10/2026

Task 5347e3e0-2388-4394-854c-5672e8731755 được gửi qua MCP stdio rồi đóng client; worker vẫn hoàn tất LTX-Video 2B 0.9.8 distilled trên RTX 3060. Tám bước đúng lịch noise, prompt 88 token không bị cắt, seed 1729. Clip rừng lúc bình minh: 768×448, 121 frame/24fps, 5.041667 giây. FFmpeg full decode với -xerror qua. File: outputs/ai-generated-forest.mp4, outputs/local-generation-verification.json. SHA256 71cd1937649ac0ca30f56b55aff87f5c29029196d4e7554371f5374ab437d539.

Đã xem frame đầu/giữa/cuối: cây, ánh nắng và bố cục giữ liên hệ; đây là minh hoạ AI, texture mềm, không phải tư liệu quay thật. Đây là bằng chứng text-to-video; image-to-video đã được live-test trong đợt nâng cấp tiếp theo bên dưới. ComfyUI/Runway vẫn chỉ kiểm giao thức.

Peak allocated riêng process CUDA 4,220,250,624 byte, không tính ứng dụng khác/driver. Lần chạy này mất 1176.3s, trong đó cache hint LTX 720.38s trên HDD. Không coi đây là tốc độ điển hình hoặc bảo đảm VRAM trên máy khác. Prefetch là tuỳ chọn mặc định tắt; bản cuối dùng mapping read-only và chỉ chọn vùng tensor cần dùng. SSD phù hợp hơn để nạp các checkpoint lớn.

Bộ kiểm tra: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q: 39 passed, 1 skipped, 143.79s. Test runtime encoder được chạy riêng và qua. Việc tắt autoload bỏ plugin Hydra không dùng trong test; không bỏ test dự án.

## Temporal inpainting chạy thật — 12/10/2026

ProPainter pin commit e870e79321c31b733e2031af5aa2fb1fe3ac7eec chạy CUDA trên RTX 3060 với hai chủ thể đang nhảy/che khuất. Task fe6af504-2de7-49f3-a5e8-d2e38d153f1c xoá chủ thể thứ hai, giữ đủ 60 frame/30fps; working 512×288, output 960×540. Full decode qua; pixel ngoài vùng mask/feather giữ nguyên trước encode. File thật: outputs/subject-temporal-inpaint.mp4, outputs/temporal-comparison.jpg và outputs/temporal-verification.json.

Task dc53df38-62c8-4640-a9f6-f2d5d3ffee63 chạy ba cửa sổ [0,24], [18,42], [36,60]; giữ 60 frame, outside-feather error 0 và giải mã toàn bộ qua. outputs/temporal-multiwindow-verification.json. Cửa sổ/biên cảnh và frame cô lập được kiểm trong test; hard-cut detection vẫn là heuristic.

Same-pixel residual RGB trong phần lõi vùng lấp, loại chủ thể giữ lại: LaMa 7.20, ProPainter một cửa sổ 2.42; ba cửa sổ 2.72. Đây là số đo hạn chế trên camera gần tĩnh, không là điểm thẩm mỹ hoặc bảo đảm mọi cảnh. Giấy phép ProPainter S-Lab 1.0 phi thương mại.

Encoder T5 có FP8 linear storage và BF16 computation được kiểm số học trên runtime Torch/Transformers đã cài: đầu ra khớp chính xác bản dùng cùng trọng số lượng tử hoá đổi toàn bộ sang BF16, giảm dung lượng tham số. EDITVIDEO_RUN_RUNTIME_TESTS=1 python -m pytest -q tests/test_temporal_runtime.py: 1 passed. Không so với encoder FP32 gốc.

## Nâng cấp perception, thẩm mỹ và dựng đa tầng

- `python -m pytest -q`: **23 test qua** sau nâng cấp. Kiểm tra thực: candidate cut ở 1s, frame đỏ/xanh trước/sau cut, crop coordinate mapping, tracking vùng có texture dịch chuyển theo clip sinh có ground truth, params/target sai bị chặn và batch lỗi không ghi dữ liệu.
- Test âm thanh dùng FFT của file mix: tone 1000Hz không xuất hiện trước mốc đặt, xuất hiện trong đoạn đã đặt; chạy cả duck/no-duck và playback rate 1.5. Phát hiện và sửa lỗi FFmpeg timestamp khi phối atempo/delay bằng sample-based delay/trim 48kHz.
- MCP client stdio thật nhận catalog structured output, danh sách 25 tools, director prompt và inline crop pixels. Không xác nhận phiên Claude của người dùng đã kết nối; cấu hình project/skill đã sẵn.
- Portable runtime có đủ 50 ID trùng catalog; animation random-seek xác định với seed; keyframe nội suy đúng giá trị giữa hai mốc. Catalog có preview từ atlas thực và target text/data được validate.
- Đợt trước `scripts/effect_atlas.py` render **đủ 50 effect ở cả Remotion và Hyperframes**, Full HD ngang, 300 frame/10s, audio 48kHz. Manifest/hash/frame paths: `outputs/effect-atlas.json`. Atlas phục vụ thấy kỹ thuật; signal âm thanh là fixture, không thuyết minh nội dung.
- `scripts/verify_advanced.py`: hai engine render 120 frame/4s, speed 1.5, nonzero source start, dissolve giữ frame cuối, bảy loại lớp đồ họa, delayed audio, snapshot ngược thứ tự frame 63/9. Corner pixel xác nhận đỏ → xanh → blend tím → xanh; full decode qua. Entry source hash giữ nguyên dù patch sau export. `outputs/advanced-verification.json` chứa job/hash/pixel evidence.
- Whisper small CPU int8 chạy local trên voice tiếng Việt 20.832s: 69 word units, 10 cue ngắn, transcript/SRT và segment gốc; lần lặp dùng cache không tải model. `outputs/asr-verification.json`. Base sai nhiều từ chuyên môn; small + vocabulary hint tốt hơn nhưng vẫn có sai từ, không công bố accuracy/WER hay gọi là forced alignment.
- Skill Codex qua quick_validate, bản Claude cùng nội dung; Python dependencies `pip check` qua, lock cập nhật.

Các phần bên dưới ghi bằng chứng của bản nền trước nâng cấp; số test và giới hạn mới áp dụng theo phần này và phần “Giới hạn đã biết”.

## MCP, edits và nguồn

- `python -m pytest -q`: **15 test qua**. Một cảnh báo deprecation TestClient/httpx từ dependency; không test lỗi.
- Client MCP SDK thực chạy `run.py` qua stdio: initialize, list tools, create/read project, resource schema, nhận image content thực, revision conflict không sửa dữ liệu.
- Edit batch sai ở thao tác sau không ghi thao tác trước. Split shot, overlay và history qua kiểm tra. Ghi source dùng hash, từ chối stale hash và path thoát thư mục.
- Job duplicate bị chặn; khi đang hủy giữ lock tới khi worker dừng. Job của process đã chết được phép resubmit; khởi động client mới không hủy jobs của client khác.
- `.agents/skills/editvideo-agent` qua `skill-creator/scripts/quick_validate.py`; Claude skill là bản tương ứng cùng nội dung.
- `pip check`: không broken requirements. Python lock và npm lock được lưu.

## Hai engine thực

`scripts/smoke_code_engines.py` tạo source thật, render, giải mã và lấy ảnh kết quả.

| Engine | Job đã qua | Output |
|---|---|---|
| Remotion 4.0.534 | `628282ba-4987-4964-8718-f8af382e5d29` | 640×360, 36 frame, 30fps, 1.2s, audio 48kHz |
| Hyperframes 0.8.147 | `305e83f3-ea35-4c90-9444-9b0ef40e31d9` | 640×360, 36 frame, 30fps, 1.2s, audio 48kHz |

Hai engine đều render overlay và phụ đề Unicode. Cả hai cũng snapshot được code tại frame 6 và 24 trước khi xuất video.

`scripts/test_video_sources.py`: nguồn thử đỏ ở đoạn đầu, xanh ở đoạn sau. Timeline có hai shot với nonzero source offsets. Render thật và lấy frame ở 0.2/0.8s cho thấy đỏ/xanh đúng thứ tự:

- Remotion job `8846d30b-8812-4e50-80eb-35ea436692fe`: mean RGB `[253,1,0]` và `[0,0,254]`.
- Hyperframes job `94f79e2d-0d66-4af7-9fee-824c5756b46c`: mean RGB `[231,0,3]` và `[2,0,244]`.

Điểm này kiểm tra clip seek/cut thực tế, không chỉ JSON timeline. Hyperframes video được đặt đúng hợp đồng: ID riêng và không lồng timed video trong timed plain wrapper.

## Vòng biên tập thật qua MCP

`scripts/demo_agent.py` và `scripts/refine_demo.py` dùng MCP client để:

1. Tạo project và import local illustrations/music/narration.
2. Giữ thuyết minh Việt thật từ Edge HoaiMy, nhận SRT từ word timing đã có.
3. Patch timeline, export Remotion, read/write TSX bằng hash.
4. Tạo sơ đồ động bằng SVG: ánh sáng + nước + CO₂ → chất hữu cơ + O₂.
5. Snapshot/quan sát ảnh, sửa mũi tên tránh đè nhãn, ngắt caption theo cụm nghĩa (giữ “chất hữu cơ”, “chăm sóc”).
6. Render lại Full HD và observe MP4 cuối qua MCP.

Project: `8f2e867c-9234-46be-a3a1-10bbe4955f9f`. Final job: `476de697-3f2f-436e-9207-ac2edd515008`.

- Video: **1080×1920, 625 frame, 30fps, 20.833333s, audio AAC 48kHz**.
- FFmpeg full decode `-xerror`: qua.
- SHA256: `253d77f24ca3b23b3a070e4159e132e8630ebdb939d2e28dc279f38cc47040c0`.
- Output dễ mở: `outputs/agent-quang-hop.mp4`, `outputs/agent-quang-hop.zip`, `outputs/agent-storyboard.jpg`.
- Manifest/job: `outputs/agent-demo.json`.
- ZIP có MP4, timeline, SRT, voice/mix WAV, words, source React/assets/package lock và source hashes.

## Giới hạn đã biết

Bổ sung ngày 12/10/2026: `outputs/subject-verification.json` ghi SAM2.1 Tiny chạy CUDA trên RTX 3060, hai chủ thể/60 frame, correction session bất biến, LaMa xoá chủ thể thật, foreground VP9 alpha và crop bám dọc. `subject-composite-remotion.mp4` và `subject-composite-hyperframes.mp4` đã render và full decode; góc nền giữ màu thay thế, vùng chủ thể hiện đúng. Ảnh đầu/giữa/cuối mask được xem trực tiếp; nền inpaint có thể bịa texture, không chứng minh hoàn hảo mọi frame.

Bộ test của bản subject trước nâng cấp temporal: **30 passed trong 35.53s**, `python -m pytest -q`; `pip check` không có dependency hỏng. Output mask edit/alpha giữ độ phân giải nguồn 960×540, 60 frame/2 giây; crop bám 360×640. SAM2 mask inference 640×360. Test bảo vệ snapshot graph/ảnh tham chiếu, mask hashes, revision, narration, single-worker claim và xử lý worker chết. [Ảnh so sánh](../outputs/subject-upgrade-preview.jpg) là frame 0.9s từ các clip thật.

`outputs/media-mcp-verification.json`: submit neural tracking qua MCP stdio → đóng client → worker vẫn hoàn tất → nối lại đọc 6 ảnh inline (overlay/mask) và schema mới. Windows dùng worker ẩn ngoài Job Object của client. 36 tools. `scripts/verify_media_mcp.py` tái hiện được.

Test HTTP ComfyUI qua local server và Runway qua MockTransport: prompt/image contracts, scoped cancel, graph snapshot, đo/decode output, API key không truyền sang host storage. **ComfyUI/Runway chưa có live API generation**; các clip xác nhận HTTP là fixture. Local LTX có bằng chứng model sinh thật ở phần mới phía trên. Chi tiết setup/công cụ ở [SUBJECTS_AND_GENERATION.md](SUBJECTS_AND_GENERATION.md).

Đã có ASR local, tracker vùng, SAM2 segmentation/corrections và LaMa inpainting chạy GPU thật. Chưa có semantic retrieval chạy nền, nhận diện lại chủ thể được xác minh, forced alignment. Calling AI nhìn pixel thực và dùng director guide; chưa huấn luyện aesthetic model độc lập. Planner local theo tags chỉ tạo bản đầu. Không giả định tool làm AI văn bản thuần hiểu ảnh/audio.

Hai source React và HTML không tự dịch custom code. Runtime v2 giữ entry/runtime khi patch timeline, cập nhật data trong snapshot; legacy v1 cần migration có giữ custom code. Đã có audio clips/SFX và import footage giữ audio nguồn. Video layers mặc định muted. Transition portable giữ tĩnh frame cuối phía trước; chưa có moving source handles hai phía.

Engine được kiểm bằng media local và code-generated diagrams; adapter planner AI/Pexels chưa kiểm với khóa người dùng. Chưa tự thêm MCP vào cấu hình Codex toàn máy hay xác nhận một phiên Claude đã kết nối; `.mcp.json` và hướng dẫn sẵn trong repo.

Kết quả kỹ thuật này không tuyên bố mọi video tự sinh đạt chất lượng editor chuyên nghiệp. Chất lượng nội dung được nâng qua vòng AI nhìn/nghe → sửa bản dựng, không qua scoring/approval gates.
