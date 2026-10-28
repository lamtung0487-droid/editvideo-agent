# Nghề dựng: nguyên tắc của giới chuyên nghiệp → thao tác và số đo trong hệ thống

## Nội dung
1. Thứ tự ưu tiên khi đánh giá một vết cắt (Murch)
2. Đường mắt nhìn và cắt nhanh (Fury Road)
3. Cắt trên chuyển động, đổi nhịp (Kurosawa)
4. Nhịp, montage, cắt theo nhạc
5. Chuyển động trong đồ họa (12 nguyên lý, ngôn ngữ chuyển động)
6. Title sequence: học từ các tác phẩm kinh điển
7. Màu: quy trình của colorist
8. Hộp công cụ chuyên nghiệp đã có trong cả Remotion và HyperFrames
9. Quy trình làm phim (checklist)

## 1. Thứ tự ưu tiên khi đánh giá một vết cắt

Walter Murch (*In the Blink of an Eye*) xếp sáu tiêu chí theo thứ tự quan trọng: **cảm xúc → câu chuyện → nhịp → đường mắt nhìn (eye trace) → mặt phẳng 2D của khung → không gian 3D của hành động**. Riêng cảm xúc được ông cho là hơn một nửa giá trị của vết cắt. Murch dùng danh sách này để chẩn đoán từ trên xuống. Lỗi ở các tiêu chí thấp thường không bị nhận ra nếu cảm xúc đúng; nhưng không tiêu chí thấp nào cứu được một vết cắt sai cảm xúc.

Áp dụng: hai tiêu chí đầu thuộc về AI và người dùng (storyboard: message, beat cảm xúc của từng khung). Hệ thống chỉ *đo* được nhịp và eye trace, qua `cut_audit` và `motion_audit`. Vì vậy số đo không bao giờ được thắng ý đồ.

## 2. Đường mắt nhìn và cắt nhanh

*Mad Max: Fury Road* (dựng: Margaret Sixel) có độ dài shot trung bình khoảng 2,6 giây mà vẫn dễ theo dõi. Lý do là đạo diễn yêu cầu đặt thông tin chính gần tâm khung ("crosshair framing"), nên mắt người xem không phải đi tìm điểm chính sau mỗi vết cắt.

Áp dụng:
- `cut_audit` đo điểm nhìn trước và sau mỗi vết cắt (saliency + chuyển động) và độ nhảy `eye_jump` tính theo đường chéo khung. Cắt nhanh (shot < 2 giây) có `eye_jump` > 0,35 thì đáng xem lại. Phim có ASL < 2 giây mà nhảy trung bình > 0,25 dễ thành "chaos cinema".
- Sửa bằng cách reframe shot vào (`focus_x/focus_y`, `reframe_footage`) để chủ thể rơi gần điểm nhìn cũ, hoặc giữ shot lâu hơn.
- Ví dụ thật: vết cắt tên lửa → tên lửa trong Artemis v3 chỉ nhảy 0,08, khớp đúng kiểu này.

## 3. Cắt trên chuyển động, đổi nhịp

Kurosawa tự dựng phim của mình và thường cắt *trong lúc chuyển động*, nên người xem bám theo chủ thể mà không thấy vết cắt. Ông hay kết cảnh bằng một hình tĩnh rồi cắt thẳng vào chuyển động để đổi nhịp (phân tích của Every Frame a Painting).

Áp dụng: `cut_audit` phân loại mỗi vết cắt là `on_action`, `static_to_motion`, `motion_to_static` hoặc `static` (đo bằng năng lượng chuyển động đã lọc grain). Nếu đa số vết cắt là static → static, hãy đặt điểm cắt vào giữa động tác (`move_boundary`). Dùng `static_to_motion` có chủ ý ở cuối mỗi phần.

## 4. Nhịp, montage, cắt theo nhạc

- Montage metric (độ dài đều) chỉ hợp khi bám lưới beat. `cut_audit` báo `metric_rhythm` khi hệ số biến thiên độ dài shot < 0,12.
- Nhịp tăng tốc về cao trào (trailer) hoặc giảm tốc (kết thư giãn): `rhythm.trend_s_per_shot`.
- Cắt theo nhạc: `beat_track` trả BPM, beat và downbeat. `snap_cuts_to_beats` dời từng điểm cắt về beat gần nhất trong ngưỡng cho phép, mặc định sớm hơn 1 frame để hình đổi ngay trước tiếng nhấn. Cắt đúng beat tạo năng lượng; cắt lệch beat tạo căng thẳng.
- Mỗi phim cần đúng một khoảnh khắc "thở" (breather) để các điểm cao trào có tác dụng. `storyboard(check)` cùng `render_path` kiểm khung breather có thật sự êm nhất không.

## 5. Chuyển động trong đồ họa

12 nguyên lý hoạt hình áp vào motion graphics:
- **Chuẩn bị (anticipation):** lùi nhẹ trước khi bật. Dùng `bezier` [.68,-.55,.27,1.55] hoặc [.6,-.28,.74,.05].
- **Quán tính (follow-through):** `bouncy`/`springy` chỉ dùng cho transform, không dùng cho opacity hay con số.
- **Chuyển động gối nhau (overlapping action):** stagger với độ lệch ngắn hơn hoạt ảnh, không đều nhau; vật chính vào trước.
- **Hành động phụ:** hạt, glow phụ hỗ trợ chứ không tranh với chuyển động chính.

Ngôn ngữ chuyển động (`easing`): `smooth`, `ease_out` cho vào, `ease_in` cho ra, `snappy` (power4.out), `dramatic` (expo.out), `bouncy` (back.out), `springy` (elastic.out), `dreamy` (sine.inOut), `ease_in_out`, `stepped` (stop-motion 6 bậc), và `bezier` tùy ý như graph editor của After Effects.

Thời lượng tham khảo: nhanh 0,2 giây, chuyên nghiệp 0,4, sang 0,6, điện ảnh 1–2. Push-in máy 4–8%. Dừng 1,5–2,5 giây ở khoảnh khắc chính. Lúc giữ cảnh nên có nhịp thở 1–2% (`pulse`) trừ khi phong cách chọn hold tĩnh.

Dấu hiệu rẻ tiền mà `audit_timeline` đo được:
- `simultaneous_entrances`, `missing_entrance`, `compound_motion`, `number_overshoot`;
- `dip_transition` (fade ra rồi fade vào);
- `transition_variety` (mỗi chỗ nối một kiểu);
- năng lượng đều đều, xem `motion_audit` / `calm_shot`.

## 6. Title sequence: học từ các tác phẩm kinh điển

- **Se7en (Kyle Cooper, 1995):** làm chủ yếu bằng tay và quang học, chữ khắc lên nhũ tương phim, dựng giật cục khớp với nhạc, phô bày chính cách nó được làm ra. Nó còn giới thiệu nhân vật phản diện ngay từ phần title.
  - Hệ thống: phong cách `collage_zine` / `film_noir`, film `dust`, easing `stepped`, `glitch` dùng tiết chế, cắt theo beat.
- **Saul Bass:** giản lược đồ họa đến một hình tượng trung tâm, màu phẳng, chuyển động hình học.
  - Hệ thống: `swiss_minimal`, `kinetic_title` reveal, một màu nhấn.
- **Powers of Ten (Eames):** một cú zoom liên tục qua các thang bậc. Đây là gốc của kỹ thuật `globe_dive` với camera Hermite liên tục.

Bài học chung: một ý tưởng hình ảnh xuyên suốt, chất liệu phục vụ tâm trạng, và nhịp khớp với âm thanh.

## 7. Màu: quy trình của colorist

Thứ tự trong DaVinci Resolve: **chuẩn hóa nguồn (log → display, gắn đúng color space) → cân bằng trắng và phơi sáng bằng scope → màu sơ cấp (lift/gamma/gain, contrast quanh pivot) → thứ cấp (cô lập da/trời) → look sáng tạo sau cùng**. Mở waveform cho độ sáng, parade cho cân bằng màu, vectorscope cho da (đường skin tone).

Hệ thống:
- `process_color` + LUT cho chuẩn hóa và look trên footage (pipeline gốc, ngoài trình duyệt).
- `inspect_color` cho scope.
- Layer `adjust`: chỉnh trên toàn bộ composite phía dưới, gồm exposure, contrast, saturation, temperature, hue, grayscale, sepia, blur, vignette, mix, ramp. Đây là xấp xỉ trong không gian hiển thị, giống adjustment layer, không thay được việc grade gốc trên footage.
- Đừng grade làm đổi ý nghĩa của footage bằng chứng.

## 8. Hộp công cụ chuyên nghiệp (Remotion và HyperFrames dùng chung runtime)

| Chức năng (tương đương) | Trong hệ thống |
|---|---|
| Adjustment layer (AE/Premiere) | layer `adjust` (backdrop-filter, có ramp vào/ra) |
| Graph editor, easing tùy chỉnh | `bezier` trên effect/keyframe; 11 easing có tên |
| Wiggle, máy cầm tay | effect `handheld` (nhiễu mượt có seed: amount, frequency, rotation) |
| Motion blur theo shutter | effect `motion_blur` (shutter angle, theo vận tốc của layer) và `retime_footage` motion_blur cho footage |
| Chromatic aberration, glitch | `rgb_split`, `glitch` (seeded) |
| Text animator (decode/scramble) | `decode`, `char_spring`, `mask_reveal`, `word_reveal`… |
| Film emulation | film `grain`, `dust`, `scanlines`, `vhs`, `light_leak` |
| Warp Stabilizer | `stabilize_footage` (KLT + RANSAC, smooth/lock, zoom tối thiểu có giới hạn) |
| Auto Reframe | `reframe_footage` (điểm bám SAM2 hoặc saliency + vùng chết) |
| Time remapping, speed ramp, optical flow | `retime_footage` |
| Roto, tách nền, tracking | `track_subject` (SAM2), `edit_subject`, `track_region` |
| Beat markers | `beat_track`, `snap_cuts_to_beats` |
| Track matte, chữ sau chủ thể | recipe `text_behind_subject` |
| Camera 3D, DOF, parallax | Scene3D, `photo_3d`, `estimate_depth` |

## 9. Quy trình làm phim (checklist)

```
- [ ] storyboard: message, arc, audience, mood, direction_id, breather, negative list, callback
- [ ] style_directions → apply_direction (restyle khi đã có layer)
- [ ] dựng: recipes (compose_cinematic dry_run), chuyển cảnh theo vocabulary của direction
- [ ] audit_timeline → sửa likely_problem; đọc check theo ý đồ
- [ ] snapshot/review_frames các frame đã định
- [ ] render → motion_audit + cut_audit → storyboard(check, render_path)
- [ ] project_credits → giao
```

Nguồn: Murch, *In the Blink of an Eye* (tóm lược tại [StudioBinder](https://www.studiobinder.com/blog/walter-murch-rule-of-six/), [No Film School](https://nofilmschool.com/2016/11/6-rules-good-cutting-according-oscar-winning-editor-walter-murch)); Fury Road ([Vashi Nedomansky qua Eugene Wei](https://www.eugenewei.com/blog/2015/5/31/creating-order-out-of-the-chaos-of-mad-max-fury-road), [No Film School](https://nofilmschool.com/how-to-watch-mad-max-fury-road)); Kurosawa ([Cutting on action](https://en.wikipedia.org/wiki/Cutting_on_action), Every Frame a Painting "Composing Movement"); Se7en ([Art of the Title](https://www.artofthetitle.com/title/se7en/)); quy trình màu ([DaVinci Resolve Club](https://davinciresolveclub.com/how-to-color-grade-davinci-resolve/)); chuyển động ([HyperFrames prompting: motion](https://hyperframes.heygen.com/prompting/motion.md), [transitions](https://hyperframes.heygen.com/prompting/transitions.md)); motion blur ([Remotion](https://www.remotion.dev/docs/motion-blur-guide)).
