import streamlit as st
import folium
from streamlit_folium import st_folium
import re
from datetime import date

# ─── PAGE CONFIG ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FieldSync — KML Automation",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ─── CUSTOM CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=Space+Mono:wght@400;700&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.main { background: #f8fffe; }

.header-block {
    background: #1b4332;
    padding: 18px 28px;
    border-radius: 10px;
    margin-bottom: 24px;
    border-bottom: 3px solid #40916c;
    display: flex;
    align-items: center;
    gap: 12px;
}
.logo-text {
    font-family: 'Space Mono', monospace;
    font-size: 22px;
    font-weight: 700;
    color: white;
    margin: 0;
}
.logo-sub {
    font-size: 12px;
    color: #74c69d;
    background: rgba(116,198,157,0.15);
    border: 1px solid rgba(116,198,157,0.3);
    padding: 2px 10px;
    border-radius: 20px;
    margin-left: 8px;
}
.section-label {
    font-family: 'Space Mono', monospace;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: #1b4332;
    margin-bottom: 8px;
}
.stat-row {
    display: flex;
    gap: 12px;
    margin: 12px 0;
}
.stat-card {
    flex: 1;
    background: #f0faf3;
    border: 1px solid #d1fae5;
    border-radius: 8px;
    padding: 10px;
    text-align: center;
}
.stat-val {
    font-family: 'Space Mono', monospace;
    font-size: 20px;
    font-weight: 700;
    color: #1b4332;
}
.stat-key {
    font-size: 10px;
    color: #9ca3af;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.correction-row {
    background: #fffbeb;
    border: 1px solid #fcd34d;
    border-left: 4px solid #f59e0b;
    border-radius: 6px;
    padding: 8px 12px;
    margin: 4px 0;
    font-size: 13px;
    font-family: 'Space Mono', monospace;
}
.upload-note {
    background: #f0faf3;
    border: 1px dashed #a7f3d0;
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 12px;
    color: #6b7280;
    margin-top: 12px;
}
.stTextArea textarea {
    font-family: 'Space Mono', monospace !important;
    font-size: 11px !important;
    background: #f0faf3 !important;
}
div[data-testid="stButton"] > button[kind="primary"] {
    background-color: #1b4332 !important;
    border-color: #1b4332 !important;
    color: white !important;
    font-weight: 600 !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
    background-color: #2d6a4f !important;
}
div[data-testid="stButton"] > button[kind="secondary"] {
    background-color: white !important;
    border: 1.5px dashed #fca5a5 !important;
    color: #dc2626 !important;
    font-weight: 600 !important;
}
div[data-testid="stButton"] > button[kind="secondary"]:hover {
    background-color: #fef2f2 !important;
    border-style: solid !important;
}
div[data-testid="stDownloadButton"] > button {
    background-color: #2d6a4f !important;
    border-color: #2d6a4f !important;
    color: white !important;
    font-weight: 600 !important;
    width: 100%;
}
</style>
""", unsafe_allow_html=True)

# ─── SESSION STATE INIT ───────────────────────────────────────────────────────
for key, default in {
    "kml_data": None,
    "outer_coords": None,
    "inner_coords": None,
    "corrections": [],
    "stats": {},
    "filename": "field.kml",
    "field_name": "Farm"
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ─── PARSER ───────────────────────────────────────────────────────────────────
def parse_coordinates(raw: str):
    corrections = []
    if not raw or not raw.strip():
        return [], corrections

    lines = raw.strip().split('\n')
    numbers = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.match(r'^[a-zA-Z\s]+$', line):
            continue

        def fix_comma(m):
            original = m.group(0)
            fixed = original.replace(',', '.')
            corrections.append({'original': original, 'corrected': fixed, 'error_type': 'comma as decimal'})
            return fixed
        line = re.sub(r'\b(\d+),(\d+)\b', fix_comma, line)

        tokens = line.split()
        merged = []
        i = 0
        while i < len(tokens):
            cur = tokens[i]
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None

            if re.match(r'^\d+\.$', cur) and nxt and re.match(r'^\d+$', nxt):
                fixed = f"{cur}{nxt}"
                corrections.append({'original': f"{cur} {nxt}", 'corrected': fixed, 'error_type': 'space in number'})
                merged.append(fixed)
                i += 2
            elif re.match(r'^\d+\.\d+$', cur) and nxt and re.match(r'^\d{4,}$', nxt):
                fixed = f"{cur}{nxt}"
                corrections.append({'original': f"{cur} {nxt}", 'corrected': fixed, 'error_type': 'space in number'})
                merged.append(fixed)
                i += 2
            else:
                merged.append(cur)
                i += 1

        for token in merged:
            try:
                numbers.append(float(token))
            except ValueError:
                pass

    pairs = []
    for i in range(0, len(numbers) - 1, 2):
        pairs.append((numbers[i], numbers[i + 1]))

    return pairs, corrections

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def validate_pairs(pairs, label):
    errors = []
    if len(pairs) < 3:
        errors.append(f"{label} needs at least 3 points (got {len(pairs)}).")
    for i, (lat, lon) in enumerate(pairs):
        if lat < -90 or lat > 90:
            errors.append(f"{label} row {i+1}: latitude {lat} out of range.")
        if lon < -180 or lon > 180:
            errors.append(f"{label} row {i+1}: longitude {lon} out of range.")
    return errors

def close_ring(pairs):
    if not pairs:
        return pairs
    if pairs[0] != pairs[-1]:
        return pairs + [pairs[0]]
    return pairs

def pairs_to_kml_coords(pairs):
    return '\n'.join(f'              {lon},{lat},0' for lat, lon in pairs)

def generate_kml(field_name, outer_pairs, inner_pairs):
    outer_closed = close_ring(outer_pairs)
    inner_block = ''
    if inner_pairs:
        inner_closed = close_ring(inner_pairs)
        inner_block = f"""
        <innerBoundaryIs>
          <LinearRing>
            <coordinates>
{pairs_to_kml_coords(inner_closed)}
            </coordinates>
          </LinearRing>
        </innerBoundaryIs>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <n>{field_name}</n>
    <Style id="fieldStyle">
      <LineStyle><color>ff2d7d32</color><width>2</width></LineStyle>
      <PolyStyle><color>402d7d32</color></PolyStyle>
    </Style>
    <Placemark>
      <n>{field_name}</n>
      <styleUrl>#fieldStyle</styleUrl>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
{pairs_to_kml_coords(outer_closed)}
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>{inner_block}
      </Polygon>
    </Placemark>
  </Document>
</kml>"""

def build_map(outer_pairs, inner_pairs):
    center_lat = sum(p[0] for p in outer_pairs) / len(outer_pairs)
    center_lon = sum(p[1] for p in outer_pairs) / len(outer_pairs)
    m = folium.Map(location=[center_lat, center_lon], zoom_start=14, tiles='OpenStreetMap')
    folium.Polygon(
        locations=[(lat, lon) for lat, lon in outer_pairs],
        color='#2d6a4f', weight=2, fill=True,
        fill_color='#40916c', fill_opacity=0.25, tooltip='Outer Boundary'
    ).add_to(m)
    if inner_pairs:
        folium.Polygon(
            locations=[(lat, lon) for lat, lon in inner_pairs],
            color='#f59e0b', weight=2, fill=True,
            fill_color='#fcd34d', fill_opacity=0.35, tooltip='Inner Boundary (Hole)'
        ).add_to(m)
    m.fit_bounds([(lat, lon) for lat, lon in outer_pairs])
    return m

def read_uploaded_file(uploaded_file):
    if uploaded_file is not None:
        return uploaded_file.read().decode("utf-8")
    return None

# ─── HEADER ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="header-block">
    <span style="font-size:28px">⬡</span>
    <span class="logo-text">FieldSync</span>
    <span class="logo-sub">KML Automation</span>
</div>
""", unsafe_allow_html=True)

# ─── LAYOUT ───────────────────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

# ─── LEFT: INPUT ──────────────────────────────────────────────────────────────
with left:
    st.markdown('<div class="section-label">Input</div>', unsafe_allow_html=True)

    field_name = st.text_input("Field Name", value=st.session_state.field_name, placeholder="e.g. Farm A")

    # ── OUTER BOUNDARY ────────────────────────────────────────────────────────
    st.markdown("**🟢 Outer Boundary** — field perimeter")

    outer_file = st.file_uploader(
        "Upload file (.txt or .csv)",
        type=["txt", "csv"],
        key="outer_file",
        help="Upload a text or CSV file with lat/lon pairs"
    )

    outer_file_content = read_uploaded_file(outer_file)

    if outer_file_content:
        st.caption(f"✅ File loaded: {outer_file.name} — you can also paste below to override")

    outer_raw = st.text_area(
        label="outer_coords",
        label_visibility="collapsed",
        height=180,
        placeholder="Or paste lat/lon pairs here...\n0.4087957  35.478962\n0.4084061  35.4782717\n...",
        key="outer"
    )

    # File takes priority; fall back to pasted text
    outer_input = outer_file_content if outer_file_content and not outer_raw.strip() else outer_raw

    # ── INNER BOUNDARY ────────────────────────────────────────────────────────
    st.markdown("**🟡 Inner Boundary** — hole / excluded area *(optional)*")

    inner_file = st.file_uploader(
        "Upload file (.txt or .csv)",
        type=["txt", "csv"],
        key="inner_file",
        help="Upload a text or CSV file with lat/lon pairs"
    )

    inner_file_content = read_uploaded_file(inner_file)

    if inner_file_content:
        st.caption(f"✅ File loaded: {inner_file.name} — you can also paste below to override")

    inner_raw = st.text_area(
        label="inner_coords",
        label_visibility="collapsed",
        height=140,
        placeholder="Or paste lat/lon pairs here (optional)...\n0.4061545  35.4725321\n...",
        key="inner"
    )

    # File takes priority; fall back to pasted text
    inner_input = inner_file_content if inner_file_content and not inner_raw.strip() else inner_raw

    generate = st.button("⚡ Generate KML", type="primary", use_container_width=True)

    # ── GENERATE LOGIC ────────────────────────────────────────────────────────
    if generate:
        if not outer_input or not outer_input.strip():
            st.error("⚠ Outer boundary coordinates are required — paste or upload a file.")
        else:
            outer_pairs, outer_corrections = parse_coordinates(outer_input)
            inner_pairs, inner_corrections = (
                parse_coordinates(inner_input) if inner_input and inner_input.strip() else ([], [])
            )
            all_corrections = outer_corrections + inner_corrections
            validation_errors = validate_pairs(outer_pairs, "Outer boundary")
            if inner_pairs:
                validation_errors += validate_pairs(inner_pairs, "Inner boundary")

            if validation_errors:
                for e in validation_errors:
                    st.error(f"⚠ {e}")
            else:
                kml_content = generate_kml(field_name or "Field", outer_pairs, inner_pairs)
                today = date.today().isoformat()
                filename = f"{(field_name or 'Field').replace(' ', '_')}_{today}.kml"

                st.session_state.kml_data = kml_content
                st.session_state.outer_coords = outer_pairs
                st.session_state.inner_coords = inner_pairs
                st.session_state.corrections = all_corrections
                st.session_state.filename = filename
                st.session_state.field_name = field_name
                st.session_state.stats = {
                    'outer_points': len(outer_pairs),
                    'inner_points': len(inner_pairs) if inner_pairs else 0,
                    'errors_fixed': len(all_corrections)
                }

# ─── RIGHT: OUTPUT ────────────────────────────────────────────────────────────
with right:
    st.markdown('<div class="section-label">Output</div>', unsafe_allow_html=True)

    if not st.session_state.kml_data:
        st.markdown("""
        <div style="text-align:center; padding:60px 20px; color:#9ca3af;">
            <div style="font-size:52px; margin-bottom:16px;">◈</div>
            <div style="font-size:16px; font-weight:600; color:#374151;">Your field will appear here</div>
            <div style="font-size:13px; margin-top:8px;">Paste or upload coordinates, then click ⚡ Generate KML</div>
        </div>
        """, unsafe_allow_html=True)

    else:
        stats = st.session_state.stats
        err_icon = "🟡" if stats['errors_fixed'] > 0 else "🟢"

        # Stats
        st.markdown(f"""
        <div class="stat-row">
            <div class="stat-card">
                <div class="stat-val">{stats['outer_points']}</div>
                <div class="stat-key">outer pts</div>
            </div>
            <div class="stat-card">
                <div class="stat-val">{stats['inner_points'] if stats['inner_points'] else '—'}</div>
                <div class="stat-key">inner pts</div>
            </div>
            <div class="stat-card">
                <div class="stat-val">{err_icon} {stats['errors_fixed']}</div>
                <div class="stat-key">errors fixed</div>
            </div>
            <div class="stat-card">
                <div class="stat-val">✓</div>
                <div class="stat-key">valid KML</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Corrections
        if st.session_state.corrections:
            st.warning(f"⚠ {len(st.session_state.corrections)} error(s) detected and auto-corrected:")
            for c in st.session_state.corrections:
                st.markdown(f"""
                <div class="correction-row">
                    <span style="color:#92400e;font-size:10px;text-transform:uppercase;font-weight:700">{c['error_type']}</span>
                    &nbsp;&nbsp;
                    <span style="color:#dc2626">"{c['original']}"</span>
                    &nbsp;→&nbsp;
                    <span style="color:#2d7d32">"{c['corrected']}"</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("✅ No formatting errors — data was clean.")

        # Map
        st.markdown("**Map Preview**")
        field_map = build_map(st.session_state.outer_coords, st.session_state.inner_coords)
        st_folium(field_map, height=300, use_container_width=True)

        # Download
        st.download_button(
            label=f"⬇ Download {st.session_state.filename}",
            data=st.session_state.kml_data,
            file_name=st.session_state.filename,
            mime="application/vnd.google-earth.kml+xml",
            use_container_width=True
        )

        # Reset
        if st.button("↺ Start Over", type="secondary", use_container_width=True):
            st.session_state.kml_data = None
            st.session_state.outer_coords = None
            st.session_state.inner_coords = None
            st.session_state.corrections = []
            st.session_state.stats = {}
            st.session_state.filename = "field.kml"
            st.session_state.field_name = "Farm"
            st.rerun()

        # KML source
        with st.expander("View KML Source"):
            st.code(st.session_state.kml_data, language="xml")

        st.markdown("""
        <div class="upload-note">
            ☁ Ready to upload &nbsp;·&nbsp; xFarm → Map → New field → Import from file
        </div>
        """, unsafe_allow_html=True)
