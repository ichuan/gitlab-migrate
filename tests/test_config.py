"""Tests for configuration management."""

import pytest
import tempfile
import os
from pathlib import Path

from src.gitlab_migrate.config.config import Config, GitLabInstanceConfig


class TestGitLabInstanceConfig:
    """Test GitLab instance configuration."""

    def test_valid_config(self):
        """Test valid configuration creation."""
        config = GitLabInstanceConfig(
            url='https://gitlab.example.com',
            token='test-token',
            api_version='v4',
            timeout=30,
            rate_limit_per_second=10,
        )

        assert config.url == 'https://gitlab.example.com'
        assert config.token == 'test-token'
        assert config.api_version == 'v4'
        assert config.timeout == 30
        assert config.rate_limit_per_second == 10

    def test_url_validation(self):
        """Test URL validation."""
        # Valid URLs should work
        valid_urls = [
            'https://gitlab.com',
            'https://gitlab.example.com',
            'http://localhost:8080',
        ]

        for url in valid_urls:
            config = GitLabInstanceConfig(url=url, token='test')
            assert config.url == url

    def test_missing_token(self):
        """Test that missing token raises validation error."""
        with pytest.raises(ValueError):
            GitLabInstanceConfig(url='https://gitlab.com')


class TestConfig:
    """Test main configuration class."""

    def test_config_creation(self):
        """Test configuration creation with all fields."""
        config = Config(
            source=GitLabInstanceConfig(
                url='https://source.gitlab.com', token='source-token'
            ),
            destination=GitLabInstanceConfig(
                url='https://dest.gitlab.com', token='dest-token'
            ),
        )

        assert config.source.url == 'https://source.gitlab.com'
        assert config.destination.url == 'https://dest.gitlab.com'
        assert config.migration.users is True
        assert config.migration.groups is True
        assert config.migration.projects is True
        assert config.migration.repositories is True

    def test_config_from_dict(self):
        """Test configuration creation from dictionary."""
        config_dict = {
            'source': {'url': 'https://source.gitlab.com', 'token': 'source-token'},
            'destination': {'url': 'https://dest.gitlab.com', 'token': 'dest-token'},
            'migration': {'users': False, 'batch_size': 25},
        }

        config = Config(**config_dict)
        assert config.source.url == 'https://source.gitlab.com'
        assert config.destination.url == 'https://dest.gitlab.com'
        assert config.migration.users is False
        assert config.migration.batch_size == 25

    def test_config_from_file(self):
        """Test configuration loading from YAML file."""
        config_content = """
source:
  url: https://source.gitlab.com
  token: source-token

destination:
  url: https://dest.gitlab.com
  token: dest-token

migration:
  users: true
  groups: false
  batch_size: 100
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            f.flush()

            try:
                config = Config.from_file(f.name)
                assert config.source.url == 'https://source.gitlab.com'
                assert config.destination.url == 'https://dest.gitlab.com'
                assert config.migration.users is True
                assert config.migration.groups is False
                assert config.migration.batch_size == 100
            finally:
                os.unlink(f.name)

    def test_config_from_env(self):
        """Test configuration loading from environment variables."""
        env_vars = {
            'GITLAB_SOURCE_URL': 'https://source.gitlab.com',
            'GITLAB_SOURCE_TOKEN': 'source-token',
            'GITLAB_DEST_URL': 'https://dest.gitlab.com',
            'GITLAB_DEST_TOKEN': 'dest-token',
            'GITLAB_MIGRATE_USERS': 'false',
            'GITLAB_BATCH_SIZE': '75',
        }

        # Set environment variables
        for key, value in env_vars.items():
            os.environ[key] = value

        try:
            config = Config.from_env()
            assert config.source.url == 'https://source.gitlab.com'
            assert config.destination.url == 'https://dest.gitlab.com'
            # Note: Environment loading would need to be implemented in the actual Config class
        finally:
            # Clean up environment variables
            for key in env_vars:
                os.environ.pop(key, None)

    def test_invalid_config_file(self):
        """Test handling of invalid configuration file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('invalid: yaml: content:')
            f.flush()

            try:
                with pytest.raises(Exception):  # Should raise YAML parsing error
                    Config.from_file(f.name)
            finally:
                os.unlink(f.name)

    def test_missing_config_file(self):
        """Test handling of missing configuration file."""
        with pytest.raises(FileNotFoundError):
            Config.from_file('/nonexistent/config.yaml')
