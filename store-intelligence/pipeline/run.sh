#!/bin/bash

# Exit on error
set -e

echo "=== Starting Store Intelligence Pipeline ==="

# 1. Check if python is available in the virtual env
if [ -d "venv" ]; then
    PYTHON_CMD="./venv/bin/python"
elif [ -d "../venv" ]; then
    PYTHON_CMD="../venv/bin/python"
else
    PYTHON_CMD="python"
fi

# Determine python command path for Windows vs Unix
if [ -f "./venv/Scripts/python" ]; then
    PYTHON_CMD="./venv/Scripts/python"
elif [ -f "../venv/Scripts/python" ]; then
    PYTHON_CMD="../venv/Scripts/python"
fi

echo "Using Python: $PYTHON_CMD"

# 2. Run detection and tracking pipeline
# This will output events_output.jsonl
$PYTHON_CMD pipeline/detect.py --store_id ST1076 --video_dir d:/purple_hackathon/Store\ 2 --output events_output.jsonl --frame_skip 15

# 3. Feed generated JSONL events to API
echo "Ingesting events into local running API..."
$PYTHON_CMD pipeline/feed_to_api.py events_output.jsonl

echo "=== Pipeline execution completed successfully! ==="
