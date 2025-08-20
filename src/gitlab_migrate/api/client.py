"""GitLab API client implementation."""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin

import aiohttp
import requests
from loguru import logger
from pydantic import BaseModel

from ..config.config import GitLabInstanceConfig
from .exceptions import (
    GitLabAPIError,
    GitLabAuthenticationError,
    GitLabNotFoundError,
    GitLabRateLimitError,
)


class APIResponse(BaseModel):
    """Standard API response wrapper."""

    status_code: int
    data: Any
    headers: Dict[str, str]
    success: bool


class GitLabClient:
    """GitLab API client with authentication."""

    def __init__(self, config: GitLabInstanceConfig):
        """Initialize GitLab client.

        Args:
            config: GitLab instance configuration
        """
        self.config = config
        self.base_url = config.url.rstrip('/') + '/api/v4'
        self.session = requests.Session()

        # Set authentication headers
        if config.token:
            self.session.headers.update({'Private-Token': config.token})
        elif config.oauth_token:
            self.session.headers.update(
                {'Authorization': f'Bearer {config.oauth_token}'}
            )
        else:
            raise GitLabAuthenticationError('No authentication token provided')

        # Set common headers
        self.session.headers.update(
            {'Content-Type': 'application/json', 'User-Agent': 'gitlab-migrate/1.0.0'}
        )

        logger.info(f'Initialized GitLab client for {config.url}')

    def _build_url(self, endpoint: str) -> str:
        """Build full API URL from endpoint.

        Args:
            endpoint: API endpoint path

        Returns:
            Full API URL
        """
        return urljoin(self.base_url + '/', endpoint.lstrip('/'))

    def _handle_response(self, response: requests.Response) -> APIResponse:
        """Handle API response and convert to standard format.

        Args:
            response: Raw HTTP response

        Returns:
            Standardized API response

        Raises:
            GitLabAPIError: For various API errors
        """
        headers = dict(response.headers)

        # Handle rate limiting
        if response.status_code == 429:
            retry_after = int(headers.get('Retry-After', 60))
            raise GitLabRateLimitError(
                f'Rate limit exceeded. Retry after {retry_after} seconds',
                retry_after=retry_after,
            )

        # Handle authentication errors
        if response.status_code == 401:
            raise GitLabAuthenticationError('Authentication failed')

        # Handle not found
        if response.status_code == 404:
            raise GitLabNotFoundError('Resource not found')

        # Handle other client/server errors
        if response.status_code >= 400:
            try:
                error_data = response.json()
                message = error_data.get('message', f'HTTP {response.status_code}')
            except ValueError:
                message = f'HTTP {response.status_code}: {response.text}'

            raise GitLabAPIError(
                f'API request failed: {message}',
                status_code=response.status_code,
                response_data=error_data if 'error_data' in locals() else None,
            )

        # Parse response data
        try:
            data = response.json() if response.content else None
        except ValueError:
            data = response.text

        return APIResponse(
            status_code=response.status_code,
            data=data,
            headers=headers,
            success=200 <= response.status_code < 300,
        )

    async def _make_request_async(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> APIResponse:
        """Make asynchronous API request.

        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            data: Request body data
            **kwargs: Additional request arguments

        Returns:
            API response
        """
        url = self._build_url(endpoint)

        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'gitlab-migrate/1.0.0',
        }
        if self.config.token:
            headers['Private-Token'] = self.config.token
        elif self.config.oauth_token:
            headers['Authorization'] = f'Bearer {self.config.oauth_token}'

        async with aiohttp.ClientSession(headers=headers) as session:
            try:
                async with session.request(
                    method=method, url=url, params=params, json=data, **kwargs
                ) as response:
                    response_headers = dict(response.headers)

                    # Handle rate limiting
                    if response.status == 429:
                        retry_after = int(response_headers.get('Retry-After', 60))
                        raise GitLabRateLimitError(
                            f'Rate limit exceeded. Retry after {retry_after} seconds',
                            retry_after=retry_after,
                        )

                    # Handle authentication errors
                    if response.status == 401:
                        raise GitLabAuthenticationError('Authentication failed')

                    # Handle not found
                    if response.status == 404:
                        raise GitLabNotFoundError('Resource not found')

                    # Handle other errors
                    if response.status >= 400:
                        try:
                            error_data = await response.json()
                            message = error_data.get(
                                'message', f'HTTP {response.status}'
                            )
                        except (ValueError, aiohttp.ContentTypeError):
                            message = f'HTTP {response.status}: {await response.text()}'

                        raise GitLabAPIError(
                            f'API request failed: {message}',
                            status_code=response.status,
                            response_data=error_data
                            if 'error_data' in locals()
                            else None,
                        )

                    # Parse response data
                    try:
                        response_text = await response.text()
                        if response_text:
                            response_data = json.loads(response_text)
                        else:
                            response_data = None
                    except (ValueError, json.JSONDecodeError):
                        response_data = response_text

                    return APIResponse(
                        status_code=response.status,
                        data=response_data,
                        headers=response_headers,
                        success=200 <= response.status < 300,
                    )

            except aiohttp.ClientError as e:
                logger.error(f'Network error during API request: {e}')
                raise GitLabAPIError(f'Network error: {e}')

    def get(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None, **kwargs
    ) -> APIResponse:
        """Make GET request.

        Args:
            endpoint: API endpoint
            params: Query parameters
            **kwargs: Additional request arguments

        Returns:
            API response
        """
        url = self._build_url(endpoint)

        try:
            response = self.session.get(url, params=params, **kwargs)
            return self._handle_response(response)
        except requests.RequestException as e:
            logger.error(f'Network error during GET request: {e}')
            raise GitLabAPIError(f'Network error: {e}')

    def post(
        self, endpoint: str, data: Optional[Dict[str, Any]] = None, **kwargs
    ) -> APIResponse:
        """Make POST request.

        Args:
            endpoint: API endpoint
            data: Request body data
            **kwargs: Additional request arguments

        Returns:
            API response
        """
        url = self._build_url(endpoint)

        try:
            response = self.session.post(url, json=data, **kwargs)
            return self._handle_response(response)
        except requests.RequestException as e:
            logger.error(f'Network error during POST request: {e}')
            raise GitLabAPIError(f'Network error: {e}')

    def put(
        self, endpoint: str, data: Optional[Dict[str, Any]] = None, **kwargs
    ) -> APIResponse:
        """Make PUT request.

        Args:
            endpoint: API endpoint
            data: Request body data
            **kwargs: Additional request arguments

        Returns:
            API response
        """
        url = self._build_url(endpoint)

        try:
            response = self.session.put(url, json=data, **kwargs)
            return self._handle_response(response)
        except requests.RequestException as e:
            logger.error(f'Network error during PUT request: {e}')
            raise GitLabAPIError(f'Network error: {e}')

    def delete(self, endpoint: str, **kwargs) -> APIResponse:
        """Make DELETE request.

        Args:
            endpoint: API endpoint
            **kwargs: Additional request arguments

        Returns:
            API response
        """
        url = self._build_url(endpoint)

        try:
            response = self.session.delete(url, **kwargs)
            return self._handle_response(response)
        except requests.RequestException as e:
            logger.error(f'Network error during DELETE request: {e}')
            raise GitLabAPIError(f'Network error: {e}')

    async def get_async(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None, **kwargs
    ) -> APIResponse:
        """Make asynchronous GET request.

        Args:
            endpoint: API endpoint
            params: Query parameters
            **kwargs: Additional request arguments

        Returns:
            API response
        """
        return await self._make_request_async('GET', endpoint, params=params, **kwargs)

    async def post_async(
        self, endpoint: str, data: Optional[Dict[str, Any]] = None, **kwargs
    ) -> APIResponse:
        """Make asynchronous POST request.

        Args:
            endpoint: API endpoint
            data: Request body data
            **kwargs: Additional request arguments

        Returns:
            API response
        """
        return await self._make_request_async('POST', endpoint, data=data, **kwargs)

    async def put_async(
        self, endpoint: str, data: Optional[Dict[str, Any]] = None, **kwargs
    ) -> APIResponse:
        """Make asynchronous PUT request.

        Args:
            endpoint: API endpoint
            data: Request body data
            **kwargs: Additional request arguments

        Returns:
            API response
        """
        return await self._make_request_async('PUT', endpoint, data=data, **kwargs)

    async def delete_async(self, endpoint: str, **kwargs) -> APIResponse:
        """Make asynchronous DELETE request.

        Args:
            endpoint: API endpoint
            **kwargs: Additional request arguments

        Returns:
            API response
        """
        return await self._make_request_async('DELETE', endpoint, **kwargs)

    def get_paginated(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        per_page: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get all pages of a paginated endpoint.

        Args:
            endpoint: API endpoint
            params: Query parameters
            per_page: Items per page

        Returns:
            List of all items from all pages
        """
        all_items = []
        page = 1

        if params is None:
            params = {}

        params['per_page'] = per_page

        while True:
            params['page'] = page
            response = self.get(endpoint, params=params)

            if not response.success:
                break

            items = response.data
            if not items:
                break

            all_items.extend(items)

            total_pages = response.headers.get('X-Total-Pages')
            if total_pages and page >= int(total_pages):
                break

            if len(items) < per_page:
                break

            page += 1

        logger.info(f'Retrieved {len(all_items)} items from {endpoint}')
        return all_items

    def test_connection(self) -> bool:
        """Test connection to GitLab instance.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self.get('/user')
            return response.success
        except Exception as e:
            logger.error(f'Connection test failed: {e}')
            return False

    def get_version(self) -> Optional[str]:
        """Get GitLab version.

        Returns:
            GitLab version string or None if unavailable
        """
        try:
            response = self.get('/version')
            if response.success and response.data:
                return response.data.get('version')
        except Exception as e:
            logger.warning(f'Could not retrieve GitLab version: {e}')

        return None

    def close(self):
        """Close the client session."""
        self.session.close()
        logger.info('GitLab client session closed')

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class GitLabClientFactory:
    """Factory for creating GitLab API clients."""

    @staticmethod
    def create_client(config: GitLabInstanceConfig) -> GitLabClient:
        """Create GitLab client from configuration.

        Args:
            config: GitLab instance configuration

        Returns:
            Configured GitLab client

        Raises:
            GitLabAuthenticationError: If authentication configuration is invalid
        """
        if not config.token and not config.oauth_token:
            raise GitLabAuthenticationError(
                'Either token or oauth_token must be provided'
            )

        return GitLabClient(config)
