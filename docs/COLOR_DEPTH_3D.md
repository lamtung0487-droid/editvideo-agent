# Màu có quản lý, depth và cảnh3D cho agent

## Phân biệt các pipeline

**Màu:** `process_color` thực thi FFmpeg zscale qua float linear RGB, exposure trong linear light, tonemap HDR→SDR, LUT3D trong display BT.709, SDR hoặc HEVC10bit/PQ/BT.2020 đầu ra. [FFmpeg filters](https://ffmpeg.org/ffmpeg-filters.html#zscale) mô tả transfer/primaries/range và [tonemap](https://ffmpeg.org/ffmpeg-filters.html#tonemap) cần linear float. Không suy HDR từ extension, tên file hoặc chỉ bitdepth.

**Authoring browser:** Remotion/Hyperframes composition hiện SDR; font/text/graphics/native3D được chụp qua Chromium SDR. Nhập HDR cần tạo proxy tonemap SDR trước. Pipeline media độc lập có thể giữ PQ/HLG native, nhưng ghép toàn bộ phim qua Chromium hiện không phải compositor HDR scene-linear end-to-end. Xuất phim SDR sang PQ có thể đúng transfer/tag/10bit nhưng phải gọi **SDR-derived PQ**, không tuyên bố khôi phục highlights/gamut chưa có. Không tự bịa mastering display, MaxCLL hay MaxFALL.

**Depth:** [Depth Anything V2 Small HF](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf),24.8M,Apache2.0, revision5426e4f0f36572d16453bbda7a8389317b1bef99, safetensors~100MB. Là image model relative inverse depth: trắng/cao≈gần. Không có mét hoặc camera calibration. [Upstream](https://github.com/DepthAnything/Depth-Anything-V2) có các biến thể metric/video khác; phiên này không quảng cáo chúng là đã tích hợp.

**3D:** Native geometry với perspective camera, lights, MeshStandardMaterial và shadows. Remotion dùng ThreeCanvas; HTML dùng Three.js WebGL với cùng scene functions. [Remotion ThreeCanvas](https://www.remotion.dev/docs/three-canvas), [Three.js docs](https://threejs.org/docs/). Mọi camera/object pose lấy từ frame, không useFrame/requestAnimationFrame/wall clock. Không biến relative depth thành một bản tái dựng hình học chính xác.

## Thư viện màu và workflow

`color_catalog` trả6 original LUT: identity/documentary/warm_story/cool_science/forest/monochrome. LUT17³, normalized0..1, display-referred BT.709RGB; sha trong assets/luts/manifest.json. Đây là transform tự tạo, không phải look-pack của người khác hoặc camera-log conversion LUT. Tetrahedral interpolation; lut_strength blend với identity trong cùng display domain.

Custom .cube: local≤8MB, size2..33, N³ finite output0..1, domain0..1. Không1D/shaper/log/extendedHDRdomain. Strict parser từ chối trường hợp không hỗ trợ; không cố chạy một LUT chưa hiểu. File custom được snapshot vào task trước khi worker chạy.

ColorRequest: path,input_space auto|bt709|srgb|hdr10|hlg,input_range auto|limited|full,start/end≤120s,output sdr|hdr10,lut_id hoặc lut_path,lut_strength,exposure±2,tonemap hable/mobius/reinhard/linear/clip,source_peak_nits,paper_white_nits,crf. `auto` chỉ dùng metadata nhận biết được; source chưa tag phải khai space/range từ nguồn biết được. Hable/desat0 là lựa chọn mặc định, không một chuẩn cho mọi cảnh. source_peak_nits là giá trị khai báo để tonemap, không đo MaxCLL. paper_white_nits chỉ điều khiển phép scale SDR-derived PQ; native HDR giữ absolute luminance theo transfer, ngoài exposure explicit.

`process_color` trả task durable/cancellable; `get_media_task` sau đó `inspect_color` và `observe_media` cho SDR. Xem decoded tags và floating-linear sampled waveforms/percentiles. PQ scope dùng100nit reference conversion để trở về absolute nits; HLG scene-relative và SDR100nit không đo màn hình thực. Resize scope bằng zscale trước/chung linear conversion để không clamp highlights>1 ở swscale. Scope≤8 timestamp/downsampled không chứng nhận max toàn phim. Grade bằng mục đích/nguồn; LUT không chữa clipping sẵn trong SDR.

```json
{"request":{"path":"<known HDR source.mp4>","input_space":"hdr10","input_range":"limited","output":"sdr","source_peak_nits":1000,"tonemap":"hable"}}
{"request":{"path":"<SDR source.mp4>","input_space":"bt709","input_range":"limited","output":"sdr","lut_id":"documentary","lut_strength":0.4}}
```

## Đọc depth rồi edit

Cài explicit `install_depth_model(allow_download=true)` hoặc scripts/setup_depth.py --download. Optional environment requirements.temporal.txt cung cấp torch/transformers. Model pin/sha verified, không download trong inference. Gói source không chứa100MBweights.

`estimate_depth` DepthRequest: ảnh hoặc video window≤15s/450frames,width128..960,fps1..30,temporal_strength0..0.6,deviceauto/cpu/cuda,scene_cuts explicit. GPU dùng khóa chung tránh tranh với SAM/LTX. Output: rawfloatNPZ, scene indices,16bitPNG normalized, diagnosticclip, frame/hash/flow-support records. Chuẩn hóa percentile2..98 **theo scene/window**, không min/max từng frame gây nhấp nháy. Runtime dùng model ảnh và bounded affine scale/shift alignment + flow-consistent blend giữa frame; reset ở cut tự phát hiện hoặc caller supplied. Không gọi đây là neural video-depth.

`read_depth(task_id,offset,limit,frames)` trả source/depthpreview/16bitmap inline, cùng timestamp/source coordinates. Near-white convention phải được giữ khi chọn focus. Kiểm occlusion, tóc, tay, kính/mặt nước, mỏng/reflective. Flow-reliable fraction không phải confidence depth hay danh tính. Không khẳng định tất cả pixels hoặc hidden surfaces chính xác.

`edit_depth`: focus_blur (focus_depth/focus_end/focus_width,blur_sigma,strength), atmosphere (far fog_color,strength), visualize, **still-only parallax**(small shift_x/y±.06,duration,fps). Blur là screen-space continuous Gaussian mix theo depth, không lens aperture/optical bokeh. Fog là compositing graphic, không physical scattering. Parallax là2.5D inverse warp phản chiếu viền, không unseen-view reconstruction; giữ shift nhỏ và xem vùng co giãn/occlusion. Visual clips im lặng; giữ narration/đặt source audio độc lập. Các artifact source/depth checked SHA trước edit.

Attach output bằng `attach_media_result` với revision hiện tại; edit không tự thay shot/camera. Source videos frame rate đã biết, map source_time với playback_rate khi ghép. Pixel source/depth cùng dimensions/window, không lấy source-normalized anchor làm canvas-normalized nếu có contain/crop khác.

##3D camera, vật liệu và ánh sáng

`scene3d_catalog`: depth_layers,material_study,mechanism,product_pedestal.4presets/7geometries (box/sphere/torus/cylinder/cone/plane/icosahedron). Preset mechanism chỉ là hình minh họa, không simulation kỹ thuật. Object size trong arbitrary authored units, rotation **radians**. Với sphere size[0] là đường kính; torus size[0]major radius,size[1]tube radius; cylinder size[0]/2topradius,size[2]/2bottomradius,size[1]height. Không trộn những units này với mét từ footage.

`compose_scene3d` nhận id,preset hoặc scene,start/end,x/y/width/height/z. Scene3D schema:≤64objects với geometry/color/material/position/rotation/scale/keyframes;≤8ambient/directional/pointlights,intensity/color/position;fov15..90,camera_position/target và sorted camera_keys;ground/shadows/transparent/background. Poses localframes tronglayer, phải tăng và nằm trongduration. Camera/pose interpolate smooth từ tuyệt đối, seek ngược không tích lũy lỗi. Material roughness/metalness có ánh sáng; không chỉ flat-CSS3D. Camera nhìn scene, không calibrated pose estimate.

**Texture và glTF:** object nhận `texture` (màu, sRGB), `bump_texture`+`bump_scale`, `emissive_texture`, `alpha_texture` (ví dụ lớp mây), `texture_repeat`, `texture_tint`; sphere dùng UV equirectangular nên bản đồ địa cầu 2:1 khớp trực tiếp. Scene nhận `background_texture`/`environment_texture` equirect (phản chiếu PMREM). `model` nhận asset `.glb` tự chứa (import_media kiểm header glTF 2.0, từ chối buffer/ảnh ngoài), fit cạnh lớn nhất vào `size[0]`; Draco được giải nén bằng decoder local đóng gói vào `public/draco/`. `animation`/`animation_speed`/`animation_offset` lấy mẫu clip glTF theo thời gian frame tuyệt đối (AnimationMixer.setTime), không theo wall clock. Asset tải trước frame đầu (Remotion delayRender, HTML trước khi đăng ký timeline). Đã render thật: Trái Đất NASA Blue Marble + mây, mô hình Apollo LM (NASA 3D Resources, Draco).

**Nâng cấp ánh sáng/vật liệu/hậu kỳ 3D:** `environment:"studio"` tạo phản chiếu từ RoomEnvironment procedural (PMREM) cho kim loại/kính, `environment_intensity`; `bloom:{strength,radius,threshold}` qua EffectComposer+UnrealBloomPass+OutputPass (Remotion dùng useFrame priority1 trong frameloop do Remotion advance, HTML dùng cùng hàm); `fog:{color,near,far}`. Object có `emissive/emissive_intensity`, `transmission` (kính), `clearcoat` (MeshPhysicalMaterial), geometry mới torus_knot/capsule/octahedron/dodecahedron và `detail`. Pose key có thể chỉ khai rotation hoặc position; phần thiếu kế thừa giá trị gốc của object (trước đây âm thầm về gốc toạ độ). Bloom mạnh dễ cháy sáng: bắt đầu strength≈.5, threshold≈.85 và nhìn snapshot.

**Đường ống, bám đường, ảnh 3D từ depth, mờ dần:** geometry `tube` nhận `path` (≤512 điểm [x,y,z], CatmullRom centripetal), `tube_radius`, `grow:[start,end]` để ống tự vẽ theo chiều dài (drawRange theo vòng, xác định theo frame). Object khác đặt `follow:"<id tube>"`+`follow_range` để chạy dọc đường cong (getPointAt, `follow_orient` quay theo tiếp tuyến), ví dụ tàu Orion trên quỹ đạo. `plane`/`sphere` nhận `segments` (≤512) và `displacement_texture`+`displacement_scale`+`displacement_bias`: đặt ảnh lên plane bằng `emissive_texture` (màu không phụ thuộc đèn), lấy depth PNG của `estimate_depth` (gần = trắng) làm displacement, rồi dolly/crane camera để có parallax thật. Depth là tương đối: vùng biên/đối tượng mảnh bị kéo dãn khi nhìn lệch nhiều, nên giữ góc camera vừa phải (đã kiểm tra bằng snapshot nhìn nghiêng). Pose key có `opacity` (0..1) làm mờ cả object, ẩn hẳn ở 0. Scene `camera_ease`: `smooth` (mặc định, ease vào/ra giữa từng cặp key — hợp 2–4 key đặt tay) hoặc `linear` cho key dày đã tính sẵn chuyển động (camera bám theo vật, dive địa cầu); dùng `smooth` với key cách nhau vài frame sẽ làm camera dừng ở mỗi key và rung. `label_facing:{x,y,z}` ẩn nhãn khi object quay mặt khỏi camera so với tâm đó (mặt sau địa cầu); nhãn cũng mờ/ẩn theo scale của object nên không hiện trước khi marker xuất hiện. Kích thước thành phần `size` cho phép từ .0005.

**Địa cầu (`compose_globe`):** dựng sẵn một layer scene3d từ `earth_texture` (equirect 2:1), `clouds_texture` (alpha, trôi chậm và mỏng dần khi camera hạ thấp, `clouds_opacity`), `bump_texture`, khí quyển, sao. `markers` [{id,lat,lon,label,appear,size,pulse,pulse_every}]: chấm phát sáng nhỏ + vòng sóng nằm phẳng trên bề mặt lan ra/mờ dần. `arcs` [{start,end,height,grow,color,radius,traveler}]: cung great-circle nâng khỏi mặt đất, mọc theo frame với chấm "traveler" chỉ hiện khi đang bay. `outlines` [{id,points:[[lon,lat]…≤5000],grow,color,radius,lift}]: vẽ biên giới (ví dụ Natural Earth) phát sáng trên mặt cầu, tự rút gọn RDP ≤480 điểm. `camera` [{frame,lat,lon,altitude,look}] được slerp trên mặt cầu mỗi3 frame nên lao xuống không xuyên địa cầu. `sun_lat`/`sun_lon` đặt điểm mặt trời chiếu thẳng: chọn vài độ phía tây vùng đích để vùng đích sáng và có đường phân ranh ngày/đêm. Với Blue Marble 5400px, giữ `altitude` ≥≈1 bán kính ở khung cuối; thấp hơn ảnh sẽ mềm. Bloom: strength≈.4, threshold≈.86 cho tuyến/biên; mạnh hơn sẽ thành quầng trắng. Đây là địa lý minh họa, không phải phép chiếu GIS.

Các cảnh3D WebGL output SDR, dùng ACESFilmicToneMapping ở display và sRGB, shadowPCF; ánh sáng graphic không chứng nhận physical radiance. Rigging/IK tự tạo, motion blur3D và tái dựng mesh thật từ nhiều ảnh chưa tích hợp; ảnh 3D ở trên chỉ là plane biến dạng theo depth tương đối, không phải hình học thật của cảnh. Có thể mở rộng source nhưng chỉ gọi là available sau implementation/preview.

Engine setup pinned three0.186.1,@remotion/three4.0.534,@react-three/fiber9.5.0. Fresh source includes scene3d.js/Scene3D.tsx và localThree modules choHTML. Customized old source cần merge explicit entry/runtime/importmap. Windows filesystem case-insensitive: Reactimport phải ghi **./scene3d.js** để tránh resolve sang Scene3D.tsx. Không tự overwrite source người dùng.

## Chọn kỹ thuật theo nội dung

- Kiến thức:3Dplanes giải thích che khuất/parallax; label đọc được, camera chậm, captions độc lập. Đừng orbit camera nhanh trong khi người xem đọc đoạn dài.
- Tư liệu: giữ màu nguồn, LUT nhẹ sau transform đúngdomain; nguồn màu mang ý nghĩa không dùng creativegrade để thay đổi kết luận.
- Phỏng vấn: depth blur nhẹ khi cần nhấn subject; xem tóc/viền/tay xuyên thời gian trước gọi finished. Segmentationmask có thể tốt hơn depth cho contour chính xác.
- Ảnh minh họa:2.5Dparallax rất nhỏ, giữ backgroundshape; vùng lộ mới cần inpainting/cảnh dựng khác, không che bằng lời “3D reconstruction”.
- HDRfootage: giữ bản native archive +tonemap authoringproxy. Master HDR toàn bộcomposition cần compositing32bit/scene-linear khác; không giả rằng render browser+metadata là masterHDRnative.

Bằng chứng thực trong outputs/color-live-verification.json,depth-live-observation.json,scene3d-live-verification.json và advanced-narrated-demo.json. Script verify_color_depth_3d.py tạo radiancefixture20/100/400/1000nit thành PQ10bit, kiểmdecode/scopes; scene3D được render hai engine và nhìnpixels. Demo thuyết minh được dựng mới từtiming TTS thật; video cuối là SDR, có HDR sample tonemap được ghi rõ nguồn kỹ thuật.

## Color graph scene-referred

`process_color` nhận `graph` thay cho `grade`: input transform (log máy quay hoặc BT.1886 của footage hiển thị) →
scene-linear Rec.709 → các node grade trong ACEScct (`exposure` theo stop, `white_balance`, `cdl` slope/offset/power/sat,
`contrast` quanh xám 18 %, `saturation`) → `look` nằm dưới output transform (LUT in phim nhận Cineon như
`print_film_cineon`, hoặc LUT cct/display) → output transform (filmic cho log, BT.1886 cho footage hiển thị: graph rỗng
là identity). Node `window` chấm màu bên trong mask mềm di chuyển theo box, keyframe box hoặc track. Mọi node per-pixel
được bake thành một LUT 3D trên mã nguồn (tetrahedral float); mỗi cửa sổ thêm một LUT và một mask FFV1 trộn bằng
`maskedmerge` (chính xác trong/ngoài cửa sổ, vùng feather trộn kết quả cuối). `graph_checks` cho biết xám 18 %, đen,
trắng khuếch tán và +2 stop rơi vào đâu trên màn hình. Giới hạn: gamut Rec.709 (đường cong ACEScct, không AP1); chỉ SDR.

