# Kỹ thuật điện ảnh: từ ý tưởng đến xử lý hình (treatment)

Tài liệu này dạy cách *chọn* kỹ thuật, không phải liệt kê hiệu ứng. Công cụ `cinematic_catalog` trả cùng nội dung ở dạng có cấu trúc, kèm kiểm tra sẵn sàng (thư viện/project đã đủ tài nguyên chưa). `compose_cinematic` biên dịch kỹ thuật thành layer có tính toán hình học thật.

## 1. Vì sao video "chưa ấn tượng"

Sau nhiều vòng dựng thử, các lý do lặp lại đều nằm ở cách xử lý chứ không ở số hiệu ứng:

| Triệu chứng | Nguyên nhân thật | Hướng sửa |
|---|---|---|
| Footage + chữ dưới chân trông như slideshow | Đồ họa chồng lên hình, không tương tác với hình | Chữ sau chủ thể, nhãn bám theo vật, chiều sâu (ảnh 3D) |
| Mỗi cảnh như bắt đầu lại từ đầu | Không có không gian liên tục giữa các cảnh | Lao địa cầu → cắt flash vào mặt đất; bản đồ góc nối hành trình; layer gắn shot đi theo chuyển cảnh |
| Chữ to mà vẫn "phẳng" | Chữ vào không có nhịp, chỉ fade | mask_reveal / char_spring đo trước bằng layout_text |
| Nguồn lẫn lộn, màu rời rạc | Thiếu lớp hoàn thiện chung | Grain nhẹ toàn phim, light leak chỉ ở chuyển cảnh lớn |
| Cảnh dài mà không có gì xảy ra | Năng lượng chuyển động không đều | Đo `motion_audit`; cắt, thêm tiến trình (đường bay vẽ dần), hoặc chủ ý giữ |

## 2. Quy trình treatment

1. **Ý chính của phim** trong một câu: người xem phải nhớ điều gì.
2. **Một kỹ thuật chủ đạo (hero)** mang ý đó. Hành trình → không gian liên tục (globe_dive, map_journey, trajectory_3d). Con người/địa danh → text_behind_subject. Ký ức/tư liệu tĩnh → photo_3d. Tối đa 2–3 kỹ thuật hỗ trợ.
3. **Mỗi beat**: người xem cần hiểu gì → hình nào chứng minh → kỹ thuật nào giúp hiểu nhanh hơn → *frame kiểm tra* (giữa chuyển cảnh, lúc tới mốc, lúc camera gần nhất).
4. **Dựng bằng recipe**, chạy `dry_run` trước: kết quả kèm `audit` cho chính các layer vừa tạo.
5. **Vòng kiểm tra** (xem [REVIEW_AND_EVIDENCE.md](REVIEW_AND_EVIDENCE.md)): `audit_timeline` → snapshot/`review_frames` các frame đã định → render → `motion_audit` → `project_credits`.

Nguyên tắc: kỹ thuật nào chỉ để trang trí thì bỏ; định hướng, giải thích hoặc gắn thông tin vào hình mới giữ. Hiệu ứng nhiều không làm phim hay hơn.

## 3. Bản đồ kỹ thuật (tóm tắt — chi tiết trong `cinematic_catalog`)

| Kỹ thuật | Cho người xem | Cần | Công cụ |
|---|---|---|---|
| globe_dive | Đặt câu chuyện lên Trái Đất, đi liền mạch từ toàn cầu đến địa phương | Texture Trái Đất (thư viện), `geo` outline | `compose_globe` |
| map_journey | Không lạc hướng giữa các điểm đến | Natural Earth + toạ độ thành phố | recipe `map_journey` |
| trajectory_3d | Hiểu hình dạng một hành trình/quy trình | Điểm đường đi, (tuỳ chọn) thiên thể có texture | recipe `trajectory_3d` |
| photo_3d | Ảnh tĩnh có thời gian và chiều sâu | Ảnh + `estimate_depth` | recipe `photo_3d` |
| text_behind_subject | Chữ thuộc về cảnh, gắn với người/địa danh | SAM2 `track_subject` + `edit_subject` foreground | recipe `text_behind_subject` |
| kinetic_title | Câu ngắn có nhịp | Typography role | recipe `kinetic_title` |
| film_finish | Thống nhất nguồn, đánh dấu chuyển cảnh lớn | — | recipe `film_finish` |
| live_transitions | Chuyển cảnh theo hướng có lý do; đồ họa đi cùng shot | source handle | `update_shot` + `attach_shot` |
| speed_ramp | Nén chờ đợi, kéo dài khoảnh khắc quyết định | Footage có một đỉnh hành động | `retime_footage` |
| tracked_callout, hero_object_3d, match_cut | Chỉ chi tiết đang chuyển động; vật thể footage không có; nối hai shot bằng hình dạng chung | — | `compose_edit`, scene3d, `split_shot` |

## 4. Recipe và hình học được tính sẵn

- **text_behind_subject**: rasterize glyph thật bằng file font đóng gói, chồng lên alpha foreground (SAM2) của từng frame mẫu đã map về canvas theo cover crop, rồi chọn y để *tỉ lệ glyph bị che* đạt mục tiêu (mặc định 25%). Trả về dải che theo thời gian. Ví dụ thực: "HỘI AN" có trung vị 25%, dải 6–49%, vì hai người bán hàng di chuyển. Shot phải `motion: hold`, focus 0.5/0.5, fit cover.
- **photo_3d**: chọn khoảng cách camera và quãng lia sao cho khung nhìn luôn nằm trong plane ảnh, kể cả phần relief bị đẩy ra sau. Camera đối diện plane (truck/crane/push), không orbit. Trả về parallax gần–xa tính bằng pixel. Bản dựng tay trước đó bị lộ viền ở frame 900–933; recipe không lộ.
- **trajectory_3d**: tính frame tới từng mốc theo đúng cách runtime chạy vật thể dọc ống (smoothstep theo chiều dài cung). Nhãn hiện lúc tới, ẩn sau ~2,5 giây. Camera đi theo 3 pha thiết lập → bám → toàn cảnh, offset cố định theo thế giới để không quay ngoắt ở khúc cua; key dày với `camera_ease: linear`.
- **map_journey**: Natural Earth → SVG, mỗi chặng một layer gắn shot; các chặng trước giữ nguyên, chặng hiện tại vẽ dần kèm chấm chạy.
- **kinetic_title / film_finish**: đo xuống dòng và tràn khung trước; light leak tự đặt quanh flash/burn/zoom_through trong ngân sách thời lượng.

## 5. Thông số đã đứng vững trong render thật

- Địa cầu: `sun_lat/sun_lon` lệch tây vài độ so với điểm đến. Độ cao cuối ≥1 bán kính với texture 5400px (audit đo mức phóng texture: 3,4 px/texel ở độ cao 1 là đã mềm). Bloom strength≈.4, threshold≈.86. Marker nhỏ (0,008 bán kính) có vòng sóng.
- Quỹ đạo 3D: ống bán kính≈.0075, emissive≈1,5, bloom .35/.88. Ống dày hơn sẽ thành dải sáng mờ khi camera ở gần.
- Camera 3D: 2–4 key đặt tay dùng `smooth`; key dày (globe, chase) bắt buộc `linear`. Smooth trên key cách nhau 3 frame tạo rung ~10 Hz (độ dao động đo được 0,45, ngưỡng 0,12).
- Chữ sau chủ thể: đặt ở vùng nền phía trên đầu/nón; đặt giữa người thì chữ gần như mất hết.
- Footage 25fps trong timeline 30fps lặp frame mỗi 5–6 frame (motion_audit: duplicate_frames chu kỳ 6). Dùng `retime_footage` với interpolation flow nếu cảnh có chuyển động đều.

## 6. Giới hạn trung thực

Ảnh 3D là plane biến dạng theo depth tương đối, không phải hình học thật; vật mảnh phía trước bị kéo giãn. Địa cầu và quỹ đạo là minh họa, không theo tỉ lệ hay phép chiếu GIS. Audit và review là phép đo có ngưỡng heuristic; quyết định cuối thuộc về ý đồ của AI và người dùng.
