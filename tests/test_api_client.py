"""Tests for GitLab API client."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import requests
import aiohttp

from src.gitlab_migrate.api.client import GitLabClient, GitLabClientFactory, APIResponse
from src.gitlab_migrate.api.exceptions import (
    GitLabAPIError,
    GitLabAuthenticationError,
    GitLabRateLimitError,
    GitLabNotFoundError,
)
from src.gitlab_migrate.config.config import GitLabInstanceConfig


class TestAPIResponse:
    """Test API response model."""

    def test_api_response_creation(self):
        """Test API response creation."""
        response = APIResponse(
            status_code=200,
            data={'id': 1, 'name': 'test'},
            headers={'Content-Type': 'application/json'},
            success=True,
        )

        assert response.status_code == 200
        assert response.data == {'id': 1, 'name': 'test'}
        assert response.headers == {'Content-Type': 'application/json'}
        assert response.success is True


class TestGitLabClient:
    """Test GitLab API client."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = GitLabInstanceConfig(
            url='https://gitlab.example.com',
            token='test-token',
            api_version='v4',
            timeout=30,
            rate_limit_per_second=10,
        )

    def test_client_initialization(self):
        """Test client initialization."""
        client = GitLabClient(self.config)

        assert client.config == self.config
        assert client.base_url == 'https://gitlab.example.com/api/v4'
        assert 'Private-Token' in client.session.headers
        assert client.session.headers['Private-Token'] == 'test-token'

    def test_client_initialization_oauth(self):
        """Test client initialization with OAuth token."""
        config = GitLabInstanceConfig(
            url='https://gitlab.example.com',
            oauth_token='oauth-token',
        )
        client = GitLabClient(config)

        assert 'Authorization' in client.session.headers
        assert client.session.headers['Authorization'] == 'Bearer oauth-token'

    def test_client_initialization_no_auth(self):
        """Test client initialization without authentication."""
        config = GitLabInstanceConfig(url='https://gitlab.example.com')

        with pytest.raises(GitLabAuthenticationError):
            GitLabClient(config)

    def test_build_url(self):
        """Test URL building."""
        client = GitLabClient(self.config)

        # Test various endpoint formats
        assert client._build_url('/users') == 'https://gitlab.example.com/api/v4/users'
        assert client._build_url('users') == 'https://gitlab.example.com/api/v4/users'
        assert (
            client._build_url('/projects/1/issues')
            == 'https://gitlab.example.com/api/v4/projects/1/issues'
        )

    @patch('requests.Session.get')
    def test_get_request_success(self, mock_get):
        """Test successful GET request."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'id': 1, 'name': 'test'}
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_response.content = b'{"id": 1, "name": "test"}'
        mock_get.return_value = mock_response

        client = GitLabClient(self.config)
        response = client.get('/users')

        assert response.success is True
        assert response.status_code == 200
        assert response.data == {'id': 1, 'name': 'test'}
        mock_get.assert_called_once()

    @patch('requests.Session.get')
    def test_get_request_404(self, mock_get):
        """Test GET request with 404 error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.headers = {}
        mock_get.return_value = mock_response

        client = GitLabClient(self.config)

        with pytest.raises(GitLabNotFoundError):
            client.get('/nonexistent')

    @patch('requests.Session.get')
    def test_get_request_401(self, mock_get):
        """Test GET request with authentication error."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.headers = {}
        mock_get.return_value = mock_response

        client = GitLabClient(self.config)

        with pytest.raises(GitLabAuthenticationError):
            client.get('/users')

    @patch('requests.Session.get')
    def test_get_request_429(self, mock_get):
        """Test GET request with rate limit error."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {'Retry-After': '60'}
        mock_get.return_value = mock_response

        client = GitLabClient(self.config)

        with pytest.raises(GitLabRateLimitError) as exc_info:
            client.get('/users')

        assert exc_info.value.retry_after == 60

    @patch('requests.Session.post')
    def test_post_request_success(self, mock_post):
        """Test successful POST request."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {'id': 2, 'name': 'created'}
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_response.content = b'{"id": 2, "name": "created"}'
        mock_post.return_value = mock_response

        client = GitLabClient(self.config)
        response = client.post('/users', data={'name': 'test'})

        assert response.success is True
        assert response.status_code == 201
        assert response.data == {'id': 2, 'name': 'created'}
        mock_post.assert_called_once()

    @patch('requests.Session.get')
    def test_get_paginated(self, mock_get):
        """Test paginated GET request."""
        # Mock multiple pages of responses
        responses = [
            # Page 1
            Mock(
                status_code=200,
                json=lambda: [{'id': 1}, {'id': 2}],
                headers={'X-Total-Pages': '2', 'Content-Type': 'application/json'},
                content=b'[{"id": 1}, {"id": 2}]',
            ),
            # Page 2
            Mock(
                status_code=200,
                json=lambda: [{'id': 3}, {'id': 4}],
                headers={'X-Total-Pages': '2', 'Content-Type': 'application/json'},
                content=b'[{"id": 3}, {"id": 4}]',
            ),
        ]

        mock_get.side_effect = responses

        client = GitLabClient(self.config)
        items = client.get_paginated('/users', per_page=2)

        assert len(items) == 4
        assert items == [{'id': 1}, {'id': 2}, {'id': 3}, {'id': 4}]
        assert mock_get.call_count == 2

    @patch('requests.Session.get')
    def test_test_connection_success(self, mock_get):
        """Test successful connection test."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'id': 1, 'username': 'test'}
        mock_response.headers = {}
        mock_response.content = b'{"id": 1, "username": "test"}'
        mock_get.return_value = mock_response

        client = GitLabClient(self.config)
        result = client.test_connection()

        assert result is True
        mock_get.assert_called_once_with(
            'https://gitlab.example.com/api/v4/user', params=None
        )

    @patch('requests.Session.get')
    def test_test_connection_failure(self, mock_get):
        """Test failed connection test."""
        mock_get.side_effect = requests.RequestException('Connection failed')

        client = GitLabClient(self.config)
        result = client.test_connection()

        assert result is False

    @patch('requests.Session.get')
    def test_get_version(self, mock_get):
        """Test GitLab version retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'version': '15.0.0'}
        mock_response.headers = {}
        mock_response.content = b'{"version": "15.0.0"}'
        mock_get.return_value = mock_response

        client = GitLabClient(self.config)
        version = client.get_version()

        assert version == '15.0.0'

    def test_context_manager(self):
        """Test client as context manager."""
        with patch.object(GitLabClient, 'close') as mock_close:
            with GitLabClient(self.config) as client:
                assert isinstance(client, GitLabClient)
            mock_close.assert_called_once()


class TestGitLabClientFactory:
    """Test GitLab client factory."""

    def test_create_client_with_token(self):
        """Test client creation with token."""
        config = GitLabInstanceConfig(
            url='https://gitlab.example.com', token='test-token'
        )

        client = GitLabClientFactory.create_client(config)

        assert isinstance(client, GitLabClient)
        assert client.config == config

    def test_create_client_with_oauth(self):
        """Test client creation with OAuth token."""
        config = GitLabInstanceConfig(
            url='https://gitlab.example.com', oauth_token='oauth-token'
        )

        client = GitLabClientFactory.create_client(config)

        assert isinstance(client, GitLabClient)
        assert client.config == config

    def test_create_client_no_auth(self):
        """Test client creation without authentication."""
        config = GitLabInstanceConfig(url='https://gitlab.example.com')

        with pytest.raises(GitLabAuthenticationError):
            GitLabClientFactory.create_client(config)


class TestAsyncMethods:
    """Test asynchronous API methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = GitLabInstanceConfig(
            url='https://gitlab.example.com',
            token='test-token',
        )

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.request')
    async def test_get_async_success(self, mock_request):
        """Test successful async GET request."""
        # Mock aiohttp response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_response.json = MagicMock(return_value={'id': 1, 'name': 'test'})
        mock_response.content_length = 100
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = None

        mock_session = MagicMock()
        mock_session.request.return_value = mock_response
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        with patch('aiohttp.ClientSession', return_value=mock_session):
            client = GitLabClient(self.config)
            response = await client.get_async('/users')

            assert response.success is True
            assert response.status_code == 200

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.request')
    async def test_get_async_404(self, mock_request):
        """Test async GET request with 404 error."""
        mock_response = MagicMock()
        mock_response.status = 404
        mock_response.headers = {}
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = None

        mock_session = MagicMock()
        mock_session.request.return_value = mock_response
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        with patch('aiohttp.ClientSession', return_value=mock_session):
            client = GitLabClient(self.config)

            with pytest.raises(GitLabNotFoundError):
                await client.get_async('/nonexistent')
