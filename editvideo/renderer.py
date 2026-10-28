import json
import math
import re
import shutil
import zipfile
from pathlib import Path
from PIL import Image, ImageDraw
from . import store
from .audio import write_srt
from .graphics import card, font, wrap, prepare_still
from .media import FFMPEG, command, probe, sha256, safe_asset_path
from .planner import validate_sources


def ass_time(t):
    cs = math.ceil(t * 100)
    return f"{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}"


def ass_text(text):
    # No user ASS overrides or escape directives.
    return text.replace("\\", "／").replace("{", "(").replace("}", ")").replace("\r", " ").replace("\n", " ")


def captions_ass(path, cues, width, height):
    size = max(22, round(width*.047))
    # Landscape text size is proportional to height to keep images dominant.
    if width > height:
        size = max(22, round(height*.058))
    face = font(size, True)
    content = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\n"
               "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
               f"Style: Default,Segoe UI,{size},&H00FFFFFF,&H00FFFFFF,&H5010181B,&H5010181B,-1,0,0,0,100,100,0,0,3,10,0,2,{round(width*.08)},{round(width*.08)},{round(height*.17)},1\n"
               "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    for c in cues:
        lines = wrap(ass_text(c.text), face, width*.81)
        if len(lines) > 3:
            raise ValueError("Phụ đề quá nhiều chữ. Hãy chia thành các cụm ngắn hơn trong timeline.")
        text = "\\N".join(lines)
        content += f"Dialogue: 0,{ass_time(c.start)},{ass_time(c.end)},Default,,0,0,0,,{text}\n"
    path.write_text(content, encoding="utf-8-sig")


def render_shot(pid, shot, timeline, config, work, index, width, height, cancelled):
    frames = shot.end_frame-shot.start_frame
    duration = frames/30
    target = work / f"shot-{index:03}.mp4"
    inputs = []
    if shot.asset_id:
        asset = store.find_asset(pid, shot.asset_id)
        source = safe_asset_path(pid, shot.asset_id)
    else:
        asset = {"kind": "image"}
        source = work / f"card-{index:03}.png"
        card(source, width*2, height*2, config["title"], shot.text, index, len(timeline.shots), config["style"])
    if asset["kind"] == "image":
        still = work / f"still-{index:03}.png"
        prepare_still(source, still, width*2, height*2, shot.fit, shot.focus_x, shot.focus_y)
        inputs = ["-loop", "1", "-framerate", "30", "-i", still]
        n = max(1,frames-1)
        if shot.motion == "hold" or shot.fit == "contain":
            vf = f"scale={width}:{height}:flags=lanczos,setsar=1"
        else:
            # Continuous frame-based motion; oversampling avoids low-res jitter.
            p = f"min(on/{n},1)"
            ease = f"(0.5-0.5*cos(PI*{p}))"
            zoom = f"1+0.075*{ease}" if shot.motion == "push" else f"1.075-0.075*{ease}" if shot.motion == "pull" else "1.075"
            x = f"(iw-iw/zoom)*{ease}" if shot.motion == "pan" else "(iw-iw/zoom)/2"
            vf = f"zoompan=z='{zoom}':x='{x}':y='(ih-ih/zoom)/2':d=1:s={width}x{height}:fps=30,setsar=1"
    else:
        inputs = ["-ss", shot.source_start, "-i", source]
        if shot.fit == "contain":
            vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x10191b"
        else:
            vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                  f"crop={width}:{height}:(iw-ow)*{shot.focus_x}:(ih-oh)*{shot.focus_y}")
        vf += ",fps=30,setsar=1"
    vf += ",format=yuv420p"
    command([FFMPEG, "-y", "-v", "warning", *inputs, "-vf", vf, "-an", "-frames:v", frames,
             "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-threads", "4", "-r", "30", target],
            cwd=work, cancelled=cancelled, log=work/"render.log")
    return target


ROLE_CHAIN = {"dialogue": "highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=80:makeup=2,alimiter=limit=0.708:level=disabled",
              "ambience": "lowpass=f=9000", "foley": "highpass=f=60", "music": "", "sfx": ""}
# AudioClip.treatment: a character filter applied after the role chain (see models.AudioClip).
TREATMENT_CHAIN = {"radio": "highpass=f=300,highpass=f=300,lowpass=f=3400,lowpass=f=3400,acompressor=threshold=-24dB:ratio=4:attack=5:release=60:makeup=3,alimiter=limit=0.7:attack=2:release=40:level=disabled",
                   "muffled": "lowpass=f=450,lowpass=f=450,lowpass=f=450",
                   "distant": "highpass=f=90,lowpass=f=1800,lowpass=f=1800,aecho=0.8:0.5:230|470:0.35|0.2",
                   "telephone": "highpass=f=500,highpass=f=500,lowpass=f=3000,lowpass=f=3000,acompressor=threshold=-20dB:ratio=6:attack=3:release=50:makeup=4",
                   "archival": "highpass=f=140,highpass=f=140,lowpass=f=5200,lowpass=f=5200,vibrato=f=0.7:d=0.004,acompressor=threshold=-22dB:ratio=3:attack=8:release=90:makeup=2"}


# Level change of each treatment measured on pink noise at -25 LUFS (radio -21.2, muffled -32.8, distant -37.9,
# telephone -20.2, archival -22.5), half compensated: a treated clip stays near its role level while distance still reads quieter.
TREATMENT_MAKEUP_DB = {"radio": -3.8, "muffled": 3.9, "distant": 6.5, "telephone": -4.8, "archival": -1.3}


def clip_chain(c, gain_db=0.0):
    """Filters between the trimmed source and the clip's volume: optional reverse, playback rate, the role level
    (normalisation measured on the untreated source, so it is applied before anything that reacts to level), the
    role chain, the treatment and its makeup."""
    parts = ["areverse"] if c.get("reverse") else []
    parts += ["aresample=48000", f"atempo={c.get('playback_rate', 1)}", f"volume={gain_db:.2f}dB"]
    parts += [x for x in (ROLE_CHAIN.get(c.get("role") or "", ""), TREATMENT_CHAIN.get(c.get("treatment") or "", "")) if x]
    if c.get("treatment"):
        parts.append(f"volume={TREATMENT_MAKEUP_DB[c['treatment']]:.1f}dB")
    return ",".join(parts)


ROLE_LUFS = {"dialogue": -16, "music": -30, "ambience": -42, "foley": -28, "sfx": -24}
ROLE_PEAK = {"dialogue": -6, "music": -18, "ambience": -30, "foley": -18, "sfx": -12}


def clip_level(path, start, seconds):
    """Integrated loudness and true peak of the used section of a source (FFmpeg EBU R128)."""
    out = command([FFMPEG, "-hide_banner", "-nostats", "-ss", max(0, start), "-t", max(.05, seconds), "-i", path, "-vn",
                   "-filter_complex", "ebur128=peak=true", "-f", "null", "-"], timeout=120)
    tail = out.split("Summary:")[-1]
    grab = lambda k: (lambda m: float(m.group(1)) if m else None)(re.search(k + r":\s*(-?[\d.]+|-inf)", tail))
    try:
        lufs = grab("I")
    except ValueError:
        lufs = None
    try:
        peak = grab("Peak")
    except ValueError:
        peak = None
    return lufs, peak


def role_gain_db(pid, c, seconds):
    """Gain (dB) that brings a clip to its role target: loudness for sections >= 1.5 s, peak for short accents."""
    if not c.get("normalize") or not c.get("role"):
        return 0.0
    lufs, peak = clip_level(safe_asset_path(pid, c["asset_id"]), c["source_start"], seconds * c.get("playback_rate", 1))
    if seconds >= 1.5 and lufs is not None and math.isfinite(lufs) and lufs > -70:
        return max(-30.0, min(24.0, (c.get("target_lufs") or ROLE_LUFS[c["role"]]) - lufs))
    if peak is not None and math.isfinite(peak) and peak > -80:
        return max(-30.0, min(24.0, ROLE_PEAK[c["role"]] - peak))
    return 0.0


def mix_audio(pid, config, work, duration, cancelled):
    from .models import AudioMix,Ducking
    timeline=store.read_json(work/"timeline.json") if (work/"timeline.json").exists() else {}
    master=AudioMix.model_validate(timeline.get('audio_mix',{}))
    def duck_filter(settings):
        d=Ducking.model_validate(settings)
        return f"sidechaincompress=threshold={d.threshold}:ratio={d.ratio}:attack={d.attack_ms}:release={d.release_ms}"
    voice = work / "voice.wav"
    mixed = work / "mixed.wav"
    if config.get("music_id"):
        music = safe_asset_path(pid, config["music_id"])
        fade = min(1.4, duration/5)
        graph = (f"[0:a]asplit=2[voice][side];[1:a]volume={config['music_volume']},"
                 f"afade=t=in:d={fade},afade=t=out:st={max(0,duration-fade)}:d={fade}[music];"
                 f"[music][side]{duck_filter(master.music_ducking.model_dump())}[duck];"
                 "[voice][duck]amix=inputs=2:duration=first:normalize=0[out]")
        command([FFMPEG, "-y", "-v", "warning", "-i", voice, "-stream_loop", "-1", "-i", music,
                 "-filter_complex", graph, "-map", "[out]", "-t", duration, "-ar", "48000", "-ac", "2", mixed],
                cancelled=cancelled, log=work/"render.log")
    else:
        command([FFMPEG, "-y", "-v", "error", "-i", voice, "-ar", "48000", "-ac", "2", mixed], cancelled=cancelled)
    clips=timeline.get("audio_clips",[])
    if clips:
        base=work/"base-mix.wav"
        shutil.copyfile(mixed,base)
        args=[FFMPEG,"-y","-v","warning","-i",base,"-i",voice]
        graph=[];outputs=["[0:a]"]
        # "voice" is the narration track and every dialogue clip: a silent project's narrator, interviews and archive
        # voices live in dialogue clips, and music marked duck_under_voice dips under them and swells back in the pauses
        dialogue=[i for i,c in enumerate(clips) if c.get("role")=="dialogue"]
        ducked=[i for i,c in enumerate(clips) if c["duck_under_voice"] and c.get("role")!="dialogue"]
        # a dialogue clip marked duck_under_voice (an interview bed under the narrator) ducks under the narration track
        # alone, as before the voice bus; it never keys itself
        dlg_ducked=[i for i in dialogue if clips[i]["duck_under_voice"]]
        # one input per distinct file, split for the clips that use it: one -i per clip passed Windows' 32 767-character
        # command line at ~270 clips (a documentary's sound design reaches 150 clips over ~50 files)
        files=[];use={}
        for c in clips:
            path=str(safe_asset_path(pid,c["asset_id"]))
            if path not in use:
                use[path]=[];files.append(path)
            use[path].append(c)
        label={}
        for k,path in enumerate(files):
            args += ["-i",path]
            users=use[path]
            if len(users)==1:
                label[id(users[0])]=f"[{k+2}:a]"
            else:
                graph.append(f"[{k+2}:a]asplit={len(users)}"+"".join(f"[src{k}_{j}]" for j in range(len(users))))
                for j,c in enumerate(users):
                    label[id(c)]=f"[src{k}_{j}]"
        for i,c in enumerate(clips):
            d=(c["end_frame"]-c["start_frame"])/30
            fi=min(c["fade_in"],d/2);fo=min(c["fade_out"],d/2)
            # Sample-based final trim avoids timestamp propagation through atempo
            # causing FFmpeg to consume the leading delay as pre-roll.
            gain=role_gain_db(pid,c,d)
            graph.append(f"{label[id(c)]}atrim=start={c['source_start']}:duration={d*c['playback_rate']},asetpts=PTS-STARTPTS,{clip_chain(c, gain)},volume={c['volume']},afade=t=in:d={max(fi,.0001)},afade=t=out:st={d-fo}:d={max(fo,.0001)},adelay={c['start_frame']*1600}S:all=1,apad,asetpts=N/SR/TB,atrim=end_sample={round(duration*48000)}[clip{i}]")
        nar_uses=(1 if ducked else 0)+len(dlg_ducked)
        if nar_uses:
            graph.append(f"[1:a]asplit={nar_uses}"+"".join(f"[nar{j}]" for j in range(nar_uses)))
        nar=iter(range(nar_uses))
        if ducked:
            keys=[f"[nar{next(nar)}]"]
            for i in dialogue:
                graph.append(f"[clip{i}]asplit=2[clipo{i}][key{i}]");keys.append(f"[key{i}]")
            bus=keys[0]
            if len(keys)>1:
                graph.append("".join(keys)+f"amix=inputs={len(keys)}:duration=first:normalize=0[voicebus]");bus="[voicebus]"
            graph.append(f"{bus}asplit={len(ducked)}"+"".join(f"[side{j}]" for j in range(len(ducked))))
            for j,i in enumerate(ducked):
                graph.append(f"[clip{i}][side{j}]{duck_filter(clips[i].get('ducking',{}))}[duck{i}]")
        for i in dlg_ducked:
            graph.append(f"{'[clipo%d]' % i if ducked else '[clip%d]' % i}[nar{next(nar)}]{duck_filter(clips[i].get('ducking',{}))}[duck{i}]")
        ducked_out=set(ducked)|set(dlg_ducked);dialogue_set=set(dialogue)
        for i in range(len(clips)):
            outputs.append(f"[duck{i}]" if i in ducked_out else f"[clipo{i}]" if ducked and i in dialogue_set else f"[clip{i}]")
        graph.append("".join(outputs)+f"amix=inputs={len(outputs)}:duration=first:normalize=0[out]")
        from .media import filter_complex_args
        command([*args,*filter_complex_args(";".join(graph),work,"mix-filter.txt"),"-map","[out]","-ar","48000","-ac","2",mixed],cancelled=cancelled,log=work/"render.log")
    measurement = command([FFMPEG, "-v", "info", "-i", mixed, "-af", f"loudnorm=I={master.target_lufs}:TP={master.true_peak_db}:LRA={master.loudness_range}:print_format=json", "-f", "null", "-"], cancelled=cancelled)
    match = re.search(r'\{\s*"input_i".*?\}', measurement, re.S)
    if not match:
        raise ValueError("Không chuẩn hóa được âm thanh")
    measured = json.loads(match.group())
    if not all(math.isfinite(float(measured[k])) for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")):
        if timeline.get("timing_method") in ("source_video_silent","silent_placeholder"):
            # Silent footage, or a plan timed on the offline narration placeholder (no TTS reachable): render silent
            # and say so in the job folder instead of failing the render.
            mixed.replace(work/"mix.wav")
            (work/"base-mix.wav").unlink(missing_ok=True)
            method={"source_video_silent":"original_silent_footage","silent_placeholder":"silent_placeholder"}[timeline["timing_method"]]
            store.write_json(work/'audio-master.json',{'silent':True,'method':method,'note':'No audible narration: the plan was timed on a silent placeholder; '
                           'replace it with real narration and re-plan before delivery.' if method=='silent_placeholder' else 'Source footage has no audio.'})
            return {"silent":True,"method":method}
        raise ValueError("Giọng đọc không có tín hiệu đủ nghe. Hãy chọn file giọng khác.")
    af = master_filter(master, measured)
    command([FFMPEG, "-y", "-v", "warning", "-i", mixed, "-af", af, "-ar", "48000", "-ac", "2", work/"mix.wav"],
            cancelled=cancelled, log=work/"render.log")
    for f in (mixed, work/"base-mix.wav"):  # pre-loudnorm intermediates; mix.wav is the master
        f.unlink(missing_ok=True)
    lin = linear_gain(master, measured)
    store.write_json(work/'audio-master.json',{'settings':master.model_dump(),'input_measurements':measured,
                     'method':(f'linear gain {lin[0]} dB into the true-peak limiter ({lin[1]} dB of peaks limited): the mix keeps its range' if lin else
                               'two-pass FFmpeg loudnorm; may use dynamic mode when linear constraints cannot be satisfied')})
    return measured


def linear_gain(master, measured):
    """(gain dB, dB of peaks the limiter takes) when loudnorm's linear pass would fall back to its dynamic mode only
    because the gain lifts the peaks over the true-peak target while the mix's own range fits the target LRA. Dynamic
    mode flattened a dossier's crescendo (LRA 16.7 -> 5.3, its thirds within 3 dB): a plain gain into the limiter keeps
    the shape. At most 6 dB of peaks are limited; beyond that the master stays quieter than the target. None otherwise."""
    try:
        i, tp, lra = float(measured["input_i"]), float(measured["input_tp"]), float(measured["input_lra"])
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (i, tp, lra)):
        return None
    gain = master.target_lufs - i
    over = tp + gain - master.true_peak_db
    if over <= 0 or lra > master.loudness_range:
        return None
    return round(gain - max(0.0, over - 6.0), 2), round(min(over, 6.0), 2)


def master_filter(master, measured):
    """The second loudnorm pass, then a limiter: linear loudnorm only applies gain, and a narration onset still reached
    +0.66 dBTP (round 13, sixth cut). The limiter sits half a dB under the target for the peaks between samples and the
    AAC encode. When only the peaks stop loudnorm from staying linear, a plain gain into the limiter (linear_gain)."""
    lin = linear_gain(master, measured)
    if lin:
        return f"volume={lin[0]}dB,aresample=48000,alimiter=limit={10 ** ((master.true_peak_db - .5) / 20):.4f}:attack=1:release=60:level=disabled"
    return (f"loudnorm=I={master.target_lufs}:TP={master.true_peak_db}:LRA={master.loudness_range}:measured_I={measured['input_i']}:"
            f"measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}:"
            f"measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:linear=true,"
            f"aresample=48000,alimiter=limit={10 ** ((master.true_peak_db - .5) / 20):.4f}:attack=1:release=60:level=disabled")


def encoded_audio_guard(path, target, work, cancelled=None):
    """Measure final AAC; correct only audio if codec overshoot exceeds the requested ceiling."""
    from .delivery import loudness
    import math
    before = loudness(path, cancelled or (lambda: False))
    peak = float(before['input_tp'])
    if not math.isfinite(peak) or peak <= target + .05:
        result = {'before': before, 'after': before, 'corrected': False}
    else:
        gain, result = target - peak - .7, None
        for _ in range(3):
            fixed = Path(work) / 'audio-guard.mp4'
            command([FFMPEG,'-y','-v','error','-i',path,'-map','0','-c','copy','-c:a','aac','-b:a','256k',
                     '-af',f'volume={gain:.4f}dB','-movflags','+faststart',fixed],cancelled=cancelled)
            after = loudness(fixed, cancelled or (lambda: False))
            if float(after['input_tp']) <= target + .05:
                fixed.replace(path)
                result = {'before':before,'after':after,'corrected':True,'gain_db':gain}
                break
            gain -= float(after['input_tp']) - target + .35
        if result is None: raise ValueError('Encoded audio cannot meet peak ceiling; previous video retained')
    store.write_json(Path(work)/'encoded-audio.json',result)
    return result


def verify(path, timeline, width, height, cancelled):
    info = probe(path)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
    if (video["width"], video["height"]) != (width,height) or video["r_frame_rate"] != "30/1":
        raise ValueError("Thông số video xuất không khớp cấu hình")
    if int(video.get("nb_frames", 0)) != timeline.total_frames:
        raise ValueError("Video xuất bị thiếu hoặc thừa frame")
    if abs(float(info["format"]["duration"])-timeline.total_frames/30) > .12:
        raise ValueError("Thời lượng video xuất không khớp timeline")
    if audio.get("sample_rate") != "48000":
        raise ValueError("Audio xuất không đúng 48 kHz")
    command([FFMPEG, "-v", "error", "-xerror", "-i", path, "-map", "0:v", "-map", "0:a", "-f", "null", "-"], cancelled=cancelled)
    return {"decoded": True, "frames": timeline.total_frames, "duration": float(info["format"]["duration"]),
            "width": width, "height": height, "fps": 30, "audio_sample_rate": 48000,
            "sha256": sha256(path)}


def contact_sheet(video, timeline, work, cancelled):
    count = min(len(timeline.shots), 8)
    tile_w, tile_h = 240, round(240*timeline.height/timeline.width)
    tiles = []
    for i in range(count):
        shot = timeline.shots[round(i*(len(timeline.shots)-1)/max(1,count-1))]
        at = (shot.start_frame+shot.end_frame)/60
        target = work/f"frame-{i}.jpg"
        command([FFMPEG, "-y", "-v", "error", "-ss", at, "-i", video, "-frames:v", "1",
                 "-vf", f"scale={tile_w}:{tile_h}", target], cancelled=cancelled)
        with Image.open(target) as im:
            tiles.append(im.copy())
    sheet = Image.new("RGB", (tile_w*min(4,count), (tile_h+30)*math.ceil(count/4)), "#111b1b")
    draw = ImageDraw.Draw(sheet)
    for i, im in enumerate(tiles):
        x,y = i%4*tile_w, i//4*(tile_h+30)
        sheet.paste(im,(x,y))
        draw.text((x+10,y+tile_h+6), f"{i+1:02}", font=font(16), fill="white")
    sheet.save(work/"storyboard.jpg", quality=92)


def render(pid, timeline, config, work, quality, cancelled, progress):
    validate_sources(pid, timeline, store.assets(pid))
    width,height = timeline.width,timeline.height
    if quality == "preview":
        scale = 640 / max(width,height)
        width,height = round(width*scale/2)*2,round(height*scale/2)*2
    progress(35, "Dựng hình và chuyển động từng cảnh")
    shot_files = []
    for i, shot in enumerate(timeline.shots):
        if cancelled():
            from .media import Cancelled
            raise Cancelled()
        progress(35+40*i/len(timeline.shots), f"Đang dựng cảnh {i+1}/{len(timeline.shots)}")
        shot_files.append(render_shot(pid,shot,timeline,config,work,i,width,height,cancelled))
    (work/"concat.txt").write_text("\n".join(f"file '{p.name}'" for p in shot_files), encoding="utf-8")
    command([FFMPEG,"-y","-v","error","-f","concat","-safe","1","-i","concat.txt","-c","copy","visual.mp4"], cwd=work,cancelled=cancelled)
    progress(77, "Phối giọng, giảm nhạc nền và cân âm lượng")
    mix_audio(pid,config,work,timeline.total_frames/30,cancelled)
    captions_ass(work/"captions.ass",timeline.cues,width,height)
    write_srt(work/"captions.srt",[c.model_dump() for c in timeline.cues])
    progress(85, "Ghép phụ đề và xuất MP4")
    final = work/("preview.mp4" if quality == "preview" else "final.mp4")
    args = [FFMPEG,"-y","-v","warning","-i","visual.mp4","-i","mix.wav","-map","0:v","-map","1:a"]
    if config["captions"]:
        args += ["-vf","subtitles=filename=captions.ass"]
    args += ["-c:v","libx264","-preset","fast","-crf","18" if quality=="final" else "23",
             "-threads","4","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-ar","48000",
             "-frames:v",timeline.total_frames,"-t",timeline.total_frames/30,"-movflags","+faststart",final.name]
    command(args,cwd=work,cancelled=cancelled,log=work/"render.log")
    if quality == 'final':
        encoded_audio_guard(final, timeline.audio_mix.true_peak_db, work, cancelled)
    progress(94,"Đọc kiểm tra file video đã xuất")
    report = verify(final,timeline,width,height,cancelled)
    report["timing_method"] = timeline.timing_method
    report["estimated_captions"] = timeline.timing_method.startswith("estimated")
    store.write_json(work/"technical.json",report)
    contact_sheet(final,timeline,work,cancelled)
    # Intermediates: per-shot encodes and the silent concat are fully contained in the muxed output.
    for f in [*shot_files, work/"visual.mp4"]:
        Path(f).unlink(missing_ok=True)
    sources = [{k:a.get(k) for k in ("id","name","kind","sha256","source_url","role","tags")} for a in store.assets(pid)
               if a["id"] in {s.asset_id for s in timeline.shots} | {config.get("narration_id"),config.get("music_id")}]
    store.write_json(work/"assets.json",sources)
    store.write_json(work/"render-settings.json",{"quality":quality,"width":width,"height":height,"fps":30,
                     "voice":config["voice"],"style":config["style"],"music_volume":config["music_volume"],"captions":config["captions"]})
    if quality == "final":
        with zipfile.ZipFile(work/"delivery.zip","w",compression=zipfile.ZIP_STORED) as z:
            # final.mp4 is served on its own; zipping it again doubled every delivery on disk.
            for name in ("captions.srt","timeline.json","assets.json","technical.json","render-settings.json"):
                z.write(work/name,name)
            if (work/'meaning.json').exists():z.write(work/'meaning.json','meaning.json')
    return final,report
