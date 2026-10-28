# Kiểm tra bằng bằng chứng: audit, review khung hình, motion

Ảnh chụp tĩnh không cho thấy rung giật. Mắt cũng dễ bỏ sót viền ảnh lộ ở góc hoặc nhãn chồng tiêu đề trong một khoảnh khắc. Ba công cụ dưới đây trả **số đo có ngưỡng** và bước sửa cụ thể. Chúng không chấm điểm đẹp, không duyệt, và ý đồ có thể bác một heuristic.

## Vòng chất lượng

1. `compose_cinematic(..., dry_run=true)` trả kèm `audit` cho các layer sắp tạo.
2. `audit_timeline(project_id)` chạy trước khi render, không tốn render.
3. `snapshot_code` / `review_frames` trên đúng các frame mà audit và recipe đã nêu.
4. Render rồi chạy `motion_audit(path, project_id=...)`.
5. `project_credits(project_id)` trước khi giao.

## audit_timeline — đọc timeline như runtime

| Mã | Đo gì | Ngưỡng / ghi chú |
|---|---|---|
| camera_oscillation | Bước di chuyển camera xen kẽ lớn–nhỏ từng frame (key dày + ease smooth) | > 0,12 → rung. Ví dụ thật: globe cũ 0,448 |
| camera_stops | Camera gần như dừng tại key giữa | tốc độ < 30% lân cận |
| texture_magnified | Số pixel màn hình trên mỗi texel lúc camera gần nhất | > 1,6 → bề mặt mềm (globe v3: 3,44) |
| plane_edge_visible | Frustum ra khỏi plane ảnh 3D | khung frame cụ thể. Ví dụ thật: Hạ Long 900–933, đã xác minh bằng crop |
| displacement_angle | Góc nhìn lệch pháp tuyến plane | > 22° → kéo giãn ở biên độ sâu |
| label_collision | Nhãn 3D chiếu xuống canvas chồng nhau hoặc chồng layer chữ | ví dụ thật: "01/12 · Rời DRO" × tiêu đề, frame 1272–1290 |
| bloom_haze, light_leak_coverage | Bloom quá mạnh; light leak > 35% thời lượng | |
| static_hold, long_shot, transition_repeat, transition_long | Nhịp shot | long_shot nhắc đo bằng motion_audit |
| reading_load, small_text, text_boxes_overlap, outside_safe_region | Tải đọc (~3 từ/giây), cỡ chữ trên điện thoại, hộp chữ chồng nhau, vùng UI nền tảng | heuristic chỉnh được |

## review_frames — đo chữ ở mức glyph

Mỗi frame được render ba kiểu: đầy đủ, bỏ hết chữ (plate), và từng lớp chữ đứng riêng (trắng trên đen). Kết quả cho mỗi lớp chữ:

- `visible_fraction`: phần glyph thực sự làm đổi ảnh cuối.
- `covered_fraction`: glyph bị vật khác che. Với chữ sau chủ thể đây là điều mong muốn, nên giữ người xem vẫn đọc được chữ.
- `same_as_background_fraction`: màu chữ trùng màu nền ngay sau nó, ví dụ chữ trắng trên lan can trắng. Phần này tách riêng khỏi "bị che" để không đọc nhầm bằng chứng.
- `contrast_median`, `contrast_p10`: tỉ lệ WCAG giữa màu chữ render thật và nền thật dưới từng pixel glyph. Shadow/outline làm chữ dễ đọc hơn con số này.
- Overlay trực quan: xanh là glyph thấy được, đỏ là bị che, vàng là tương phản dưới 3:1.

Ví dụ thật: dòng "gánh trái cây dạo phố" có tương phản trung vị 2,1:1 trên mặt đường sáng, nên khó đọc dù trông "có chữ".

## motion_audit — đọc video đã encode

Ảnh được thu nhỏ và làm mờ để grain phim và nhiễu encoder không bị tính là chuyển động. Tính chu kỳ sau khi trừ trung bình trượt 9 frame, để camera tăng tốc đều không bị nhầm là rung.

- `duplicate_frames`: frame lặp giữa chuỗi chuyển động. Ví dụ thật: clip Hội An lặp mỗi 5–6 frame vì nguồn 25fps.
- `periodic_judder`: bước chuyển động lặp theo chu kỳ 2–6 frame.
- `static_span`: đoạn gần như không đổi. Có thể là chủ ý; các phần tử nhỏ có thể vẫn đang chuyển động.
- `calm_shot`: shot dài hơn 3 giây có năng lượng chuyển động dưới 35% trung vị của phim. Ví dụ thật: Hạ Long 1,84 so với trung vị 6,91.
- `brightness_jump`: thường là chuyển cảnh flash.

## Giới hạn

Review chạy bằng runtime Remotion ở độ phân giải preview. Nhãn 3D được ước lượng bằng hộp chữ. Năng lượng chuyển động là chênh lệch độ sáng trung bình, không phải optical flow, nên vật nhỏ chuyển động trên nền tối cho số thấp.

## cut_audit — nghề dựng ở mỗi vết cắt

`cut_audit(path, project_id)` đo, cho mỗi vết cắt:
- điểm nhìn của frame cuối shot ra và frame đầu shot vào đã ổn định (saliency + chuyển động);
- `eye_jump` theo đường chéo khung;
- chuyển động quanh vết cắt, phân loại `on_action`, `static_to_motion`, `motion_to_static` hoặc `static`;
- nhịp độ dài shot (trung bình, hệ số biến thiên, xu hướng).

Kèm theo là contact sheet các cặp frame có đánh dấu điểm nhìn. Các finding:
- `eye_trace_jump`: cắt nhanh mà mắt phải nhảy xa.
- `fast_cutting_without_eye_trace`: ASL < 2 giây và độ nhảy trung bình lớn.
- `metric_rhythm`: các shot dài gần như bằng nhau.
- `few_cuts_on_action`: đa số vết cắt rơi vào lúc đứng yên.

Đây là bằng chứng cho tiêu chí eye trace và nhịp của Murch. Cảm xúc và câu chuyện vẫn đứng trước (xem EDITING_CRAFT.md).

## Dấu hiệu "rẻ tiền" và lệch phong cách (audit_timeline)

- **Dấu hiệu rẻ tiền:**
  - `simultaneous_entrances`: ≥3 phần tử vào cùng frame bằng cùng một kiểu.
  - `missing_entrance`: chữ xuất hiện giữa shot mà không có hiệu ứng vào.
  - `compound_motion`: ≥3 chuyển động khác nhau cùng lúc trên một lớp.
  - `number_overshoot`: con số bị bật vượt giá trị.
  - `dip_transition`: fade ra rồi fade vào.
  - `transition_variety`: hơn 3 kiểu chuyển cảnh.
- **Lệch direction:**
  - `off_direction_transitions`, `pacing_vs_direction`, `mixed_motion_language`.
  - `storyboard(check)` còn báo `negative_list_violation`, `reveal_not_found`, `technique_missing`, `breather_not_calmest`.
