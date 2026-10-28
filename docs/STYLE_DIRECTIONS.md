# Creative directions: đa dạng hóa thẩm mỹ một cách nhất quán

Một video "đẹp" không đến từ việc thêm hiệu ứng mà từ sự **nhất quán của một ngôn ngữ**: chữ, màu, đường cong chuyển động, nhịp cắt, bộ chuyển cảnh, chất liệu và những điều bị cấm. `style_directions` có 20 direction, mỗi direction là một khối máy đọc được; `apply_direction` ghi khối đó vào `design.direction`. Từ đó các recipe dùng nó làm mặc định và `audit_timeline` báo khi phim lệch khỏi nó.

## Chọn direction

Chọn theo khán giả, nền tảng và ý chính của phim, không chọn theo trend. Năng lượng (calm / medium / high) quyết định nhịp trước, rồi mới đến easing.

| Năng lượng | Direction |
|---|---|
| calm | cinematic_documentary, premium_product, film_noir, nature_calm, luxury_fashion |
| medium | tech_launch, editorial_magazine, swiss_minimal, data_journalism, flat_vector_explainer, retro_vhs, crt_terminal, corporate_clean, tutorial_code |
| high | travel_energy, kinetic_hype, collage_zine, action_trailer, kids_playful, breaking_news |

## Mỗi direction gồm

- `look`: style kit, palette, font tiêu đề/nội dung, tinh chỉnh chữ (weight, tracking, line-height), màu nhấn ghi đè.
- `motion`: đường cong, thời gian vào/ra, tỉ lệ stagger, nhịp thở khi giữ cảnh, push-in máy, có cho phép bật vượt (chỉ transform) hay không.
- `pacing`: số giây cho mỗi ý, thời gian dừng ở khoảnh khắc chính.
- `transitions`: một kiểu chính, vài điểm nhấn, tỉ lệ cắt thẳng, live/freeze.
- `titles`, `captions`: hiệu ứng tiêu đề; tông caption (hype, corporate, tutorial, storytelling, social) kèm cỡ chữ và chế độ.
- `finish`: grain, light leak (chỉ ở điểm nhấn), vignette, look (vhs, scanlines, dust), gợi ý grade.
- `composition` và `negative`: quy tắc bố cục và danh sách cấm. Đưa danh sách cấm vào storyboard để `storyboard(check)` tự phát hiện vi phạm.
- `hero_techniques`: kỹ thuật chủ đạo hợp với direction (xem CINEMATIC_TECHNIQUES.md).

## Áp dụng

1. `apply_direction(project, rev, id, dry_run=true)` để xem trước. `overrides` sửa bất kỳ phần nào, ví dụ `{"look": {"palette_id": "sand"}}`.
2. `restyle=true` khi đã có layer:
   - đổi đường cong và thời lượng vào/ra theo motion;
   - giãn các phần tử vào cùng lúc (vật chính trước, độ lệch không đều và ngắn hơn hoạt ảnh);
   - thêm nhịp thở cho tiêu đề chính.
3. `finish=true` thêm grain, look và light leak ở các chuyển cảnh điểm nhấn.
4. Chuyển cảnh và nhịp vẫn do AI quyết định ở từng chỗ nối, theo `follow.transitions` / `follow.pacing`. `audit_timeline` báo `off_direction_transitions`, `pacing_vs_direction` và `mixed_motion_language`.

## Ví dụ thật

Cùng film Việt Nam v3:
- **Đối chiếu với `travel_energy`:** shot trung vị 6 giây so với chuẩn 1,5–3 giây; burn và push_up nằm ngoài bộ chuyển cảnh.
- **Đối chiếu với `nature_calm`:** mọi chuyển cảnh mạnh (flash, whip, zoom_through, burn) đều ngoài bộ chuyển cảnh, vì phong cách này chỉ dùng dissolve.

Cùng một nội dung nhưng hai cách xử lý hoàn toàn khác nhau, và hệ thống chỉ rõ phải đổi gì.
