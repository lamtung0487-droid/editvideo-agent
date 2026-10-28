# Phạm vi xây dựng từ đặc tả v0.2

Đầu vào: `Bao_cao_Phan_tich_Agent_Dung_Video_v0.2.docx`. Hướng triển khai được người dùng yêu cầu: tập trung vào hệ thống dựng và chất lượng nội dung; giảm phần thiên về kiểm duyệt, đánh giá, đo lường và phê duyệt. Loại video ưu tiên đã được chọn: thuyết minh/kiến thức.

## Sản phẩm chính sau khi làm rõ yêu cầu

Hệ thống để AI trực tiếp đọc media và dựng bằng code trên **Hyperframes + Remotion**. MCP/CLI là cửa thao tác chính. Studio từ bản xây trước được giữ như tùy chọn legacy.

- MCP trả pixel khung hình có timestamp và WAV snippet để agent nhìn/nghe rồi quyết định.
- Timeline edits theo revision; code edits theo SHA256, có history và source snapshot của từng render.
- AI viết React/TSX hoặc HTML/CSS/GSAP trực tiếp; xem ảnh từ code trước khi encode toàn video.
- Engine chạy local với dependency pin; FFmpeg mix audio và làm backend dựng đơn giản.
- Skill Claude/Codex hướng dẫn voice timing, caption refinement và source contract.
- Nâng cấp 12/10/2026: 50 effects/catalog/atlas, đa tầng/keyframes/transitions/audio, temporal index, crop mapping, ASR local, tracking vùng và guide thẩm mỹ. Xem [nghiên cứu và phạm vi thực](RESEARCH_AND_UPGRADE.md).

## Giữ và thực thi

| Thành phần đặc tả | Triển khai |
|---|---|
| Voice-first | Audio thật chuẩn hóa mono 48 kHz trước khi gán cảnh/phụ đề |
| Tách quyết định sáng tạo và thi hành | Agent nhìn pixel, quyết định và viết source; runtime thực thi source snapshot |
| Beat khác shot | Beat lời nói riêng với shot hình; sửa điểm cắt không cắt audio |
| Timeline có đơn vị rõ | Frame nguyên 30 fps, audio sample, khoảng nửa mở |
| Biên tập hình–lời | Agent observe pixels và sửa shot; planner theo nhãn là điểm xuất phát; model planner tùy chọn |
| Hồ sơ đầu ra | Dọc/ngang/vuông Full HD, preview nhẹ |
| Giọng và phụ đề tiếng Việt | TTS hai giọng, giọng riêng/SRT, chữ phát âm riêng, khai báo timing ước lượng |
| Âm thanh theo vai trò | Voice/music riêng, fade, duck và chuẩn hóa mix |
| Vùng chữ, crop, motion | Font Unicode, subtitle wrap, safe margins, contain/cover và focal point thủ công |
| Tư liệu có nguồn | Metadata nguồn/hash và manifest; người dùng chọn vai trò, không có cổng quyền bắt buộc |
| Sửa bản dựng | MCP sửa shot/crop/motion/clip offset/cut/cue/overlay và React/HTML; giữ bản cũ |
| Kiểm tra file dùng thật | Source range/timing trước render; decode toàn MP4 sau render; codec/kích thước/frame/audio |
| Giao nhận | MP4 + SRT + timeline + nguồn + render settings + ZIP |

## Lược bỏ theo yêu cầu

- `SCRIPT_APPROVED`, `FINAL_APPROVED`, khóa người duyệt và cổng duyệt từng bước.
- Critic chấm điểm thẩm mỹ, mô hình chấm ảnh/GPU aesthetic, bộ calibration và rubric sáu chiều.
- Benchmark B0–B3, editor chấm mù, Spearman/alpha, retention research và SC1–SC7 như cổng xuất.
- Dashboard accepted-delivery-rate, chi phí/video được chấp nhận, P50/P95 và nghiệm thu nghiên cứu.
- Rights approval engine, quyền tenant nhiều tầng, escalations và hồ sơ chứng cứ phê duyệt.
- Reservation/budget ledger phức tạp khi chưa có luồng tạo clip trả phí.
- Mạng 12 service/agent, framework điều phối phân tán và loop critic/repair tự động.

Nút xem video phục vụ chỉnh nội dung và hình ảnh, không phải hành động phê duyệt. File được xuất ngay khi cấu trúc/tư liệu hợp lệ và decoder đọc được. Không có điểm chất lượng quyết định cho phép tải.

## Chất lượng được ưu tiên trong code

1. Không sửa lời đọc trong planner; giữ dấu câu ở phụ đề.
2. Ưu tiên đổi cảnh ở cuối câu hoặc cuối mệnh đề, không cắt nhịp cứng khiến cụm ý bị lẻ.
3. Khi thiếu hình có liên quan, thể hiện bằng đồ họa chữ rõ ràng; không chọn ngẫu nhiên tư liệu.
4. Giọng đọc xuyên suốt; audio nguồn được đưa vào có chủ đích bằng project import hoặc audio clips.
5. Nhạc giảm theo giọng, có fade để đầu/cuối êm.
6. Crop/contain để người dùng bảo toàn chi tiết; hình chứng cứ mặc định không zoom.
7. Người dùng nhìn và sửa thẳng cảnh/phụ đề; không cần giải thích cho critic hoặc chờ approval.

Không khẳng định đã đạt chất lượng editor chuyên nghiệp. Bộ chọn local chưa nhìn pixel; agent gọi MCP observe để nhận pixel thật. Timing giọng riêng thiếu SRT là ước lượng, khai rõ trong metadata.

## Hướng mở rộng khi có tư liệu sản xuất

Đã thực thi ASR local, temporal inspection, tracker vùng + SAM2 segmentation/corrections, LaMa inpainting, alpha composition/crop bám, infographic/effects/audio và adapter sinh clip ComfyUI/Runway. Adapter chưa chạy live provider; đọc [hướng dẫn](SUBJECTS_AND_GENERATION.md). Còn cần khi có nhu cầu: forced alignment tiếng Việt, semantic retrieval/re-identification, temporal neural inpainting, moving source-handle transitions. Không đưa lại bộ máy chấm điểm/phê duyệt làm điều kiện dựng.


Bổ sung dựng chuyên nghiệp:64 MCP tools/69effects/14layer kinds,16 executable editorial recipes, paged word captions, tracked SVG callout, audio acoustic evidence/procedural accents và master/ducking control. Xem [professional playbook](PROFESSIONAL_VIDEO_PLAYBOOK.md) cho phần đã có và các khoảng trống hậu kỳ sâu.

[Thư viện thiết kế](DESIGN_LIBRARY.md):16 font families/23faces offline,24 palettes,16 style kits,10 type roles,12 motion directions,10 components,12 patterns và24 original icons. Roles, local FontFace loading/export, glyph/advance evidence và palette harmony generator đã tích hợp; không thêm điểm đẹp/cổng duyệt.
