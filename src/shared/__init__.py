"""Shared infrastructure for the Multi-Agent Task Dispatch System.

Submodules are imported explicitly by each service to avoid pulling in
dependencies that a particular service does not need.

Usage:
    from shared.database import create_pool, close_pool
    from shared.models import AgentStatus, TaskRecord, ...
    from shared.rabbitmq import create_connection, setup_infrastructure, ...
"""
