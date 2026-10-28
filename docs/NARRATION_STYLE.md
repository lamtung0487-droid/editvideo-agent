# Narration style: documentary prose both audiences can trust

Round 13, the Vietnam film. The owner found the sixth cut's draft hard to follow in places, and found wording that could
start an argument (a declaration of independence "leading to" a war). This guide is the rule set; `script_audit.style`
checks the parts a machine can see (loaded words, stock phrases, uncredited causes, irony, dashes, sentence length) on
every narration beat.

Sources:
- Wikipedia's "Signs of AI writing", as packaged in the humanizer skill (github.com/blader/humanizer, MIT). It is installed
  for all projects at `~/.claude/skills/humanizer/`.
- Ken Burns' teaching: use words to fight abstraction, write with poetic detail, build structure around facts.
- The owner's reviews of five cuts (kept with the private production files).

## Rules

1. **Say what the picture cannot.** Give time, place, who decided and what followed. Do not describe what is on screen.
2. **One fact per sentence, one breath per sentence.** Vietnamese: up to about 32 syllables. English: about 28 words.
   Put the date or place first when the scene changes.
3. **A named actor and a concrete verb.** "Nixon ordered", not "an order was given". People, units and places by name.
4. **No verdicts in the narrator's mouth.** Leave out heroic, brutal, glorious, puppet, aggressor (vĩ đại, tàn bạo, anh dũng,
   ngụy, giặc, đế quốc, xâm lược). Judgement belongs to a witness in a quotation, or to the facts.
5. **Cause only with a source.** "led to", "forced", "because of this" (dẫn đến, khiến, buộc, vì vậy) are claims. Credit them
   ("Historian Lien-Hang Nguyen argues…", "Washington believed…"), or tell the events in order and let the viewer connect
   them. A declaration, a song or a speech does not "lead to" a war. Tell what each side did next.
6. **Contested numbers: both, with their source, like for like.** "Vietnam reported 34 B-52s shot down; the US Air Force
   recorded 15 lost." The totals (81 and 26 aircraft) go on screen with their sources. Put the source on screen when the
   narration does not say it.
7. **No irony, no rhetorical staging.** Drop "They called it a civilising mission. But…", "not only… but also" (không
   chỉ… mà còn), one-line closers, forced lists of three, and dashes.
8. **No stock phrases.** Drop journey, testament, landmark chapter, epic, unprecedented (hành trình, dấu ấn, minh chứng,
   bản hùng ca, trang sử vàng, chưa từng có, đáng kinh ngạc). Say the specific thing.
9. **Quote faithfully and translate plainly.** Roosevelt's "France has milked it for one hundred years" is "nước Pháp đã
   bòn rút xứ này một trăm năm", not a stronger word. Name who said it and when.
10. **Read it aloud before recording.** A sentence that needs a second breath, or a word a listener has to stop on, is
    rewritten.

The owner's team reviewed the sixth cut's script (2026-10-24, owner_reviews.json, grade "team"). Five more rules came from
it, and `script_audit` checks each one that a machine can check:

11. **No feelings in a person's mouth, no absolutes.** "Bà không còn ai để chờ" invents what a mother felt. "Không ai",
    "hoàn toàn", "san phẳng" claim more than most sources do (`absolute_claim`). Keep an absolute only when the source says
    exactly that, and say so on the beat: `accept={"absolute_claim": "the 1956 elections were never held"}`.
12. **Two figures a sentence at most.** The ear holds two. Dates, model names (B-52) and rough sizes ("hàng nghìn") do not
    count. The rest go on screen with their source (`number_load`, `MAX_QUANTITIES = 2`).
13. **Time moves forward inside a chapter.** A beat opens at or after the point the last one reached (`beat_order`): the
    1940 famine before Roosevelt's 1944 memo, the July 1945 parachute drop before 2 September. A coda is marked
    `flashback`, a then-and-now pair `comparison`, and either gets a date card on screen.
14. **Nothing is recorded before its source is traced.** A line with a figure, a date or a quotation needs status
    "verified" and a named source (`recording_gate`). The narration lives in one file with status and sources per line
    (the production's narration source); the reading copy is generated from it.
15. **No poetry, no closing formula.** A documentary ends a chapter on a fact or on the picture. "Hòa bình đến, nhưng cái
    nghèo ở lại", "sau tất cả, vẫn đang nối dài" explain instead of telling (`formula_line`).

## Names: neutral and consistent

| For | Narration (Vietnamese) | Subtitles (English) | Avoid in narration |
|---|---|---|---|
| The northern army | Quân đội nhân dân Việt Nam | the People's Army of Vietnam | quân Bắc Việt |
| Southern revolutionary forces | Quân Giải phóng miền Nam | the Liberation Army (Viet Cong) at first mention | Việt Cộng, except in quotations |
| The southern state | Việt Nam Cộng hòa, chính quyền Sài Gòn, quân đội Việt Nam Cộng hòa | the Republic of Vietnam, Saigon, the ARVN | ngụy |
| The United States | Mỹ, chính phủ Mỹ, quân đội Mỹ, Washington | the US, Washington | đế quốc Mỹ |
| France before 1954 | chính quyền thuộc địa Pháp, quân đội Pháp | the French colonial government | thực dân as an epithet (keep it inside historical names) |

## Before and after, from the sixth cut's draft

| Draft | Rewritten | Why |
|---|---|---|
| Người Pháp gọi đó là sứ mệnh khai hóa. Nhưng năm 1914, ba mươi bảy phần trăm ngân sách… | Năm 1914, ba mươi bảy phần trăm ngân sách chung của Đông Dương đến từ độc quyền thuốc phiện. | Irony (rule 7). The number says it. |
| Các làng… bị ép mua ít nhất tám triệu lít rượu | Các làng… phải mua ít nhất tám triệu lít rượu… Làng nào mua thiếu thì phần thiếu bị cộng vào thuế. | The second sentence shows the compulsion (rule 4). |
| Roosevelt mất, và Washington đổi ý. | Đến tháng 3 năm 1945, ông chấp nhận để Pháp trở lại, với điều kiện Đông Dương sẽ được độc lập. Một tháng sau, ông qua đời. | The draft was wrong: Roosevelt himself had accepted it (rule 5, and the sources). |
| …trút xuống Lào hơn hai triệu tấn bom | Hơn hai triệu tấn bom được thả xuống Lào. | A loaded verb (rule 4). |
| Chính CIA phải cắt giảm những con số ấy | CIA về sau giảm những con số ấy tới ba phần tư. | Staging (rule 7). |
| Năm 1968 là năm đẫm máu nhất với lính Mỹ | Năm 1968, mười sáu nghìn tám trăm chín mươi chín lính Mỹ chết, nhiều nhất trong cả cuộc chiến. | Number instead of adjective (rule 4). |
| Hai đồng minh lớn nhất của Hà Nội cùng bắt tay với Washington. | Washington cải thiện quan hệ với cả hai nước viện trợ nhiều nhất cho Hà Nội. | A figure of speech becomes a fact (rule 3). |

## Recorded lines the audit flagged (settled in the team-review revision)

- c3d, c9c: causes stated as fact. Re-recorded: the events in order, no "khiến".
- c10c: rewritten in the order of the years.
- c2b, c6f, c8e, c10b: split into sentences of one breath.
- c3b: Hà Nội's reasoning, now credited ("Hà Nội cho rằng…").
- c2e: a temporary military demarcation line, "để Mỹ không can thiệp".
- c3a ("không bao giờ diễn ra") and o1 ("Không người nào trở về"): absolutes the sources support, kept with `accept`.
