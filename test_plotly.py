import streamlit as st
import plotly.graph_objects as go

st.title("Plotly Selection Test")

fig = go.Figure(data=go.Scatter(
    x=[1, 2, 3],
    y=[1, 2, 3],
    mode='markers',
    marker=dict(symbol='hexagon', size=20)
))

# Test if on_select is supported
try:
    event = st.plotly_chart(fig, on_select="rerun")
    st.write("Selection:", event.selection)
except TypeError as e:
    st.error(f"Error: {e}")
    st.plotly_chart(fig)
