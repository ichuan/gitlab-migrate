"""Configuration management for GitLab Migration Tool."""

from typing import Optional, Dict, Any
from pathlib import Path
import os

from pydantic import BaseModel, Field, validator
import yaml
from dotenv import load_dotenv


class GitLabInstanceConfig(BaseModel):
    """Configuration for a GitLab instance."""

    url: str = Field(..., description='GitLab instance URL')
    token: Optional[str] = Field(default=None, description='Personal access token')
    oauth_token: Optional[str] = Field(default=None, description='OAuth access token')
    api_version: str = Field(default='v4', description='GitLab API version')
    timeout: int = Field(default=30, description='Request timeout in seconds')
    rate_limit_per_second: float = Field(
        default=10.0, description='API requests per second limit'
    )

    @validator('url')
    def validate_url(cls, v):
        """Validate GitLab URL format."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v.rstrip('/')

    @validator('token', 'oauth_token')
    def validate_auth_token(cls, v, values):
        """Validate that at least one authentication method is provided."""
        # This will be called for both token and oauth_token fields
        # We need to check if at least one is provided after both are processed
        return v

    @validator('oauth_token')
    def validate_auth_complete(cls, v, values):
        """Ensure at least one authentication method is provided."""
        token = values.get('token')
        if not token and not v:
            raise ValueError('Either token or oauth_token must be provided')
        return v

    @validator('rate_limit_per_second')
    def validate_rate_limit(cls, v):
        """Validate rate limit is positive."""
        if v <= 0:
            raise ValueError('Rate limit must be positive')
        return v


class MigrationConfig(BaseModel):
    """Migration-specific configuration."""

    users: bool = Field(default=True, description='Migrate users')
    groups: bool = Field(default=True, description='Migrate groups')
    projects: bool = Field(default=True, description='Migrate projects')
    repositories: bool = Field(default=True, description='Migrate repositories')

    batch_size: int = Field(default=50, description='Batch size for processing')
    max_workers: int = Field(default=5, description='Maximum concurrent workers')
    timeout: int = Field(default=300, description='Operation timeout in seconds')

    dry_run: bool = Field(default=False, description='Perform dry run without changes')

    @validator('batch_size')
    def validate_batch_size(cls, v):
        """Validate batch size is positive."""
        if v <= 0:
            raise ValueError('Batch size must be positive')
        return v

    @validator('max_workers')
    def validate_max_workers(cls, v):
        """Validate max workers is positive."""
        if v <= 0:
            raise ValueError('Max workers must be positive')
        return v


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(default='INFO', description='Log level')
    file: Optional[str] = Field(default=None, description='Log file path')
    format: str = Field(
        default='{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}',
        description='Log format',
    )

    @validator('level')
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of: {valid_levels}')
        return v.upper()


class Config(BaseModel):
    """Main configuration class for GitLab Migration Tool."""

    source: GitLabInstanceConfig = Field(..., description='Source GitLab instance')
    destination: GitLabInstanceConfig = Field(
        ..., description='Destination GitLab instance'
    )
    migration: MigrationConfig = Field(
        default_factory=MigrationConfig, description='Migration settings'
    )
    logging: LoggingConfig = Field(
        default_factory=LoggingConfig, description='Logging settings'
    )

    class Config:
        """Pydantic configuration."""

        extra = 'forbid'  # Don't allow extra fields

    @classmethod
    def from_file(cls, config_path: str) -> 'Config':
        """Load configuration from YAML file."""
        config_file = Path(config_path)

        if not config_file.exists():
            raise FileNotFoundError(f'Configuration file not found: {config_path}')

        with open(config_file, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)

        return cls(**config_data)

    @classmethod
    def from_env(cls) -> 'Config':
        """Load configuration from environment variables."""
        # Load .env file if it exists
        load_dotenv()

        config_data = {
            'source': {
                'url': os.getenv('SOURCE_GITLAB_URL'),
                'token': os.getenv('SOURCE_GITLAB_TOKEN'),
            },
            'destination': {
                'url': os.getenv('DEST_GITLAB_URL'),
                'token': os.getenv('DEST_GITLAB_TOKEN'),
            },
            'migration': {
                'batch_size': int(os.getenv('MIGRATION_BATCH_SIZE', 50)),
                'max_workers': int(os.getenv('MIGRATION_MAX_WORKERS', 5)),
                'timeout': int(os.getenv('MIGRATION_TIMEOUT', 300)),
            },
            'logging': {
                'level': os.getenv('LOG_LEVEL', 'INFO'),
                'file': os.getenv('LOG_FILE'),
            },
        }

        # Remove None values
        config_data = cls._remove_none_values(config_data)

        return cls(**config_data)

    @staticmethod
    def _remove_none_values(data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively remove None values from dictionary."""
        if isinstance(data, dict):
            return {
                k: Config._remove_none_values(v)
                for k, v in data.items()
                if v is not None
            }
        return data

    def to_file(self, config_path: str) -> None:
        """Save configuration to YAML file."""
        config_file = Path(config_path)
        config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(
                self.dict(), f, default_flow_style=False, indent=2, sort_keys=False
            )

    def validate_connectivity(self) -> bool:
        """Validate that both GitLab instances are accessible."""
        # TODO: Implement connectivity validation
        return True

    def create_template(self, output_path: str) -> None:
        """Create a configuration template file."""
        template_config = {
            'source': {
                'url': 'https://gitlab-source.example.com',
                'token': 'your-source-personal-access-token',
                'api_version': 'v4',
                'timeout': 30,
            },
            'destination': {
                'url': 'https://gitlab-dest.example.com',
                'token': 'your-destination-personal-access-token',
                'api_version': 'v4',
                'timeout': 30,
            },
            'migration': {
                'users': True,
                'groups': True,
                'projects': True,
                'repositories': True,
                'batch_size': 50,
                'max_workers': 5,
                'timeout': 300,
                'dry_run': False,
            },
            'logging': {
                'level': 'INFO',
                'file': 'migration.log',
                'format': '{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}',
            },
        }

        config_file = Path(output_path)
        config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(
                template_config, f, default_flow_style=False, indent=2, sort_keys=False
            )
