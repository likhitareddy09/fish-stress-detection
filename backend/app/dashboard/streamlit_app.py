"""
Fish Stress Detection — Live Streamlit Dashboard
Connects to FastAPI backend at localhost:8000
Run from backend/ folder: streamlit run app/dashboard/streamlit_app.py
"""
import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import time

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Fish Stress Monitor",
    page_icon="🐟",
    layout="wide",
    initial_sidebar_state="expanded",
)

API = "http://localhost:8000/api/v1"

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 2rem; }
.stress-normal  { color: #1D9E75; font-size: 2.2rem; font-weight: 600; }
.stress-warning { color: #BA7517; font-size: 2.2rem; font-weight: 600; }
.stress-critical{ color: #E24B4A; font-size: 2.2rem; font-weight: 600; }
.alert-critical { background:#FCEBEB; border-left:4px solid #E24B4A;
                  padding:8px 12px; border-radius:4px; margin:4px 0; color:#3A1414; }
.alert-warning  { background:#FAEEDA; border-left:4px solid #BA7517;
                  padding:8px 12px; border-radius:4px; margin:4px 0; color:#3D2A05; }
.alert-normal   { background:#E1F5EE; border-left:4px solid #1D9E75;
                  padding:8px 12px; border-radius:4px; margin:4px 0; color:#0D3D2E; }
.alert-critical strong, .alert-warning strong, .alert-normal strong { color: inherit; }
.alert-critical small, .alert-warning small, .alert-normal small { opacity: 0.75; }
</style>
""", unsafe_allow_html=True)


# ── Helper functions ──────────────────────────────────────────────────────────

def api_get(path: str, params: dict = None):
    """Safe GET request — returns None on any error."""
    try:
        r = requests.get(f"{API}{path}", params=params, timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def fsi_gauge(fsi: float, level: str) -> go.Figure:
    """Plotly gauge chart showing FSI score 0.0 → 1.0."""
    color = {"normal": "#1D9E75", "warning": "#BA7517", "critical": "#E24B4A"}.get(level, "#888")
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=fsi,
        number={"font": {"size": 36, "color": color}, "suffix": ""},
        gauge={
            "axis": {"range": [0, 1], "tickwidth": 1, "tickcolor": "#888",
                     "tickvals": [0, 0.3, 0.6, 1.0],
                     "ticktext": ["0", "0.3", "0.6", "1.0"]},
            "bar": {"color": color, "thickness": 0.3},
            "steps": [
                {"range": [0,   0.3], "color": "#E1F5EE"},
                {"range": [0.3, 0.6], "color": "#FAEEDA"},
                {"range": [0.6, 1.0], "color": "#FCEBEB"},
            ],
            "threshold": {
                "line": {"color": color, "width": 3},
                "thickness": 0.75,
                "value": fsi,
            },
        },
    ))
    fig.update_layout(
        height=220,
        margin=dict(l=20, r=20, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": "#444"},
    )
    return fig


def sensor_chart(readings: list, field: str, label: str, color: str,
                 low: float = None, high: float = None) -> go.Figure:
    """Line chart for a single sensor parameter with threshold lines."""
    if not readings:
        return go.Figure()

    df = pd.DataFrame(readings)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.dropna(subset=[field])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df[field],
        mode="lines+markers",
        line={"color": color, "width": 2},
        marker={"size": 4},
        name=label,
    ))

    if high is not None:
        fig.add_hline(y=high, line_dash="dash", line_color="#E24B4A",
                      annotation_text=f"Max {high}", annotation_position="top right")
    if low is not None:
        fig.add_hline(y=low, line_dash="dash", line_color="#E24B4A",
                      annotation_text=f"Min {low}", annotation_position="bottom right")

    fig.update_layout(
        height=200,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis={"showgrid": False, "color": "#888"},
        yaxis={"gridcolor": "#eee", "color": "#888"},
        showlegend=False,
    )
    return fig


def fsi_trend_chart(scores: list) -> go.Figure:
    """FSI score trend over time with color zones."""
    if not scores:
        return go.Figure()

    df = pd.DataFrame(scores)
    df["computed_at"] = pd.to_datetime(df["computed_at"])

    colors = df["stress_level"].map(
        {"normal": "#1D9E75", "warning": "#BA7517", "critical": "#E24B4A"}
    ).fillna("#888")

    fig = go.Figure()
    fig.add_hrect(y0=0,   y1=0.3, fillcolor="#E1F5EE", opacity=0.4, line_width=0)
    fig.add_hrect(y0=0.3, y1=0.6, fillcolor="#FAEEDA", opacity=0.4, line_width=0)
    fig.add_hrect(y0=0.6, y1=1.0, fillcolor="#FCEBEB", opacity=0.4, line_width=0)

    fig.add_trace(go.Scatter(
        x=df["computed_at"], y=df["fsi_score"],
        mode="lines+markers",
        line={"color": "#378ADD", "width": 2},
        marker={"color": colors, "size": 6, "line": {"width": 1, "color": "#fff"}},
        name="FSI",
    ))

    fig.update_layout(
        height=200,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis={"range": [0, 1], "gridcolor": "#eee", "color": "#888"},
        xaxis={"showgrid": False, "color": "#888"},
        showlegend=False,
    )
    return fig


def get_recommendation(level, alert_list, fish_summary):
    """Build a recommendation message based on stress level and active alerts."""
    if level == "critical":
        lines = ["🚨 **Immediate intervention required.**"]
        if any("TEMP" in a for a in alert_list):
            lines.append("• Check water temperature — adjust heater/cooler")
        if any("PH" in a for a in alert_list):
            lines.append("• Test pH — add buffer solution, retest in 30 min")
        if any("DO" in a for a in alert_list):
            lines.append("• Check aerator — increase surface agitation immediately")
        if any("AMMONIA" in a for a in alert_list):
            lines.append("• Do 25% water change — ammonia spike detected")
        if fish_summary and fish_summary.get("critical_count", 0) > 0:
            lines.append(f"• {fish_summary['critical_count']} fish showing critical stress — inspect tank now")
        return "\n".join(lines)
    elif level == "warning":
        return "⚠️ **Monitor closely.** Check all equipment. Retest in 30 minutes."
    else:
        return "✅ **All good.** Fish are healthy. Continue regular monitoring schedule."


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🐟 Fish Stress Monitor")
    st.caption("Real-time aquaculture health system")
    st.divider()

    tanks_data = api_get("/tanks/")
    tank_options = ["tank_01"]
    if tanks_data:
        tank_options = [t["tank_id"] for t in tanks_data if t.get("is_active")]

    tank_id = st.selectbox("Select Tank", tank_options, index=0)
    hours   = st.selectbox("History window", [1, 6, 12, 24, 48], index=3, format_func=lambda h: f"Last {h}h")

    st.divider()
    auto_refresh = st.checkbox("Auto-refresh", value=True)
    refresh_sec  = st.slider("Refresh every (sec)", 5, 60, 10)

    st.divider()
    st.caption("Water quality thresholds")
    st.markdown("🌡 **Temp:** 22°C – 28°C")
    st.markdown("🧪 **pH:** 6.5 – 8.0")
    st.markdown("💧 **DO:** > 5.0 mg/L")
    st.markdown("☣ **Ammonia:** < 0.02 ppm")

    st.divider()
    st.caption("FSI zones")
    st.markdown("🟢 **Normal:** 0.00 – 0.29")
    st.markdown("🟡 **Warning:** 0.30 – 0.59")
    st.markdown("🔴 **Critical:** 0.60 – 1.00")

    st.divider()
    if st.button("🔄 Refresh now"):
        st.rerun()


# ── Load all data (must happen before anything uses it) ──────────────────────

st.title(f"Fish Stress Monitor — {tank_id.upper()}")
last_update = st.empty()

dashboard   = api_get(f"/tanks/{tank_id}/dashboard")
history     = api_get(f"/sensors/{tank_id}/history", {"hours": hours})
fsi_hist    = api_get(f"/sensors/{tank_id}/stress/history", {"hours": hours})
alert_stats = api_get("/alerts/stats/summary", {"hours": 24})
fish_data   = api_get(f"/sensors/{tank_id}/fish-stress/latest")

if not dashboard:
    st.error(f"Cannot reach backend API at {API}. Is the server running on port 8000?")
    st.stop()

tank_info      = dashboard.get("tank", {})
sensor         = dashboard.get("latest_sensor") or {}
stress         = dashboard.get("latest_stress") or {}
alerts         = dashboard.get("active_alerts", [])
fsi_score      = stress.get("fsi_score", 0.0) or 0.0
stress_level   = stress.get("stress_level", "normal") or "normal"
readings_today = dashboard.get("readings_today", 0)
alert_count    = dashboard.get("alert_count", 0)
readings       = history.get("readings", []) if history else []
alert_types    = [a.get("alert_type", "") for a in alerts]

last_update.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')} | "
                    f"Readings today: {readings_today} | "
                    f"Tank: {tank_info.get('name', tank_id)}")

st.divider()

# ── Row 0: Video panel + quick stats ─────────────────────────────────────────
col_video, col_info = st.columns([2, 1])

with col_video:
    st.subheader("🎥 Processed Video Feed")
    uploaded_video = st.file_uploader(
        "Upload processed video from CV module",
        type=["mp4", "avi", "mov"],
        help="Upload the output video from Likhita's CV pipeline"
    )
    if uploaded_video:
        st.video(uploaded_video)
    else:
        st.info("Upload a processed video from Likhita's CV module to display it here.")

with col_info:
    st.subheader("📊 Quick Stats")
    if fish_data:
        st.metric("🐟 Fish tracked", fish_data.get("fish_count", 0))
        st.metric("🚨 Critical",     fish_data.get("critical_count", 0))
        st.metric("📈 Avg stress",   f"{fish_data.get('avg_stress', 0):.3f}")
    else:
        st.metric("🐟 Fish tracked", "—")
        st.metric("🚨 Critical",     "—")
        st.metric("📈 Avg stress",   "—")

st.divider()

# ── Row 1: FSI gauge + key metrics ───────────────────────────────────────────
col_gauge, col_temp, col_ph, col_do, col_alerts = st.columns([2, 1, 1, 1, 1])

with col_gauge:
    st.subheader("Fish Stress Index")
    st.plotly_chart(fsi_gauge(fsi_score, stress_level), width="stretch", key="gauge")
    emoji = {"normal": "✅ NORMAL", "warning": "⚠️ WARNING", "critical": "🚨 CRITICAL"}.get(stress_level, "❓")
    css_class = f"stress-{stress_level}"
    st.markdown(f'<p class="{css_class}">{emoji}</p>', unsafe_allow_html=True)

with col_temp:
    temp = sensor.get("temperature")
    temp_ok = temp is not None and 22 <= temp <= 28
    st.metric(
        "🌡 Temperature",
        f"{temp:.1f} °C" if temp is not None else "—",
        delta="OK" if temp_ok else "OUT OF RANGE" if temp is not None else None,
        delta_color="normal" if temp_ok else "inverse",
    )

with col_ph:
    ph = sensor.get("ph")
    ph_ok = ph is not None and 6.5 <= ph <= 8.0
    st.metric(
        "🧪 pH Level",
        f"{ph:.2f}" if ph is not None else "—",
        delta="OK" if ph_ok else "OUT OF RANGE" if ph is not None else None,
        delta_color="normal" if ph_ok else "inverse",
    )

with col_do:
    do2 = sensor.get("dissolved_o2")
    do_ok = do2 is not None and do2 >= 5.0
    st.metric(
        "💧 Dissolved O₂",
        f"{do2:.1f} mg/L" if do2 is not None else "—",
        delta="OK" if do_ok else "LOW" if do2 is not None else None,
        delta_color="normal" if do_ok else "inverse",
    )

with col_alerts:
    sys_status = alert_stats.get("system_status", "normal") if alert_stats else "unknown"
    st.metric("🚨 Active Alerts", alert_count)
    st.metric("System Status", sys_status.upper())

st.divider()

# ── Row 2: Sensor charts ──────────────────────────────────────────────────────
st.subheader("📈 Sensor History")

tab_temp, tab_ph, tab_do, tab_fsi = st.tabs(["Temperature", "pH", "Dissolved O₂", "FSI Trend"])

with tab_temp:
    if readings:
        st.plotly_chart(
            sensor_chart(readings, "temperature", "Temperature (°C)", "#E24B4A", low=22, high=28),
            width="stretch", key="chart_temp"
        )
        temps = [r["temperature"] for r in readings if r.get("temperature") is not None]
        if temps:
            c1, c2, c3 = st.columns(3)
            c1.metric("Min", f"{min(temps):.1f}°C")
            c2.metric("Max", f"{max(temps):.1f}°C")
            c3.metric("Avg", f"{sum(temps)/len(temps):.1f}°C")
    else:
        st.info("No temperature data yet. Send sensor readings via MQTT or the API.")

with tab_ph:
    if readings:
        st.plotly_chart(
            sensor_chart(readings, "ph", "pH", "#378ADD", low=6.5, high=8.0),
            width="stretch", key="chart_ph"
        )
        phs = [r["ph"] for r in readings if r.get("ph") is not None]
        if phs:
            c1, c2, c3 = st.columns(3)
            c1.metric("Min", f"{min(phs):.2f}")
            c2.metric("Max", f"{max(phs):.2f}")
            c3.metric("Avg", f"{sum(phs)/len(phs):.2f}")
    else:
        st.info("No pH data yet.")

with tab_do:
    if readings:
        st.plotly_chart(
            sensor_chart(readings, "dissolved_o2", "Dissolved O₂ (mg/L)", "#1D9E75", low=5.0),
            width="stretch", key="chart_do"
        )
    else:
        st.info("No dissolved oxygen data yet.")

with tab_fsi:
    fsi_scores = fsi_hist if isinstance(fsi_hist, list) else []
    if fsi_scores:
        st.plotly_chart(fsi_trend_chart(fsi_scores), width="stretch", key="chart_fsi")
        fsi_vals = [s["fsi_score"] for s in fsi_scores if s.get("fsi_score") is not None]
        if fsi_vals:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Current", f"{fsi_vals[-1]:.3f}")
            c2.metric("Min", f"{min(fsi_vals):.3f}")
            c3.metric("Max", f"{max(fsi_vals):.3f}")
            c4.metric("Avg", f"{sum(fsi_vals)/len(fsi_vals):.3f}")
    else:
        st.info("No FSI history yet.")

st.divider()

# ── Row 3: Per-fish stress table ─────────────────────────────────────────────
st.subheader("🐟 Individual Fish Stress (Latest Window)")

if fish_data and fish_data.get("fish"):
    fish_df = pd.DataFrame(fish_data["fish"])

    def color_stress(val):
        colors = {"normal": "background-color: #E1F5EE",
                  "warning": "background-color: #FAEEDA",
                  "critical": "background-color: #FCEBEB"}
        return colors.get(val, "")

    display_cols = ["fish_id", "stress_score", "stress_level",
                    "avg_speed", "surface_visits", "inactivity_pct"]
    display_cols = [c for c in display_cols if c in fish_df.columns]

    styled = fish_df[display_cols].style.map(
        color_stress, subset=["stress_level"]
    )
    st.dataframe(styled, width="stretch", hide_index=True)

    col1, col2, col3 = st.columns(3)
    col1.metric("Fish analysed", fish_data.get("fish_count", 0))
    col2.metric("Critical fish",  fish_data.get("critical_count", 0))
    col3.metric("Avg stress",     f"{fish_data.get('avg_stress', 0):.3f}")
else:
    st.info("No per-fish data yet. Waiting for CV module output...")

st.divider()

# ── Row 4: Alerts panel ───────────────────────────────────────────────────────
col_active, col_stats = st.columns([2, 1])

with col_active:
    st.subheader("🚨 Active Alerts")
    if alerts:
        for alert in alerts:
            sev   = alert.get("severity", "normal")
            atype = alert.get("alert_type", "UNKNOWN")
            msg   = alert.get("message", "")
            ts    = alert.get("created_at", "")
            try:
                ts_fmt = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%H:%M:%S")
            except Exception:
                ts_fmt = ts[:19] if ts else ""
            css = f"alert-{sev}"
            st.markdown(
                f'<div class="{css}"><strong>{atype}</strong> — {msg}'
                f'<br><small>{ts_fmt}</small></div>',
                unsafe_allow_html=True,
            )
    else:
        st.success("✅ No active alerts — fish are healthy!")

with col_stats:
    st.subheader("📊 Alert Statistics (24h)")
    if alert_stats:
        st.metric("Total alerts",    alert_stats.get("total_alerts", 0))
        st.metric("Active",          alert_stats.get("active_alerts", 0))
        st.metric("Resolved",        alert_stats.get("resolved_alerts", 0))
        st.metric("Critical active", alert_stats.get("critical_active", 0))
    else:
        st.info("No stats available.")

st.divider()

# ── Row 5: Raw data table ─────────────────────────────────────────────────────
with st.expander("🗃 Raw sensor data table"):
    if readings:
        df = pd.DataFrame(readings)
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        display_cols = [c for c in ["timestamp", "temperature", "ph", "dissolved_o2", "ammonia"] if c in df.columns]
        st.dataframe(df[display_cols], width="stretch", hide_index=True)
    else:
        st.info("No data to display.")

st.divider()

# ── Row 6: Recommendations ───────────────────────────────────────────────────
st.subheader("📋 Recommendations")

recommendation = get_recommendation(stress_level, alert_types, fish_data)
box_color = {"critical": "#FCEBEB", "warning": "#FAEEDA", "normal": "#E1F5EE"}.get(stress_level, "#F8F9FA")
st.markdown(
    f'<div style="background:{box_color};padding:16px;border-radius:8px;white-space:pre-line;">{recommendation}</div>',
    unsafe_allow_html=True
)

st.divider()

# ── Row 7: Export report ──────────────────────────────────────────────────────
st.subheader("📤 Export Report")

col_export1, col_export2 = st.columns(2)

with col_export1:
    if readings:
        df_export = pd.DataFrame(readings)
        df_export["timestamp"] = pd.to_datetime(df_export["timestamp"])
        csv = df_export.to_csv(index=False)
        st.download_button(
            label="📥 Download sensor data (CSV)",
            data=csv,
            file_name=f"sensor_data_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )

with col_export2:
    if fish_data and fish_data.get("fish"):
        df_fish = pd.DataFrame(fish_data["fish"])
        csv_fish = df_fish.to_csv(index=False)
        st.download_button(
            label="📥 Download fish stress (CSV)",
            data=csv_fish,
            file_name=f"fish_stress_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if auto_refresh:
    time.sleep(refresh_sec)
    st.rerun()