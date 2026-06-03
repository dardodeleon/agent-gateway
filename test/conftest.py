"""Shared test configuration and fixtures."""

import logging
import os
import sys

import json
from pathlib import Path
import pytest
import pytest_asyncio
from dotenv import load_dotenv

def load_test_data(file: str):
    data_dir = Path(__file__).resolve().parent / "data"
    file_path = data_dir / f"{file}.json"
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list) and all(isinstance(item, list) for item in data):
        return [tuple(item) for item in data]
    return data

@pytest.fixture
def server_config():
    return load_test_data("server_mcp_agent_gateway")

def pytest_addoption(parser):
     parser.addoption(
         "--fail",
         action="store_true",
         default=False,
         help="Omit hint suffix so the agent produces a verbose (failing) response",
     )