# -*- coding: utf-8 -*-
"""音频/视频入库: ffmpeg抽音轨 → silero-VAD切句 → SenseVoice转写(17x实时) → [视频]场景关键帧OCR → 时间轴合并入库。
结构完全对齐 process_office: documents+pages+vault markdown, 让下游embedding/检索/图谱零改动。
"""
import datetime as _dt
import os
import re
import subprocess
import tempfile

BASE = os.environ.get("BRAIN_DATA", "/home/kb/brain")
# ★模型解析:打包客户端里模型在 _MEIPASS(包内),源码/服务器在 BASE/models。两处都找。
import sys as _sys, shutil as _shutil
_MEI = getattr(_sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

def _find_model(*rel):
    """在 _MEIPASS(打包) 和 BASE(数据目录/服务器) 两处找模型资源,返回第一个存在的路径。"""
    for root in (_MEI, BASE):
        p = os.path.join(root, "models", *rel)
        if os.path.exists(p):
            return p
    return os.path.join(BASE, "models", *rel)   # 都没有:返回 BASE 路径(_rec 里 os.path.exists 判空优雅降级)

# ffmpeg:打包客户端用包内 bin/ffmpeg(Mac版);没有则回落系统 which('ffmpeg')
FF = os.path.join(_MEI, "bin", "ffmpeg")
if not os.path.exists(FF):
    FF = _shutil.which("ffmpeg") or os.path.join(BASE, "bin", "ffmpeg")
_M = _find_model("sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17")
_VAD = _find_model("silero_vad.onnx")
# 说话人分离(A②): pyannote分割 + 3D-Speaker声纹, 纯CPU/ONNX, 复用已装的 sherpa_onnx
_DIAR_SEG = _find_model("sherpa-onnx-pyannote-segmentation-3-0", "model.onnx")
_DIAR_EMB = _find_model("3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx")

AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma", ".amr")
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".ts")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".heic", ".gif", ".bmp")
MEDIA_EXTS = AUDIO_EXTS + VIDEO_EXTS + IMAGE_EXTS

_recognizer = None
def _rec():
    global _recognizer
    if _recognizer is None:
        import sherpa_onnx
        _recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=os.path.join(_M, "model.int8.onnx"),
            tokens=os.path.join(_M, "tokens.txt"),
            num_threads=4, use_itn=True, language="auto")
    return _recognizer


def _fmt_t(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return ("%d:%02d:%02d" % (h, m, s)) if h else ("%d:%02d" % (m, s))


def extract_wav(src, out_wav):
    r = subprocess.run([FF, "-nostdin", "-y", "-i", src, "-vn", "-ar", "16000",
                        "-ac", "1", out_wav], capture_output=True, text=True)
    return r.returncode == 0 and os.path.exists(out_wav) and os.path.getsize(out_wav) > 4000


def transcribe_segments(wav_path, progress_cb=None):
    """VAD切句 + SenseVoice逐段转写 → [(start_sec, end_sec, text)]"""
    import wave
    import numpy as np
    import sherpa_onnx
    w = wave.open(wav_path)
    total = w.getnframes() / w.getframerate()
    samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    vcfg = sherpa_onnx.VadModelConfig()
    vcfg.silero_vad.model = _VAD
    vcfg.silero_vad.threshold = 0.5
    vcfg.silero_vad.min_silence_duration = 0.4
    vcfg.silero_vad.min_speech_duration = 0.25
    vcfg.silero_vad.max_speech_duration = 15
    vcfg.sample_rate = 16000
    vad = sherpa_onnx.VoiceActivityDetector(vcfg, buffer_size_in_seconds=180)
    rec = _rec()
    segs = []
    win = 512
    i = 0
    def _drain(flush=False):
        if flush:
            vad.flush()
        while not vad.empty():
            sg = vad.front
            start = sg.start / 16000.0
            dur = len(sg.samples) / 16000.0
            st = rec.create_stream()
            st.accept_waveform(16000, np.array(sg.samples, dtype=np.float32))
            rec.decode_stream(st)
            txt = st.result.text.strip()
            if txt:
                segs.append((start, start + dur, txt))
            vad.pop()
            if progress_cb:
                try:
                    progress_cb(min(int(start), int(total)), int(total))
                except Exception:
                    pass
    while i < len(samples):
        vad.accept_waveform(samples[i:i + win])
        i += win
        if i % (win * 200) == 0:
            _drain()
    _drain(flush=True)
    return segs, total


_diarizer = None
_DIAR_OK = None
def _diar():
    """离线说话人分离器(sherpa-onnx pyannote分割 + 3D-Speaker声纹, 纯CPU)。模型缺失/初始化失败则返回None(优雅降级, 不阻塞入库)。"""
    global _diarizer, _DIAR_OK
    if _DIAR_OK is False:
        return None
    if _diarizer is None:
        if not (os.path.exists(_DIAR_SEG) and os.path.exists(_DIAR_EMB)):
            _DIAR_OK = False
            return None
        import sherpa_onnx
        cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=_DIAR_SEG),
                num_threads=4),
            embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=_DIAR_EMB, num_threads=4),
            # threshold=0.9 是 3D-Speaker eres2net 声纹的甜点(实测四人样本正好4簇);
            # 宁可略欠分割也不过度分割(把一个人标成多人比合并更伤可读性)
            clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=0.9),
            min_duration_on=0.3, min_duration_off=0.5)
        try:
            _diarizer = sherpa_onnx.OfflineSpeakerDiarization(cfg)
            _DIAR_OK = True
        except Exception as e:
            print("  ⚠️ 说话人分离初始化失败:", e)
            _DIAR_OK = False
            return None
    return _diarizer


def diarize(wav_path):
    """→ [(start_sec, end_sec, speaker_int)] 按起始排序; 不可用/失败返回 []。"""
    d = _diar()
    if d is None:
        return []
    try:
        import wave
        import numpy as np
        w = wave.open(wav_path)
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        res = d.process(samples).sort_by_start_time()
        return [(sg.start, sg.end, sg.speaker) for sg in res]
    except Exception as e:
        print("  ⚠️ 说话人分离跳过:", e)
        return []


def _label_speakers(segs, spk):
    """转写段按时间重叠映射到说话人, 文本前缀"说话人N:"。仅≥2人时加(单人不加, 免噪声)。"""
    ids = sorted({s for (_, _, s) in spk})
    if len(ids) < 2:
        return segs
    remap = {sid: i + 1 for i, sid in enumerate(ids)}  # 声纹簇 → 顺序人号
    out = []
    for (s, e, txt) in segs:
        best, who = 0.0, None
        for (ss, se, sid) in spk:
            ov = min(e, se) - max(s, ss)
            if ov > best:
                best, who = ov, sid
        out.append((s, e, ("说话人%d:%s" % (remap[who], txt)) if who is not None else txt))
    return out


def video_keyframes_ocr(src, tmpdir, max_frames=40):
    """场景切换抽关键帧(今天闪帧战役的同款检测) → RapidOCR → [(t_sec, text)]"""
    pat = os.path.join(tmpdir, "kf_%04d.jpg")
    r = subprocess.run([FF, "-nostdin", "-y", "-i", src, "-vf",
                        "select='gt(scene,0.30)',showinfo", "-vsync", "vfr",
                        "-frames:v", str(max_frames), "-q:v", "3", pat],
                       capture_output=True, text=True)
    times = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", r.stderr)]
    frames = sorted(
        os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.startswith("kf_"))
    out = []
    if not frames:
        return out
    try:
        from rapidocr import RapidOCR  # noqa: F401
        cap = len(frames)
    except ImportError:
        cap = min(len(frames), int(os.environ.get("VIDEO_OCR_MAX_FRAMES", "3")))  # 大模型OCR慢, 限帧
    for idx, fp in enumerate(frames[:cap]):
        t = times[idx] if idx < len(times) else 0.0
        try:
            lines = [l for l in _ocr_image_file(fp) if len(l) >= 2]
        except Exception:
            lines = []
        if lines:
            out.append((t, "\n".join(lines)))
    if cap < len(frames):
        print("  ⚠️ 画面OCR限帧 %d/%d (大模型较慢)" % (cap, len(frames)))
    return out


def _glossary(con, limit=150):
    """用户知识库实体词表: doc_summaries.topics + 文档名词干。库越厚, 纠错越准(复利)。"""
    import json as _j
    terms = []
    try:
        for (t,) in con.execute("SELECT topics FROM doc_summaries WHERE topics IS NOT NULL"):
            try:
                terms += [x for x in _j.loads(t) if isinstance(x, str) and 1 < len(x) <= 12]
            except Exception:
                pass
        for (fn,) in con.execute("SELECT filename FROM documents"):
            stem = os.path.splitext(fn)[0]
            stem = re.sub(r"^(书籍|文档|报告)__", "", stem)
            if 1 < len(stem) <= 24:
                terms.append(stem)
    except Exception:
        pass
    seen, out = set(), []
    for t in terms:
        if t not in seen:
            seen.add(t); out.append(t)
    return out[:limit]


def _llm_fix(text, glossary):
    """LLM同音字纠错(结构由我保管): 拆行去戳→编号送LLM→按行装回时间戳。
    行数不符逐行回退原文, 失败整体原样返回, 绝不阻塞入库。"""
    lines = text.split("\n")
    parsed = []  # (prefix, body)
    for ln in lines:
        m = re.match(r"^(\[[\d:]+\](?: \(画面\))?) (.*)$", ln)
        parsed.append((m.group(1), m.group(2)) if m else ("", ln))
    bodies = [b for (_, b) in parsed if b.strip()]
    if not bodies:
        return text
    try:
        import llm as LLM
        gl = "、".join(glossary) if glossary else "(无)"
        numbered = "\n".join("%d. %s" % (i + 1, b) for i, b in enumerate(bodies))
        sysp = ("你是语音转写校对员。逐行修正ASR同音字/专业术语/英文拼写错误"
                "(如: 9期→久期, 路沿→路演, 会议既要→会议纪要, sp ratio→Sharpe ratio)。"
                "用户知识库高频术语表(优先按它校对): " + gl + "。"
                "规则: 不增删行、不合并行、不改数字和事实, 没错的行原样输出。"
                "输出格式: 与输入完全相同的编号行, 每行一条, 不要任何解释。")
        out = LLM.chat([{"role": "system", "content": sysp},
                        {"role": "user", "content": numbered}],
                       temperature=0.1,
                       # v4推理模型会拿max_tokens去思考, 太小正文被吃空(2026-07-25 P0教训): 给足下限
                       max_tokens=max(3000, len(numbered) * 2 + 300),
                       model=LLM.fast_model())
        fixed = {}
        for ln in (out or "").split("\n"):
            m = re.match(r"^\s*(\d+)[.、]\s*(.*)$", ln.strip())
            if m:
                fixed[int(m.group(1))] = m.group(2).strip()
        idx = 0
        rebuilt = []
        for (pfx, body) in parsed:
            if body.strip():
                idx += 1
                nb = fixed.get(idx, body)  # 该行没返回就用原文
                # 单行防线: 修正行长度不能离谱(防LLM合并/扩写)
                if not nb or len(nb) > len(body) * 2 + 20:
                    nb = body
                rebuilt.append((pfx + " " + nb) if pfx else nb)
            else:
                rebuilt.append((pfx + " " + body) if pfx else body)
        return "\n".join(rebuilt)
    except Exception as e:
        print("  ⚠️ LLM纠错跳过:", e)
    return text


_OCR_WATERMARK = re.compile(r"bilibili|哔哩哔哩", re.I)
_OCR_JUNK_LINE = re.compile(
    r"^(\d{1,2}:\d{2}(:\d{2})?|[\W_]+|关注|已关注|点赞|投币|收藏|转发|分享|弹幕|自动连播|稍后再看|正在缓冲)$", re.I)


def _clean_ocr_lines(lines):
    """OCR结果清洗(rapidocr 与 8100百度 共用): 去布局标记 / [Non-Text] / B站水印UI / 纯符号行 / 折叠相邻重复。"""
    out = []
    for ln in lines:
        ln = re.sub(r"<\|det\|>.*?<\|/det\|>", "", str(ln))    # 布局坐标块(含坐标数字)整体删
        ln = re.sub(r"<\|[^|]*\|>", "", ln)                    # 其它孤立特殊标记
        ln = ln.strip().strip("#").strip()
        if not ln or ln == "[Non-Text]":
            continue
        if _OCR_WATERMARK.search(ln) or _OCR_JUNK_LINE.match(ln):
            continue
        out.append(ln)
    dedup = []
    for ln in out:
        if not dedup or dedup[-1] != ln:   # 同一水印在多帧/多行重复 → 折叠
            dedup.append(ln)
    return dedup


def _ocr_image_file(path):
    """图片OCR: rapidocr可用则用(快), 否则走本机8100百度OCR服务(质量高)。返回清洗后的行列表。"""
    try:
        from rapidocr import RapidOCR
        res, _ = RapidOCR()(path)
        return _clean_ocr_lines([x[1] for x in (res or [])])
    except ImportError:
        pass
    import json as _j
    import subprocess as _sp
    r = _sp.run(["curl", "-s", "-X", "POST", "http://127.0.0.1:8100/ocr/image",
                 "-F", "file=@" + path], capture_output=True, text=True, timeout=180)
    try:
        d = _j.loads(r.stdout)
    except Exception:
        return []
    t = d.get("text") or d.get("markdown") or ""
    return _clean_ocr_lines(str(t).split("\n"))


def process_image(con, path, vault_dir, force=False, progress_cb=None):
    """截图/图片 → RapidOCR → 一页文档入库(结构同 process_office)。"""
    from ingest import file_hash, already_ingested
    fhash = file_hash(path)
    if not force and already_ingested(con, path, fhash):
        print(f"  ⏭  已入库,跳过: {os.path.basename(path)}")
        return "skipped"
    try:
        lines = _ocr_image_file(path)
    except Exception as e:
        print(f"  ⚠️  OCR失败: {e}")
        return "error"
    if not lines:
        print("  ⚠️  图内无可识别文字, 跳过")
        return "error"
    text = "\n".join(lines)
    if progress_cb:
        try:
            progress_cb(1, 1)
        except Exception:
            pass
    con.execute("DELETE FROM documents WHERE source_path=?", (path,))
    cur = con.execute(
        "INSERT INTO documents(source_path,filename,pages,backend,file_hash,ingested_at)"
        " VALUES(?,?,?,?,?,?)",
        (path, os.path.basename(path), 1, "ocr:rapidocr", fhash,
         _dt.datetime.now().isoformat(timespec="seconds")))
    doc_id = cur.lastrowid
    con.execute("INSERT INTO pages(doc_id,page_no,method,text) VALUES(?,?,?,?)",
                (doc_id, 1, "ocr:rapidocr", text))
    con.commit()
    os.makedirs(vault_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    with open(os.path.join(vault_dir, stem + ".md"), "w", encoding="utf-8") as f:
        f.write("# %s\n\n%s\n" % (stem, text))
    print(f"     ✅ 图片入库  [{len(lines)}行文字]")
    return "ok"


def process_media(con, path, vault_dir, force=False, progress_cb=None):
    """音/视频 → 转写(+画面OCR) → documents+pages+vault md。结构同 process_office。"""
    from ingest import file_hash, already_ingested
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTS:
        return process_image(con, path, vault_dir, force=force, progress_cb=progress_cb)
    is_video = ext in VIDEO_EXTS
    fhash = file_hash(path)
    if not force and already_ingested(con, path, fhash):
        print(f"  ⏭  已入库,跳过: {os.path.basename(path)}")
        return "skipped"
    tmpdir = tempfile.mkdtemp(prefix="media_")
    try:
        wav = os.path.join(tmpdir, "a.wav")
        if not extract_wav(path, wav):
            print(f"  ⚠️  抽音轨失败: {os.path.basename(path)}")
            return "error"
        print(f"  🎙  转写中: {os.path.basename(path)}")
        segs, total = transcribe_segments(wav, progress_cb)
        if os.environ.get("ASR_DIARIZE", "1") == "1" and segs:
            spk = diarize(wav)
            if spk:
                n_spk = len({s for (_, _, s) in spk})
                if n_spk >= 2:
                    segs = _label_speakers(segs, spk)
                    print("  🗣  识别到 %d 位说话人" % n_spk)
        vis = video_keyframes_ocr(path, tmpdir) if is_video else []
        if not segs and not vis:
            print("  ⚠️  无语音也无画面文字,跳过")
            return "error"
        # 时间轴合并: 语音段+画面段排序交织
        timeline = [(s, e, "语音", t) for (s, e, t) in segs] + \
                   [(t, t, "画面", txt) for (t, txt) in vis]
        timeline.sort(key=lambda x: x[0])
        # 切"页": 每页≈1200字, 保持段落完整, 页首记起止时间
        units = []
        buf, p_start, p_chars = [], None, 0
        for (s, e, kind, txt) in timeline:
            if p_start is None:
                p_start = s
            tag = "[%s]" % _fmt_t(s) + (" (画面)" if kind == "画面" else "")
            buf.append(tag + " " + txt)
            p_chars += len(txt)
            if p_chars >= 1200:
                units.append((p_start, "\n".join(buf)))
                buf, p_start, p_chars = [], None, 0
        if buf:
            units.append((p_start or 0, "\n".join(buf)))
        if os.environ.get("ASR_LLM_FIX", "1") == "1" and units:
            print("  ✏️  LLM词典纠错中(%d页)…" % len(units))
            gl = _glossary(con)
            units = [(t0, _llm_fix(txt, gl)) for (t0, txt) in units]
        n = len(units)
        method0 = "asr:sensevoice" + ("+ocr" if vis else "")
        dur_line = "时长 %s, 语音段 %d, 画面帧 %d" % (_fmt_t(total), len(segs), len(vis))
        print(f"  📄 {os.path.basename(path)}  ({n} 页, {method0}, {dur_line})")
        con.execute("DELETE FROM documents WHERE source_path=?", (path,))
        cur = con.execute(
            "INSERT INTO documents(source_path,filename,pages,backend,file_hash,ingested_at)"
            " VALUES(?,?,?,?,?,?)",
            (path, os.path.basename(path), n, method0, fhash,
             _dt.datetime.now().isoformat(timespec="seconds")))
        doc_id = cur.lastrowid
        md_parts = ["---", f"source: {path}", f"pages: {n}", f"backend: {method0}",
                    f"duration: {_fmt_t(total)}",
                    f"ingested: {_dt.datetime.now().isoformat(timespec='seconds')}", "---", "",
                    f"# {os.path.splitext(os.path.basename(path))[0]}", "", f"> {dur_line}", ""]
        for no, (t0, text) in enumerate(units, 1):
            con.execute("INSERT INTO pages(doc_id,page_no,method,text) VALUES(?,?,?,?)",
                        (doc_id, no, method0, text))
            con.commit()  # 逐页提交(07-31锁死事故的铁律)
            md_parts += [f"## 第 {no} 段 · 起于 {_fmt_t(t0)}", "", text, ""]
        os.makedirs(vault_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(path))[0]
        with open(os.path.join(vault_dir, stem + ".md"), "w", encoding="utf-8") as f:
            f.write("\n".join(md_parts))
        con.commit()
        print(f"     ✅ 入库完成  [{method0}×{n}页]")
        return "ok"
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
