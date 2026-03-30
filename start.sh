#!/bin/bash
PORT="${PORT:-8501}"
exec streamlit run app.py --server.port="$PORT" --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false
