import streamlit as st
import pandas as pd
import glob
import os
import plotly.express as px
import numpy as np
import re
from io import BytesIO

# =================================================
# Streamlit setup
# =================================================
st.set_page_config(page_title="Error Count Diff Dashboard", layout="wide")
st.title("📊 Error Count Diff Dashboard")

# =================================================
# Base folder (Streamlit Cloud compatible)
# =================================================
BASE_PATH = "data"

files = glob.glob(os.path.join(BASE_PATH, "*.xlsx"))
if not files:
    st.error("No Excel files found in data/ folder")
    st.stop()

# =================================================
# Helpers to parse filenames
# =================================================
def extract_market(filename: str) -> str:
    base = os.path.basename(filename).replace(".xlsx", "")
    return base.split("_")[-1]

def clean_report_name(filename: str) -> str:
    return (
        os.path.basename(filename)
        .replace("Error_Count_Diff_", "")
        .replace(".xlsx", "")
    )

# =================================================
# Build Market → Report mapping
# =================================================
market_map = {}
for f in files:
    market = extract_market(f)
    report = clean_report_name(f)
    market_map.setdefault(market, {})[report] = f

# =================================================
# Sidebar selection
# =================================================
st.sidebar.header("📁 Select Report")

selected_market = st.sidebar.selectbox(
    "Select Market",
    sorted(market_map.keys())
)

selected_report = st.sidebar.selectbox(
    "Select Report",
    sorted(market_map[selected_market].keys())
)

selected_file = market_map[selected_market][selected_report]

# =================================================
# Load selected report
# =================================================
df = pd.read_excel(selected_file)

st.write(
    f"### ✅ Loaded Report: **{selected_report}** "
    f"(Market: **{selected_market}**)"
)

# =================================================
# Ensure Bug Ticket column exists
# =================================================
if "Bug Ticket" not in df.columns:
    df["Bug Ticket"] = np.nan

# =================================================
# Convert HERESUP text → clickable HTML
# =================================================
JIRA_BASE = "https://here-technologies.atlassian.net/browse/"
ticket_re = re.compile(r"(HERESUP-\d+)")

def make_clickable(val):
    if pd.isna(val):
        return ""
    m = ticket_re.search(str(val))
    if m:
        ticket = m.group(1)
        url = f"{JIRA_BASE}{ticket}"
        return f'<a href="{url}" target="_blank">{ticket}</a>'
    return str(val)

df["Bug Ticket"] = df["Bug Ticket"].apply(make_clickable)

# =================================================
# Summary
# =================================================
st.subheader("📦 Summary")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Tests", len(df))
c2.metric("Regressions (diff > 0)", (df["diff"] > 0).sum())
c3.metric("Improvements (diff < 0)", (df["diff"] < 0).sum())
c4.metric("No Change (diff = 0)", (df["diff"] == 0).sum())

# =================================================
# Filters
# =================================================
st.sidebar.header("🔍 Filters")

mode = st.sidebar.radio(
    "Show",
    ["All", "Only Regressions", "Only Improvements"]
)

view = df.copy()

if mode == "Only Regressions":
    view = view[view["diff"] > 0]
elif mode == "Only Improvements":
    view = view[view["diff"] < 0]

min_d, max_d = int(df["diff"].min()), int(df["diff"].max())
rng = st.sidebar.slider("Diff Range", min_d, max_d, (min_d, max_d))
view = view[(view["diff"] >= rng[0]) & (view["diff"] <= rng[1])]

search = st.sidebar.text_input("Search Test ID / Name")
if search:
    view = view[
        view["testId"].str.contains(search, case=False, na=False) |
        view["testName"].str.contains(search, case=False, na=False)
    ]

# =================================================
# Diff Table (HTML-rendered, clickable HERESUP ✅)
# =================================================
st.subheader("📋 Diff Table")

display_cols = [
    "testId",
    "testName",
    *[c for c in df.columns if c.endswith("_errors")],
    "diff",
    "Bug Ticket"
]

display_cols = [c for c in display_cols if c in view.columns]

st.markdown(
    view[display_cols].to_html(escape=False, index=False),
    unsafe_allow_html=True
)

# =================================================
# New Failures (Pass → Fail)
# =================================================
status_cols = [c for c in df.columns if c.endswith(selected_market)]
if len(status_cols) >= 2:
    old_status, new_status = status_cols[:2]

    st.subheader("🆕 New Failures (Pass → Fail)")

    nf = df[
        (df[old_status] == "Pass") &
        (df[new_status] == "Fail")
    ].copy()

    if nf.empty:
        st.info("No new Pass → Fail cases detected.")
    else:
        st.markdown(
            nf[
                ["testId", "testName", "diff", "Bug Ticket"]
            ].to_html(escape=False, index=False),
            unsafe_allow_html=True
        )

# =================================================
# Severity Pie Chart
# =================================================
if "Severity" in df.columns:
    st.subheader("🟣 Severity Distribution")

    sev = df["Severity"].value_counts().reset_index()
    sev.columns = ["Severity", "Count"]

    fig = px.pie(sev, names="Severity", values="Count")
    st.plotly_chart(fig, use_container_width=True)

# =================================================
# Export (FIXED)
# =================================================
st.subheader("📤 Export")

buffer = BytesIO()
view.to_excel(buffer, index=False)
buffer.seek(0)

st.download_button(
    "⬇️ Download Filtered Data (Excel)",
    data=buffer,
    file_name=f"{selected_report}_Filtered.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
