#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "=== isnad deployment ==="

# Build and start
docker compose build
docker compose up -d

echo ""
echo "✅ Services running:"
echo "   nginx  → http://localhost (port 80)"
echo "   API    → http://localhost/api/v1/"
echo "   Web    → http://localhost/"
echo ""
echo "📋 Status:"
docker compose ps

echo ""
echo "⚠️  TODO for production:"
echo "   1. Choose domain name"
echo "   2. Set up SSL (Let's Encrypt / certbot)"
echo "   3. Update nginx.conf server_name"
echo "   4. Uncomment SSL block in nginx.conf"
echo "   5. Add .env for any API secrets"
