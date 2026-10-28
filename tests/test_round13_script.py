"""Round 13, documentary script audit (editvideo/script_audit.py): a chronicle of dates is told apart from a chapter
that explains why, what it led to and who lived it; the audit rides along with every persisted creative brief."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from editvideo.script_audit import audit

CHRONICLE = [{"id": f"b{k}", "chapter": "doimoi", "narration": t} for k, t in enumerate((
    "Năm 1988, ruộng đất được giao về tay người nông dân.", "Năm 1989, Việt Nam xuất khẩu gạo.", "Năm 1991, Việt Nam và Trung Quốc bình thường hóa quan hệ.",
    "Năm 1994, Mỹ bỏ cấm vận.", "Năm 1995, Việt Nam và Mỹ bình thường hóa quan hệ."))]
STORY = [
    {"id": "q", "chapter": "doimoi", "role": "context", "narration": "Năm 1985, lạm phát ăn mòn từng đồng lương, vì nền kinh tế bao cấp không nuôi nổi người làm ra lúa gạo."},
    {"id": "w", "chapter": "doimoi", "role": "witness", "voice": "Kim Ngọc", "narration": "Ở Vĩnh Phúc, ông Kim Ngọc đã lặng lẽ giao ruộng cho từng hộ từ những năm 1960."},
    {"id": "d", "chapter": "doimoi", "role": "decision", "narration": "Tháng 12 năm 1986, Đại hội VI quyết định nhìn thẳng vào sự thật."},
    {"id": "c", "chapter": "doimoi", "role": "consequence", "narration": "Kết quả đến nhanh hơn ai ngờ: chỉ ba năm sau, Việt Nam bán gạo ra thế giới."},
    {"id": "br", "chapter": "doimoi", "role": "breath", "narration": "(nhạc)"}]


def codes(beats):
    return {f["code"] for f in audit({"beats": beats})["findings"]}


def test_a_list_of_dated_events_is_a_chronicle_not_an_explanation():
    c = codes(CHRONICLE)
    assert {"chronicle_not_story", "chapter_without_cause", "chapter_without_person"} <= c


def test_a_chapter_with_causes_a_person_and_a_consequence_passes():
    c = codes(STORY)
    assert not c & {"chronicle_not_story", "chapter_without_cause", "chapter_without_consequence", "chapter_without_person"}
    row = audit({"beats": STORY})["chapters"][0]
    assert row["breaths"] == 1 and "Kim Ngọc" in row["people"] and row["causal_connectives"] >= 2


def test_order_question_and_callback():
    beats = [{"id": "h", "chapter": "open", "role": "hook", "narration": "Vì sao một dân tộc nhỏ lại đi qua ba mươi năm chiến tranh?", "motif": "vòng tay"},
             {"id": "a", "chapter": "b", "narration": "Năm 1975, chiến tranh kết thúc, nhưng cái giá còn ở lại."},
             {"id": "c", "chapter": "c", "narration": "Năm 1954, quân Pháp đầu hàng, vì vậy đất nước tạm chia đôi."},
             {"id": "e", "chapter": "end", "role": "payoff", "narration": "Và những vòng tay ấy vẫn nối dài.", "motif": "vòng tay"}]
    c = codes(beats)
    assert "time_jumps_back" in c and "opening_without_question" not in c and "no_callback" not in c


def test_places_words_and_music_are_not_people_and_a_flashback_is_not_disorder():
    beats = [{"id": "a", "chapter": "a", "role": "context", "narration": "Năm 1940, quân Nhật kéo vào Đông Dương. Văn bản ấy không còn giá trị, vì chiến tranh."},
             {"id": "s", "chapter": "a", "role": "breath", "voice": "song", "narration": "(bài hát)"},
             {"id": "b", "chapter": "b", "role": "cause", "narration": "Năm 1985, lạm phát tăng vọt, vì giá bị định từ trên xuống. "
                                                                         "Từ những năm 1960, ông Kim Ngọc đã giao ruộng cho từng hộ."}]
    r = audit({"beats": beats})
    assert r["chapters"][0]["people"] == [] and r["chapters"][1]["people"] == ["Kim Ngọc"]
    assert "time_jumps_back" not in {f["code"] for f in r["findings"]}


def test_the_creative_brief_carries_the_audit(tmp_path, monkeypatch):
    from editvideo import store
    from editvideo.agent_interface import creative_packet
    monkeypatch.setattr(store, "DATA", tmp_path)
    beats = [{**b, "visual_idea": "tư liệu"} for b in STORY]
    r = creative_packet({"title": "Đổi Mới", "audience": "người xem phổ thông", "promise": "hiểu vì sao", "payoff": "một đất nước đổi đời", "beats": beats})
    assert r["script_audit"]["chapters"][0]["chapter"] == "doimoi"


def test_text_must_explain_and_names_are_people():
    """A hook does not excuse a dated chronicle; "tự do" and "ràng buộc" are not causes; decomposed Vietnamese is read;
    places shaped like names are not people; English narration is timed as English."""
    import unicodedata
    dated = "Năm 1988 ruộng đất được giao. Năm 1989 xuất khẩu gạo. Năm 1991 bình thường hóa. Năm 1994 bỏ cấm vận."
    c = codes([{"id": "h", "chapter": "x", "role": "hook", "narration": "Hôm nay?"}, {"id": "a", "chapter": "x", "role": "cause", "narration": dated}])
    assert {"chapter_without_cause", "chronicle_not_story"} <= c
    free = [{"id": "f", "chapter": "y", "role": "context", "narration": "Tuyên ngôn độc lập, tự do, ràng buộc, Do Thái, Hoàng Sa và Phan Thiết hôm ấy " * 2}]
    r = audit({"beats": free})
    assert r["chapters"][0]["causal_connectives"] == 0 and r["chapters"][0]["people"] == []
    nfd = unicodedata.normalize("NFD", "Năm 1985, lạm phát tăng vì giá bị định từ trên. Ông Trần Ấn giao ruộng, kết quả là sản lượng tăng gấp đôi.")
    r = audit({"beats": [{"id": "n", "chapter": "z", "narration": nfd}]})
    assert r["chapters"][0]["people"] == ["Trần Ấn"] and not {f["code"] for f in r["findings"]} & {"chapter_without_cause", "chapter_without_person"}
    en = audit({"beats": [{"id": "e", "chapter": "e", "narration": "word " * 150}]})
    assert en["chapters"][0]["language"] == "en" and en["chapters"][0]["spoken_s"] == 60.0


def test_a_brief_without_chapters_or_roles_is_not_audited_as_a_documentary(tmp_path, monkeypatch):
    from editvideo import store
    from editvideo.agent_interface import creative_packet
    monkeypatch.setattr(store, "DATA", tmp_path)
    r = creative_packet({"title": "Sản phẩm", "audience": "khách hàng", "promise": "thấy rõ", "payoff": "mua",
                         "beats": [{"id": "a", "narration": "Một chiếc máy pha cà phê.", "visual_idea": "máy"}]})
    assert r["script_audit"] is None


def test_narration_style_flags_verdicts_machine_prose_and_uncredited_causes():
    """Round 13: the owner found obscure words and claims that could start an argument in the sixth cut's draft, and asked
    for documentary prose. Verdicts and epithets, stock phrases, causes nobody is credited with, irony and long sentences
    are flagged per beat; quoted words, credited claims and names with dashes are left alone."""
    from editvideo import script_audit as sa
    beats = [
        {"id": "a", "narration": "Đây không chỉ là một chiến thắng vĩ đại, mà còn là bản hùng ca của cả dân tộc."},
        {"id": "b", "narration": "Bản tuyên ngôn ấy dẫn đến chiến tranh."},
        {"id": "c", "narration": "Nhà sử học Lien-Hang Nguyễn cho rằng cuộc tiến công Xuân – Hè dẫn đến bước ngoặt ở Paris."},
        {"id": "d", "narration": "Người Pháp gọi đó là sứ mệnh khai hóa. Nhưng thuốc phiện nuôi ngân sách."},
        {"id": "e", "narration": "Người ta buộc ngọn cây hai bên đường vào nhau. Ông viết: «một cuộc chiến tàn bạo»."},
    ]
    f = {(x["where"], x["code"]) for x in sa.style(beats)}
    assert ("a", "loaded_word") in f and ("a", "machine_prose") in f
    assert ("b", "unattributed_cause") in f and ("c", "unattributed_cause") not in f
    assert ("d", "irony") in f
    assert not {k for k in f if k[0] in ("c", "e") and k[1] in ("loaded_word", "unattributed_cause", "dash")}


def test_team_review_checks_absolutes_formulas_numbers_order_and_the_recording_gate():
    """The owner's team reviewed the sixth cut's script: an invented emotional line ('bà không còn ai để chờ'), formula
    contrasts ('Hòa bình đến, nhưng cái nghèo ở lại'), sentences dense with numbers, beats that go back in time unannounced,
    and lines locked for recording before their figures were traced."""
    from editvideo import script_audit as sa
    beats = [
        {"id": "c7e", "chapter": "7", "narration": "Ở Điện Bàn, mẹ Thứ đã mất thêm năm người con trai. Bà không còn ai để chờ."},
        {"id": "c9a", "chapter": "9", "narration": "Hòa bình đến, nhưng cái nghèo ở lại."},
        {"id": "N1", "chapter": "1", "narration": "Năm 1914, ba mươi bảy phần trăm ngân sách đến từ thuốc phiện, tám triệu lít rượu, "
                                                  "bảy mươi mốt phần trăm chủ đất giữ mười hai phần trăm ruộng."},
        {"id": "N4", "chapter": "1", "narration": "Tháng 3 năm 1945, Roosevelt bàn về Đông Dương."},
        {"id": "c1b", "chapter": "1", "narration": "Năm 1940, quân Nhật vào Đông Dương."},
    ]
    f = {(x["where"], x["code"]) for x in sa.style(beats) + sa.beat_order(beats)}
    assert ("c7e", "absolute_claim") in f and ("c9a", "formula_line") in f and ("N1", "number_load") in f
    assert ("c1b", "beat_time_jump") in f and ("N4", "beat_time_jump") not in f
    # what the ear holds: dates, model names, rough sizes and rates are not figures; a span, a set date, a then-and-now
    # comparison and a checked absolute are not faults
    assert sa._quantities("Ngày 27 tháng 1 năm 1973, đêm 26, một trăm hai mươi chiếc B-52, hàng nghìn người, tỷ lệ nghèo.", "vi") == ["một trăm hai mươi"]
    assert sa._quantities("Năm 1995, chưa tới nửa tỷ đô-la; năm 2025, hơn hai trăm tỷ.", "vi") == ["nửa tỷ", "hai trăm tỷ"]
    beats = [{"id": "c2e", "chapter": "3", "narration": "Hiệp định hẹn tổng tuyển cử vào tháng 7 năm 1956."},
             {"id": "c2g", "chapter": "3", "narration": "Tháng 10 năm 1954, bộ đội tiến về Hà Nội."},
             {"id": "c10b", "chapter": "12", "narration": "Năm 1988, ruộng đất được giao cho từng hộ."},
             {"id": "c10c", "chapter": "12", "narration": "Cuối những năm 1980, viện trợ của Liên Xô giảm dần."},
             {"id": "c6i", "chapter": "12", "narration": "Tù binh Mỹ được trả về. Có người bị bắn rơi năm 1967."},
             {"id": "R6", "chapter": "13", "narration": "Năm 2024, họ được trao huân chương."},
             {"id": "R2", "chapter": "13", "narration": "Từ năm 1988, hai bên cùng đi tìm hài cốt."},
             {"id": "R7", "chapter": "13", "narration": "Năm 1995, thương mại chưa tới nửa tỷ. Năm 2025, hơn hai trăm tỷ.", "comparison": True},
             {"id": "c3a", "chapter": "4", "narration": "Cuộc tổng tuyển cử không bao giờ diễn ra.", "accept": {"absolute_claim": "fact"}}]
    assert not sa.beat_order(beats) and not [x for x in sa.style(beats) if x["code"] != "dash"]
    g = sa.recording_gate([{"id": "a", "text": "Anh đã không đốt."},
                           {"id": "b", "text": "Năm 1972, 26 máy bay.", "status": "verified", "sources": ["USAF fact sheet"]},
                           {"id": "c", "text": "Năm 1975, con trai cả hy sinh.", "status": "needs_source"},
                           {"id": "d", "text": "Năm 1993, 58 phần trăm.", "status": "verified"}])
    assert g["ready"] == ["a", "b"] and [w["id"] for w in g["waiting"]] == ["c", "d"]
