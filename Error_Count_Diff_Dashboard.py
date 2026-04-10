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
# Pattern:
# Error_Count_Diff_P173_vs_261E0_NAR.xlsx
# =================================================
def extract_market(filename: str) -> str:
    base = os.path.basename(filename).replace(".xlsx", "")
    return base.split("_")[-1]

def clean_report_name(filename: str) -> str:
    base = os.path.basename(filename)
    base = base.replace("Error_Count_Diff_", "")
    base = base.replace(".xlsx", "")
    return base

# =================================================
# Build Market → Report mapping
# =================================================
market_map = {}

for f in files:
    market = extract_market(f)
    report_name = clean_report_name(f)
    market_map.setdefault(market, {})[report_name] = f

# =================================================
# Sidebar selection
# =================================================
st.sidebar.header("📁 Select Report")

markets = sorted(market_map.keys())
selected_market = st.sidebar.selectbox("Select Market", markets)

reports = sorted(market_map[selected_market].keys())
selected_report = st.sidebar.selectbox("Select Report", reports)

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
# Convert HERESUP → Jira URL (for LinkColumn)
# =================================================
JIRA_BASE = "https://here-technologies.atlassian.net/browse/"
ticket_re = re.compile(r"(HERESUP-\d+)")

def ticket_to_url(val):
    if pd.isna(val):
        return None
    m = ticket_re.search(str(val))
    if m:
        return f"{JIRA_BASE}{m.group(1)}"
    return None

df["Bug Ticket Link"] = df["Bug Ticket"].apply(ticket_to_url)

# =================================================
# Summary section
# =================================================
st.subheader("📦 Summary")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Tests", len(df))
c2.metric("Regressions (diff > 0)", (df["diff"] > 0).sum())
c3.metric("Improvements (diff < 0)", (df["diff"] < 0).sum())
c4.metric("No Change (diff = 0)", (df["diff"] == 0).sum())

# =================================================
# Sidebar filters
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
rng = st.sidebar.slider(
    "Diff Range",
    min_d,
    max_d,
    (min_d, max_d)
)

view = view[
    (view["diff"] >= rng[0]) &
    (view["diff"] <= rng[1])
]

search = st.sidebar.text_input("Search Test ID / Name")
if search:
    view = view[
        view["testId"].str.contains(search, case=False, na=False) |
        view["testName"].str.contains(search, case=False, na=False)
    ]

# =================================================
# Diff table (HERESUP text is clickable ✅)
# =================================================
st.subheader("📋 Diff Table")

display_cols = [
    "testId",
    "testName",
    *[c for c in df.columns if c.endswith("_errors")],
    "diff",
    "Bug Ticket Link"
]

display_cols = [c for c in display_cols if c in view.columns]

st.dataframe(
    view[display_cols],
    use_container_width=True,
    column_config={
        "Bug Ticket Link": st.column_config.LinkColumn(
            "Bug Ticket",
            display_text=r"HERESUP-\d+",
            help="Click to open HERESUP Jira ticket"
        )
    }
)

# =================================================
# New Failures (Pass → Fail)
# =================================================
status_cols = [
    c for c in df.columns
    if c not in display_cols and c.endswith(selected_market)
]

if len(status_cols) >= 2:
    old_status, new_status = status_cols[:2]

    st.subheader("🆕 New Failures (Pass → Fail)")

    nf = df[
        (df[old_status] == "Pass") &
        (df[new_status] == "Fail")
    ].copy()

    nf["Bug Ticket Link"] = nf["Bug Ticket"].apply(ticket_to_url)

    if nf.empty:
        st.info("No new Pass → Fail cases detected.")
    else:
        st.write(f"**Total New Failures:** {len(nf)}")
        st.dataframe(
            nf[
                ["testId", "testName", "diff", "Bug Ticket Link"]
            ],
            use_container_width=True,
            column_config={
                "Bug Ticket Link": st.column_config.LinkColumn(
                    "Bug Ticket",
                    display_text=r"HERESUP-\d+"
                )
            }
        )

# =================================================
# Severity Pie Chart (if present)
# =================================================
if "Severity" in df.columns:
    st.subheader("🟣 Severity Distribution")

    sev_counts = df["Severity"].value_counts().reset_index()
    sev_counts.columns = ["Severity", "Count"]

    fig = px.pie(
        sev_counts,
        names="Severity",
        values="Count",
        color="Severity"
    )

    st.plotly_chart(fig, use_container_width=True)

# =================================================
# Export filtered view (FIXED)
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