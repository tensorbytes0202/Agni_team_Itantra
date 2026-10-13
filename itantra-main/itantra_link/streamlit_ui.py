"""
Connection UI: scan WiFi -> connect (password only if needed) -> find the peer -> send.
Messages typed while offline stay queued (also on disk) and go out when a link comes back.

    streamlit run itantra_link/streamlit_ui.py                                   # sender
    streamlit run itantra_link/streamlit_ui.py --server.port 8502 -- receiver    # receiver
"""
import collections
import os
import sys
import time
from types import SimpleNamespace

import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from itantra_link import channel_lab as CH, wifi_scan as W
from itantra_link.radio_manager import RadioManager
from itantra_link.transports import EmulatedLowBitrateTransport, UdpWifiTransport

PORTS = {"sender": (5001, 6001), "receiver": (5002, 6002)}       # (wifi, low-bitrate)
LANGS = ["en", "hi", "gu", "mr", "kn", "ml", "ta", "te", "or", "bn"]


@st.cache_resource
def node(role: str) -> SimpleNamespace:
    (wp, lp), (pwp, plp) = PORTS[role], PORTS[CH.OTHER[role]]
    n = SimpleNamespace(inbox=collections.deque(maxlen=50), logs=collections.deque(maxlen=30))
    n.wifi = UdpWifiTransport(wp, "127.0.0.1", pwp)
    n.lb = EmulatedLowBitrateTransport(lp, "127.0.0.1", plp)
    log = lambda s: n.logs.appendleft(f"{time.strftime('%H:%M:%S')} {s.strip()}")
    n.rm = RadioManager([n.wifi, n.lb], on_receive=n.inbox.appendleft, log=log,
                        queue_file=f"queue_{role}.json")

    def on_peer(ip, info):
        n.wifi.peer, n.lb.peer = (ip, int(info["wifi_port"])), (ip, int(info["lb_port"]))
        for s in n.rm.stats.values():                    # forget probes sent to the old address
            s.results.clear()
            s.rtts.clear()
        log(f"peer {info.get('name', '?')} found at {ip}")

    n.disc = CH.Discovery(role, role, wp, lp, on_peer=on_peer, on_env=lambda env: None)
    n.rm.start()
    n.disc.start()
    return n


st.set_page_config(page_title="iTantra Link", page_icon="📡", layout="wide")
ROLES = ["sender", "receiver"]
role = st.sidebar.radio("Role", ROLES, index=int("receiver" in sys.argv[1:]))   # `-- receiver` on the CLI
n = node(role)
n.lb.enabled = st.sidebar.toggle("Low-bitrate link (emulated)", value=True)
n.wifi.enabled = st.sidebar.toggle("WiFi link", value=True)
ip = st.sidebar.text_input("Peer IP (optional, if broadcast is blocked)")
if st.sidebar.button("Use this IP") and ip:
    n.disc.manual_ip = ip.strip()

st.title(f"📡 iTantra Link — {role}")

# ------------------------------------------------------------------ 1. network
st.subheader("1 · Network")
if st.button("🔍 Search networks"):
    with st.spinner("Scanning nearby WiFi…"):
        st.session_state.nets = W.scan()
nets = st.session_state.get("nets", [])
if nets:
    st.dataframe([{"SSID": x["ssid"], "Signal %": x["signal"], "Band": x["band"],
                   "Security": x["auth"] if x["secured"] else "Open 🔓"} for x in nets],
                 hide_index=True, width="stretch")
    pick = st.selectbox("Choose network", nets, format_func=lambda x:
                        f"{x['ssid']}  ·  {x['signal']}%  ·  {x['band']}  {'🔒' if x['secured'] else '🔓 open'}")
    pw = st.text_input("Password (leave empty if saved before)", type="password") if pick["secured"] else None
    if st.button("Connect", type="primary"):
        with st.spinner(f"Connecting to {pick['ssid']}…"):
            ok, msg = W.connect(pick["ssid"], pw or None, pick["auth"])
        (st.success if ok else st.error)(msg)


# ------------------------------------------------------------------ 2. live status
@st.fragment(run_every=2)
def live():
    ssid, sig = W.current()
    n.rm.wifi_signal = sig
    c = st.columns(5)
    c[0].metric("Network", ssid or "offline")
    c[1].metric("Signal", f"{sig}%" if sig is not None else "—")
    c[2].metric("Peer", n.disc.peer_ip if n.disc.connected else "searching…")
    c[3].metric("Active link", n.rm.current or "none")
    c[4].metric("Queued", n.rm.queued)
    if n.rm.queued and not n.rm.current:
        st.warning("No link: messages are queued and will be sent automatically when a link is back.")
    elif n.rm.current == "WIFI" and n.rm._weak_wifi():
        st.info("Weak WiFi: sending compressed text to save bandwidth.")
    st.caption(n.rm.status())

    st.subheader("3 · Received")
    for m in list(n.inbox):
        lat = f" · {m.latency_ms:.0f} ms" if m.latency_ms is not None else ""
        (st.error if m.alert else st.info)(f"**[{m.kind}] via {m.channel} · {m.lang}{lat}**  \n{m.text}")
    with st.expander("Log"):
        st.text("\n".join(n.logs) or "—")


st.subheader("2 · Send")
with st.form("send", clear_on_submit=True):
    col = st.columns([5, 1])
    text = col[0].text_input("Message", placeholder="emergency, madad bhejo")
    lang = col[1].selectbox("Lang", LANGS)
    if st.form_submit_button("Send") and text.strip():
        n.rm.send_message(text.strip(), lang)
live()
