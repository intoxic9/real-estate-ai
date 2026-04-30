#!/bin/bash
echo "Installing dependencies..."
pip install -r requirements.txt
echo ""
echo "Starting PropScraper Pro..."
echo "Open http://localhost:5000 in your browser"
echo "Admin login: admin / admin123"
echo ""
python app.py
