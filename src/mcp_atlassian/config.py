from dataclasses import dataclass


@dataclass
class ConfluenceConfig:
    """Confluence API configuration."""

    url: str  # Base URL for Confluence
    api_token: str  # API token used as password

    @property
    def is_cloud(self) -> bool:
        """Check if this is a cloud instance."""
        return "atlassian.net" in self.url


@dataclass
class JiraConfig:
    """Jira API configuration."""

    url: str  # Base URL for Jira
    api_token: str  # API token used as password

    @property
    def is_cloud(self) -> bool:
        """Check if this is a cloud instance."""
        return "atlassian.net" in self.url
