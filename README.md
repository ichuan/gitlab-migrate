# GitLab Migration Tool

A high-performance, async-powered tool for migrating users, repositories, groups, and projects from one GitLab instance to another using API-based migration approaches with concurrent processing capabilities.

## Features

- **User Management**: Extract users from source instance and create them on destination
- **Group Migration**: Preserve group hierarchies and permissions
- **Project Migration**: Complete project data transfer with metadata preservation
- **Repository Migration**: Full Git history preservation with all branches and tags
- **Async Processing**: High-performance concurrent operations for faster migrations
- **Rate Limiting**: Built-in rate limiting to respect GitLab API constraints
- **Comprehensive Validation**: Pre-migration validation and post-migration verification

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd gitlab-migrate

# Install dependencies
poetry install

# Activate virtual environment
poetry shell
```

## Quick Start

```bash
# Initialize configuration
gitlab-migrate init

# Run migration with async processing
gitlab-migrate migrate --config config.yaml

# Validate migration results
gitlab-migrate validate --config config.yaml

# Monitor progress with detailed logging
gitlab-migrate migrate --config config.yaml --log-level INFO
```

For detailed setup instructions, configuration options, and troubleshooting, see the [User Guide](docs/user-guide.md).

## Configuration

Create a `config.yaml` file with your GitLab instance details:

```yaml
source:
  url: 'https://gitlab-source.example.com'
  token: 'your-source-token'

destination:
  url: 'https://gitlab-dest.example.com'
  token: 'your-destination-token'

migration:
  users: true
  groups: true
  projects: true
  repositories: true
```

## Documentation

- [User Guide](docs/user-guide.md) - Complete installation, configuration, and usage instructions
- [Configuration Reference](docs/configuration.md) - Detailed configuration options and performance tuning
- [API Documentation](docs/api.md) - Technical architecture and API reference
- [Troubleshooting](docs/troubleshooting.md) - Common issues, solutions, and debugging tips

## Development

```bash
# Run tests
poetry run pytest

# Format code
poetry run black src/

# Lint code
poetry run flake8 src/

# Type checking
poetry run mypy src/
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.
