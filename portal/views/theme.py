"""SeestarScope cosmic theme - starfield background, glowing accents, astronomy icons."""

import streamlit as st

# Navigation items with icons - use actual emoji characters
NAV_ITEMS = {
    "Dashboard": "Dashboard",
    "Live Status": "Live Status",
    "Sky Map": "Sky Map",
    "GoTo": "GoTo / Slew",
    "Imaging": "Imaging",
    "Focus": "Focus",
    "Autofocus": "Autofocus",
    "Plate Solve": "Plate Solve",
    "Sequence": "Sequence",
    "Gallery": "Gallery",
    "Settings": "Settings",
}

NAV_ICONS = {
    "Dashboard": "\u2604\ufe0f",  # comet
    "Live Status": "\U0001f4e1",  # satellite antenna
    "Sky Map": "\U0001f30c",  # milky way
    "GoTo": "\u2b50",  # star
    "Imaging": "\U0001f4f7",  # camera
    "Focus": "\U0001f52d",  # telescope
    "Autofocus": "\U0001f3af",  # bullseye
    "Plate Solve": "\U0001f5fa\ufe0f",  # world map
    "Sequence": "\U0001f3ac",  # clapper
    "Gallery": "\U0001f5bc\ufe0f",  # framed picture
    "Settings": "\u2699\ufe0f",  # gear
}

DEVICE_ICONS = {
    "telescope": "\U0001f52d",
    "camera": "\U0001f4f7",
    "focuser": "\U0001f3af",
    "filterwheel": "\U0001f308",
    "switch": "\u26a1",
}


def inject_cosmic_css():
    """Inject the full cosmic theme CSS."""
    st.markdown(
        """
    <style>
    /* ===== STARFIELD BACKGROUND ===== */
    @keyframes twinkle {
        0%, 100% { opacity: 0.3; }
        50% { opacity: 1.0; }
    }
    @keyframes drift {
        0% { transform: translateY(0px); }
        100% { transform: translateY(-2000px); }
    }
    @keyframes pulse-glow {
        0%, 100% { box-shadow: 0 0 5px rgba(0, 200, 255, 0.3); }
        50% { box-shadow: 0 0 20px rgba(0, 200, 255, 0.6); }
    }
    @keyframes nebula-shift {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    /* Main app background - deep space gradient */
    .stApp {
        background: linear-gradient(160deg, #0a0a1a 0%, #0d1117 30%, #0a0e1a 60%, #111128 100%);
    }

    /* Starfield overlay via pseudo-element on main area */
    .stApp::before {
        content: '';
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        pointer-events: none;
        z-index: 0;
        background-image:
            radial-gradient(1px 1px at 10% 20%, rgba(255,255,255,0.8) 0%, transparent 100%),
            radial-gradient(1px 1px at 25% 45%, rgba(200,220,255,0.6) 0%, transparent 100%),
            radial-gradient(1.5px 1.5px at 40% 15%, rgba(255,200,100,0.7) 0%, transparent 100%),
            radial-gradient(1px 1px at 55% 70%, rgba(255,255,255,0.5) 0%, transparent 100%),
            radial-gradient(1px 1px at 70% 30%, rgba(180,200,255,0.6) 0%, transparent 100%),
            radial-gradient(1.5px 1.5px at 85% 55%, rgba(255,180,100,0.5) 0%, transparent 100%),
            radial-gradient(1px 1px at 15% 80%, rgba(255,255,255,0.4) 0%, transparent 100%),
            radial-gradient(1px 1px at 90% 85%, rgba(200,200,255,0.6) 0%, transparent 100%),
            radial-gradient(1px 1px at 35% 90%, rgba(255,255,255,0.5) 0%, transparent 100%),
            radial-gradient(1.5px 1.5px at 60% 10%, rgba(100,180,255,0.7) 0%, transparent 100%),
            radial-gradient(1px 1px at 5% 50%, rgba(255,220,150,0.5) 0%, transparent 100%),
            radial-gradient(1px 1px at 45% 40%, rgba(255,255,255,0.3) 0%, transparent 100%),
            radial-gradient(1px 1px at 75% 65%, rgba(180,180,255,0.5) 0%, transparent 100%),
            radial-gradient(2px 2px at 20% 5%, rgba(100,200,255,0.9) 0%, transparent 100%),
            radial-gradient(1px 1px at 65% 95%, rgba(255,255,255,0.4) 0%, transparent 100%),
            radial-gradient(1px 1px at 50% 50%, rgba(200,150,255,0.3) 0%, transparent 100%),
            radial-gradient(1.5px 1.5px at 80% 10%, rgba(255,255,200,0.6) 0%, transparent 100%),
            radial-gradient(1px 1px at 30% 60%, rgba(255,255,255,0.5) 0%, transparent 100%);
        animation: twinkle 4s ease-in-out infinite;
    }

    /* Ensure main content is above starfield — exclude sidebar to preserve its scroll */
    .stApp > *:not(section[data-testid="stSidebar"]) {
        position: relative;
        z-index: 1;
    }

    /* ===== SIDEBAR - NEBULA GRADIENT + STARFIELD ===== */
    /* Streamlit's resize handle sets inline height:auto — override with !important */
    section[data-testid="stSidebar"] {
        background:
            radial-gradient(1px 1px at 20% 10%, rgba(255,255,255,0.6) 0%, transparent 100%),
            radial-gradient(1px 1px at 80% 30%, rgba(200,200,255,0.4) 0%, transparent 100%),
            radial-gradient(1px 1px at 50% 60%, rgba(255,200,150,0.3) 0%, transparent 100%),
            radial-gradient(1px 1px at 30% 80%, rgba(180,200,255,0.5) 0%, transparent 100%),
            radial-gradient(1px 1px at 70% 90%, rgba(255,255,255,0.3) 0%, transparent 100%),
            linear-gradient(180deg,
                #0a0a2e 0%,
                #0d1230 20%,
                #1a0a2e 50%,
                #0d1a30 80%,
                #0a0a20 100%) !important;
        border-right: 1px solid rgba(100, 150, 255, 0.15);
        height: 100vh !important;
        overflow: hidden !important;
    }

    /* Inner container scrolls the actual content */
    [data-testid="stSidebarContent"] {
        height: 100% !important;
        overflow-y: auto !important;
    }

    /* ===== TYPOGRAPHY ===== */
    h1, h2, h3, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
        background: linear-gradient(135deg, #00c8ff 0%, #a78bfa 50%, #00c8ff 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-weight: 700;
        letter-spacing: 0.5px;
    }

    /* Sidebar title special treatment */
    section[data-testid="stSidebar"] h1 {
        background: linear-gradient(135deg, #00e5ff 0%, #7c4dff 50%, #00e5ff 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 1.8rem !important;
        text-align: center;
        letter-spacing: 2px;
    }

    /* ===== METRIC CARDS - GLASSMORPHISM ===== */
    [data-testid="stMetric"] {
        background: linear-gradient(135deg,
            rgba(10, 20, 40, 0.8) 0%,
            rgba(20, 30, 60, 0.6) 100%);
        border: 1px solid rgba(0, 200, 255, 0.2);
        border-radius: 12px;
        padding: 12px 16px;
        backdrop-filter: blur(10px);
        transition: all 0.3s ease;
    }

    [data-testid="stMetric"]:hover {
        border-color: rgba(0, 200, 255, 0.5);
        box-shadow: 0 0 15px rgba(0, 200, 255, 0.15);
        transform: translateY(-1px);
    }

    /* Metric values - bright cyan */
    [data-testid="stMetricValue"] {
        color: #00e5ff !important;
        font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
        font-weight: 600 !important;
    }

    /* Metric labels */
    [data-testid="stMetricLabel"] {
        color: rgba(160, 180, 220, 0.9) !important;
        text-transform: uppercase;
        font-size: 0.7rem !important;
        letter-spacing: 1.5px;
    }

    /* ===== BUTTONS ===== */
    .stButton > button {
        border: 1px solid rgba(0, 200, 255, 0.3);
        border-radius: 8px;
        background: linear-gradient(135deg,
            rgba(0, 40, 80, 0.6) 0%,
            rgba(0, 60, 120, 0.4) 100%);
        color: #b0d4ff;
        font-weight: 500;
        letter-spacing: 0.5px;
        transition: all 0.3s ease;
        backdrop-filter: blur(5px);
    }

    .stButton > button:hover {
        border-color: rgba(0, 200, 255, 0.7);
        box-shadow: 0 0 20px rgba(0, 200, 255, 0.25);
        color: #ffffff;
        transform: translateY(-1px);
    }

    /* Primary buttons - bright cyan glow */
    .stButton > button[kind="primary"],
    .stButton > button[data-testid*="primary"] {
        background: linear-gradient(135deg, #0066cc 0%, #00aaff 50%, #0077dd 100%) !important;
        border: 1px solid rgba(0, 220, 255, 0.5) !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        animation: pulse-glow 3s ease-in-out infinite;
    }

    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #0077dd 0%, #00ccff 50%, #0088ee 100%) !important;
        box-shadow: 0 0 30px rgba(0, 200, 255, 0.4) !important;
    }

    /* ===== INPUTS ===== */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stSelectbox > div > div {
        background: rgba(10, 20, 40, 0.7) !important;
        border: 1px solid rgba(0, 150, 255, 0.2) !important;
        border-radius: 8px !important;
        color: #c0d8ff !important;
        backdrop-filter: blur(5px);
    }

    .stTextInput > div > div > input:focus,
    .stNumberInput > div > div > input:focus {
        border-color: rgba(0, 200, 255, 0.6) !important;
        box-shadow: 0 0 10px rgba(0, 200, 255, 0.2) !important;
    }

    /* ===== RADIO BUTTONS (NAV) ===== */
    .stRadio > div {
        gap: 2px;
    }

    .stRadio > div > label {
        padding: 8px 12px !important;
        border-radius: 8px;
        transition: all 0.2s ease;
        border: 1px solid transparent;
    }

    .stRadio > div > label:hover {
        background: rgba(0, 100, 200, 0.15);
        border-color: rgba(0, 200, 255, 0.2);
    }

    .stRadio > div > label[data-checked="true"],
    .stRadio > div > label:has(input:checked) {
        background: linear-gradient(135deg, rgba(0, 60, 150, 0.3), rgba(0, 100, 200, 0.2));
        border-color: rgba(0, 200, 255, 0.4);
        box-shadow: 0 0 10px rgba(0, 200, 255, 0.1);
    }

    /* ===== DIVIDERS ===== */
    hr {
        border-color: rgba(0, 150, 255, 0.15) !important;
        background: linear-gradient(90deg,
            transparent 0%,
            rgba(0, 200, 255, 0.3) 50%,
            transparent 100%) !important;
        height: 1px !important;
    }

    /* ===== ALERTS ===== */
    .stAlert {
        border-radius: 10px;
        backdrop-filter: blur(5px);
    }

    /* ===== EXPANDER ===== */
    .streamlit-expanderHeader {
        background: rgba(10, 20, 40, 0.5);
        border: 1px solid rgba(0, 150, 255, 0.15);
        border-radius: 8px;
    }

    /* ===== TABS ===== */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background: rgba(10, 15, 30, 0.5);
        border-radius: 10px;
        padding: 4px;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        color: #8090b0;
        padding: 8px 16px;
    }

    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background: linear-gradient(135deg, rgba(0, 60, 150, 0.4), rgba(0, 100, 200, 0.2));
        color: #00e5ff;
    }

    .stTabs [data-baseweb="tab-highlight"] {
        background-color: #00aaff !important;
    }

    /* ===== SLIDER ===== */
    .stSlider > div > div > div[role="slider"] {
        background: #00ccff !important;
        box-shadow: 0 0 8px rgba(0, 200, 255, 0.5);
    }

    .stSlider > div > div > div > div {
        background: linear-gradient(90deg, #003366, #0088cc) !important;
    }

    /* ===== PROGRESS BAR ===== */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #0066cc, #00ccff, #00ffcc) !important;
        box-shadow: 0 0 10px rgba(0, 200, 255, 0.3);
    }

    /* ===== SCROLLBAR ===== */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    ::-webkit-scrollbar-track {
        background: #0a0a1a;
    }
    ::-webkit-scrollbar-thumb {
        background: linear-gradient(180deg, #1a3050, #0066aa);
        border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(180deg, #2a4060, #0088cc);
    }

    /* ===== CONTAINERS ===== */
    [data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"] {
        gap: 12px;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )


def render_sidebar_brand():
    """Render the branded sidebar header with logo effect."""
    st.markdown(
        """
    <div style="text-align: center; padding: 10px 0 5px 0;">
        <div style="font-size: 3rem; line-height: 1; margin-bottom: 4px;">
            &#x1F52D;
        </div>
        <div style="
            font-size: 1.5rem;
            font-weight: 800;
            letter-spacing: 3px;
            background: linear-gradient(135deg, #00e5ff 0%, #a78bfa 40%, #ff6bff 70%, #00e5ff 100%);
            background-size: 200% auto;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            animation: nebula-shift 6s ease infinite;
        ">SEESTARSCOPE</div>
        <div style="
            font-size: 0.7rem;
            color: rgba(160, 180, 220, 0.7);
            letter-spacing: 4px;
            margin-top: 2px;
        ">SEESTAR S50 CONTROL</div>
    </div>
    """,
        unsafe_allow_html=True,
    )


def render_connection_status(alpaca, stellarium):
    """Render device connection indicators with icons."""
    st.markdown(
        """
    <div style="
        font-size: 0.7rem;
        color: rgba(160, 180, 220, 0.6);
        letter-spacing: 2px;
        text-transform: uppercase;
        margin-bottom: 8px;
        margin-top: 4px;
    ">DEVICES</div>
    """,
        unsafe_allow_html=True,
    )

    device_labels = {
        "telescope": "&#x1F52D; Telescope",
        "camera": "&#x1F4F7; Camera",
        "focuser": "&#x1F3AF; Focuser",
        "filterwheel": "&#x1F308; Filterwheel",
        "switch": "&#x26A1; Switch",
    }

    for device in alpaca.DEVICES:
        connected = alpaca.connected_devices.get(device, False)
        dot = "&#x1F7E2;" if connected else "&#x1F534;"
        label = device_labels.get(device, device.title())
        color = "#00e5ff" if connected else "#ff4466"
        st.markdown(
            f"""
        <div style="
            padding: 3px 8px;
            font-size: 0.85rem;
            font-family: monospace;
            color: {color};
        ">{dot} {label}</div>
        """,
            unsafe_allow_html=True,
        )

    # Stellarium
    stell_ok = stellarium.is_available()
    dot = "&#x1F7E2;" if stell_ok else "&#x1F534;"
    color = "#aa88ff" if stell_ok else "#ff4466"
    st.markdown(
        f"""
    <div style="
        padding: 3px 8px;
        font-size: 0.85rem;
        font-family: monospace;
        color: {color};
        margin-top: 4px;
    ">{dot} &#x2B50; Stellarium</div>
    """,
        unsafe_allow_html=True,
    )


def render_nav_radio():
    """Render navigation with icons."""
    options = list(NAV_ITEMS.keys())

    page = st.radio(
        "Navigation",
        options,
        format_func=lambda x: f"{NAV_ICONS[x]}  {x}",
        label_visibility="collapsed",
    )
    return page
