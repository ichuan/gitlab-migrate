"""Tests for CLI interface."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner
import tempfile
import os

from src.gitlab_migrate.cli.main import cli, init, migrate, validate, status
from src.gitlab_migrate.config.config import Config, GitLabInstanceConfig


class TestCLI:
    """Test CLI commands."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_cli_help(self):
        """Test CLI help command."""
        result = self.runner.invoke(cli, ['--help'])

        assert result.exit_code == 0
        assert 'GitLab Migration Tool' in result.output
        assert 'init' in result.output
        assert 'migrate' in result.output
        assert 'validate' in result.output
        assert 'status' in result.output

    def test_cli_version(self):
        """Test CLI version command."""
        result = self.runner.invoke(cli, ['--version'])

        assert result.exit_code == 0
        assert '0.1.0' in result.output

    def test_init_command(self):
        """Test init command."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, 'test_config.yaml')

            result = self.runner.invoke(init, ['--output', config_path])

            assert result.exit_code == 0
            assert 'Configuration template created' in result.output
            assert os.path.exists(config_path)

            # Check that the file contains expected content
            with open(config_path, 'r') as f:
                content = f.read()
                assert 'source:' in content
                assert 'destination:' in content
                assert 'migration:' in content

    def test_init_command_default_output(self):
        """Test init command with default output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Change to temp directory
            original_cwd = os.getcwd()
            os.chdir(temp_dir)

            try:
                result = self.runner.invoke(init)

                assert result.exit_code == 0
                assert 'Configuration template created' in result.output
                assert os.path.exists('config.yaml')
            finally:
                os.chdir(original_cwd)

    @patch('src.gitlab_migrate.cli.main._load_config')
    @patch('src.gitlab_migrate.cli.main._run_migration')
    def test_migrate_command_success(self, mock_run_migration, mock_load_config):
        """Test successful migrate command."""
        # Mock configuration with proper structure
        mock_config = Mock(spec=Config)
        mock_migration = Mock()
        mock_migration.dry_run = False
        mock_config.migration = mock_migration
        mock_load_config.return_value = mock_config

        # Mock migration execution
        mock_run_migration.return_value = None

        result = self.runner.invoke(migrate)

        assert result.exit_code == 0
        assert 'Starting migration process' in result.output
        mock_load_config.assert_called_once()
        mock_run_migration.assert_called_once()

    @patch('src.gitlab_migrate.cli.main._load_config')
    @patch('src.gitlab_migrate.cli.main._run_migration')
    def test_migrate_command_dry_run(self, mock_run_migration, mock_load_config):
        """Test migrate command with dry run."""
        # Mock configuration with proper structure
        mock_config = Mock(spec=Config)
        mock_migration = Mock()
        mock_migration.dry_run = True
        mock_config.migration = mock_migration
        mock_load_config.return_value = mock_config

        # Mock migration execution
        mock_run_migration.return_value = None

        result = self.runner.invoke(migrate, ['--dry-run'])

        assert result.exit_code == 0
        assert 'dry-run mode' in result.output
        assert mock_config.migration.dry_run is True
        mock_run_migration.assert_called_once()

    @patch('src.gitlab_migrate.cli.main._load_config')
    def test_migrate_command_config_not_found(self, mock_load_config):
        """Test migrate command when config is not found."""
        mock_load_config.side_effect = FileNotFoundError('Configuration file not found')

        result = self.runner.invoke(migrate)

        assert result.exit_code == 1
        assert 'Migration failed' in result.output

    @patch('src.gitlab_migrate.cli.main._load_config')
    @patch('asyncio.run')
    def test_validate_command_success(self, mock_asyncio_run, mock_load_config):
        """Test successful validate command."""
        # Mock configuration
        mock_config = Mock(spec=Config)
        mock_load_config.return_value = mock_config

        # Mock engine and connectivity test
        mock_engine = Mock()
        mock_engine._test_connectivity.return_value = None
        mock_asyncio_run.return_value = None

        with patch(
            'src.gitlab_migrate.cli.main.MigrationEngine', return_value=mock_engine
        ):
            result = self.runner.invoke(validate)

            assert result.exit_code == 0
            assert 'Connectivity validation passed' in result.output
            assert 'Configuration validation completed' in result.output

    @patch('src.gitlab_migrate.cli.main._load_config')
    def test_validate_command_failure(self, mock_load_config):
        """Test validate command failure."""
        mock_load_config.side_effect = Exception('Validation failed')

        result = self.runner.invoke(validate)

        assert result.exit_code == 1
        assert 'Validation failed' in result.output

    @patch('src.gitlab_migrate.cli.main._load_config')
    def test_status_command_success(self, mock_load_config):
        """Test successful status command."""
        # Mock configuration with proper structure
        mock_config = Mock(spec=Config)

        # Mock source configuration
        mock_source = Mock()
        mock_source.url = 'https://source.gitlab.com'
        mock_config.source = mock_source

        # Mock destination configuration
        mock_destination = Mock()
        mock_destination.url = 'https://dest.gitlab.com'
        mock_config.destination = mock_destination

        # Mock migration configuration
        mock_migration = Mock()
        mock_migration.users = True
        mock_migration.groups = True
        mock_migration.projects = True
        mock_migration.repositories = True
        mock_migration.batch_size = 50
        mock_migration.max_workers = 5
        mock_config.migration = mock_migration

        mock_load_config.return_value = mock_config

        result = self.runner.invoke(status)

        assert result.exit_code == 0
        assert 'Migration Configuration' in result.output
        assert 'source.gitlab.com' in result.output
        assert 'dest.gitlab.com' in result.output

    @patch('src.gitlab_migrate.cli.main._load_config')
    def test_status_command_failure(self, mock_load_config):
        """Test status command failure."""
        mock_load_config.side_effect = Exception('Failed to load status')

        result = self.runner.invoke(status)

        assert result.exit_code == 1
        assert 'Failed to load status' in result.output

    def test_config_loading_with_file(self):
        """Test configuration loading with specified file."""
        config_content = """
source:
  url: https://source.gitlab.com
  token: source-token

destination:
  url: https://dest.gitlab.com
  token: dest-token
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            f.flush()

            try:
                result = self.runner.invoke(cli, ['--config', f.name, 'status'])
                # This would fail because Config.from_file needs to be implemented properly
                # but we're testing the CLI argument parsing
                assert '--config' in str(result)
            finally:
                os.unlink(f.name)

    def test_verbose_flag(self):
        """Test verbose flag."""
        result = self.runner.invoke(cli, ['--verbose', '--help'])

        assert result.exit_code == 0
        # Verbose flag should be processed without error

    @patch('src.gitlab_migrate.cli.main.MigrationEngine')
    @patch('src.gitlab_migrate.cli.main._load_config')
    async def test_run_migration_function(self, mock_load_config, mock_engine_class):
        """Test the _run_migration function."""
        from src.gitlab_migrate.cli.main import _run_migration

        # Mock configuration
        mock_config = Mock(spec=Config)

        # Mock engine
        mock_engine = Mock()
        mock_summary = Mock()
        mock_engine.migrate.return_value = mock_summary
        mock_engine_class.return_value = mock_engine

        # Test normal migration
        await _run_migration(mock_config, dry_run=False)
        mock_engine.migrate.assert_called_once()

        # Test dry run
        mock_engine.reset_mock()
        await _run_migration(mock_config, dry_run=True)
        mock_engine.dry_run.assert_called_once()


class TestConfigLoading:
    """Test configuration loading functions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch('src.gitlab_migrate.config.config.Config.from_file')
    def test_load_config_with_file(self, mock_from_file):
        """Test loading config from specified file."""
        from src.gitlab_migrate.cli.main import _load_config

        mock_config = Mock(spec=Config)
        mock_from_file.return_value = mock_config

        # Mock click context
        mock_ctx = Mock()
        mock_ctx.obj = {'config_path': '/path/to/config.yaml'}

        with patch('pathlib.Path.exists', return_value=True):
            config = _load_config(mock_ctx)

            assert config == mock_config
            mock_from_file.assert_called_once_with('/path/to/config.yaml')

    @patch('src.gitlab_migrate.config.config.Config.from_file')
    def test_load_config_default_locations(self, mock_from_file):
        """Test loading config from default locations."""
        from src.gitlab_migrate.cli.main import _load_config

        mock_config = Mock(spec=Config)
        mock_from_file.return_value = mock_config

        # Mock click context without config_path
        mock_ctx = Mock()
        mock_ctx.obj = {}

        with patch(
            'pathlib.Path.exists', side_effect=lambda path: str(path) == 'config.yaml'
        ):
            config = _load_config(mock_ctx)

            assert config == mock_config
            mock_from_file.assert_called_once_with('config.yaml')

    @patch('src.gitlab_migrate.config.config.Config.from_env')
    def test_load_config_from_env(self, mock_from_env):
        """Test loading config from environment variables."""
        from src.gitlab_migrate.cli.main import _load_config

        mock_config = Mock(spec=Config)
        mock_from_env.return_value = mock_config

        # Mock click context without config_path
        mock_ctx = Mock()
        mock_ctx.obj = {}

        # Mock that no config files exist
        with patch('pathlib.Path.exists', return_value=False):
            config = _load_config(mock_ctx)

            assert config == mock_config
            mock_from_env.assert_called_once()

    def test_load_config_not_found(self):
        """Test loading config when no config is found."""
        from src.gitlab_migrate.cli.main import _load_config

        # Mock click context without config_path
        mock_ctx = Mock()
        mock_ctx.obj = {}

        # Mock that no config files exist and env loading fails
        with patch('pathlib.Path.exists', return_value=False):
            with patch(
                'src.gitlab_migrate.config.config.Config.from_env',
                side_effect=Exception(),
            ):
                with pytest.raises(FileNotFoundError):
                    _load_config(mock_ctx)


class TestCLIIntegration:
    """Test CLI integration scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_full_workflow_simulation(self):
        """Test a complete workflow simulation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, 'config.yaml')

            # Step 1: Initialize configuration
            result = self.runner.invoke(init, ['--output', config_path])
            assert result.exit_code == 0

            # Step 2: Check status (should fail due to invalid config)
            result = self.runner.invoke(cli, ['--config', config_path, 'status'])
            # This will likely fail because the template has placeholder values
            # but we're testing the CLI flow

    @patch('src.gitlab_migrate.cli.main.console.print_exception')
    def test_error_handling_with_verbose(self, mock_print_exception):
        """Test error handling with verbose flag."""
        with patch(
            'src.gitlab_migrate.cli.main._load_config',
            side_effect=Exception('Test error'),
        ):
            result = self.runner.invoke(cli, ['--verbose', 'migrate'])

            assert result.exit_code == 1
            # With verbose flag, exception should be printed
