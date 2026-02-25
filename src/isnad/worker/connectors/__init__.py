"""Platform connectors for the isnad worker.

Each connector fetches data from a specific platform and returns
a standardized ConnectorResult dict.
"""

from .base import ConnectorResult, BaseConnector
from .github import GitHubConnector
from .ugig import UgigConnector
from .generic import GenericConnector

CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {
    "github": GitHubConnector,
    "ugig": UgigConnector,
}


def get_connector_for_url(url: str) -> BaseConnector:
    """Return the appropriate connector for a given URL."""
    url_lower = url.lower()
    if "github.com" in url_lower:
        return GitHubConnector()
    if "ugig.net" in url_lower:
        return UgigConnector()
    return GenericConnector()


__all__ = [
    "ConnectorResult",
    "BaseConnector",
    "GitHubConnector",
    "UgigConnector",
    "GenericConnector",
    "CONNECTOR_REGISTRY",
    "get_connector_for_url",
]
