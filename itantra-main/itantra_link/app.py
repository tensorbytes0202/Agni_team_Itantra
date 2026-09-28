"""
iTantra desktop app: everything in one window (standard-library tkinter, offline).

    language tiles -> unzip that language pack -> load STT (one model in RAM)
    HOLD TO TALK / hands-free -> STT -> Radio Manager (WiFi / emulated low-bitrate, location, alerts)
    received messages -> TTS voice (unzipped on demand) with alert rules

Two laptops on the same WiFi (they find each other automatically):
    laptop 1:  python -m itantra_link.app --role sender   --lat 28.669156 --lon 77.453758
    laptop 2:  python -m itantra_link.app --role receiver --lat 28.66 --lon 77.44
If they don't find each other (some WiFi blocks broadcast), add --peer-ip <other laptop IP>
or type it in the "Peer IP" box. The same two commands also work on one laptop
(use headphones so the mic does not hear the speaker).

The "Channel" card changes WiFi interference, radio frequency and noise
(EMULATED, synced to the other laptop) to show the link surviving a bad channel.
"""
import argparse
import queue
import threading
import time
import tkinter as tk

from itantra_ai import model_packs as MP

from . import channel_lab as CH
from . import location as L
from .radio_manager import RadioManager, Received
from .transports import EmulatedLowBitrateTransport, UdpWifiTransport
from .voice_node import MIN_SPEECH_MS, SR, AutoListener, Speech

try:                                   # hide Vosk's internal LOG/WARNING spam
    from vosk import SetLogLevel
    SetLogLevel(-1)
except Exception:
    pass

PRESETS = {"sender": dict(wifi_port=5001, peer_wifi_port=5002, lb_port=6001, peer_lb_port=6002),
           "receiver": dict(wifi_port=5002, peer_wifi_port=5001, lb_port=6002, peer_lb_port=6001)}
NATIVE = {"en": "English", "hi": "हिन्दी", "gu": "ગુજરાતી", "mr": "मराठी", "kn": "ಕನ್ನಡ",
          "ml": "മലയാളം", "ta": "தமிழ்", "te": "తెలుగు", "or": "ଓଡ଼ିଆ", "bn": "বাংলা"}

# colours
BG, CARD, INK, MUTED, LINE = "#eef1f6", "#ffffff", "#1c2333", "#6b7385", "#d9dee8"
HEAD, ACCENT = "#1f2a44", "#ff8a00"
GREEN, RED, BLUE, PURPLE = "#2e9e5b", "#d93838", "#2f6fdb", "#7a3fb0"
YELLOW = "#e0b000"
LEVEL_COLOR = {"Clean": GREEN, "Noisy": YELLOW, "Bad": ACCENT, "Dead": RED, "Jammed": RED}
ROLE_COLOR = {"sender": ACCENT, "receiver": BLUE}
TILE = {"ready": ("#e3f6ea", GREEN, "● unzipped"), "zipped": ("#e6eeff", BLUE, "● in zip"),
        "missing": ("#f0f0f0", "#9aa0ab", "○ not available")}
PTT_IDLE = "🎙  HOLD TO TALK\nor click: start / stop"
F = "Nirmala UI"                       # Windows font with all Indic scripts


class App:
    def __init__(self, root, a):
        self.root, self.a = root, a
        self.lang = None                 # selected STT language
        self.speech = None               # Speech: holds exactly one STT model
        self.busy = False                # a language is being unzipped / loaded
        self.heard = {"en"}              # voices used this session (kept unzipped)
        self.auto = None
        self.rec_frames, self.rec_stream, self.rec_start, self.rec_click_mode = [], None, 0.0, False
        self._ui = queue.Queue()         # tkinter is not thread-safe: other threads post here
        self._was_connected = False

        # until discovery finds the other laptop, links point at this machine (one-laptop test)
        self.wifi = UdpWifiTransport(a.wifi_port, a.peer_ip or "127.0.0.1", a.peer_wifi_port)
        self.lb = EmulatedLowBitrateTransport(a.lb_port, a.peer_ip or "127.0.0.1", a.peer_lb_port,
                                              bitrate_bps=a.lb_bps, loss=a.lb_loss)
        self.rm = RadioManager([self.wifi, self.lb], on_receive=self.on_receive,
                               log=lambda s: self.note(s.strip()), verbose=a.verbose)
        if a.lat is not None and a.lon is not None:
            self.rm.set_location(a.lat, a.lon)
        self.disc = CH.Discovery(a.role, a.name, a.wifi_port, a.lb_port, on_peer=self.on_peer,
                                 on_env=lambda env: self.root.after(0, self.apply_env, env, True),
                                 manual_ip=a.peer_ip, port_offset=a.discovery_offset)
        CH.apply_env(self.disc.env, self.wifi, self.lb)
        self.speaker = None
        if not a.no_tts:
            from .speaker import Speaker
            self.speaker = Speaker(lambda: self.rm.location, save_dir=a.save_wav,
                                   log=lambda s: self.note(s.strip(), "tts"))

        self._build_ui()
        self._disk()
        self.rm.start()
        self.disc.start()
        self.note(f"{a.role.upper()} '{a.name}' ready  •  looking for the {CH.OTHER[a.role]} on this WiFi...  "
                  f"•  low-bitrate link is EMULATED ({a.lb_bps} bps). Pick a language to start.")
        self.root.after(100, self._pump)
        self.root.after(500, self._refresh)
        if a.lang:
            self.select_lang(a.lang)

    # ================================================================== layout
    def _build_ui(self):
        r = self.root
        r.title(f"iTantra - {self.a.role.upper()}")
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()      # fit small laptop screens
        r.geometry(f"{min(1100, sw - 20)}x{min(780, sh - 90)}+10+10")
        r.minsize(880, 560)
        r.configure(bg=BG)
        r.protocol("WM_DELETE_WINDOW", self.close)

        # ---- header
        head = tk.Frame(r, bg=HEAD, padx=16, pady=10)
        head.pack(fill="x")
        tk.Label(head, text="iTantra", bg=HEAD, fg="white", font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(head, text=f" {self.a.role.upper()} ", bg=ROLE_COLOR[self.a.role], fg="white",
                 font=("Segoe UI", 12, "bold"), padx=8).pack(side="left", padx=10)
        self.peer_lbl = tk.Label(head, text="", bg=HEAD, fg="white", font=("Segoe UI", 10, "bold"))
        self.peer_lbl.pack(side="left", padx=4)
        self.active_pill = tk.Label(head, text="", bg=HEAD, fg="white", font=("Segoe UI", 10, "bold"),
                                    padx=10, pady=3)
        self.active_pill.pack(side="right")
        self.loc_lbl = tk.Label(head, text="", bg=HEAD, fg="#aab4cc", font=("Segoe UI", 9))
        self.loc_lbl.pack(side="right", padx=12)

        body = tk.Frame(r, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=10)
        left = tk.Frame(body, bg=BG, width=390)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))

        self._language_card(left)
        self._links_card(left)
        self._channel_card(right)
        self._chat(right)

    def _card(self, parent, title, **pack):
        outer = tk.Frame(parent, bg=LINE, padx=1, pady=1)       # 1-px border
        outer.pack(fill="x", pady=(0, 10), **pack)
        c = tk.Frame(outer, bg=CARD, padx=12, pady=10)
        c.pack(fill="both", expand=True)
        tk.Label(c, text=title, bg=CARD, fg=INK, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        return c

    def _language_card(self, parent):
        c = self._card(parent, "Language")
        grid = tk.Frame(c, bg=CARD)
        grid.pack(fill="x", pady=(6, 4))
        self.tiles = {}
        for i, lang in enumerate(MP.LANGS):
            t = tk.Frame(grid, bg=CARD, cursor="hand2", padx=8, pady=1, highlightthickness=2,
                         highlightbackground=CARD)
            t.grid(row=i // 2, column=i % 2, padx=2, pady=2, sticky="ew")
            top = tk.Label(t, text=NATIVE[lang], font=(F, 11, "bold"), anchor="w")
            top.pack(side="left")
            sub = tk.Label(t, text="", font=("Segoe UI", 8), anchor="e")
            sub.pack(side="right", pady=(3, 0))
            for w in (t, top, sub):
                w.bind("<Button-1>", lambda e, l=lang: self.select_lang(l))
            self.tiles[lang] = (t, top, sub)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        legend = tk.Frame(c, bg=CARD)
        legend.pack(fill="x", pady=(0, 4))
        for st in ("ready", "zipped", "missing"):
            _, fg, word = TILE[st]
            tk.Label(legend, text=word, bg=CARD, fg=fg, font=("Segoe UI", 8)).pack(side="left", padx=(0, 8))
        tk.Label(legend, text="🔊 voice", bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(side="left")

        self.lang_lbl = tk.Label(c, text="No language loaded", bg=CARD, fg=MUTED, font=("Segoe UI", 9),
                                 anchor="w", justify="left", wraplength=320)
        self.lang_lbl.pack(fill="x")
        self.prune_var = tk.BooleanVar(value=not self.a.keep_unzipped)
        tk.Checkbutton(c, text="Save disk: re-delete other unzipped languages", variable=self.prune_var,
                       bg=CARD, fg=INK, activebackground=CARD, font=("Segoe UI", 9)).pack(anchor="w")
        self.disk_lbl = tk.Label(c, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 8), anchor="w")
        self.disk_lbl.pack(fill="x")

    def _links_card(self, parent):
        c = self._card(parent, "Radio links")
        self.link_rows = {}
        for name, tr, label in (("WIFI", self.wifi, "WiFi"),
                                ("LOWBITRATE", self.lb, "Low-bitrate*")):
            row = tk.Frame(c, bg=CARD)
            row.pack(fill="x", pady=3)
            btn = tk.Button(row, text=label, width=12, relief="flat", font=("Segoe UI", 9, "bold"),
                            fg="white", cursor="hand2", command=lambda t=tr, l=label: self.toggle_link(t, l))
            btn.pack(side="left")
            info = tk.Label(row, text="", bg=CARD, fg=MUTED, font=("Consolas", 8), anchor="w")
            info.pack(side="left", padx=6)
            self.link_rows[name] = (tr, btn, info)
        tk.Label(c, text=f"* EMULATED {self.a.lb_bps} bps radio (LoRa-ready interface). "
                         f"Click a link to switch it off / on.", bg=CARD, fg=MUTED, font=("Segoe UI", 8),
                 wraplength=340, justify="left", anchor="w").pack(fill="x")

        row = tk.Frame(c, bg=CARD)
        row.pack(fill="x", pady=(8, 2))
        self.peer_ip = self._field(row, "Peer IP", self.a.peer_ip or "", 15)
        self._button(row, "Connect", self.connect_ip, small=True).pack(side="left", padx=4)
        row = tk.Frame(c, bg=CARD)
        row.pack(fill="x", pady=2)
        loc = self.rm.location or ("", "")
        self.lat = self._field(row, "lat", loc[0], 10)
        self.lon = self._field(row, "lon", loc[1], 10)
        self._button(row, "Set", self.apply_loc, small=True).pack(side="left", padx=4)

    def _channel_card(self, parent):
        outer = tk.Frame(parent, bg=LINE, padx=1, pady=1)
        outer.pack(fill="x", pady=(0, 8))
        c = tk.Frame(outer, bg=CARD, padx=12, pady=8)
        c.pack(fill="x")
        top = tk.Frame(c, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, text="Channel conditions", bg=CARD, fg=INK, font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Label(top, text="  EMULATED • same on both laptops", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", pady=(3, 0))

        def chip_row(label):
            row = tk.Frame(c, bg=CARD)
            row.pack(fill="x", pady=(5, 0))
            tk.Label(row, text=label, bg=CARD, fg=MUTED, width=16, anchor="w",
                     font=("Segoe UI", 9)).pack(side="left")
            return row

        def chip(row, text, cmd, width=None):
            w = tk.Label(row, text=text, bg="#eef0f4", fg=INK, padx=8, pady=3, cursor="hand2",
                         font=("Segoe UI", 9, "bold"), **({"width": width} if width else {}))
            w.pack(side="left", padx=2)
            w.bind("<Button-1>", lambda e: cmd())
            return w

        row = chip_row("WiFi interference")
        self.wifi_chips = {lv: chip(row, lv, lambda lv=lv: self.change_env(wifi=lv), 7)
                           for lv in CH.WIFI_LEVELS}
        row = chip_row("Radio frequency")
        self.freq_chips = [chip(row, f"{mhz:.2f} MHz", lambda i=i: self.change_env(freq=i))
                           for i, mhz in enumerate(CH.FREQS_MHZ)]
        row = chip_row("Noise on this freq.")
        self.noise_chips = {lv: chip(row, lv, lambda lv=lv: self.set_noise(lv), 7) for lv in CH.RADIO_LEVELS}
        self._paint_env()

    def _chat(self, parent):
        # talk bar is packed first at the bottom so it is always visible, even on short screens
        bar = tk.Frame(parent, bg=BG)
        bar.pack(side="bottom", fill="x", pady=(8, 0))
        outer = tk.Frame(parent, bg=LINE, padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        box = tk.Frame(outer, bg=CARD)
        box.pack(fill="both", expand=True)
        sb = tk.Scrollbar(box)
        sb.pack(side="right", fill="y")
        self.out = tk.Text(box, bg=CARD, fg=INK, relief="flat", wrap="word", padx=12, pady=10,
                           font=(F, 11), state="disabled", yscrollcommand=sb.set, cursor="arrow")
        self.out.pack(fill="both", expand=True)
        sb.config(command=self.out.yview)
        t = self.out.tag_config
        t("sys", foreground=MUTED, font=("Segoe UI", 8), justify="center", spacing1=2, spacing3=2)
        t("tts", foreground=PURPLE, font=("Segoe UI", 8), lmargin1=12, lmargin2=12, spacing3=4)
        t("err", foreground=RED, font=("Segoe UI", 9, "bold"), justify="center", spacing1=3, spacing3=3)
        t("me_meta", foreground=MUTED, font=("Segoe UI", 8), justify="right", rmargin=8, spacing1=8)
        t("me", background="#dcf5e3", font=(F, 12), justify="right", lmargin1=160, lmargin2=160,
          rmargin=8, spacing3=2)
        t("them_meta", foreground=MUTED, font=("Segoe UI", 8), lmargin1=8, spacing1=8)
        t("them", background="#e3ecff", font=(F, 12), lmargin1=8, lmargin2=8, rmargin=160, spacing3=2)
        t("alert_meta", foreground=RED, font=("Segoe UI", 9, "bold"), lmargin1=8, spacing1=10)
        t("alert", background=RED, foreground="white", font=(F, 13, "bold"), lmargin1=8, lmargin2=8,
          rmargin=120, spacing3=2)
        t("where", foreground=BLUE, font=("Segoe UI", 9, "bold"), lmargin1=8, spacing3=4)

        self.ptt = tk.Label(bar, text=PTT_IDLE, bg=ACCENT, fg="white", width=18, pady=6,
                            font=("Segoe UI", 12, "bold"), cursor="hand2")
        self.ptt.pack(side="left")
        self.ptt.bind("<ButtonPress-1>", self.ptt_down)
        self.ptt.bind("<ButtonRelease-1>", self.ptt_up)
        self.auto_var = tk.BooleanVar()
        tk.Checkbutton(bar, text="Hands-free\n(send on pause)", variable=self.auto_var, bg=BG, fg=INK,
                       activebackground=BG, command=self.toggle_auto,
                       font=("Segoe UI", 9)).pack(side="left", padx=10)
        entry_box = tk.Frame(bar, bg=LINE, padx=1, pady=1)
        entry_box.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry = tk.Entry(entry_box, font=(F, 12), relief="flat")
        self.entry.pack(fill="both", ipady=9, ipadx=6)
        self.entry.bind("<Return>", lambda e: self.send_typed())
        self._button(bar, "Send", self.send_typed).pack(side="left")

    @staticmethod
    def _button(parent, text, cmd, small=False):
        return tk.Button(parent, text=text, command=cmd, bg=BLUE, fg="white", relief="flat",
                         activebackground="#2459b5", activeforeground="white", cursor="hand2",
                         font=("Segoe UI", 9 if small else 11, "bold"),
                         padx=8 if small else 18, pady=2 if small else 11)

    @staticmethod
    def _field(parent, label, value, width):
        tk.Label(parent, text=label, bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(0, 3))
        e = tk.Entry(parent, width=width, relief="solid", bd=1)
        e.insert(0, str(value))
        e.pack(side="left", padx=(0, 8))
        return e

    # ================================================================== output
    def note(self, text: str, tag: str = "sys"):
        """One small line. Thread-safe: may be called from any thread."""
        self._ui.put([(text, tag)])

    def bubble(self, parts):
        """parts = [(text, tag), ...] written together. Thread-safe."""
        self._ui.put(parts)

    def _pump(self):
        try:
            while True:
                parts = self._ui.get_nowait()
                self.out.configure(state="normal")
                for text, tag in parts:
                    stamp = time.strftime("%H:%M:%S  ") if tag in ("sys", "tts", "err") else ""
                    self.out.insert("end", stamp + text + "\n", tag)
                self.out.see("end")
                self.out.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._pump)

    def _refresh(self):
        other = CH.OTHER[self.a.role].upper()
        if self.disc.connected:
            p = self.disc.peer
            self.peer_lbl.config(text=f"● connected to {other} '{p.get('name', '?')}' ({self.disc.peer_ip})",
                                 fg="#7ee2a8")
        else:
            self.peer_lbl.config(text=f"○ searching for {other} on this WiFi...", fg="#ffb3b3")
        if self._was_connected and not self.disc.connected:
            self.note(f"{other} not heard for {CH.PEER_TIMEOUT:.0f} s (closed or out of range) - "
                      f"messages will wait in the queue", "err")
        self._was_connected = self.disc.connected
        cur = self.rm.current
        self.active_pill.config(text=f"ACTIVE LINK: {cur or 'NONE (queueing)'}",
                                bg={"WIFI": GREEN, "LOWBITRATE": ACCENT}.get(cur, RED))
        loc = self.rm.location
        self.loc_lbl.config(text=f"📍 {loc[0]:.5f}, {loc[1]:.5f}" if loc else "📍 no location set")
        for name, (tr, btn, info) in self.link_rows.items():
            st = self.rm.stats[name]
            up = self.rm.healthy(name)
            btn.config(bg=GREEN if up else (RED if tr.enabled else "#9aa0ab"),
                       activebackground=btn.cget("bg"))
            rtt = "-" if st.rtt_ms == float("inf") else f"{st.rtt_ms:.0f}ms"
            state = ("UP" if up else "DOWN") if tr.enabled else "OFF"
            info.config(text=f"{state:<4} PER {st.per * 100:3.0f}%  RTT {rtt:>5}  CRC-drop {st.crc_drops}")
        self._paint_tiles()
        if self.rec_stream is not None:
            how = "click to send" if self.rec_click_mode else "release to send"
            self.ptt.config(text=f"●  REC {time.time() - self.rec_start:4.1f}s\n{how}")
        self.root.after(500, self._refresh)

    def _paint_tiles(self):
        for lang, (t, top, sub) in self.tiles.items():
            bg, fg, word = TILE[MP.state("stt", lang)]
            sel = lang == self.lang
            voice = "" if MP.state("tts", lang) == "missing" else "  🔊"
            for w in (t, top, sub):
                w.config(bg=bg)
            t.config(highlightbackground=ACCENT if sel else bg)
            top.config(fg=INK)
            sub.config(fg=fg, text=f"{MP.NAMES[lang]} {word[0]}{voice}")

    # ================================================================== language packs
    def select_lang(self, lang: str):
        if self.busy or lang == self.lang:
            return
        if MP.state("stt", lang) == "missing":
            self.note(f"No speech model for {MP.NAMES[lang]} yet (no zip in language_packs/). "
                      f"You can still type text.", "err")
            return
        self.busy = True
        self.lang_lbl.config(text=f"⏳ Loading {MP.NAMES[lang]}...", fg=ACCENT)
        self.ptt.config(bg="#c9ced8")
        threading.Thread(target=self._load_lang, args=(lang,), daemon=True).start()

    def _load_lang(self, lang: str):
        t = time.time()
        done = None
        try:
            step = lambda s: self.note(f"[packs] {s}")
            MP.ensure("stt", lang, step)
            if MP.state("tts", lang) != "missing":
                MP.ensure("tts", lang, step)             # own voice too, e.g. for alerts
            unzip_s = time.time() - t
            if self.speech is None:
                self.speech = Speech(lang)
            else:
                self.speech.set_lang(lang)             # frees the old model first
            self.lang = lang
            self.heard.add(lang)
            done = (f"✓ {MP.NAMES[lang]} speech model loaded in {time.time() - t:.1f}s "
                    f"(unzip {unzip_s:.1f}s)")
            if MP.state("tts", lang) == "missing":
                done += f"\n  no {MP.NAMES[lang]} voice installed (receiver can't speak it)"
            self.note(done.replace("\n", "  "))
            if self.prune_var.get():
                freed = MP.prune({"stt": [lang], "tts": set(self.heard)}, log=self.note)
                if freed:
                    self.note(f"[packs] freed {freed / 1e6:.0f} MB (other languages stay in zips)")
        except Exception as e:
            self.note(f"loading {lang} failed: {type(e).__name__}: {e}", "err")
        finally:
            self.busy = False
            msg, col = (done, GREEN) if done else (
                (f"✓ {MP.NAMES[self.lang]} loaded", GREEN) if self.lang else ("No language loaded", MUTED))
            self.root.after(0, lambda: (self.lang_lbl.config(text=msg, fg=col),
                                        self.ptt.config(bg=ACCENT), self._disk()))

    def _disk(self):
        lines = MP.status_table().splitlines()
        self.disk_lbl.config(text=lines[-1] if lines else "")

    # ================================================================== talking
    def _ready_to_talk(self) -> bool:
        if self.busy:
            self.note("wait - a language is still loading", "err")
            return False
        if self.speech is None:
            self.note("pick a language first", "err")
            return False
        return True

    def ptt_down(self, _e=None):
        if self.rec_stream is not None:              # click mode: second click stops and sends
            self._stop_rec()
            return
        if not self._ready_to_talk():
            return
        self.rec_click_mode = False
        import sounddevice as sd
        self.rec_frames = []
        try:
            self.rec_stream = sd.RawInputStream(samplerate=SR, channels=1, dtype="int16",
                                                callback=lambda d, n, t, s: self.rec_frames.append(bytes(d)))
            self.rec_stream.start()
        except Exception as e:
            self.rec_stream = None
            self.note(f"cannot open microphone: {e}", "err")
            return
        self.rec_start = time.time()
        self.ptt.config(bg=RED, text="●  REC 0.0s\nrelease to send")

    def ptt_up(self, _e=None):
        if self.rec_stream is None:
            return
        if time.time() - self.rec_start < 0.4 and not self.rec_click_mode:
            self.rec_click_mode = True               # quick click = keep recording until next click
            return
        self._stop_rec()

    def _stop_rec(self):
        self.rec_stream.stop()
        self.rec_stream.close()
        self.rec_stream = None
        self.ptt.config(bg=ACCENT, text=PTT_IDLE)
        pcm = b"".join(self.rec_frames)
        self.note("transcribing...")
        threading.Thread(target=self.handle_speech, args=(pcm, "push-to-talk"), daemon=True).start()

    def handle_speech(self, pcm: bytes, source: str = "hands-free"):
        if len(pcm) < SR * 2 * MIN_SPEECH_MS / 1000:
            self.note("too short, ignored (hold the button while speaking)", "err")
            return
        try:
            text, stt_s, audio_s = self.speech.transcribe_pcm(pcm)
        except Exception as e:
            self.note(f"STT error: {e}", "err")
            return
        if not text:
            self.note(f"no speech recognized ({audio_s:.1f}s audio), nothing sent", "err")
            return
        self._send(text, f"🎙 {source}  •  audio {audio_s:.1f}s  •  STT {stt_s * 1000:.0f} ms  •  "
                         f"RTF {stt_s / audio_s:.2f}")

    def toggle_auto(self):
        if self.auto_var.get():
            if not self._ready_to_talk():
                self.auto_var.set(False)
                return
            self.auto = AutoListener(self.speech, self.rm, on_speech=self.handle_speech,
                                     log=lambda s: self.note(s.strip()))
            self.auto.start()
        elif self.auto:
            self.auto.running = False
            self.auto = None
            self.note("[auto] stopped")

    def send_typed(self):
        text = self.entry.get().strip()
        if text:
            self.entry.delete(0, "end")
            self._send(text, "⌨ typed")

    def _send(self, text: str, how: str):
        lang = self.lang or "en"
        self.rm.send_message(text, lang)
        where = (self.rm.current if self.rm.current and self.disc.connected
                 else f"waiting for {CH.OTHER[self.a.role]} (queued, sends automatically)")
        self.bubble([(f"{how}  •  {lang}  •  {where}", "me_meta"), (f" {text} ", "me")])

    # ================================================================== receiving
    def on_receive(self, msg: Received):
        lat = f"{msg.latency_ms:.0f} ms" if msg.latency_ms is not None else "n/a on compact link"
        extra = f"  •  FEC fixed {msg.fec_corrections} bit(s)" if msg.fec_corrections else ""
        kind = "short alert summary" if msg.kind == "SUMMARY" else "message"
        meta = f"{'🚨 ALERT  •  ' if msg.alert else ''}{kind} via {msg.channel}  •  {msg.lang}  •  latency {lat}{extra}"
        parts = [(meta, "alert_meta" if msg.alert else "them_meta"),
                 (f" {msg.text} ", "alert" if msg.alert else "them")]
        if msg.location:
            parts.append((f"📍 {L.describe(msg.location, self.rm.location)}", "where"))
        self.bubble(parts)
        if self.speaker is not None:
            from .speaker import voice_for_text
            voice = (voice_for_text(msg.text, msg.lang) if msg.kind != "SUMMARY"
                     else "hi" if msg.lang == "hi" else "en")    # same rule as Speaker
            if voice in MP.LANGS:
                self.heard.add(voice)
                if MP.state("tts", voice) == "zipped":
                    self.note(f"[packs] unzipping {MP.NAMES[voice]} voice for this message...")
            self.speaker.say(msg)

    # ================================================================== links
    def toggle_link(self, tr, label):
        tr.enabled = not tr.enabled
        self.note(f"{label} switched {'ON' if tr.enabled else 'OFF'}")

    # ================================================================== peer + channel lab
    def on_peer(self, ip: str, info: dict):
        """Discovery found the other laptop: point both links at it (called from a network thread)."""
        self.wifi.peer = (ip, int(info["wifi_port"]))
        self.lb.peer = (ip, int(info["lb_port"]))
        for st in self.rm.stats.values():               # forget probes sent to the old address
            st.results.clear()
            st.rtts.clear()
        self.note(f"🔗 Connected to {info['role'].upper()} '{info.get('name', '?')}' at {ip}. "
                  f"Links come up in a few seconds.")

    def connect_ip(self):
        ip = self.peer_ip.get().strip()
        if ip:
            self.disc.manual_ip = ip
            self.note(f"looking for the {CH.OTHER[self.a.role]} at {ip}...")

    def change_env(self, **changes):
        self.apply_env(self.disc.set_env(**changes), False)

    def set_noise(self, level: str):
        noise = list(self.disc.env["noise"])
        noise[self.disc.env["freq"]] = level
        self.change_env(noise=noise)

    def apply_env(self, env: dict, from_peer: bool):
        CH.apply_env(env, self.wifi, self.lb)
        self._paint_env()
        f = env["freq"]
        self.note(f"📡 Channel: WiFi {env['wifi']}  •  radio {CH.FREQS_MHZ[f]:.4f} MHz ({env['noise'][f]})"
                  + ("   (changed on the other laptop)" if from_peer else ""))

    def _paint_env(self):
        env = self.disc.env
        for lv, w in self.wifi_chips.items():
            on = lv == env["wifi"]
            w.config(bg=LEVEL_COLOR[lv] if on else "#eef0f4", fg="white" if on else INK)
        for i, w in enumerate(self.freq_chips):
            on = i == env["freq"]
            w.config(bg=BLUE if on else "#eef0f4", fg="white" if on else LEVEL_COLOR[env["noise"][i]])
        cur = env["noise"][env["freq"]]
        for lv, w in self.noise_chips.items():
            on = lv == cur
            w.config(bg=LEVEL_COLOR[lv] if on else "#eef0f4", fg="white" if on else INK)

    def apply_loc(self):
        try:
            self.rm.set_location(float(self.lat.get()), float(self.lon.get()))
            self.note(f"location = {self.rm.location}")
        except ValueError:
            self.note("lat / lon must be numbers", "err")

    def close(self):
        if self.auto:
            self.auto.running = False
        if self.rec_stream is not None:
            self.rec_stream.close()
        self.rm.stop()
        self.disc.stop()
        self.root.destroy()


def main():
    import socket
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=["sender", "receiver"], default="sender")
    ap.add_argument("--name", default=None, help="shown on the other laptop (default: computer name)")
    ap.add_argument("--lang", default=None, help="language to load at start (optional)")
    ap.add_argument("--peer-ip", default=None, help="other laptop's IP, only if auto-discovery fails")
    ap.add_argument("--discovery-offset", type=int, default=0, help=argparse.SUPPRESS)
    ap.add_argument("--wifi-port", type=int)
    ap.add_argument("--peer-wifi-port", type=int)
    ap.add_argument("--lb-port", type=int)
    ap.add_argument("--peer-lb-port", type=int)
    ap.add_argument("--lb-bps", type=int, default=600)
    ap.add_argument("--lb-loss", type=float, default=0.1)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--no-tts", action="store_true", help="show received messages without speaking")
    ap.add_argument("--save-wav", default=None, help="write received audio to this folder instead of playing")
    ap.add_argument("--keep-unzipped", action="store_true", help="do not delete other unzipped languages")
    ap.add_argument("--lat", type=float, default=None)
    ap.add_argument("--lon", type=float, default=None)
    a = ap.parse_args()
    for k, v in PRESETS[a.role].items():
        if getattr(a, k) is None:
            setattr(a, k, v)
    a.name = a.name or socket.gethostname()

    try:                                   # sharp text on high-DPI Windows screens
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    try:
        App(root, a)
    except OSError as e:
        root.destroy()
        raise SystemExit(f"\nCannot start: a port is already in use ({e}).\n"
                         f"An iTantra {a.role.upper()} window is probably already open - close it "
                         f"(or its terminal) and run again.")
    root.mainloop()


if __name__ == "__main__":
    main()
