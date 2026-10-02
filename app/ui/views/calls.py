"""Every LLM call this session: latency, tokens, cost. Good material for the pitch."""

import plotly.express as px
import streamlit as st

from app.ui.components import calls_dataframe, header

header("Call log", "Per-call latency and cost since the app started.")

df = calls_dataframe()
if df.empty:
    st.info("No calls yet. Try the playground or the agent demo.")
    st.stop()

live = df[~df["cached"]]
c1, c2, c3 = st.columns(3)
c1.metric("Calls", len(df), border=True)
c2.metric(
    "p50 latency", f"{live['latency_ms'].median() / 1000:.2f}s" if len(live) else "-", border=True
)
c3.metric("Total cost", f"${live['cost_usd'].fillna(0).sum():.4f}", border=True)

fig = px.bar(
    df, x=df.index, y="latency_ms", color="label", labels={"x": "call", "latency_ms": "ms"}
)
fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0))
st.plotly_chart(fig, width="stretch")
st.dataframe(df.iloc[::-1], width="stretch", hide_index=True)
