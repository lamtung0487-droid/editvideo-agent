# Thư viện thiết kế video cho Claude

Thư viện này cung cấp tài nguyên thật, tham số, mẫu render và cách phối hợp. Claude đọc hình/âm thanh, chọn ngôn ngữ hình ảnh và sửa composition qua MCP. Không có studio, điểm thẩm mỹ hay cổng phê duyệt.

## Nghiên cứu và quyết định xây dựng

[Google Fonts: phối typeface](https://fonts.google.com/knowledge/choosing_type/pairing_typefaces) gợi ý khai thác size/weight/style của một family trước khi thêm family khác; dùng font thứ hai khi nó giải quyết một vai trò khác. Quyết định triển khai: font có **vai trò**, thay vì chọn ngẫu nhiên từng shot. Các cặp font dưới đây là đề xuất thiết kế của EditVideo, không phải chứng nhận từ Google.

[Be Vietnam Pro upstream](https://github.com/bettergui/BeVietnamPro) chú trọng chữ và dấu tiếng Việt. Quyết định triển khai: kiểm tra cmap trên file tải thật, không chỉ tên font/subset quảng cáo; kiểm thử toàn bộ U+1EA0–U+1EF9 và Đ/Ơ/Ư. DM Sans trong revision khảo sát thiếu các glyph này nên không được đưa vào registry. Kiểm tra này không xác lập hỗ trợ toàn bộ Unicode hoặc mọi ngôn ngữ.

[Material: type roles](https://m3.material.io/styles/typography/applying-type) và [color roles](https://m3.material.io/styles/color/the-color-system) tổ chức token theo mục đích. EditVideo dùng ý tưởng vai trò, tự xây thang chữ và palette cho video; không bê kích thước giao diện app sang video. Màu đồ họa tách khỏi màu tư liệu: đổi palette không tự grade footage.

[Remotion: local fonts](https://www.remotion.dev/docs/fonts) hướng dẫn chờ font tải trước khi render. Cả hai engine dùng FontFace local, chờ load xong rồi dựng; lỗi tải phải báo lỗi. Font/giấy phép đi cùng source/export, không dựa CDN hoặc font hệ điều hành. Alias `EV <id>` tránh một font cài trên máy che mất lỗi đóng gói.

[W3C: contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) nêu 4.5:1 cho chữ thường và 3:1 cho chữ lớn trong phạm vi WCAG. Thư viện tính tương phản sRGB của swatch đặc và chọn các cặp chữ nền >=4.5; **không tuyên bố video đạt WCAG**. Nền video thay đổi, độ trong suốt, kích thước trên điện thoại và compression cần nhìn lại bằng frame thật.

[Blackmagic: training](https://www.blackmagicdesign.com/products/davinciresolve/training) bao phủ dựng, màu, âm thanh và motion graphics. Kiến trúc ở đây kết nối các kỹ năng đó thành những quyết định có thể chỉnh bằng code; các preset CSS không tương đương một pipeline compositing/grade 3D, HDR hoặc một khóa học điện ảnh hoàn chỉnh.

## Tài nguyên đã tích hợp

| Thư viện | Quy mô | Claude sử dụng |
|---|---:|---|
| Font offline | 16 family, 23 file/face | `design_catalog(kind="font")`, `layout_text`; xem glyph, weight/italic thật, file SHA/license |
| Palette | 24 bảng màu với 7 vai trò | `design_catalog(kind="palette")`; background/surface/text/muted/accent/secondary/on_accent |
| Màu tự tạo | 5 harmony × dark/light | `derive_palette(seed,harmony,tone)` trả token và contrast; agent chọn/tinh chỉnh |
| Bộ phối font–màu | 16 style kit | `apply_design` với override palette/heading/body; từng vai trò vẫn sửa bằng `set_design` |
| Thang chữ | 10 vai trò | display/headline/title/body/caption/label/source/data/quote/code |
| Hướng chuyển động | 12 tổ hợp có mục đích | Tra `motion`; chọn hiệu ứng cần dùng, không tự stack toàn bộ |
| Đồ họa bố cục | 10 component chạy thật | `compose_graphic`: title/quote/statistic/chapter/source_card/two_column/steps/lower_third/keyword/end_card |
| Nền vector | 12 pattern | grid/dots/stripes/diagonal/checker/crosshatch/hexagons/rings/waves/contour/speckles/gradient |
| Biểu tượng vector gốc | 24 icon | play/pause/check/close/arrows/info/question/lightbulb/book/eye/camera/mic/clock/link/chart/code/location/star/heart/volume/search/target/spark |
| Hiệu ứng portable | 69 | `effect_catalog`; 7 mới bên dưới cùng 62 kỹ thuật trước |
| Công cụ MCP | 64 tổng (compact7entry) | Tích hợp vào đọc video, tracking, mask/inpaint, sinh footage, dựng, nghe/xem và chỉnh source hiện có |

Font: **Be Vietnam Pro, Noto Sans, Noto Serif, Manrope, Archivo, Oswald, Bitter, Lora, IBM Plex Mono, Comfortaa, Roboto Slab, Inter, Source Sans 3, Vollkorn, Lexend, Montserrat**. Normal variable axes được ghi trong registry; 3 family có face italic thật trong gói: Be Vietnam Pro, Noto Serif, Lora. Be Vietnam Pro/IBM Plex Mono có normal400/600/700. Không quảng cáo italic/weight chưa đóng gói; TypeStyle từ chối yêu cầu đó. Không phân phối Segoe UI/Arial/font Windows.

Font tải nguyên trạng từ `google/fonts` commit **bd8f81ddb5c74d5c8897b36ad88b440266245103**: 15 family SIL OFL1.1, Roboto Slab Apache2.0 kèm copyright. `assets/fonts/manifest.json` ghi URL, kích thước, axes, SHA256, giấy phép. Khoảng12.6MB font; không có model nặng/API key. `scripts/build_font_library.py` dùng GitHub CLI để tái tạo từ commit đã pin; không tự đổi sang latest khi render.

## Kỹ năng thẩm mỹ cần dùng

1. **Ngôn ngữ hình ảnh:** chọn mục đích, người xem và thiết bị trước. Một câu hỏi kiến thức có thể dùng `vietnam_knowledge` hoặc `science_lab`; tư liệu cần nguồn và khoảng lặng có thể dùng `documentary`/`editorial_paper`. Những tên này là điểm bắt đầu, không giới hạn nội dung.
2. **Thứ bậc:** một ý chính nhìn thấy đầu tiên, sau đó minh họa, cuối cùng chi tiết/nguồn. Tạo chênh lệch bằng size, weight, vị trí và khoảng trống; tránh tất cả chữ đều đậm, sáng và chuyển động.
3. **Tiếng Việt:** giữ dấu, chọn weight có thật, đo ascent/descent; để khoảng trên/dưới tránh cắt “Ấ”, “Ữ”, “ỵ”. NFC-normalize trước xử lý grapheme. Đo câu thật, không dựa số ký tự. Mono dành cho code/đơn vị, condensed dành cho tiêu đề ngắn; không mặc định đặt cả đoạn phụ đề bằng Oswald.
4. **Dòng chữ:** chia theo đơn vị ý nghĩa, giữ cụm danh từ, tên riêng và số–đơn vị. `layout_text` đo FreeType và đề xuất dòng; Chromium có thể wrap khác. Đặt newline có chủ ý, nhìn snapshot và sửa. Không đổi nội dung lời thoại để vừa template.
5. **Màu:** dùng background để ổn định tổng thể, surface cho vùng đọc, text/muted theo thứ bậc, accent cho một trọng tâm. Màu mang ý nghĩa dữ liệu phải đi cùng nhãn/hình; không dùng đỏ/xanh làm dấu hiệu duy nhất. HSL harmony là máy tạo lựa chọn, không mô hình tâm lý màu hay màu perceptual-uniform.
6. **Bố cục:** căn các trục, giữ gutter và vùng an toàn; kiểm tra mặt/ngón tay/vật chính/UI TikTok. Safe region chỉ là heuristic chỉnh được. Khoảng trống cần phục vụ đọc và chủ thể, không chỉ lấp đầy bằng texture/icon.
7. **Chuyển động:** chọn điểm vào, hold và điểm ra theo lời/cut. Một chuyển động trọng tâm mỗi nhịp; hỗ trợ sự chú ý bằng fade/mask vừa đủ. Chỉ animate so sánh hoặc số liệu đã cung cấp; interpolation không tạo ra quan sát mới.
8. **Nhịp và thẩm mỹ xuyên thời gian:** xem đầu–giữa–cuối animation, cut sát cạnh, nghe lời và SFX. Nhìn freeze frame không xác lập flicker, tempo hay thời gian đọc. `inspect_window`, `extract_clip`, `analyze_motion` giúp quan sát; flux không phải BPM và residual không phải điểm đẹp.
9. **Phối tư liệu:** lời giải thích quyết định footage, inset hay diagram. Nguồn có crop/grade/mask phải giữ ý nghĩa. Generated footage là minh họa; chữ chính xác, biểu đồ và nguồn dựng bằng vector/text độc lập để Claude sửa được.
10. **Nhất quán có biến thiên:** giữ body/caption và màu vai trò xuyên video; đổi layout/cỡ/ảnh khi ý đổi. Cần đổi ngữ cảnh mới đổi family, không thay font mỗi shot. Xem lại bản dọc và ngang riêng.

Thang chữ mặc định ở short side1080px: display112, headline84, title64, body42, caption54, label32, source28, data64, quote66, code34. Các số này là preset chỉnh được, không tiêu chuẩn nền tảng. Runtime nhân theo short side; `font_size` explicit vẫn giữ nguyên khi không có `typography_role`. Mỗi TypeStyle có size/weight/italic/line_height/tracking và variation_axes cho trục thực có trong face (ví dụ wdth/opsz), kiểm range từ metadata; wght điều khiển bằng weight. Có thể truyền cùng variation_axes vào layout_text để đo đúng lựa chọn. Explicit opsz tắt optical sizing tự động. `font_id` của layer override family từ role; chọn weight có thật trước khi override.

## Phối hợp cho cảnh chuyên nghiệp

| Mục đích | Phối chữ và màu | Hiệu ứng / bố cục | Tránh |
|---|---|---|---|
| Mở câu hỏi kiến thức | Be Vietnam Pro + forest | title + line_reveal; hold câu hỏi | Text nhỏ + 3 effect đồng thời |
| Chốt một khái niệm | Archivo + electric | keyword + word_reveal | Nháy sáng theo mọi từ |
| Giải thích kỹ thuật | Oswald title / Source Sans body + blueprint | steps + grid rất nhẹ | Grid đậm cạnh tranh với diagram |
| Trích dẫn văn hóa | Lora / Source Sans + paper | quote + fade; marker/underline một cụm | Viết cả đoạn bằng typewriter |
| Phần lịch sử | Noto Serif / Be Vietnam + amber | chapter; paper_grain .035, nguồn | Sepia làm sai màu vật chứng |
| Một con số có đơn vị | Mono data / Noto Sans body + slate | statistic; nguồn; counter giữ số thật | Đếm từ0 nếu ngụ ý tăng trưởng giả |
| Đối chiếu | Inter + cobalt | two_column; label, scale thống nhất | Màu như bằng chứng duy nhất |
| Quy trình | Roboto Slab / Noto Sans + science | steps/flow; reveal theo bước | Animate bước trước lời giải thích |
| Cận chi tiết | body ổn định, surface tối | PiP + border mảnh + fade | Zoom+pan+shake cùng lúc |
| Nhãn chuyên gia | body rõ, nền đặc | lower_third + slide_spring nhỏ | Nhãn che miệng/tay, spring quá lớn |
| Theo chủ thể | label ngoài vùng đối tượng | tracked_callout, target_keyframes | Bỏ qua mất track/crop mapping |
| Captions theo lời | body bold + nền đặc | caption pages + active-word box | Stagger giả thay word timestamps |
| Ảnh tư liệu cần thở | font nguồn ổn định | focus_zoom .04 / reference | Chuyển động che mất bối cảnh |
| Tiêu đề sự kiện | Montserrat + magenta | word_reveal; text_gradient rất ít | Gradient mất tương phản trên footage |
| Phỏng vấn mềm | Manrope + rose | quiet fade, ít texture | Icon trang trí trên mặt |
| Chủ đề thiên nhiên | Bitter / Noto Sans + moss | ảnh chủ đạo, source, fade | Overlay rực phá màu thực địa |
| Chương mới | title và label khác vai trò | chapter + wipe16frames | Transition tại mỗi cut |
| Tư duy/ý tưởng | Comfortaa / Lexend + lavender | icon có ý nghĩa + line_reveal | Quá nhiều ký hiệu chưa giải thích |
| Mã/đơn vị | IBM Plex Mono + arctic | code/data role + underline | Mono cho toàn bộ narration |
| Card nguồn | Source Sans3 + surface | source_card, URL/tác giả rõ | Nguồn quá nhỏ, mất thời gian đọc |
| Luận điểm phản biện | Archivo / Inter + noir | một accent, bố cục cố định | Flash/invert khiến thông tin mơ hồ |
| Kết đoạn | font bộ phim đang dùng | end_card; payoff; audio fade | CTA che kết luận |
| Trang giấy | serif heading + paper | speckles/paper_grain opacity thấp | Noise chuyển động gây flicker |
| Âm nối cảnh | type/body giữ nhịp | J/L/sound_bridge + duck | Double narration, SFX tại mọi cut |

Không tự ghép tất cả trong một hàng: chọn kỹ thuật cần thiết cho ý. Âm thanh, tracking, segmentation và sinh footage dùng tool hiện có; bảng trên chỉ kết nối mục đích thiết kế với khả năng đã tích hợp.

7 effect mới: **word_reveal, line_reveal, character_reveal, text_gradient, underline_draw, radial_glow, edge_feather**. Reveal dùng frame/grapheme và giữ layout cuối để tránh chữ nhảy vị trí; word_reveal không phải phụ đề theo âm thanh. line_reveal tách theo newline authored, không đo line-wrap trình duyệt. Gradient/halo/mask là CSS graphic operations, không vật liệu3D/depth/light reconstruction. Pattern là SVG/vector deterministic; speckles dùng seed cố định để không tự flicker.

## MCP: áp dụng rồi nhìn kết quả

```json
{"tool":"editvideo_design_catalog","arguments":{"kind":"style","query":"tri thức","limit":8}}
{"tool":"editvideo_apply_design","arguments":{"project_id":"<id>","base_revision":12,"request":{"style_id":"vietnam_knowledge","palette_id":"forest"}}}
{"tool":"editvideo_compose_graphic","arguments":{"project_id":"<id>","base_revision":13,"request":{"component":"title","id":"intro","start_frame":0,"end_frame":120,"text":"Tại sao hình ảnh cần ngữ cảnh?","detail":"Nhìn chi tiết để hiểu đúng toàn cảnh.","pattern":"dots"}}}
```

Tra schema thật ở `editvideo://schemas`; revision phải đọc mới nhất. `apply_design.layer_roles` chỉ chỉnh layer chỉ định, không tự suy đoán typography của toàn bộ custom code. Layer thêm `color_role`/`background_role` để nhận palette; màu explicit ở layer khác giữ nguyên. `compose_graphic` dùng role và cùng id thay cả namespace để bỏ phần detail/source cũ khi tinh chỉnh. Components đo font thật để wrap từ, bố trí chiều cao của heading/detail/source, hàng so sánh/bước và plate lower-third; trường hợp vượt vùng dành sẵn được báo trước khi patch. Việc này giữ nguyên nội dung, chỉ thêm newline; agent vẫn kiểm Chromium và chia dòng theo ý nghĩa. Câu dài cần chỉnh size/line break/x/y/height hoặc dựng composition riêng. Token không tự hiểu chủ thể hoặc safe zone.

Font files và payload cập nhật trong snapshot mà không viết lại source. Export mới có design.cjs/design.js và loader. Source đã tùy chỉnh từ trước cần **merge có chủ đích**: resource `editvideo://runtime/remotion/design.cjs` hoặc `.../hyperframes/design.js`, rồi entry/HTML font-loader integration; đọc hash và `write_code` có backup. Hyperframes phải đưa design.js trước hyper-runtime.js. Không tự overwrite custom entry. 14 loại layer (pattern/icon/scene3d thêm vào), tối đa1000 lớp phân bố trên timeline; không khuyến nghị1000 lớp cùng một frame.

Với các thư viện mới dùng Remotion/Hyperframes. FFmpeg renderer đơn giản không thực thi DOM/FontFace/graphic widgets. Source archive chứa font/license/manifest và có thể dựng lại offline sau khi dependency/browser runtime đã cài.

## Những thư viện/kỹ thuật còn có thể mở rộng

| Phần | Trạng thái thực |
|---|---|
| Typography/palette/style/layout/pattern/icon | Đã tích hợp; previews/font bounds và role sửa được |
| Motion/data/captions/audio |69 effect, typed keyframe, charts/flow, real caption times, procedural SFX/duck/master/J-L |
| Footage/subject/temporal | Có asset index, thực nghiệm local LTX, SAM2, LaMa/ProPainter và motion evidence |
| Semantic shot retrieval/re-ID | Chưa có embedding retrieval hay danh tính xuyên cut; cần model/evidence mới |
| Color-managed scene-linear/HDR/LUT | Đã có pipeline media zscale float/nativePQ/HLG/tonemap và6 displayLUT; browsercomposition SDR, không fullHDRcompositor |
| Depth/3D/lighting/material | Relative depth model local; native3D primitives/lights/roughness/metalness/shadows/camera; DOFscreenblur, chưa opticalbokeh/rigging/calibratedgeometry |
| Motion blur/interpolation/speed ramp | Chưa portable toàn hệ thống; rate hiện tuyến tính, không quảng cáo nonlinear timewarp |
| Dialogue stems/ADR/learned music | Chưa tích hợp; SFX hiện procedural, không phải model âm nhạc |
| Stock/reference packs/fonts mọi ngôn ngữ | Không tự lấy media có giấy phép chưa rõ; gói hiện chỉ open fonts đã pin và vector gốc |

Mẫu kiểm tra: `scripts/design_atlas.py` tạo16 style +10 component +patterns/icons/effects, render60s trong hai engine và đọc lại MP4 từng page. Video dictionary im lặng để xem thiết kế; không phải phim thuyết minh/đo thời gian đọc. `read_design_preview` trả PNG/JPEG inline cho Claude. `tests/test_design_library.py` kiểm glyph/font/license SHA, contrast, cập nhật atomic giữ voice/source, grapheme/escape và geometry scaling. Luôn kiểm video thật sau khi kết hợp vào nội dung.
