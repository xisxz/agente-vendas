#!/bin/bash

# Build script for Render deployment

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Downloading spaCy language model..."
python -m spacy download pt_core_news_sm

echo "Creating database directory..."
mkdir -p src/database

echo "Build completed successfully!"

