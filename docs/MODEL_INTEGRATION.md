# Claude, Codex và OpenAI dùng EditVideo

EditVideo cung cấp công cụ, dữ liệu quan sát và mã dựng cho AI. Model phụ trách hiểu nội dung, chọn cách kể và tinh chỉnh thẩm mỹ; runtime thực thi thao tác và trả hình ảnh, âm thanh cùng trạng thái thực. Hệ thống không chấm điểm đẹp hay thêm cổng phê duyệt.

## Thiết kế từ nghiên cứu

[Claude tool search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool) mô tả khám phá công cụ khi cần. [Codex skills](https://learn.chatgpt.com/docs/build-skills) tổ chức hướng dẫn và tài nguyên theo tác vụ. [OpenAI MCP](https://developers.openai.com/api/docs/guides/tools-connectors-mcp) mô tả gọi công cụ qua remote MCP và các transport được hỗ trợ. Từ đó, EditVideo dùng skill ngắn, references theo nhiệm vụ, catalog phân trang và schema lấy trực tiếp từ registry đang chạy.

Không thể bật tính năng API chỉ bằng cách viết vào prompt. Chế độ compact bên dưới là cơ chế MCP của EditVideo, không phải bằng chứng đã cấu hình tool search của Claude hoặc gọi API OpenAI.

[Claude vision](https://platform.claude.com/docs/en/build-with-claude/vision) và [OpenAI vision](https://developers.openai.com/api/docs/guides/images-vision) cho phép model phù hợp nhận ảnh. Host phải giữ các khối ImageContent/AudioContent khi chuyển kết quả MCP. Đường dẫn trong JSON không tự cung cấp khả năng nhìn hoặc nghe. Nếu model không hỗ trợ audio, dùng transcript và waveform với giới hạn riêng; không coi chúng là bằng chứng đã nghe.

## Bắt đầu nhanh

1. Kết nối MCP stdio bằng Python venv và `run.py`; xem `.mcp.json` để cấu hình đường dẫn trên máy.
2. Gọi `editvideo_bootstrap(task, project_id?, client)` để nhận tuyến công cụ và tóm tắt dự án hiện tại.
3. Gọi `editvideo_discover_tools(query, include_schema=true)` để lấy tên và tham số thật. Chỉ đọc reference của skill liên quan đến việc đang làm.
4. Lấy hình/âm thanh thực, dựng hoặc sửa với revision hiện tại, xuất video rồi quan sát lại để tinh chỉnh.

Ví dụ cho host ở chế độ compact:

```json
{"tool":"editvideo_bootstrap","arguments":{"task":"Dựng video kiến thức với depth và phụ đề","client":"claude"}}
{"tool":"editvideo_discover_tools","arguments":{"query":"depth","include_schema":true,"limit":5}}
{"tool":"editvideo_execute_tool","arguments":{"tool":"editvideo_estimate_depth","arguments":{"request":{"path":"<local RGB footage>","start":0,"end":3,"fps":12,"width":512}}}}
```

## Hai chế độ công cụ

Mặc định **full** công khai toàn bộ tool (127 ở bản hiện tại gồm nâng cấp chưa phát hành; `bootstrap` trả số hiện tại), giữ tương thích với các client đang dùng. Env `EDITVIDEO_TOOLSET=compact` chỉ công khai 7 công cụ đầu vào:

- `editvideo_bootstrap`
- `editvideo_discover_tools`
- `editvideo_execute_tool`
- `editvideo_get_job`
- `editvideo_get_media_task`
- `editvideo_read_design_preview`
- `editvideo_observe_media`

`discover_tools(query, offset, limit, include_schema)` trả tên, mô tả, annotations và schema từ registry thật; tìm kiếm chuẩn hóa tiếng Việt/Anh. `execute_tool(tool, arguments)` gọi đúng SDK tool sau validation, giữ image/audio blocks và trả `isError=true` khi thất bại. Nó từ chối tên tùy ý và dispatch đệ quy; các thao tác vẫn có quyền và tác động như tool gốc.

`editvideo://schema/<name>` trả riêng một schema, ví dụ `Scene3D`, `DepthRequest` hoặc `CreativeBrief`. Resource `editvideo://schemas` vẫn có để giữ tương thích. Không đoán tham số từ trí nhớ.

Đo trên máy: definitions full có 49.208 ký tự, compact có 4.964 ký tự, giảm **89,91%**. Đây là ký tự JSON đã serialize, **không phải** đo token, tốc độ, chi phí hoặc chất lượng model. Bằng chứng: `outputs/model-context-footprint.json`.

`.mcp.compact.example.json` là mẫu; điền đường dẫn Python/run.py và reconnect MCP nếu muốn dùng. Không tự thay cấu hình host đang chạy.

## Ngữ cảnh sáng tạo và đọc video

`creative_brief(request=None)` cung cấp schema và gợi ý suy nghĩ. Caller tạo các phương án về premise, cấu trúc hoặc ẩn dụ hình ảnh; lưu phương án đã chọn với audience, promise, payoff, tone, style và beats. Mỗi beat giữ narration, câu hỏi người xem, mục đích hình ảnh, loại cảnh, nguồn, trạng thái bằng chứng, motif và continuity. Brief được lưu thành JSON và script UTF-8; runtime không tự xác minh nội dung hoặc tạo word timing.

`read_edit_context(project_id, start, end, layer_offset, layer_limit)` đọc cửa sổ tối đa 15 giây: revision, shot/layer/cue/audio liên quan, metadata asset cần dùng và mapping narration → source theo tốc độ/offset. Layers có phân trang. Đây là dữ liệu để chọn vùng nhìn thực, không phải semantic analysis tự động. Khi neo callout, còn phải tính crop/fit và chuyển tọa độ source sang canvas.

Chuỗi thao tác: **bootstrap → index/inspect → creative brief → narration thực → word timing khớp → design kit → compose/patch/code → snapshot → render → observe/listen → sửa cụ thể**. Chỉ tải catalog, frames và references cần thiết. Dùng crop hoặc cửa sổ liên tục khi ảnh mẫu chưa đủ để hiểu chuyển động.

Về thẩm mỹ, xem [AESTHETIC_DIRECTION](AESTHETIC_DIRECTION.md), [DESIGN_LIBRARY](DESIGN_LIBRARY.md) và [PROFESSIONAL_VIDEO_PLAYBOOK](PROFESSIONAL_VIDEO_PLAYBOOK.md): hierarchy, framing, typography, màu, motion, âm thanh, continuity và cách nối hình với lời. Footage sinh hoặc đồ họa minh họa cần được phân biệt với tư liệu xác thực; biểu đồ cần đơn vị và nguồn.

Không gửi nhiều mutation cùng revision của một dự án. Batch các thay đổi liên quan bằng patch nguyên tử, rồi đọc revision mới. Reads độc lập có thể chạy song song; tác vụ GPU dùng shared lock. Brief và source snapshots giữ ý đồ sáng tạo qua các cửa sổ context.

## Khác biệt host và phạm vi đã kiểm tra

| Host | Cách dùng | Phạm vi |
| --- | --- | --- |
| Claude Code | MCP stdio + `.claude/skills/editvideo-agent` | Công cụ local; API host phải giữ đúng modality blocks. |
| Codex | MCP stdio + `.agents/skills/editvideo-agent` | Skill và references theo tác vụ; full hoặc compact do cấu hình lựa chọn. |
| OpenAI Responses | Remote MCP với transport reachable hoặc cầu nối client | Local stdio không phải remote URL. Chưa cấu hình tunnel/key hoặc kiểm tra trực tiếp API tài khoản trả phí. |
| Model không có vision/audio | Code, timeline và metadata | Không được suy ra đã nhìn/nghe nội dung từ đường dẫn file. |

MCP stdio thật đã kiểm tra discovery, validation, error và giữ ImageContent. Không chọn hay đổi model/provider/API key thay người dùng. Depth là tương đối với ổn định theo thời gian; 3D là cảnh hình học do caller tạo; HDR native chạy ở pipeline media riêng, còn compositor Chromium xuất SDR. Xem [COLOR_DEPTH_3D](COLOR_DEPTH_3D.md) để biết hợp đồng kỹ thuật.
