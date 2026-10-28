# Tài nguyên, nguồn mở và credit

## Thư viện local

`data/library/catalog.json` ghi mỗi file với `kind` (texture, model, geo, footage, image, audio, lut, font, data), license, credit, trang nguồn, độ phân giải, sha256 và ghi chú cách dùng.

- `resources(query, kind)`: tìm tài nguyên; đường dẫn tuyệt đối dùng thẳng cho `import_media`.
- `register_resource(path, kind, title, license, credit, ...)`: ghi nhận file mới. Chưa xác lập được license thì ghi `unknown`, không đoán.
- `register_resource(path, derived_from=<id>)`: file phái sinh (resize, crop, grade) kế thừa license của nguồn.
- `register_resource(seed=true)`: nạp các file đã có (NASA, Natural Earth, Commons qua `credits.jsonl`).

## Tìm và tải nguồn mở

1. `find_sources(query, provider="wikimedia"|"nasa", media)` chỉ tìm, không tải. Kết quả có license, tác giả, dung lượng, độ phân giải/thời lượng và trang nguồn.
2. Với NASA, gọi `source_files(asset_manifest)` để chọn bản và biết dung lượng.
3. **Trình người dùng** tên file, trang nguồn, license và dung lượng; chờ họ đồng ý rõ ràng cho từng file hoặc từng lô.
4. `fetch_source(url, provider, title, license, credit, source_page, kind, expected_bytes=...)`: tải một file, từ chối nếu dung lượng khác bản đã duyệt, rồi ghi vào thư viện và `credits.jsonl`.

## Credit từ hồ sơ, không từ trí nhớ

`project_credits(project_id)` lần ngược mọi asset mà timeline dùng: import → copy giữa project → tác vụ retime/màu/tách chủ thể/depth → file gốc trong thư viện. Kết quả gồm dòng credit đã gộp, chuỗi truy vết cho từng asset và danh sách asset chưa có hồ sơ. Ví dụ thật: lớp foreground hai người bán hàng được lần qua `mask_edit → subject → copy asset → color task` về "HoiAn Market" (Poiana11, CC0).

## Địa lý

`geo(name, outline_only=true)` trả vòng biên [lon, lat] (Natural Earth, rút gọn RDP) cho `compose_globe.outlines`. `geo(name, cities, neighbors)` trả bản đồ SVG đã chiếu (equirectangular hiệu chỉnh cos vĩ độ) cho layer svg hoặc `map_journey`.

## Lưu ý pháp lý

License được ghi theo thời điểm tải. Với mục đích thương mại, cần kiểm lại trang nguồn. NASA nhìn chung không giữ bản quyền tại Mỹ, nhưng có thể chứa tư liệu của bên thứ ba. CC BY/BY-SA yêu cầu ghi công; BY-SA còn kèm điều kiện chia sẻ tương tự.
