@echo off
chcp 65001 >nul 2>&1
docker compose exec -e PYTHONIOENCODING=utf-8:replace dispatcher python interactive.py
