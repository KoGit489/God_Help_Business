#!/usr/bin/env bash
set -euo pipefail

allowed_branches=(main God_Help_Draft_1 God_Help_Draft_2)
branch="${1:-}"
if [[ ! " ${allowed_branches[*]} " =~ " ${branch} " ]]; then
  echo "Usage: $0 {main|God_Help_Draft_1|God_Help_Draft_2}"
  exit 2
fi

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

if [[ ! -f .env.production ]]; then
  echo "Missing .env.production. Copy .env.production.example and fill in the private values first."
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose is required on this server."
  exit 1
fi

printf 'This will replace the live app code with branch %s. Database and Spaces files remain separate.\n' "$branch"
read -r -p "Type DEPLOY to continue: " confirmation
if [[ "$confirmation" != "DEPLOY" ]]; then
  echo "Cancelled; the live app was not changed."
  exit 1
fi

git fetch origin "$branch"
git checkout "$branch"
git reset --hard "origin/$branch"
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build

echo "Deployment requested for $branch. Check status with: docker compose -f docker-compose.prod.yml ps"
