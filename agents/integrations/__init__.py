"""Agent integrations for M365 services."""
from .sharepoint import SharePointIntegration
from .documents import DocumentCreator

__all__ = ["SharePointIntegration", "DocumentCreator"]
