"""
Connection UI: scan WiFi -> connect (password only if needed) -> find the peer -> send.
Messages typed while offline stay queued (also on disk) and go out when a link comes back.
Run from the itantra-main folder, so .streamlit/config.toml (theme, localhost only) is picked up:

    python -m streamlit run itantra_link/streamlit_ui.py                                  # sender
    python -m streamlit run itantra_link/streamlit_ui.py --server.port 8502 -- receiver   # receiver
"""
import collections
import io
import os
import string
import sys
import threading
import time
import wave
from types import SimpleNamespace

import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from itantra_link import channel_lab as CH, location as L, wifi_scan as W
from itantra_link.radio_manager import RadioManager
from itantra_link.transports import EmulatedLowBitrateTransport, UdpWifiTransport

PORTS = {"sender": (5001, 6001), "receiver": (5002, 6002)}       # (wifi, low-bitrate)
LANGS = {"en": "English", "hi": "हिन्दी", "gu": "ગુજરાતી", "mr": "मराठी", "kn": "ಕನ್ನಡ",
         "ml": "മലയാളം", "ta": "தமிழ்", "te": "తెలుగు", "or": "ଓଡ଼ିଆ", "bn": "বাংলা"}
LINK_NAMES = {"WIFI": "Wi-Fi", "BLUETOOTH": "Bluetooth", "LOWBITRATE": "Low-bitrate radio"}


def plain(text) -> str:
    """Untrusted text (peer names, nearby SSIDs) inside markdown labels, shown literally: every ASCII punctuation
    character becomes an HTML entity, so markdown, links, images and :badge[...] directives never render."""
    return "".join(f"&#{ord(c)};" if c in string.punctuation else c for c in str(text))


REFRESH = 2                                                     # seconds between live updates


@st.cache_resource
def node(role: str) -> SimpleNamespace:
    """One radio node per role and process: sockets, Radio Manager, discovery."""
    (wp, lp), (pwp, plp) = PORTS[role], PORTS[CH.OTHER[role]]
    n = SimpleNamespace(feed=collections.deque(maxlen=100), logs=collections.deque(maxlen=50))
    n.wifi = UdpWifiTransport(wp, "127.0.0.1", pwp)
    n.lb = EmulatedLowBitrateTransport(lp, "127.0.0.1", plp)
    log = lambda s: n.logs.appendleft(f"{time.strftime('%H:%M:%S')}  {s.strip()}")
    n.speak = True
    try:                                                 # offline TTS; absent on a text-only install
        from itantra_link.speaker import Speaker
        n.speaker = Speaker(lambda: n.rm.location, log=log)
    except Exception as e:
        n.speaker = None
        log(f"voice playback off ({type(e).__name__}: {e})")

    def on_receive(m):
        n.feed.appendleft(("in", time.time(), m))
        if n.speaker and n.speak:
            n.speaker.say(m)                             # alerts: siren + full volume, not interruptible

    n.rm = RadioManager([n.wifi, n.lb], log=log, queue_file=f"queue_{role}.json", on_receive=on_receive)

    def on_peer(ip, info):
        n.wifi.peer, n.lb.peer = (ip, int(info["wifi_port"])), (ip, int(info["lb_port"]))
        for s in n.rm.stats.values():                    # forget probes sent to the old address
            s.results.clear()
            s.rtts.clear()
        log(f"peer '{info.get('name', '?')}' found at {ip}")

    n.disc = CH.Discovery(role, role, wp, lp, on_peer=on_peer, on_env=lambda env: None)
    n.rm.start()
    n.disc.start()
    return n


@st.cache_resource
def stt_holder() -> SimpleNamespace:
    """At most one STT model in RAM for the whole app; switching language frees the old one."""
    return SimpleNamespace(speech=None, lock=threading.Lock())


def pcm16k(wav_bytes: bytes) -> bytes:
    """Browser recording (WAV) -> 16 kHz mono int16, what both STT engines expect."""
    import numpy as np
    with wave.open(io.BytesIO(wav_bytes)) as wf:
        ch, width, rate = wf.getnchannels(), wf.getsampwidth(), wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    a = np.frombuffer(raw, dtype={1: np.uint8, 2: np.int16, 4: np.int32}[width]).astype(np.float32)
    a = (a - 128) * 256 if width == 1 else a / 65536 if width == 4 else a
    a = a.reshape(-1, ch).mean(axis=1)
    if rate != 16000:
        a = np.interp(np.arange(0, len(a), rate / 16000), np.arange(len(a)), a)
    return np.clip(a, -32768, 32767).astype(np.int16).tobytes()


def transcribe(wav_bytes: bytes, lang: str):
    """Offline STT. Returns (text, stt_seconds, audio_seconds)."""
    from itantra_ai import model_packs as MP
    from itantra_link.voice_node import Speech
    if MP.state("stt", lang) == "missing":
        raise LookupError(f"No {LANGS[lang]} speech model on this laptop yet (see README → Models).")
    h = stt_holder()
    with h.lock:
        MP.ensure("stt", lang)                           # unzip the language pack if needed
        if h.speech is None:
            h.speech = Speech(lang)
        else:
            h.speech.set_lang(lang)
        return h.speech.transcribe_pcm(pcm16k(wav_bytes))


# ------------------------------------------------------------------ page + state
st.set_page_config(page_title="iTantra link", page_icon=":material/cell_tower:", layout="wide")
st.session_state.setdefault("nets", None)
st.session_state.setdefault("flash", None)
st.session_state.setdefault("mic_n", 0)                  # bump to clear the recorder after each message
st.session_state.setdefault("mic_note", None)

with st.sidebar:
    st.title(":material/cell_tower: iTantra link")
    st.caption("Offline voice-as-text over weak links")
    default_role = "Receiver" if "receiver" in sys.argv[1:] else "Sender"
    role = (st.segmented_control("Role", ["Sender", "Receiver"], default=default_role, width="stretch")
            or default_role).lower()
    try:
        n = node(role)
    except OSError:
        st.error(f"The {role} ports on this laptop are busy: another window or terminal is already running the "
                 f"{role}, or this app's code changed while it was running. Close the other one, or restart this "
                 "app (Ctrl+C in its terminal, then run it again).", icon=":material/error:")
        st.stop()

    st.subheader(":material/settings_input_antenna: Links")
    n.wifi.enabled = st.toggle("WiFi", value=True, help="Real UDP over the local network")
    n.lb.enabled = st.toggle("Low-bitrate radio", value=True,
                             help="Emulated 600 bps LoRa-class link with loss and bit errors")

    st.subheader(":material/record_voice_over: Voice")
    n.speak = st.toggle("Speak received messages", value=n.speak, disabled=n.speaker is None,
                        help="Offline text-to-speech on this laptop. Alerts play a siren at full volume."
                        if n.speaker else "Needs the full install: pip install -r requirements.txt")

    st.subheader(":material/lan: Peer")
    with st.form("peer", border=False):
        ip = st.text_input("Peer IP", placeholder="192.168.1.23",
                           help="Only needed if the network blocks broadcast discovery")
        if st.form_submit_button("Use this IP", icon=":material/link:", width="stretch") and ip.strip():
            n.disc.manual_ip = ip.strip()
            st.toast(f"Looking for the {CH.OTHER[role]} at {plain(ip.strip())}", icon=":material/search:")

if st.session_state.flash:
    st.toast(st.session_state.flash[0], icon=st.session_state.flash[1])
    st.session_state.flash = None


# ------------------------------------------------------------------ live panels
@st.fragment(run_every=REFRESH)
def overview():
    ssid, sig = W.current()
    n.rm.wifi_signal = sig
    peer = n.disc.connected

    with st.container(horizontal=True, vertical_alignment="center"):
        st.badge(role.capitalize(), icon=":material/person:", color="blue")
        if peer:
            st.badge(f"Connected to {plain(n.disc.peer.get('name', 'peer'))}", icon=":material/check_circle:", color="green")
        else:
            st.badge(f"Searching for the {CH.OTHER[role]}", icon=":material/radar:", color="orange")
        if n.rm.current == "WIFI" and n.rm.weak_wifi():
            st.badge("Weak WiFi: compressing", icon=":material/compress:", color="yellow")

    with st.container(horizontal=True):
        st.metric((":material/wifi:" if ssid else ":material/wifi_off:") + " Network", ssid or "Offline",
                  border=True)
        st.metric(":material/signal_cellular_alt: Signal", f"{sig}%" if sig is not None else "—", border=True)
        st.metric(":material/devices: Peer", n.disc.peer_ip if peer else "—", border=True)
        st.metric(":material/route: Active link", LINK_NAMES.get(n.rm.current, "None"), border=True)
        st.metric(":material/schedule_send: Queued", n.rm.queued, border=True)

    if n.rm.queued and not n.rm.current:
        st.warning("No link right now. Queued messages are saved and will be sent automatically, alerts first.",
                   icon=":material/cloud_off:")


@st.fragment(run_every=REFRESH)
def link_health():
    rows = []
    for name in n.rm.t:
        s = n.rm.stats[name]
        rows.append({"Link": LINK_NAMES.get(name, name), "Status": "🟢 Up" if n.rm.healthy(name) else "🔴 Down",
                     "Loss": round(s.per * 100), "RTT": None if s.rtt_ms == float("inf") else round(s.rtt_ms),
                     "CRC drops": s.crc_drops, "Active": name == n.rm.current})
    st.dataframe(rows, hide_index=True, column_config={
        "Loss": st.column_config.ProgressColumn("Packet loss", format="%d%%", min_value=0, max_value=100),
        "RTT": st.column_config.NumberColumn("RTT", format="%d ms"),
        "Active": st.column_config.CheckboxColumn("In use"),
    })
    with st.expander("Event log", icon=":material/terminal:"):
        st.code("\n".join(n.logs) or "No events yet", language=None, height=200)


@st.fragment(run_every=REFRESH)
def feed():
    pending = {(p[2], p[3]) for p in n.rm.pending()}
    with st.container(height=380, border=False):
        if not n.feed:
            st.caption("No messages yet. Messages you send and receive appear here.")
        for kind, t, m in n.feed:
            when = time.strftime("%H:%M:%S", time.localtime(t))
            if kind == "out":
                text, lang = m
                state = ":orange-badge[:material/schedule: Queued]" if (text, lang) in pending \
                    else ":green-badge[:material/done_all: Sent]"
                with st.chat_message("you", avatar=":material/north_east:"):
                    st.text(text)
                    st.caption(f"{state}  ·  {LANGS.get(lang, plain(lang))}  ·  {when}")
                continue
            with st.chat_message("peer", avatar=":material/campaign:" if m.alert else ":material/south_west:"):
                tags = (":red-badge[:material/warning: Alert] " if m.alert else "") +                        (":gray-badge[Summary]" if m.kind == "SUMMARY" else "")
                if tags:
                    st.markdown(tags)
                st.text(m.text)                           # peer text: never parsed as markdown
                meta = [f"via {LINK_NAMES.get(m.channel, m.channel)}", LANGS.get(m.lang, plain(m.lang)), when]
                if m.latency_ms is not None:
                    meta.insert(1, f"{m.latency_ms:.0f} ms")
                if m.fec_corrections:
                    meta.append(f"FEC fixed {m.fec_corrections} bit(s)")
                st.caption("  ·  ".join(meta))
                if m.location:
                    st.caption(f":material/location_on: {L.describe(m.location, n.rm.location)}")


# ------------------------------------------------------------------ network dialog
@st.dialog("Connect to network")
def connect_dialog(net):
    st.markdown(f"**{plain(net['ssid'])}**  ·  {net['signal']}%  ·  {net['band'] or 'band unknown'}  ·  "
                f"{plain(net['auth'])}")
    with st.form("connect", border=False):
        pw = st.text_input("WiFi password", type="password",
                           help="The password of this network (for a phone hotspot: the hotspot password). "
                                "Leave empty if this laptop has joined it before.")
        if st.form_submit_button("Connect", type="primary", icon=":material/link:", width="stretch"):
            with st.spinner(f"Connecting to {plain(net['ssid'])}…"):
                ok, msg = W.connect(net["ssid"], pw or None, net["auth"])
            if ok:
                st.session_state.flash = (plain(msg.capitalize()), ":material/wifi:")
                st.rerun()
            st.error(plain(msg), icon=":material/error:")


# ------------------------------------------------------------------ layout
st.title(":material/hub: Connection dashboard")
overview()

left, right = st.columns(2, gap="medium")
with left:
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.subheader(":material/wifi_find: Networks")
            scan = st.button("Scan", icon=":material/refresh:", type="primary")
        if scan:
            with st.spinner("Scanning nearby WiFi…"):
                st.session_state.nets = W.scan()
        nets = st.session_state.nets
        if nets is None:
            st.caption("Scan to list nearby networks, strongest first. Open networks join in one click.")
        elif not nets:
            st.caption("No networks found. Check that WiFi is turned on."
                       + (" On macOS, also allow Location Services for your terminal app (System Settings → "
                          "Privacy & Security), or macOS hides network names." if W.MAC else ""))
        else:
            event = st.dataframe(
                [{"Network": x["ssid"], "Signal": x["signal"], "Band": x["band"],
                  "Security": "🔒 " + x["auth"].split("-")[0] if x["secured"] else "🔓 Open"} for x in nets],
                hide_index=True, on_select="rerun", selection_mode="single-row", key="nets_table",
                column_config={"Network": st.column_config.TextColumn(width="medium"),
                               "Signal": st.column_config.ProgressColumn(format="%d%%", min_value=0, max_value=100,
                                                                         width="small"),
                               "Band": st.column_config.TextColumn(width="small")})
            rows = event.selection.rows
            if not rows:
                st.caption("Select a network to connect.")
            else:
                net = nets[rows[0]]
                label = f"Connect to {plain(net['ssid'])}"
                if st.button(label, icon=":material/link:", type="primary", width="stretch"):
                    if net["secured"]:
                        connect_dialog(net)
                    else:
                        with st.spinner(f"Connecting to {plain(net['ssid'])}…"):
                            ok, msg = W.connect(net["ssid"], None, net["auth"])
                        (st.success if ok else st.error)(plain(msg))

    with st.container(border=True):
        st.subheader(":material/monitor_heart: Link health")
        link_health()

with right:
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.subheader(":material/forum: Messages")
            lang = st.selectbox("Language", list(LANGS), format_func=LANGS.get, label_visibility="collapsed",
                                width=150, help="Language of the messages you send")
        feed()
        with st.form("send", clear_on_submit=True, border=False):
            with st.container(horizontal=True, vertical_alignment="bottom"):
                text = st.text_input("Message", placeholder="emergency, madad bhejo", label_visibility="collapsed")
                sent = st.form_submit_button("Send", icon=":material/send:", type="primary")
        if sent and text.strip():
            n.rm.send_message(text.strip(), lang)
            n.feed.appendleft(("out", time.time(), (text.strip(), lang)))
            st.rerun()

        audio = st.audio_input(f":material/mic: Speak in {LANGS[lang]}", sample_rate=16000,
                               key=f"mic_{st.session_state.mic_n}",
                               help="Record, stop, and it is turned into text offline and sent. "
                                    "Pick the language at the top of this card first.")
        if audio is not None:
            with st.spinner("Converting speech to text offline…"):
                try:
                    heard, stt_s, audio_s = transcribe(audio.getvalue(), lang)
                except Exception as e:
                    st.session_state.mic_note = ("error", f"{type(e).__name__}: {e}")
                else:
                    if heard:
                        n.rm.send_message(heard, lang)
                        n.feed.appendleft(("out", time.time(), (heard, lang)))
                        st.session_state.mic_note = ("ok", f"Heard in {stt_s * 1000:.0f} ms "
                                                           f"(RTF {stt_s / max(audio_s, 1e-6):.2f}) and sent.")
                    else:
                        st.session_state.mic_note = ("warn", "Didn't catch any words. Try again, a bit closer.")
            st.session_state.mic_n += 1                  # new key = empty recorder for the next message
            st.rerun()
        if st.session_state.mic_note:
            kind, note = st.session_state.mic_note
            {"ok": st.caption, "warn": st.warning, "error": st.error}[kind](plain(note))
