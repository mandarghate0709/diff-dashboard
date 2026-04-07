import streamlit as st
import pandas as pd
import glob
import os
import plotly.express as px
from io import BytesIO

st.set_page_config(page_title="Diff Dashboard", layout="wide")

st.title("📊 Single‑Report Diff Dashboard")

BASE_PATH = "data"

files = glob.glob(os.path.join(BASE_PATH, "**", "*.xlsx"), recursive=True)
if not files:
    st.error("No Excel files found")
    st.stop()

file_names = [os.path.basename(f) for f in files]
selected_name = st.sidebar.selectbox("Select Report", file_names)
selected_file = dict(zip(file_names, files))[selected_name]

df = pd.read_excel(selected_file)
st.write(f"### ✅ Loaded Report: **{selected_name}**")

# ---------- diff % ----------
error_cols = [c for c in df.columns if c.endswith("_errors")]
if len(error_cols) == 2:
    new_col, old_col = error_cols
    df["diff_percent"] = (
        (df[new_col] - df[old_col]) / df[old_col].replace(0, pd.NA) * 100
    ).fillna(0).round(2)
else:
    df["diff_percent"] = 0.0

# ---------- severity ----------
def classify(p):
    if p > 10:
        return "Major Regression"
    elif p > 5:
        return "Moderate Regression"
    elif p > 0:
        return "Minor Regression"
    elif p < 0:
        return "Improvement"
    return "No Change"

df["Severity"] = df["diff_percent"].apply(classify)

# ---------- summary ----------
st.subheader("📦 Summary")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Tests", len(df))
c2.metric("Regressions", (df["diff"] > 0).sum())
c3.metric("Improvements", (df["diff"] < 0).sum())
c4.metric("No Change", (df["diff"] == 0).sum())

worst = df.loc[df["diff_percent"].idxmax()]
best = df.loc[df["diff_percent"].idxmin()]

if "highlight" not in st.session_state:
    st.session_state.highlight = None

c5, c6 = st.columns(2)

with c5:
    st.metric("Worst Regression (% diff)", f"{worst['diff_percent']}%")
    st.caption(f"TestId: {worst['testId']}")
    if st.button("Highlight Worst"):
        st.session_state.highlight = worst["testId"]

with c6:
    st.metric("Best Improvement (% diff)", f"{best['diff_percent']}%")
    st.caption(f"TestId: {best['testId']}")
    if st.button("Highlight Best"):
        st.session_state.highlight = best["testId"]

if st.session_state.highlight:
    if st.button("Clear Highlight"):
        st.session_state.highlight = None

# ---------- filters ----------
st.sidebar.header("Filters")
mode = st.sidebar.radio("Show", ["All", "Only Regressions", "Only Improvements"])
view = df.copy()

if mode == "Only Regressions":
    view = view[view["diff"] > 0]
elif mode == "Only Improvements":
    view = view[view["diff"] < 0]

min_d, max_d = int(df["diff"].min()), int(df["diff"].max())
rng = st.sidebar.slider("Diff Range", min_d, max_d, (min_d, max_d))
view = view[(view["diff"] >= rng[0]) & (view["diff"] <= rng[1])]

search = st.sidebar.text_input("Search")
if search:
    view = view[
        view["testId"].str.contains(search, case=False, na=False)
        | view["testName"].str.contains(search, case=False, na=False)
    ]

if st.session_state.highlight:
    view = view[view["testId"] == st.session_state.highlight]

# ---------- table ----------
def color(v):
    if isinstance(v, (int, float)):
        if v > 0:
            return "background-color:#FFC7CE"
        if v < 0:
            return "background-color:#C6EFCE"
    return ""

st.subheader("📋 Diff Table")
st.dataframe(view.style.map(color, subset=["diff"]), use_container_width=True)

# ---------- Top major ----------
st.subheader("🔥 Top 20 Major Regressions")
maj = df[df["Severity"] == "Major Regression"].sort_values("diff_percent", ascending=False).head(20)
st.dataframe(maj.style.map(color, subset=["diff"]), use_container_width=True)

# ---------- Pie ----------
st.subheader("Severity Distribution")
counts = df["Severity"].value_counts().reset_index()
counts.columns = ["Severity", "Count"]
pie = px.pie(
    counts,
    names="Severity",
    values="Count",
    color="Severity",
    color_discrete_map={
        "Major Regression": "#ff4d4d",
        "Moderate Regression": "#ff944d",
        "Minor Regression": "#ffe066",
        "Improvement": "#66cc66",
        "No Change": "#cccccc",
    },
)
st.plotly_chart(pie, use_container_width=True)

# ---------- Export ----------
def to_excel(d):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        d.to_excel(w, index=False)
    return out.getvalue()

st.download_button(
    "⬇️ Download Filtered Excel",
    data=to_excel(view),
    file_name="Filtered_Diff_Report.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
