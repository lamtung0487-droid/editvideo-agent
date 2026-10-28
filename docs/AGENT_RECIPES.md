# Thao tác dựng cho AI

Tra `editvideo://schemas` trước khi gửi batch. Tất cả frame là số nguyên 30fps. Range timeline `[start,end)`; effect/keyframe là frame local của shot/layer. `effects.end_frame` là mốc đạt trạng thái cuối, phải nằm trong độ dài lớp; keyframe cuối tối đa `duration-1`.

## Một nhãn giải thích

Ví dụ dưới đây cần timeline dài ít nhất 120 frame; dùng revision vừa đọc:

```json
{"operations":[
  {"op":"set_design","design":{"intent":"Giải thích một cơ chế, ưu tiên chữ rõ và chuyển động nhẹ","palette":["#102322","#81e6be","#ffffff"]}},
  {"op":"upsert_layer","layer":{
    "id":"concept","kind":"text","start_frame":30,"end_frame":120,
    "text":"Ánh sáng → năng lượng","x":0.1,"y":0.1,"width":0.8,"height":0.15,
    "font_size":64,"color":"#ffffff","background":"#102322",
    "effects":[{"name":"fade_in","end_frame":12},{"name":"rise","end_frame":18,"params":{"amount":30}}]
  }}
]}
```

## Chart, số liệu và quy trình

`bar_chart`/`line_chart` cần `data.values`, nhãn cùng số phần tử nếu có, `min` và `max` phù hợp. `progress` điều khiển reveal; dữ liệu luôn do agent cung cấp, không được sinh ngẫu nhiên rồi trình bày như số liệu thật. `counter` dùng `from/to/decimals/prefix/suffix`. `flow` cần 2–8 nhãn ngắn.

```json
{"op":"upsert_layer","layer":{
  "id":"process","kind":"flow","start_frame":0,"end_frame":150,
  "x":0.08,"y":0.35,"width":0.84,"height":0.25,
  "color":"#81e6be","data":{"labels":["Quan sát","Dựng","Tinh chỉnh"]},
  "effects":[{"name":"progress","end_frame":60}]
}}
```

Lớp video/image dùng `asset_id`; `kind` phải đúng loại asset. Media layer có `fit`, `source_start`, `playback_rate`; âm thanh video không tự vào mix hình. Muốn giữ âm nguồn, dùng `project_from_video` hoặc đặt audio clip riêng.

## Chuyển cảnh và điều khiển theo frame

**Chuyển cảnh hai phía (bản nâng cấp):** `push_left|push_right|push_up|push_down` đẩy cảnh cũ ra khi cảnh mới vào; `whip_left|whip_right` thêm easing mạnh và blur đỉnh giữa; `zoom_through` phóng cảnh cũ qua camera trong khi cảnh mới thu vào. `mode:"live"` cho cảnh cũ **tiếp tục chạy** từ source handle trong suốt thời gian chuyển (cả Remotion lẫn HyperFrames); planner kiểm `source_start+(độ dài shot+duration_frames)*rate` không vượt asset. `mode:"freeze"` (mặc định) giữ frame cuối như trước.

```json
{"op":"update_shot","shot_id":"s2","changes":{"transition":{"name":"whip_left","duration_frames":12,"mode":"live"}}}
```

**Retime footage:** `retime_footage({path,start,end,speed|speed_keys,motion_blur,blur_samples,fps})` tạo clip slow-motion/speed-ramp mượt bằng optical flow hai chiều (Farneback, không phải model học sâu; kiểm ghosting ở vùng che khuất/tay chân nhanh), motion blur theo shutter. Attach rồi đặt playback_rate 1 thay vì kéo chậm clip gốc (gây giật).

```json
{"op":"update_shot","shot_id":"SHOT_THỨ_HAI","changes":{
  "transition":{"name":"wipe_left","duration_frames":12},
  "effects":[{"name":"zoom_in","end_frame":119,"params":{"amount":0.05}}],
  "keyframes":{"opacity":[{"frame":0,"value":1},{"frame":119,"value":1}]}
}}
```

Shot phải đủ 120 frame cho ví dụ này. `dissolve`/wipe/iris/blur/zoom giữ frame cuối shot trước; nếu cần hai phía tiếp tục chuyển động với source handles, viết code tùy chỉnh và kiểm tra source range.

Keyframe hỗ trợ x/y pixels, scale ratio, rotate degrees, opacity 0–1, blur pixels; mỗi điểm có easing `linear|smooth|ease_in|ease_out`. Các transform được phối với effect, không thay thế: x/y/rotation cộng, scale và opacity nhân. Mask cùng property có thể ghi đè nhau; kiểm tra frame khi phối nhiều mask/filter. `fade_out` giữ trạng thái hết hiển thị sau end.

## Âm thanh

```json
{"op":"upsert_audio","audio":{
  "id":"accent","asset_id":"ASSET_AUDIO","start_frame":60,"end_frame":90,
  "source_start":0,"playback_rate":1,"volume":0.2,
  "fade_in":0.03,"fade_out":0.15,"duck_under_voice":true
}}
```

Audio source phải đủ thời lượng sau playback rate. Clip đặt trễ dùng delay theo timeline; không loop tự động. Nhạc nền cấu hình có thể loop và duck riêng. Final mix là 48kHz, được normalize sau khi trộn toàn bộ track.

## Tracking và đọc nguồn

`track_region` nhận ROI normalized trong frame nguồn và target output dimensions; trả delta x/y pixels kể từ đầu đoạn. Khi footage được contain/crop/đổi tốc độ, agent phải đổi mapping trước khi áp keyframes. Tracking không nhận diện danh tính vật thể. Dừng ở `lost_at`, inspect lại rồi mới nối track.

`inspect_window` cung cấp khoảng lấy mẫu; muốn biết một hành động 100ms phải lấy đoạn hẹp hơn. `crop_detail` trả phép đổi coordinate crop/display/source. Không dùng tọa độ của ảnh resize như pixel của footage gốc. `aesthetic_packet` cung cấp guide để agent đưa nhận xét cụ thể, không trả điểm đẹp.

## Source nâng cao

Runtime v2 giữ entry và runtime custom khi patch timeline: render tạo snapshot rồi cập nhật `input.json`, `input.js` và local assets. Đừng chỉnh các file input làm nguồn lâu dài; dùng timeline tools. Remotion import `effects.cjs`; Hyperframes dùng `effects.js` và `hyper-runtime.js`. Cả hai là source editable.

Khi replan thay thời lượng/fps/profile, root metadata trong HTML Hyperframes cần cập nhật bằng export mới, có giữ custom code trước overwrite. Patch trong timebase khóa không cần reexport. Remotion lấy metadata từ props hiện tại.

Muốn đồ họa SVG, CSS 3D, mask nhiều tầng, tracking affine hoặc hiệu ứng mới: agent đọc source, viết module riêng, snapshot mốc quan trọng rồi render. Không có bước dịch tự động giữa custom React và custom HTML. Không dùng wall-clock, `Math.random()` hoặc chạy video bằng `play()` cho animation seek được.


## Recipe chuyên nghiệp thực thi

Dùng professional_toolkit → compose_edit với RecipeRequest để áp16 recipe thực: hook/lower-third/chapter/evidence/PiP/keyword/quote/comparison/spotlight/callout/word-caption/chapter-progress/J-L audio bridge/sound/master. [Playbook](PROFESSIONAL_VIDEO_PLAYBOOK.md) giải thích nguồn, mapping và giới hạn. id thay toàn namespace của recipe khi tinh chỉnh, kể cả layer tùy chọn đã bỏ. Word caption hỗ trợ2000 page trong một layer; nguồn timing phải đúng narration.


## Minh họa vector tự vẽ (layer `svg`)

`kind:"svg"`, `data:{view_box:[W,H],elements:[...]}`. Phần tử khai báo, không nhận SVG/script thô: `path` (d chỉ gồm lệnh path và số), `polyline` (points), `circle`, `rect`, `line`, `text`, `follower` (chấm chạy dọc polyline theo độ dài cung). Thời gian là frame local: `draw:[a,b]` vẽ nét dần (pathLength), `dashed` + draw dùng mask để nét đứt cũng hiện dần, `appear` fade+scale, `fill_in` tô nền sau khi viền vẽ xong, `glow` drop-shadow. Dùng cho bản đồ (đường viền dữ liệu thật như Natural Earth), lộ trình, sơ đồ hành trình/cơ chế, timeline. Mốc nhãn nên tính từ độ dài cung để hiện đúng lúc follower đi qua.

## Layer đi cùng chuyển cảnh (`attach_shot`)

`attach_shot:"<shot id>"` đặt layer vào trong transform của shot: push/whip/zoom_through/wipe đẩy layer cùng hình; ở `mode:"live"` layer có end_frame chạm cuối shot tiếp tục chạy trong đoạn chồng. Layer phải nằm trong phạm vi shot. Layer gắn shot xếp trên shot đó nhưng dưới layer không gắn (caption toàn cục vẫn ở trên). Dùng cho tiêu đề, lower third, mini-map, cảnh 3D thuộc riêng một cảnh.

## Hoàn thiện kiểu điện ảnh (layer `film`, chữ động, chuyển cảnh sáng)

- Layer `film` với `data.type`: `grain` (hạt phim feTurbulence, seed đổi theo frame nên xác định; `intensity` .15–.3, `scale`, `speed`) đặt toàn khung, z cao, `blend:"overlay"`; `light_leak` (gradient ấm trôi, `color`/`secondary_color`/`speed`/`seed`) đặt quanh chuyển cảnh lớn với `blend:"screen"` và fade in/out. Đừng phủ light leak suốt video, nó làm bẩn màu nguồn.
- Hiệu ứng chữ `mask_reveal` (từng dòng trượt lên từ sau mép cắt, ease back-out) cho tiêu đề/địa danh; `char_spring` (từng ký tự bật scale+blur, `amount`) cho câu ngắn có nhịp. Đo trước bằng `layout_text` để chữ lớn không xuống dòng ngoài ý muốn.
- Chuyển cảnh `flash` (lóe trắng, hợp khi cắt từ không gian sang mặt đất) và `burn` (cháy sáng ấm, hợp khép phim) cùng `push_*`, `whip_*`, `zoom_through`; `mode:"live"` giữ shot ra tiếp tục chạy từ source handle.
- **Chữ nằm sau chủ thể:** `track_subject` (SAM2) → `edit_subject` foreground alpha cùng cửa sổ nguồn → `attach_media_result` video. Shot nền `motion:"hold"`, fit cover; layer foreground toàn khung, `fit:"cover"`, `source_start:0`, `attach_shot` cùng shot, z cao hơn chữ. Đặt chữ ở vùng nền phía trên đầu chủ thể để tay/nón đè lên mép chữ; nếu đặt giữa người thì chữ bị che gần hết.
- **Mở bằng địa cầu:** `compose_globe` lao từ không gian xuống vùng đích, viền quốc gia tự vẽ, marker xuất hiện, cung nối các điểm đến; sau đó `flash` vào footage thực tế. Bản đồ phẳng (`svg`) góc màn hình tiếp nối hành trình ở từng shot.
- **Quỹ đạo 3D thay sơ đồ phẳng:** đặt Trái Đất/Mặt Trăng textured, `tube` quỹ đạo mọc theo `grow`, vật thể `follow` chạy theo; camera bám đuổi tính sẵn mỗi 4 frame (`camera_ease:"linear"`), offset cố định theo thế giới để không quay ngoắt ở khúc cua gắt, rồi kéo ra toàn cảnh. Nhãn mốc dùng vật mang cực nhỏ có `label`, scale lên lúc vật tới và scale xuống sau ~2,5 giây để toàn cảnh cuối không chồng chữ. Xem data/films/build_a3.py.

