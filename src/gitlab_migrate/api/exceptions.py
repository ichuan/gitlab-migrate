"""GitLab API exceptions."""

from typing import Optional


class GitLabAPIError(Exception):
    """Base exception for GitLab API errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Optional[dict] = None,
    ):
        """Initialize GitLab API error.

        Args:
            message: Error message
            status_code: HTTP status code
            response_data: Response data from API
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class GitLabAuthenticationError(GitLabAPIError):
    """Authentication error with GitLab API."""

    pass


class GitLabRateLimitError(GitLabAPIError):
    """Rate limit exceeded error."""

    def __init__(self, message: str, retry_after: int = 60, **kwargs):
        """Initialize rate limit error.

        Args:
            message: Error message
            retry_after: Seconds to wait before retry
            **kwargs: Additional arguments for base class
        """
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class GitLabNotFoundError(GitLabAPIError):
    """Resource not found error."""

    pass


class GitLabPermissionError(GitLabAPIError):
    """Permission denied error."""

    pass


class GitLabValidationError(GitLabAPIError):
    """Validation error for API requests."""

    pass
