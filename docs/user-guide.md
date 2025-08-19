# GitLab Migration Tool - User Guide

This guide provides comprehensive instructions for using the GitLab Migration Tool to migrate users, groups, projects, and repositories between GitLab instances.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Migration Process](#migration-process)
5. [Validation](#validation)
6. [Best Practices](#best-practices)
7. [Common Scenarios](#common-scenarios)

## Prerequisites

Before using the GitLab Migration Tool, ensure you have:

- **Python 3.8+** installed on your system
- **Poetry** for dependency management
- **Git** installed and configured
- **Admin access** to both source and destination GitLab instances
- **Personal Access Tokens** with appropriate permissions for both instances

### Required Token Permissions

Your GitLab tokens must have the following scopes:

- `api` - Full API access
- `read_user` - Read user information
- `read_repository` - Read repository data
- `write_repository` - Write repository data (destination only)

## Installation

1. **Clone the repository:**

   ```bash
   git clone <repository-url>
   cd gitlab-migrate
   ```

2. **Install dependencies:**

   ```bash
   poetry install
   ```

3. **Activate the virtual environment:**

   ```bash
   poetry shell
   ```

4. **Verify installation:**
   ```bash
   gitlab-migrate --help
   ```

## Configuration

### Basic Configuration

Create a `config.yaml` file in your project root:

```yaml
source:
  url: https://gitlab-source.example.com
  token: glpat-xxxxxxxxxxxxxxxxxxxx
  api_version: v4
  timeout: 60
  rate_limit_per_second: 10.0

destination:
  url: https://gitlab-dest.example.com
  token: glpat-yyyyyyyyyyyyyyyyyyyy
  api_version: v4
  timeout: 60
  rate_limit_per_second: 10.0

migration:
  users: true
  groups: true
  projects: true
  repositories: true
  batch_size: 5
  max_workers: 20
  timeout: 600
  dry_run: false

  # Concurrent processing settings
  user_batch_size: 5
  group_batch_size: 5
  project_batch_size: 5
  member_batch_size: 5

logging:
  level: INFO
  file: migration.log
  format: '{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}'

git:
  temp_dir: /tmp/gm
  cleanup_temp: true
```

### Configuration Options Explained

#### Source/Destination Settings

- `url`: GitLab instance URL
- `token`: Personal Access Token
- `api_version`: GitLab API version (usually v4)
- `timeout`: Request timeout in seconds
- `rate_limit_per_second`: API rate limiting

#### Migration Settings

- `users`: Enable user migration
- `groups`: Enable group migration
- `projects`: Enable project migration
- `repositories`: Enable repository migration
- `batch_size`: Number of entities processed per batch
- `max_workers`: Maximum concurrent workers
- `dry_run`: Preview mode without making changes

#### Performance Tuning

- `user_batch_size`: Concurrent users to process
- `group_batch_size`: Concurrent groups to process
- `project_batch_size`: Concurrent projects to process
- `member_batch_size`: Concurrent members to process

## Migration Process

### Step 1: Initialize Configuration

```bash
gitlab-migrate init
```

This creates a template configuration file that you can customize.

### Step 2: Validate Configuration

```bash
gitlab-migrate validate --config config.yaml
```

This checks:

- GitLab instance connectivity
- Token permissions
- Configuration validity

### Step 3: Dry Run (Recommended)

```bash
gitlab-migrate migrate --config config.yaml --dry-run
```

This simulates the migration without making changes, allowing you to:

- Preview what will be migrated
- Identify potential issues
- Estimate migration time

### Step 4: Execute Migration

```bash
gitlab-migrate migrate --config config.yaml
```

The migration process follows this order:

1. **Users** - Create user accounts
2. **Groups** - Create groups and hierarchies
3. **Projects** - Create projects with metadata
4. **Repositories** - Clone and push Git repositories

### Step 5: Post-Migration Validation

```bash
gitlab-migrate validate --config config.yaml --post-migration
```

This verifies:

- All entities were migrated successfully
- Repository integrity
- Group memberships
- Project permissions

## Validation

### Pre-Migration Validation

Before starting migration, the tool validates:

- **Connectivity**: Can connect to both GitLab instances
- **Authentication**: Tokens are valid and have required permissions
- **Prerequisites**: All required dependencies are available

### During Migration

The tool provides real-time feedback:

- Progress indicators for each migration phase
- Success/failure status for each entity
- Detailed logging of all operations
- Error reporting with suggested fixes

### Post-Migration Validation

After migration, verify:

- **User Accounts**: All users created successfully
- **Group Structure**: Hierarchies preserved correctly
- **Project Data**: Metadata and settings transferred
- **Repository Content**: All branches, tags, and commits present

## Best Practices

### Before Migration

1. **Backup**: Create backups of both GitLab instances
2. **Test Environment**: Run migration on test instances first
3. **User Communication**: Notify users about the migration
4. **Maintenance Mode**: Consider enabling maintenance mode
5. **Resource Planning**: Ensure adequate disk space and bandwidth

### During Migration

1. **Monitor Progress**: Watch logs for errors or warnings
2. **Network Stability**: Ensure stable network connection
3. **Resource Usage**: Monitor CPU, memory, and disk usage
4. **Incremental Approach**: Consider migrating in phases

### After Migration

1. **Validation**: Run comprehensive validation checks
2. **User Testing**: Have users verify their data
3. **DNS Updates**: Update DNS records if needed
4. **Cleanup**: Remove temporary files and old tokens
5. **Documentation**: Update internal documentation

## Common Scenarios

### Scenario 1: Complete Instance Migration

Migrating everything from one GitLab instance to another:

```yaml
migration:
  users: true
  groups: true
  projects: true
  repositories: true
```

### Scenario 2: Selective Migration

Migrating only specific entity types:

```yaml
migration:
  users: true
  groups: true
  projects: false
  repositories: false
```

### Scenario 3: Large Instance Migration

For large instances with thousands of entities:

```yaml
migration:
  batch_size: 10
  max_workers: 50
  user_batch_size: 20
  group_batch_size: 10
  project_batch_size: 5
  member_batch_size: 30
```

### Scenario 4: Network-Constrained Migration

For slow or unreliable networks:

```yaml
source:
  timeout: 120
  rate_limit_per_second: 5.0
destination:
  timeout: 120
  rate_limit_per_second: 5.0

migration:
  batch_size: 2
  max_workers: 5
```

## Troubleshooting

### Common Issues

1. **Authentication Errors**

   - Verify token permissions
   - Check token expiration
   - Ensure admin access

2. **Network Timeouts**

   - Increase timeout values
   - Reduce batch sizes
   - Check network connectivity

3. **Rate Limiting**

   - Reduce rate_limit_per_second
   - Increase delays between requests
   - Contact GitLab admin for rate limit increases

4. **Disk Space Issues**
   - Monitor temp directory usage
   - Enable cleanup_temp option
   - Use faster storage for temp directory

### Getting Help

- Check the [Troubleshooting Guide](troubleshooting.md)
- Review migration logs for detailed error messages
- Consult the [API Documentation](api.md) for technical details
- Open an issue on the project repository

## Next Steps

After successful migration:

1. Update user documentation
2. Configure CI/CD pipelines
3. Set up monitoring and backups
4. Train users on any differences
5. Decommission old instance (after verification period)
