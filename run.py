#!/usr/bin/env python3
"""
Run script for LangGraph Triage Application
Default port: 8001 (to avoid conflict with backend on 8000)
"""

import sys
import uvicorn

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001

    print(f"Starting LangGraph Triage App on port {port}...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
