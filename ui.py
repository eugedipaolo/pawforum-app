import html
import time
from pathlib import Path
from typing import Dict, Any, Optional
import streamlit as st
from PIL import Image

from db import list_channels, insert_channel, list_messages, add_message
from auth import auth_ui, current_user

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

PALETTE = {
    "Background": "#1f2937",
    "Surface": "#0f172a",
    "Accent (Blue)": "#3b82f6",
    "Accent (Orange)": "#f59e0b",
    "Text": "#e5e7eb",
    "Text strong": "#ffffff",
}

def _ensure_defaults():
    # evita KeyError en la primera carga
    st.session_state.setdefault("uploader_key", 0)
    st.session_state.setdefault("msg_input", "")

def inject_styles():
    st.markdown(f"""
    <style>
      :root {{
        --bg: {PALETTE['Surface']};
        --panel: {PALETTE['Background']};
        --accent: {PALETTE['Accent (Blue)']};
        --accent2: {PALETTE['Accent (Orange)']};
        --text: {PALETTE['Text']};
        --text-strong: {PALETTE['Text strong']};
      }}
      html, body, [data-testid="stAppViewContainer"] {{ background: var(--bg); color: var(--text); }}
      [data-testid="stSidebar"] {{ background: var(--panel); }}
      .bubble {{
        background: var(--panel);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 10px 12px;
        margin-bottom: 8px;
      }}
      .bubble.self {{ border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent) inset; }}
      .timestamp {{ color: #9ca3af; font-size: 12px; }}
      .stButton>button {{ background: var(--accent2); color: #fff; border: 0; border-radius: 10px; padding: 8px 14px; }}
      input[type="text"], textarea, .stTextInput>div>div>input {{
        background: var(--panel) !important; color: var(--text) !important; border: 1px solid rgba(255,255,255,0.12);
        border-radius: 10px; padding: 8px 10px; transition: border-color .2s ease, box-shadow .2s ease;
      }}
      input[type="text"]:focus, textarea:focus, .stTextInput>div>div>input:focus {{
        border-color: var(--accent) !important; box-shadow: 0 0 0 2px rgba(59,130,246,.35) !important; outline: none !important;
      }}
    </style>
    """, unsafe_allow_html=True)


def render_palette():
    st.subheader("Brand colors")
    st.caption("Palette used across the app")
    cols = st.columns(3)
    items = list(PALETTE.items())
    for i, (label, hexv) in enumerate(items):
        with cols[i % 3]:
            st.markdown(
                f"""
                <div style=\"border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:12px;background:#111827\">
                  <div style=\"height:56px;border-radius:8px;background:{hexv};\"></div>
                  <div style=\"font-size:12px;color:#e5e7eb;margin-top:8px\">{label}</div>
                  <div style=\"font-size:12px;color:#9ca3af\">{hexv}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def sidebar_ui(app_title: str):
    st.sidebar.title(app_title)

    # Auth
    auth_ui()

    # Channels
    st.sidebar.subheader("Channels")
    chs = list_channels()
    ids = [c["id"] for c in chs]
    if "active_channel" not in st.session_state:
        st.session_state.active_channel = ids[0] if ids else "general"

    selected = st.sidebar.selectbox(
        "Select a channel",
        options=ids,
        format_func=lambda cid: next((f"#{c['id']} — {c['name']}" for c in chs if c['id']==cid), cid),
    )
    st.session_state.active_channel = selected

    with st.sidebar.expander("Create channel"):
        new_id = st.text_input("Channel id (e.g., cats-life)")
        new_name = st.text_input("Display name (e.g., Cats Life)")
        if st.button("Create"):
            err = insert_channel(new_id, new_name)
            if err:
                st.error(err)
            else:
                st.success(f"Channel #{new_id} created")
                st.rerun()

    # View options
    st.sidebar.subheader("View options")
    refresh = st.sidebar.checkbox("Auto-refresh", value=True, help="Update messages every few seconds")
    interval_ms = st.sidebar.slider("Refresh every (seconds)", 2, 20, 4) * 1000

    return {"refresh": refresh, "interval_ms": interval_ms}, selected, current_user()


def message_bubble(msg: Dict[str, Any], username: Optional[str]):
    from datetime import datetime
    ts = datetime.fromtimestamp(msg["ts"]).strftime("%H:%M") if msg.get("ts") else ""
    is_self = (msg.get("user") or "") == (username or "")
    bubble_class = "bubble self" if is_self else "bubble"
    st.markdown(f"<div class='{bubble_class}'>", unsafe_allow_html=True)
    st.markdown(
        f"<div><strong style='color: var(--text-strong)'>{html.escape(msg['user'])}</strong>"
        f" <span class='timestamp'>· {ts}</span></div>",
        unsafe_allow_html=True,
    )
    if msg.get("text"):
        st.markdown(f"<div style='margin-top:4px;color:var(--text)'>" + html.escape(msg["text"]) + "</div>", unsafe_allow_html=True)
    if msg.get("image_path"):
        try:
            Image.open(msg["image_path"])  # verify
            st.image(msg["image_path"], use_column_width=True)
        except Exception:
            st.caption("(Image not available)")
    st.markdown("</div>", unsafe_allow_html=True)


# uploader con key dinámico
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0


def _handle_send(active_channel: str, username: Optional[str], upload_key: str):
    if not username:
        st.warning("You must be logged in to send messages.")
        return
    text_val = (st.session_state.get("msg_input") or "").strip()
    uploaded = st.session_state.get(upload_key)

    image_path = None
    if uploaded is not None:
        safe_name = f"{int(time.time())}_{uploaded.name.replace(' ', '_')}"
        out_path = UPLOAD_DIR / safe_name
        with open(out_path, "wb") as f:
            f.write(uploaded.getbuffer())
        image_path = str(out_path)

    if not text_val and not image_path:
        st.warning("Write a message or attach an image.")
        return

    add_message(active_channel, username or "anon", text_val, image_path)

    st.session_state["msg_input"] = ""
    st.session_state["uploader_key"] += 1
    st.rerun()


def render_chat(active_channel: str, username: Optional[str]):
    _ensure_defaults()
    placeholder = st.empty()

    with placeholder.container():
        msgs = list_messages(active_channel)
        for m in msgs:
            message_bubble(m, username)


def composer_ui(active_channel: str, username: Optional[str]):
    _ensure_defaults()
    st.divider()
    col1, col2 = st.columns([4,1])

    with col1:
        st.text_input(
            f"Message #{active_channel}",
            key="msg_input",
            placeholder="Type your message…",
            disabled=(username is None),
        )
        upload_key = f"msg_upload_{st.session_state['uploader_key']}"
        st.file_uploader(
            "Attach an image (optional)",
            type=["png","jpg","jpeg","gif"],
            accept_multiple_files=False,
            key=upload_key,
            disabled=(username is None),
        )
    with col2:
        st.write("")
        st.write("")
        st.button(
            "Send",
            use_container_width=True,
            on_click=_handle_send,
            args=(active_channel, username, upload_key),
            disabled=(username is None),
        )

