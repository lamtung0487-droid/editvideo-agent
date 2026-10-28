# Hướng dẫn thẩm mỹ và hiểu video cho agent

Đầu tiên xác định ý người xem cần hiểu, cảm xúc phù hợp và nội dung hình thực sự giải thích. Dùng `aesthetic_packet`/`video_director` với frame, audio và tham chiếu; chính AI đa phương thức thực hiện suy luận. Không có điểm đẹp hay bước xin duyệt.

Đọc thêm [thư viện thiết kế và24 cách phối hợp](DESIGN_LIBRARY.md). Dùng design_catalog/read_design_preview để chọn font/palette/style từ hình thật, layout_text để đo chữ và apply_design/compose_graphic để dựng. Điều chỉnh vai trò trước khi thêm decoration.

## Quan sát theo ba mức

- Toàn video: index, cấu trúc đoạn, câu chuyện, nhịp phân bố ý, thay đổi palette/ánh sáng và những chỗ thiếu hình giải thích.
- Đoạn 2–12s: chuỗi frame và audio để kiểm tra động tác/cut, chữ vào đúng lời, chuyển động liên tục, thời gian đọc và giọng có bị âm khác che.
- Chi tiết: crop từ nguồn để đọc chữ, viền, nhãn biểu đồ, crop chủ thể, mũi tên/cấu trúc diagram; ghi coordinate mapping.

Candidate cuts và audio energy không xác lập ý nghĩa hoặc BPM. Khoảng lấy mẫu chưa bao phủ hành động nhanh thì gọi một đoạn hẹp hơn. Ví dụ “frame 2 và 3 thay đổi vị trí tay” là bằng chứng; “người này đã lấy đúng vật” cần quan sát diễn biến và đối tượng đủ rõ.

## Nhìn bằng mục đích

| Câu hỏi | Tìm trong ảnh/âm thanh | Thao tác có thể dùng |
|---|---|---|
| Người xem nhìn đâu đầu tiên? | Kích thước, độ sáng, tương phản, khoảng trống, hướng chuyển động | Đổi size/x/y/z, opacity/blur nền; crop/focus |
| Chữ có đọc được trên thiết bị đích? | Số chữ, font, tương phản với nền thay đổi, tốc độ xuất hiện | Font/background/line break; kéo dài hold; split cue |
| Hình có giúp hiểu lời? | Hình giải thích cơ chế, ví dụ hay chỉ trang trí | Chọn tư liệu khác; flow/diagram/chart có dữ liệu |
| Cut có lý do? | Cuối cụm ý, hành động, thay đổi khoảng cách nhìn | Move boundary, split shot, đối chiếu word timestamps |
| Chuyển động có hỗ trợ ý? | Hướng nhất quán, tránh nhiều điểm tranh chú ý, giữ ổn định khi đọc | Tra catalog theo intent; bớt effect, chỉnh easing/duration |
| Màu/ánh sáng có nhất quán? | Palette và tonal hierarchy giữa các shot, không mất chi tiết | Grade có mức nhẹ, nền/token chung, reference images |
| Âm thanh có phục vụ nội dung? | Giọng rõ, khoảng lặng, SFX có đúng mốc, fade cuối | Audio placement/gain/fade/duck; nghe trước/sau |
| Thông tin có giữ ý nghĩa nguồn? | Crop mất bối cảnh, grade bóp màu có nghĩa, chart không đúng scale | Contain, range đúng, nhãn/nguồn rõ, phân biệt minh họa |

Một màu rực không tự tạo thẩm mỹ tốt. Một cảnh trơn có thể phù hợp nếu nhấn đúng ý và cho thời gian hiểu. Không gán kết luận kỹ thuật điện ảnh chỉ từ tên hiệu ứng.

## Phân tích có thể chuyển thành edit

Viết theo cấu trúc ngắn:

1. **Ý định:** người xem cần hiểu điều gì ở đoạn này.
2. **Bằng chứng:** timestamp/frame/region và audio cụ thể.
3. **Diễn giải:** ảnh hưởng đến khả năng hiểu/đọc; nêu phần chưa chắc.
4. **Sửa:** operation hoặc code cần đổi, thông số và lý do chọn.
5. **Xem lại:** frame lúc bắt đầu, giữa và cuối thay đổi, cùng đoạn audio tương ứng.

Ví dụ: “Ở 3.2s, nhãn góc phải trùng nền sáng và che đầu mũi tên; chuyển nhãn lên y=.12, nền #102322, màu #ffffff, giảm glow, snapshot frame 96/108/120.” Đây là chỉ dẫn dựng cụ thể, không là điểm số hay phê duyệt.

## Sử dụng tham chiếu và effects

Tham chiếu giúp xác định hierarchy, palette, spacing, scale và nhịp; không mặc nhiên sao chép các chi tiết không phù hợp nội dung. Ghi lựa chọn vào `set_design` và áp những token cần thiết cho layers/code. `design.intent` là hướng dẫn cho AI, không tự động tạo layout.

Tra catalog, xem preview, chọn amount/duration phù hợp. Default trong atlas nhằm thấy kỹ thuật rõ; không phải thông số tối ưu cho mọi video. Hiệu ứng màu trên footage evidence phải giữ ý nghĩa; highlight cần màu chữ tương phản; typewriter dành cho text ngắn và không thay thế việc cho thời gian đọc. Khi nhiều mask cùng property, runtime có thể lấy mask sau cùng.

Một beat nên có một chuyển động chủ đạo. Kết hợp nhẹ có ích: fade+rise cho nhãn, progress cho diagram, shadow+border cho inset. Không thêm shake/glow/zoom lên mọi lớp. Khi cần nhiều loại animation mới, viết module source có thể seek theo frame rồi nhìn output thực.


## Chuyển hướng thẩm mỹ thành thao tác chuyên nghiệp

[Playbook](PROFESSIONAL_VIDEO_PLAYBOOK.md) và professional_toolkit nối từng mục đích story/composition/caption/source/audio với recipe thực thi. Đánh giá cùng câu hỏi xem video cần giúp người xem hiểu gì, ở đâu mất context hoặc khó đọc/nghe, và edit nào giải quyết đúng bằng chứng. Không dùng onset/cut count/residual làm beauty/retention verdict. Với portrait, thử viewport lớn hơn khi contain để quá nhiều khoảng trống; phải map lại tracking point theo crop/scale mới và kiểm chủ thể bị cắt. Caption không có page hoạt động phải ẩn cả nền; nhãn/marker nên ôm kích thước chữ, tránh rectangle lớn trống.

## Từ thẩm mỹ đến xử lý hình và bằng chứng

Thẩm mỹ ở đây không phải chọn hiệu ứng đẹp mà là chọn cách xử lý hình mang được ý chính của phim. Đọc [kỹ thuật điện ảnh](CINEMATIC_TECHNIQUES.md): mỗi phim chọn một kỹ thuật chủ đạo (không gian liên tục cho hành trình, chữ thuộc về cảnh cho con người/địa danh, chiều sâu cho ảnh tĩnh), mỗi beat ghi trước các frame sẽ kiểm tra. Sau khi dựng, dùng [vòng bằng chứng](REVIEW_AND_EVIDENCE.md): `audit_timeline` → `review_frames` → render → `motion_audit`. Những gì ảnh tĩnh không cho thấy (rung giật, frame lặp, viền lộ thoáng qua, nhãn chồng tiêu đề) phải được đo, không phải đoán.
