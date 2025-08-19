# Configuration Reference

This document provides a comprehensive reference for all configuration options available in the GitLab Migration Tool.

## Table of Contents

1. [Configuration File Structure](#configuration-file-structure)
2. [Source and Destination Settings](#source-and-destination-settings)
3. [Migration Settings](#migration-settings)
4. [Performance Tuning](#performance-tuning)
5. [Logging Configuration](#logging-configuration)
6. [Git Settings](#git-settings)
7. [Environment Variables](#environment-variables)
8. [Configuration Examples](#configuration-examples)

## Configuration File Structure

The configuration file uses YAML format and consists of several main sections:

```yaml
source: # Source GitLab instance settings
destination: # Destination GitLab instance settings
migration: # Migration behavior settings
logging: # Logging configuration
git: # Git-specific settings
```

## Source and Destination Settings

Both `source` and `destination` sections support the same configuration options:

### Required Settings

| Setting | Type   | Description           | Example                      |
| ------- | ------ | --------------------- | ---------------------------- |
| `url`   | string | GitLab instance URL   | `https://gitlab.example.com` |
| `token` | string | Personal Access Token | `glpat-xxxxxxxxxxxxxxxxxxxx` |

### Optional Settings

| Setting                 | Type    | Default | Description                |
| ----------------------- | ------- | ------- | -------------------------- |
| `api_version`           | string  | `v4`    | GitLab API version         |
| `timeout`               | integer | `60`    | Request timeout in seconds |
| `rate_limit_per_second` | float   | `10.0`  | API rate limiting          |

### Example

```yaml
source:
  url: https://gitlab-source.example.com
  token: glpat-source-token-here
  api_version: v4
  timeout: 60
  rate_limit_per_second: 10.0

destination:
  url: https://gitlab-dest.example.com
  token: glpat-dest-token-here
  api_version: v4
  timeout: 60
  rate_limit_per_second: 10.0
```

## Migration Settings

The `migration` section controls what gets migrated and how:

### Entity Selection

| Setting        | Type    | Default | Description                 |
| -------------- | ------- | ------- | --------------------------- |
| `users`        | boolean | `true`  | Enable user migration       |
| `groups`       | boolean | `true`  | Enable group migration      |
| `projects`     | boolean | `true`  | Enable project migration    |
| `repositories` | boolean | `true`  | Enable repository migration |

### General Settings

| Setting       | Type    | Default | Description                                    |
| ------------- | ------- | ------- | ---------------------------------------------- |
| `batch_size`  | integer | `5`     | Orchestrator batch size for splitting entities |
| `max_workers` | integer | `20`    | Maximum concurrent workers                     |
| `timeout`     | integer | `600`   | Migration timeout in seconds                   |
| `dry_run`     | boolean | `false` | Preview mode without making changes            |

### Concurrent Processing Settings

| Setting              | Type    | Default | Description                    |
| -------------------- | ------- | ------- | ------------------------------ |
| `user_batch_size`    | integer | `5`     | Concurrent users to process    |
| `group_batch_size`   | integer | `5`     | Concurrent groups to process   |
| `project_batch_size` | integer | `5`     | Concurrent projects to process |
| `member_batch_size`  | integer | `5`     | Concurrent members to process  |

### Example

```yaml
migration:
  # Entity selection
  users: true
  groups: true
  projects: true
  repositories: true

  # General settings
  batch_size: 5
  max_workers: 20
  timeout: 600
  dry_run: false

  # Concurrent processing
  user_batch_size: 5
  group_batch_size: 5
  project_batch_size: 5
  member_batch_size: 5
```

## Performance Tuning

### Batch Size Guidelines

The optimal batch sizes depend on your environment:

#### Small Instances (< 100 entities)

```yaml
migration:
  batch_size: 2
  max_workers: 5
  user_batch_size: 2
  group_batch_size: 2
  project_batch_size: 2
  member_batch_size: 3
```

#### Medium Instances (100-1000 entities)

```yaml
migration:
  batch_size: 5
  max_workers: 20
  user_batch_size: 5
  group_batch_size: 5
  project_batch_size: 5
  member_batch_size: 5
```

#### Large Instances (1000+ entities)

```yaml
migration:
  batch_size: 10
  max_workers: 50
  user_batch_size: 20
  group_batch_size: 10
  project_batch_size: 5
  member_batch_size: 30
```

### Rate Limiting

Adjust rate limits based on your GitLab instance capabilities:

#### Conservative (Shared/Limited Resources)

```yaml
source:
  rate_limit_per_second: 5.0
destination:
  rate_limit_per_second: 5.0
```

#### Moderate (Dedicated Instances)

```yaml
source:
  rate_limit_per_second: 10.0
destination:
  rate_limit_per_second: 10.0
```

#### Aggressive (High-Performance Instances)

```yaml
source:
  rate_limit_per_second: 50.0
destination:
  rate_limit_per_second: 50.0
```

## Logging Configuration

The `logging` section controls how migration activities are logged:

### Settings

| Setting  | Type   | Default         | Description                             |
| -------- | ------ | --------------- | --------------------------------------- |
| `level`  | string | `INFO`          | Log level (DEBUG, INFO, WARNING, ERROR) |
| `file`   | string | `migration.log` | Log file path                           |
| `format` | string | See below       | Log message format                      |

### Default Format

```yaml
logging:
  format: '{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}'
```

### Log Levels

- **DEBUG**: Detailed information for debugging
- **INFO**: General information about migration progress
- **WARNING**: Warning messages about potential issues
- **ERROR**: Error messages for failed operations

### Example

```yaml
logging:
  level: INFO
  file: migration.log
  format: '{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}'
```

## Git Settings

The `git` section configures Git repository operations:

### Settings

| Setting        | Type    | Default   | Description                              |
| -------------- | ------- | --------- | ---------------------------------------- |
| `temp_dir`     | string  | `/tmp/gm` | Temporary directory for Git operations   |
| `cleanup_temp` | boolean | `true`    | Clean up temporary files after migration |
| `lfs_enabled`  | boolean | `true`    | Enable Git LFS support                   |
| `timeout`      | integer | `3600`    | Git operation timeout in seconds         |

### Example

```yaml
git:
  temp_dir: /tmp/gitlab-migrate
  cleanup_temp: true
  lfs_enabled: true
  timeout: 3600
```

## Environment Variables

You can override configuration values using environment variables:

### GitLab Instance Settings

| Variable              | Description              | Example                     |
| --------------------- | ------------------------ | --------------------------- |
| `GITLAB_SOURCE_URL`   | Source GitLab URL        | `https://gitlab-source.com` |
| `GITLAB_SOURCE_TOKEN` | Source access token      | `glpat-xxxxxxxxxxxx`        |
| `GITLAB_DEST_URL`     | Destination GitLab URL   | `https://gitlab-dest.com`   |
| `GITLAB_DEST_TOKEN`   | Destination access token | `glpat-yyyyyyyyyyyy`        |

### Migration Settings

| Variable                | Description          | Example |
| ----------------------- | -------------------- | ------- |
| `MIGRATION_DRY_RUN`     | Enable dry run mode  | `true`  |
| `MIGRATION_BATCH_SIZE`  | Override batch size  | `10`    |
| `MIGRATION_MAX_WORKERS` | Override max workers | `30`    |

### Usage Example

```bash
export GITLAB_SOURCE_TOKEN="glpat-source-token"
export GITLAB_DEST_TOKEN="glpat-dest-token"
export MIGRATION_DRY_RUN="true"

gitlab-migrate migrate --config config.yaml
```

## Configuration Examples

### Complete Configuration

```yaml
source:
  url: https://gitlab-source.example.com
  token: glpat-source-token-here
  api_version: v4
  timeout: 60
  rate_limit_per_second: 10.0

destination:
  url: https://gitlab-dest.example.com
  token: glpat-dest-token-here
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
  lfs_enabled: true
  timeout: 3600
```

### Minimal Configuration

```yaml
source:
  url: https://gitlab-source.example.com
  token: glpat-source-token-here

destination:
  url: https://gitlab-dest.example.com
  token: glpat-dest-token-here

migration:
  users: true
  groups: true
  projects: true
  repositories: true
```

### High-Performance Configuration

```yaml
source:
  url: https://gitlab-source.example.com
  token: glpat-source-token-here
  rate_limit_per_second: 50.0

destination:
  url: https://gitlab-dest.example.com
  token: glpat-dest-token-here
  rate_limit_per_second: 50.0

migration:
  users: true
  groups: true
  projects: true
  repositories: true
  batch_size: 10
  max_workers: 50
  user_batch_size: 20
  group_batch_size: 10
  project_batch_size: 5
  member_batch_size: 30

logging:
  level: DEBUG
  file: migration-debug.log

git:
  temp_dir: /fast-storage/gitlab-migrate-temp
  cleanup_temp: true
```

### Conservative Configuration

```yaml
source:
  url: https://gitlab-source.example.com
  token: glpat-source-token-here
  timeout: 120
  rate_limit_per_second: 2.0

destination:
  url: https://gitlab-dest.example.com
  token: glpat-dest-token-here
  timeout: 120
  rate_limit_per_second: 2.0

migration:
  users: true
  groups: true
  projects: true
  repositories: true
  batch_size: 2
  max_workers: 3
  timeout: 1200
  user_batch_size: 2
  group_batch_size: 1
  project_batch_size: 1
  member_batch_size: 2

logging:
  level: INFO
  file: migration.log

git:
  temp_dir: /tmp/gm
  cleanup_temp: true
  timeout: 7200
```

## Configuration Validation

The tool validates your configuration before starting migration:

### Common Validation Errors

1. **Missing Required Fields**

   ```
   Error: Missing required field 'source.token'
   ```

2. **Invalid URL Format**

   ```
   Error: Invalid URL format in 'source.url'
   ```

3. **Invalid Token Format**

   ```
   Error: Token must start with 'glpat-'
   ```

4. **Invalid Batch Size**
   ```
   Error: batch_size must be greater than 0
   ```

### Validation Command

```bash
gitlab-migrate validate --config config.yaml
```

This command checks:

- Configuration file syntax
- Required fields presence
- Value ranges and formats
- GitLab instance connectivity
- Token permissions
