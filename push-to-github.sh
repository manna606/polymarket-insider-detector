#!/bin/bash
# Helper script to push to GitHub with Personal Access Token
# Usage: ./push-to-github.sh YOUR_GITHUB_TOKEN

set -e

TOKEN=$1

if [ -z "$TOKEN" ]; then
    echo "Usage: ./push-to-github.sh YOUR_GITHUB_TOKEN"
    echo ""
    echo "To get your token:"
    echo "  1. Go to https://github.com/settings/tokens"
    echo "  2. Click 'Generate new token (classic)'"
    echo "  3. Check the 'repo' box"
    echo "  4. Generate and copy the token"
    echo ""
    echo "Then run:"
    echo "  ./push-to-github.sh ghp_xxxxxxxxxxxx"
    exit 1
fi

echo "Setting remote URL with token..."
git remote set-url origin "https://manna606:${TOKEN}@github.com/manna606/polymarket-insider-detector.git"

echo "Pushing to GitHub..."
git branch -M main
git push -u origin main

echo ""
echo "Success! Your code is now at:"
echo "  https://github.com/manna606/polymarket-insider-detector"
echo ""
echo "Next step: go to railway.app and deploy from this repo."
