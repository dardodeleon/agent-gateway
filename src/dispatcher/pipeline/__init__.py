"""Task processing pipeline for the dispatcher."""

from pipeline.consumer import TaskConsumer
from pipeline.client import DispatchClient

__all__ = ["DispatchClient", "TaskConsumer"]
