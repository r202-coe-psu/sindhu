#!/bin/sh

echo "sudo git pull"
sudo git pull

echo "docker compose -f docker-compose.production.yml up -d --build --force-recreate"
docker compose -f docker-compose.production.yml up -d --build --force-recreate
