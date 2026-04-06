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

div[data-testid="stButton"] > button {
    font-family: 'DM Sans', sans-serif;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)

# ─── COORDINATE PARSER ────────────────────────────────────────────────────────
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
        # Skip header rows
        if re.match(r'^[a-zA-Z\s]+$', line):
            continue

        # Fix comma as decimal: "35,4788058" → "35.4788058"
        def fix_comma(m):
            original = m.group(0)
            fixed = original.replace(',', '.')
            corrections.append({
                'original': original,
                'corrected': fixed,
                'error_type': 'comma_as_decimal'
            })
            return fixed

        line = re.sub(r'\d+,\d+', fix_comma, line)

        # Split into tokens
        tokens = line.split()
        merged = []
        i = 0
        while i < len(tokens):
            cur = tokens[i]
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None

            # Case 1: "35." + "478103" → "35.478103"
            if re.match(r'^\d+\.$', cur) and nxt and re.match(r'^\d+$', nxt):
                original = f"{cur} {nxt}"
                fixed = f"{cur}{nxt}"
                corrections.append({'original': original, 'corrected': fixed, 'error_type': 'space_in_number'})
                merged.append(fixed)
                i += 2

            # Case 2: "35.47" + "47687" → "35.4747687" (next has 4+ digits, can't be standalone coord)
            elif re.match(r'^\d+\.\d+$', cur) and nxt and re.match(r'^\d{4,}$', nxt):
                original = f"{cur} {nxt}"
                fixed = f"{cur}{nxt}"
                corrections.append({'original': original, 'corrected': fixed, 'error_type': 'space_in_number'})
                merged.append(fixed)
                i += 2

            else:
                merged.append(cur)
                i += 1

        for token in merged:
            try:
                val = float(token)
                numbers.append(val)
            except ValueError:
                pass

    # Pair into (lat, lon)
    pairs = []
    for i in range(0, len(numbers) - 1, 2):
        pairs.append((numbers[i], numbers[i + 1]))

    return pairs, corrections


# ─── VALIDATION ───────────────────────────────────────────────────────────────
def validate_pairs(pairs, label):
    errors = []
    if len(pairs) < 3:
        errors.append(f"{label} needs at least 3 coordinate points (got {len(pairs)}).")
    for i, (lat, lon) in enumerate(pairs):
        if lat < -90 or lat > 90:
            errors.append(f"{label} row {i+1}: latitude {lat} out of range.")
        if lon < -180 or lon > 180:
            errors.append(f"{label} row {i+1}: longitude {lon} out of range.")
    return errors


# ─── KML GENERATOR ────────────────────────────────────────────────────────────
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
    <name>{field_name}</name>
    <Style id="fieldStyle">
      <LineStyle><color>ff2d7d32</color><width>2</width></LineStyle>
      <PolyStyle><color>402d7d32</color></PolyStyle>
    </Style>
    <Placemark>
      <name>{field_name}</name>
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


# ─── MAP BUILDER ──────────────────────────────────────────────────────────────
def build_map(outer_pairs, inner_pairs):
    center_lat = sum(p[0] for p in outer_pairs) / len(outer_pairs)
    center_lon = sum(p[1] for p in outer_pairs) / len(outer_pairs)

    m = folium.Map(location=[center_lat, center_lon], zoom_start=14,
                   tiles='OpenStreetMap')

    outer_latlon = [(lat, lon) for lat, lon in outer_pairs]
    folium.Polygon(
        locations=outer_latlon,
        color='#2d6a4f',
        weight=2,
        fill=True,
        fill_color='#40916c',
        fill_opacity=0.25,
        tooltip='Outer Boundary'
    ).add_to(m)

    if inner_pairs:
        inner_latlon = [(lat, lon) for lat, lon in inner_pairs]
        folium.Polygon(
            locations=inner_latlon,
            color='#f59e0b',
            weight=2,
            fill=True,
            fill_color='#fcd34d',
            fill_opacity=0.35,
            tooltip='Inner Boundary (Hole)'
        ).add_to(m)

    m.fit_bounds(outer_latlon)
    return m


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

    field_name = st.text_input("Field Name", value="Farm", placeholder="e.g. Farm A")

    st.markdown("**🟢 Outer Boundary** — field perimeter")
    outer_raw = st.text_area(
        label="outer_coords",
        label_visibility="collapsed",
        height=220,
        placeholder="Paste lat/lon pairs here...\n0.4087957  35.478962\n0.4084061  35.4782717\n...",
        key="outer"
    )

    st.markdown("**🟡 Inner Boundary** — hole / excluded area *(optional)*")
    inner_raw = st.text_area(
        label="inner_coords",
        label_visibility="collapsed",
        height=160,
        placeholder="Paste lat/lon pairs here (optional)...\n0.4061545  35.4725321\n...",
        key="inner"
    )

    generate = st.button("⚡ Generate KML", type="primary", use_container_width=True)

# ─── RIGHT: OUTPUT ────────────────────────────────────────────────────────────
with right:
    st.markdown('<div class="section-label">Output</div>', unsafe_allow_html=True)

    if not generate:
        st.info("Paste coordinates on the left and click **⚡ Generate KML** to see your field here.")

    if generate:
        if not outer_raw.strip():
            st.error("⚠ Outer boundary coordinates are required.")
        else:
            outer_pairs, outer_corrections = parse_coordinates(outer_raw)
            inner_pairs, inner_corrections = parse_coordinates(inner_raw) if inner_raw.strip() else ([], [])
            all_corrections = outer_corrections + inner_corrections

            validation_errors = validate_pairs(outer_pairs, "Outer boundary")
            if inner_pairs:
                validation_errors += validate_pairs(inner_pairs, "Inner boundary")

            if validation_errors:
                for e in validation_errors:
                    st.error(f"⚠ {e}")
            else:
                # Stats
                err_color = "🟡" if all_corrections else "🟢"
                st.markdown(f"""
                <div class="stat-row">
                    <div class="stat-card">
                        <div class="stat-val">{len(outer_pairs)}</div>
                        <div class="stat-key">outer pts</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-val">{len(inner_pairs) if inner_pairs else '—'}</div>
                        <div class="stat-key">inner pts</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-val">{err_color} {len(all_corrections)}</div>
                        <div class="stat-key">errors fixed</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-val">✓</div>
                        <div class="stat-key">valid KML</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Corrections report
                if all_corrections:
                    st.warning(f"⚠ {len(all_corrections)} error(s) detected and auto-corrected:")
                    for c in all_corrections:
                        st.markdown(f"""
                        <div class="correction-row">
                            <span style="color:#92400e;font-size:10px;text-transform:uppercase">{c['error_type'].replace('_',' ')}</span>
                            &nbsp;&nbsp;
                            <span style="color:#dc2626">"{c['original']}"</span>
                            &nbsp;→&nbsp;
                            <span style="color:#2d7d32">"{c['corrected']}"</span>
                        </div>
                        """, unsafe_allow_html=True)

                # Map preview
                st.markdown("**Map Preview**")
                field_map = build_map(outer_pairs, inner_pairs)
                st_folium(field_map, height=300, use_container_width=True)

                # Generate KML
                kml_content = generate_kml(field_name or "Field", outer_pairs, inner_pairs)
                today = date.today().isoformat()
                filename = f"{(field_name or 'Field').replace(' ', '_')}_{today}.kml"

                # Download button
                st.download_button(
                    label=f"⬇ Download {filename}",
                    data=kml_content,
                    file_name=filename,
                    mime="application/vnd.google-earth.kml+xml",
                    use_container_width=True,
                    type="primary"
                )

                # KML preview expander
                with st.expander("View KML Source"):
                    st.code(kml_content, language="xml")

                st.markdown("""
                <div class="upload-note">
                    ☁ Ready to upload &nbsp;·&nbsp; xFarm → Map → New field → Import from file
                </div>
                """, unsafe_allow_html=True)
