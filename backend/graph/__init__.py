"""
UQS Graph package.
Exports the compiled LangGraph pipeline.
"""
from backend.graph.pipeline import get_pipeline, pipeline

__all__ = ["pipeline", "get_pipeline"]
