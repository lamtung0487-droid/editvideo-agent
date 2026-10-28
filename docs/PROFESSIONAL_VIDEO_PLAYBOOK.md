# Claude dựng video chuyên nghiệp: từ TikTok đến YouTube

Video chuyên nghiệp phải phục vụ một ý tưởng và người xem cụ thể. Hiệu ứng là công cụ dẫn mắt, giải thích và nối ý; số hiệu ứng, độ rực hay nhịp cắt nhanh không tự quyết định chất lượng. Runtime cung cấp thao tác, pixel, audio và thời gian; Claude diễn giải chúng và xây bản dựng. Không thêm bảng chấm điểm, kiểm duyệt hay vòng phê duyệt.

## Nghiên cứu và phạm vi nguồn

TikTok Business hướng dẫn creative quảng cáo có hình dọc, âm thanh, vùng tránh UI, nội dung mở đầu rõ và phụ đề. Các khuyến nghị về hook trong vài giây đầu là điểm xuất phát cho **quảng cáo**; không dùng để áp một công thức nhịp/cắt cho mọi TikTok giáo dục, kể chuyện hay phỏng vấn. [Nguồn TikTok, cập nhật June 2025](https://ads.tiktok.com/resources/help/article/creative-best-practices?lang=en).

YouTube giải thích intro theo 30 giây đầu và sự phù hợp với kỳ vọng tiêu đề/thumbnail. Spike có thể là người xem thích một đoạn hoặc phải xem lại vì khó hiểu; dip cần xem ngữ cảnh để hiểu nguyên nhân. Đây là dữ liệu sau khi có người xem, **không phải mô hình dự đoán retention từ file video**. Hệ thống không tạo “điểm giữ chân” giả. [Nguồn YouTube](https://support.google.com/youtube/answer/9314415?hl=en).

Adobe mô tả J/L cut là picture và audio chuyển ở thời điểm khác nhau; tính chuyên nghiệp ở sự liền mạch của cuộc nói chuyện/cảnh, không phải tên transition. [J/L cut chính thức](https://helpx.adobe.com/ie/premiere/desktop/edit-projects/trim-clips/perform-j-cuts-and-l-cuts.html).

Blackmagic chia đào tạo hậu kỳ thành dựng, màu, âm thanh và visual effects; đây là cơ sở để tổ chức khả năng theo công việc, thay vì chỉ tăng danh sách filter. [Đào tạo DaVinci Resolve](https://www.blackmagicdesign.com/products/davinciresolve/training). Word highlighting có tiền lệ công khai trong [Remotion captions](https://www.remotion.dev/docs/captions/); phần mới ở đây là cùng hợp đồng frame/data chạy cả Remotion và Hyperframes, không gọi kỹ thuật phổ biến này là phát minh độc quyền.

## Yếu tố cần có và cách hệ thống hỗ trợ

| Năng lực | TikTok/Shorts | YouTube dài | Công cụ thực sự có |
|---|---|---|---|
| Ý tưởng, lời hứa và payoff | Một tình huống/câu hỏi rõ, ví dụ nhanh nhưng đủ ngữ cảnh | Câu hỏi/chủ đề chính, lập luận và kết luận giải quyết lời mở | Claude viết creative brief; toolkit/skill giúp lập beat và chọn recipe, không viết ý nghĩa thay Claude |
| Chọn footage theo nội dung | Hình minh họa đúng điểm nói, tránh filler | B-roll, biểu đồ/tư liệu có vai trò giải thích/chứng minh | Index/window/crop/audio/ASR, provenance và semantic roles; sinh footage là reconstruction |
| Nhịp dựng và continuity | Cắt khi đổi ý/hành động, chừa thời gian đọc | Đổi cỡ cảnh, reaction, chapter và khoảng nghỉ hợp lý | Split/move boundary, source trim/rate, audio onsets, J/L audio bridges; không tự cắt ở mọi onset |
| Composition và dẫn mắt | Điện thoại, khoảng trống cho UI, một tiêu điểm | Thứ bậc trong khung ngang, chi tiết/diagram không cạnh tranh nhau | Safe-region heuristic có thể đổi, focus_spotlight, PiP, tracked_callout, source→canvas mapping |
| Typography và caption | Cụm nghĩa ngắn, không che mặt/tay/đối tượng | Phụ đề đọc được, nhãn và nguồn rõ, không phá biểu đồ | Timed words/pages, outline, marker, stable phrase layout; TTS/ASR timestamps không phải forced alignment |
| Graphic/motion design | Accent đúng keyword/hành động | Lower thirds, chapter cards, explainers có dữ liệu | 62 effects, 11 layer kinds, typed keyframes, 16 executable recipes, editable React/HTML |
| Ánh sáng/màu/texture | Giữ da, chủ thể và tương phản chữ | Liên hệ exposure/palette giữa cảnh, không bóp màu có ý nghĩa | Pixel/palette/ROI/clipping signals, CSS display grades, masked grade; **chưa là pipeline color-managed HDR/scene-linear/LUT** |
| Dialogue/music/SFX | Giọng dễ hiểu dù loa nhỏ, accent có chủ đích | Natural audio, music bed, room tone, J/L cut và ducking | Source audio giữ riêng, trim/fade/gain/rate/duck, 5 procedural sound kinds, read_audio_events, master loudness có thể chỉnh |
| Temporal quality | Không nhảy mask/caption/chủ thể | Kiểm tra motion, camera, occlusion, inpaint continuity | Dense flow/affine/residual/FFT/lens, SAM2 masks, ProPainter, seeded image-to-video/refinement |
| Cấu trúc/chapter | Một vòng hiểu trọn vẹn; loop khi tự nhiên | Mốc chương, chuyển đoạn, tóm tắt và liên hệ | Chapter_card/progress, long caption pages; chapter timestamps do Claude lập từ nội dung |
| Adaptation/delivery | Dựng dọc, crop theo đối tượng và text/UI | Khung phù hợp nội dung, source/caption/audio chỉnh được | 3 profiles, SAM2 reframe, code snapshots, Full HD MP4/source ZIP, actual decode/metadata |
| Creative refinement | Quan sát vấn đề cụ thể, sửa một biến có ý nghĩa | Đối chiếu đầu/giữa/cuối và các đoạn phức tạp | Pixels/audio/timestamps + atomic revision/hash edits; không có auto beauty/virality verdict |

Shorts hiện có thể dài đến ba phút theo dạng vuông/dọc ở điều kiện YouTube mô tả; đây là phân loại nền tảng, không phải khuyến nghị kéo mọi clip tới ba phút. [YouTube Shorts](https://support.google.com/youtube/answer/15424877?hl=en). YouTube manual chapters yêu cầu timestamp đầu 00:00, ít nhất ba timestamp tăng dần và mỗi chương tối thiểu 10s theo tài liệu; chỉ lập mốc đủ nghĩa cho video phù hợp, không thêm chapter giả. [YouTube chapters](https://support.google.com/youtube/answer/9884579?hl=en).

## Creative brief trước khi thao tác

Claude cần xác định: ai xem; họ đang biết gì; sau video hiểu/làm/cảm thấy gì; lời hứa mở đầu; những chứng cứ/ví dụ cần có; điều gì phải giữ chính xác; style/reference; format và thời lượng dựa trên lượng thông tin. Với video dài, phân chương theo câu hỏi/luận điểm; với video ngắn, giữ một chuỗi setup→demonstration→payoff. Không đặt “mỗi 2 giây cắt một lần” hay “luôn cần zoom/shake” làm luật.

Đọc footage ở ba tầng: index toàn bộ → cửa sổ/audio có mục đích → crop/temporal detail. Ghi sự kiện/đối tượng chưa chắc; ảnh đẹp không chứng minh thông tin. Dùng transcript để tìm cụm ý, đo âm thanh để tìm khoảng nghỉ/onset, rồi nghe/xem quyết định. Sự kiện âm học không đồng nghĩa beat hoặc chỗ nên xóa lời.

## Bộ recipe thực thi

`editvideo_professional_toolkit(platform,query)` liệt kê hướng dẫn và 16 recipe. `editvideo_compose_edit(project_id,base_revision,request)` kiểm schema/range/source rồi áp các operation một lượt; trả operation, note và frame nên inspect. `dry_run=true` chỉ là tùy chọn đọc bản biên dịch, không phải vòng xin duyệt bắt buộc.

| Recipe | Dùng khi | Cần cung cấp |
|---|---|---|
| hook_card | Làm lời hứa mở đầu dễ thấy | text có ý nghĩa; tránh lặp cả đoạn voice |
| lower_third | Nhận diện người/địa điểm/khái niệm | text, secondary_text; vị trí không che action |
| chapter_card | Chuyển câu hỏi/luận điểm | tiêu đề chương, số/tên mục |
| evidence_card | Chi tiết/tư liệu cần nguồn | image/video asset, source_text đã được Claude kiểm |
| pull_quote | Một phát biểu quan trọng | câu trích ngắn và tên/nguồn; thời gian đọc |
| keyword_callout | Nhấn một thuật ngữ đúng thời điểm | keyword, range theo narration |
| picture_in_picture | Giữ chi tiết cùng context | asset, source trim, nhãn nếu cần |
| comparison_labels | So hai phía công bằng | hai label; caller dựng ảnh/dữ liệu thật tương ứng |
| focus_spotlight | Dẫn mắt vào vùng đã xem | safe_region ở recipe này là rectangle được giữ sáng |
| tracked_callout | Nối nhãn tới điểm đã tracking | target/target_keyframes trong **canvas**, label_point; frame local |
| word_captions | Giữ phrase ổn định và highlight lời đang nói | TTS words matched cue hoặc word_timings của transcript đã map sang narration |
| chapter_progress | Thấy tiến trình một đoạn | range chương; percentage là thời gian, không phải số liệu nội dung |
| j_cut_audio | Âm mới xuất hiện trước cut hình | cut_frame/start_frame, lead_frames, source_start đủ pre-roll |
| l_cut_audio | Âm cũ kéo qua cut hình | range bao quanh cut_frame, source handle thật |
| sound_bridge | Một âm liên tục nối hình | audio/video có audio track, trim/gain |
| audio_finish | Điều chỉnh master/duck | target LUFS/true peak/LRA và duck settings |

`id` là namespace các layer/audio do recipe tạo; dùng id riêng cho từng beat, giữ id khi tinh chỉnh chính beat đó. `start_frame/end_frame` là `[start,end)` ở 30fps. Voice/timebase/dimensions đã khóa không đổi. Source range thiếu thì trả lỗi thay vì kéo dài/tạo audio tưởng tượng.

Vùng tránh UI của toolkit là **heuristic bảo thủ có thể sửa**, không phải safe-zone pixel chính thức. Kiểm screenshot giao diện/format phát thực; `safe_region` override. Composition/caption cần kiểm ở kích thước điện thoại, chỗ chữ dài, ánh sáng thay đổi và lúc nhân vật đi qua nhãn. Không tự crop chủ thể chỉ dựa trên tên file.

## Caption dài và tracking callout

`caption` mới dùng `data.words` cho một phrase hoặc `data.pages` cho tối đa 2000 phrase trong **một layer**. Word frames dùng local frame của layer, page ranges không chồng. Future-word opacity, box/color/underline và active colors có schema. Phrase giữ bố cục, highlight cập nhật theo frame; không tween kích thước mỗi từ gây nhảy hàng. Normal captions bị tắt chỉ khi timed caption layer hoạt động, tránh hiện hai lần.

`word_captions` lấy plan words từ TTS; hoặc `word_timings=[{text,start,end},…]` và `timing_source` do caller cung cấp từ ASR/alignment. Phải là giây theo narration của project, sorted/in-range, text map được cue. Không tự chia đều thời gian từ theo độ dài text. ASR timing và việc quy về 30fps vẫn là ước lượng; sửa tên riêng/thuật ngữ bằng audio. Một track nhiều page xử lý video dài, không tiêu tốn hàng trăm layer.

`callout` mới là SVG leader/anchor, label cố định và target_keyframes tuyến tính để điểm neo đi theo tracking. Chuẩn hóa canvas, không lấy box source gán thẳng lên video đã contain/crop/speed. `track_region`/SAM2 cung cấp đo/tracks, Claude chịu trách nhiệm mapping. Không suy semantic identity từ điểm/mask sống sót.

## 12 effects mới

| Effect | Vai trò | Lưu ý |
|---|---|---|
| diagonal_reveal / diamond_reveal | Mask reveal khi chuyển chương/inset | Graphic reveal, không thay action cut |
| soft_edge_reveal | Mở lớp bằng alpha edge mềm | Mask sau có thể thay mask trước |
| slide_spring | Lower third có overshoot giảm dần | Dùng nhỏ, tránh đẩy người xem đọc chữ đang rung |
| focus_zoom | Push tới transform origin đã chọn | Cần focus_x/y từ quan sát; không phải camera 3D/depth |
| defocus_pulse | Một graphic tạm mất nét rồi rõ lại | Không gọi là neural rack focus theo depth |
| fade_pulse | Giảm rồi trả độ sáng qua opacity | Một focal accent, không nhấp nháy lặp |
| light_sweep | Ánh sáng lướt qua card | Nên rất nhẹ; rời lớp sau end |
| paper_grain | Texture tĩnh seeded | Không phải phục hồi film scan hay noise temporal |
| text_outline | Stroke hỗ trợ caption trên footage | Kiểm nét chữ Việt và mức stroke nhỏ |
| marker_reveal | Dải marker tăng dưới statement | Chọn màu chữ tương phản; không làm highlight mọi câu |
| exposure | CSS brightness theo display-space stop | Không phải scene-linear exposure/color management |

Tất cả seek theo frame, không dùng clock/random state tích lũy, có schema/default/use_when/caution và cùng runtime hai engine. Atlas cho Claude xem kỹ thuật thật; amount trong atlas giúp thấy rõ, không phải mức tối ưu cho production.

## Âm thanh

`editvideo_read_audio_events` trả onset candidate bằng spectral flux, khoảng RMS thấp, LUFS/true peak/range thực từ FFmpeg và WAV nghe được. Giới hạn 120s mỗi cửa sổ; waveform events 20ms hop/40ms window, loudness dùng original channels. Không suy semantic tiếng động, BPM hay tự xóa pause. Onset có thể đến từ phụ âm, tiếng gõ, nhạc hoặc noise.

`editvideo_design_sound` tạo whoosh/impact/tick/riser/ambient bằng **procedural synthesis**, không giả là neural audio model. Seed/gain/duration có giới hạn, WAV 48kHz. Import preserve_plan rồi upsert_audio/recipe theo mục đích; duck dưới speech, fade tự nhiên và nghe mix. Chỉ accent ở một vài điểm quan trọng, không đặt whoosh mỗi cut.

Master trước đây đã chuẩn hóa hai pass ở -16 LUFS; phần mới cho chỉnh `AudioMix.target_lufs/true_peak_db/loudness_range` và `music_ducking`. AudioClip có `ducking.threshold/ratio/attack_ms/release_ms` riêng. Default giữ hành vi cũ. -16 LUFS là mặc định biên tập narration của hệ thống, **không tuyên bố là yêu cầu chính thức chung của TikTok/YouTube**. [FFmpeg loudnorm/sidechaincompress](https://ffmpeg.org/ffmpeg-filters.html) là backend thực; linear normalization có thể chuyển dynamic nếu không thỏa điều kiện. Mix cần kiểm input/output, đừng chỉ nhìn target cấu hình.

J/L recipe đặt một nguồn audio chọn riêng qua cut; narration đã khóa vẫn tồn tại. Nếu voice đã chứa cùng dialogue, thêm lại sẽ thành tiếng đôi. Cần chọn ambience/SFX/dialogue khác hoặc thiết kế narration/source audio rõ ràng trong project. Hệ thống chưa có transcript-based ripple deletion tự động giữ mọi track đồng bộ, ADR/audio stem separation hay kiểm môi trường phòng thu.

## Nâng runtime của source cũ

Project export mới có widgets/effects mới. Source cũ vẫn giữ custom entry qua patch, nên data mới không tự viết đè mã cũ. Đọc `editvideo://runtime/remotion/effects.cjs`, `…/remotion/index.tsx`, `…/hyperframes/effects.js`, `…/hyperframes/hyper-runtime.js` để lấy template hiện tại. Đọc code/hash project, merge phần cần thiết hoặc thay template có chủ đích bằng write_code; tool backup bản trước. Custom entry phải gọi widget mới và xử lý tránh caption đôi. Không reexport overwrite chỉ để cập nhật dữ liệu.

## Phần còn cần mở rộng

Hiện có bộ dựng/quan sát/tinh chỉnh thực thi được; chưa thể gọi là toàn bộ hậu kỳ chuyên nghiệp: semantic retrieval/re-identification, nonlinear speed ramps/audio time-warp, moving source-handle transitions, color-managed HDR/LUT, depth/pose-controlled generation, dialogue separation/ADR và đầy đủ interchange EDL/FCPXML chưa có bằng chứng tích hợp. Khi bổ sung cần hợp đồng dữ liệu, model/dependency phù hợp, xử lý source handles và artifact render thật; không thêm tên kỹ thuật để che khoảng trống.

Claude phát huy năng lực bằng phối hợp nhận thức nhiều tầng, lập luận về nội dung, code và thao tác chính xác. Vòng làm việc là brief → evidence → edit → playable result → refine, với một video có ý nghĩa ở đích; không phải một danh sách hiệu ứng chạy cùng lúc.
