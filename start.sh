#!/bin/sh

if command -v python3 > /dev/null 2>&1; then
    PYTHON=python3
elif command -v python > /dev/null 2>&1; then
    PYTHON=python
else
    echo "No Python found!"
    exit 1
fi

$PYTHON main.py
