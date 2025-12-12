#!/bin/bash

# Run the LangGraph triage application
# Default port: 8001 (to avoid conflict with backend on 8000)

PORT=${1:-8001}

echo "Starting LangGraph Triage App on port $PORT..."
uvicorn app.main:app --host 0.0.0.0 --port $PORT --reload
