import streamlit as st
import pandas as pd
import glob
import os
import re
import numpy as np
import plotly.express as px

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
    return os.path.basename(filename).replace(".xlsx", "").split("_")[-1]

def clean_report_name(filename: str) -> str:
    base = os.path.basename(filename)
    return base.replace("Error_Count_Diff_", "").replace(".xlsx", "")

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
# Convert HERESUP ticket → Jira URL
# =================================================
JIRA_BASE = "https://here-technologies.atlassian.net/browse/"
ticket_re = re.compile(r"(HERESUP-\d+)")

def ticket_to_url(val):
    if pd.isna(val):
        return None
    text = str(val)
    m = ticket_re.search(text)
    if m:
        return f"{JIRA_BASE}{m.group(1)}"
    return None

df["Bug Ticket Link"] = df["Bug Ticket"].apply(ticket_to_url)

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
# Main Diff Table (CLICKABLE HERESUP LINKS ✅)
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
            display_text="Open Ticket",
            help="Click to open HERESUP Jira ticket"
        )
    }
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

    nf["Bug Ticket Link"] = nf["Bug Ticket"].apply(ticket_to_url)

    if nf.empty:
        st.info("No new Pass → Fail cases detected.")
    else:
        st.dataframe(
            nf[
                ["testId", "testName", "diff", "Bug Ticket Link"]
            ],
            use_container_width=True,
            column_config={
                "Bug Ticket Link": st.column_config.LinkColumn(
                    "Bug Ticket",
                    display_text="Open Ticket"
                )
            }
        )

# =================================================
# Severity Pie Chart (optional)
# =================================================
if "Severity" in df.columns:
    st.subheader("🟣 Severity Distribution")

    sev = df["Severity"].value_counts().reset_index()
    sev.columns = ["Severity", "Count"]

    fig = px.pie(sev, names="Severity", values="Count")
    st.plotly_chart(fig, use_container_width=True)

# =================================================
# Export
# =================================================
st.subheader("📤 Export")

st.download_button(
    "⬇️ Download Filtered Data (Excel)",
    data=view.to_excel(index=False),
    file_name=f"{selected_report}_Filtered.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)