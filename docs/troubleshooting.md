# Troubleshooting Guide

This guide helps you diagnose and resolve common issues when using the GitLab Migration Tool.

## Table of Contents

1. [Common Issues](#common-issues)
2. [Authentication Problems](#authentication-problems)
3. [Network and Connectivity Issues](#network-and-connectivity-issues)
4. [Performance Issues](#performance-issues)
5. [Migration Failures](#migration-failures)
6. [Configuration Problems](#configuration-problems)
7. [Git Repository Issues](#git-repository-issues)
8. [Debugging Tips](#debugging-tips)
9. [Getting Help](#getting-help)

## Common Issues

### Issue: "Command not found: gitlab-migrate"

**Symptoms:**

```bash
$ gitlab-migrate --help
bash: gitlab-migrate: command not found
```

**Solutions:**

1. **Activate virtual environment:**

   ```bash
   poetry shell
   # or
   source .venv/bin/activate
   ```

2. **Install dependencies:**

   ```bash
   poetry install
   ```

3. **Use poetry run:**
   ```bash
   poetry run gitlab-migrate --help
   ```

### Issue: "Configuration file not found"

**Symptoms:**

```
Error: Configuration file 'config.yaml' not found
```

**Solutions:**

1. **Create configuration file:**

   ```bash
   gitlab-migrate init
   ```

2. **Specify correct path:**

   ```bash
   gitlab-migrate migrate --config /path/to/config.yaml
   ```

3. **Check current directory:**
   ```bash
   ls -la config.yaml
   ```

### Issue: "Invalid YAML syntax"

**Symptoms:**

```
Error: Invalid YAML syntax in configuration file
```

**Solutions:**

1. **Validate YAML syntax:**

   ```bash
   python -c "import yaml; yaml.safe_load(open('config.yaml'))"
   ```

2. **Check indentation:**

   - Use spaces, not tabs
   - Maintain consistent indentation (2 or 4 spaces)

3. **Validate online:**
   - Use online YAML validators
   - Check for special characters

## Authentication Problems

### Issue: "Authentication failed"

**Symptoms:**

```
GitLabAuthenticationError: Authentication failed
```

**Solutions:**

1. **Verify token format:**

   ```yaml
   source:
     token: glpat-xxxxxxxxxxxxxxxxxxxx # Must start with 'glpat-'
   ```

2. **Check token permissions:**

   - Ensure token has `api` scope
   - Verify token hasn't expired
   - Test token manually:
     ```bash
     curl -H "Private-Token: your-token" https://gitlab.example.com/api/v4/user
     ```

3. **Verify admin access:**
   - User migration requires admin privileges
   - Check user permissions in GitLab

### Issue: "Token expired"

**Symptoms:**

```
Error: Token has expired
```

**Solutions:**

1. **Generate new token:**

   - Go to GitLab → User Settings → Access Tokens
   - Create new token with required scopes
   - Update configuration file

2. **Set longer expiration:**
   - Choose longer expiration period
   - Consider using service account tokens

### Issue: "Insufficient permissions"

**Symptoms:**

```
Error: User does not have permission to create users
```

**Solutions:**

1. **Verify admin status:**

   ```bash
   curl -H "Private-Token: your-token" https://gitlab.example.com/api/v4/user
   ```

   Check `is_admin: true` in response

2. **Use admin account:**

   - Switch to GitLab administrator account
   - Generate token from admin account

3. **Check instance settings:**
   - Verify user creation is enabled
   - Check registration restrictions

## Network and Connectivity Issues

### Issue: "Connection timeout"

**Symptoms:**

```
Error: Request timeout after 60 seconds
```

**Solutions:**

1. **Increase timeout:**

   ```yaml
   source:
     timeout: 120
   destination:
     timeout: 120
   ```

2. **Check network connectivity:**

   ```bash
   curl -I https://gitlab.example.com
   ping gitlab.example.com
   ```

3. **Test GitLab API:**
   ```bash
   curl https://gitlab.example.com/api/v4/version
   ```

### Issue: "SSL certificate verification failed"

**Symptoms:**

```
Error: SSL certificate verification failed
```

**Solutions:**

1. **Update certificates:**

   ```bash
   # Ubuntu/Debian
   sudo apt-get update && sudo apt-get install ca-certificates

   # CentOS/RHEL
   sudo yum update ca-certificates
   ```

2. **For self-signed certificates:**

   ```python
   # Add to client configuration (not recommended for production)
   import ssl
   ssl._create_default_https_context = ssl._create_unverified_context
   ```

3. **Use proper certificates:**
   - Install valid SSL certificates on GitLab instance
   - Use Let's Encrypt for free certificates

### Issue: "Rate limit exceeded"

**Symptoms:**

```
GitLabRateLimitError: Rate limit exceeded. Retry after 60 seconds
```

**Solutions:**

1. **Reduce rate limits:**

   ```yaml
   source:
     rate_limit_per_second: 5.0
   destination:
     rate_limit_per_second: 5.0
   ```

2. **Increase GitLab rate limits:**

   - Contact GitLab administrator
   - Adjust rate limits in GitLab configuration

3. **Use smaller batch sizes:**
   ```yaml
   migration:
     batch_size: 2
     max_workers: 3
   ```

## Performance Issues

### Issue: "Migration is very slow"

**Symptoms:**

- Migration takes hours for small datasets
- Low CPU/network utilization

**Solutions:**

1. **Increase concurrency:**

   ```yaml
   migration:
     batch_size: 10
     max_workers: 50
     user_batch_size: 20
     group_batch_size: 10
     project_batch_size: 5
   ```

2. **Increase rate limits:**

   ```yaml
   source:
     rate_limit_per_second: 50.0
   destination:
     rate_limit_per_second: 50.0
   ```

3. **Use faster storage:**
   ```yaml
   git:
     temp_dir: /fast-ssd/gitlab-migrate-temp
   ```

### Issue: "High memory usage"

**Symptoms:**

- System runs out of memory
- Process killed by OOM killer

**Solutions:**

1. **Reduce batch sizes:**

   ```yaml
   migration:
     batch_size: 2
     user_batch_size: 2
     group_batch_size: 1
     project_batch_size: 1
   ```

2. **Enable cleanup:**

   ```yaml
   git:
     cleanup_temp: true
   ```

3. **Monitor memory usage:**
   ```bash
   htop
   # or
   watch -n 1 'ps aux | grep gitlab-migrate'
   ```

### Issue: "Disk space full"

**Symptoms:**

```
Error: No space left on device
```

**Solutions:**

1. **Check disk space:**

   ```bash
   df -h
   du -sh /tmp/gm
   ```

2. **Use different temp directory:**

   ```yaml
   git:
     temp_dir: /large-disk/gitlab-migrate-temp
   ```

3. **Enable cleanup:**

   ```yaml
   git:
     cleanup_temp: true
   ```

4. **Clean up manually:**
   ```bash
   rm -rf /tmp/gm/*
   ```

## Migration Failures

### Issue: "User creation failed"

**Symptoms:**

```
Error: Failed to create user 'username': Email has already been taken
```

**Solutions:**

1. **Check for existing users:**

   - Tool automatically detects existing users
   - Verify user detection logic

2. **Handle email conflicts:**

   - Users with same email already exist
   - Consider email mapping strategy

3. **Skip problematic users:**
   - Review user data for invalid formats
   - Check for system/bot users

### Issue: "Group creation failed"

**Symptoms:**

```
Error: Failed to create group 'groupname': Path has already been taken
```

**Solutions:**

1. **Check existing groups:**

   - Group with same path exists
   - Tool should detect and skip

2. **Verify group hierarchy:**

   - Parent groups must be created first
   - Check group ordering

3. **Handle path conflicts:**
   - Consider path mapping strategy
   - Use unique path generation

### Issue: "Subgroup migration loses parent path"

**Symptoms:**

```
Error: Subgroup 'enterpriseprojects/shiyao' becomes just 'shiyao'
Error: Parent group information lost during migration
Error: Subgroups created as root-level groups
```

**Solutions:**

1. **Automatic fix (v1.1.0+):**

   - The tool now automatically handles subgroup paths correctly
   - URL encoding is applied to preserve full paths like `enterpriseprojects/shiyao`
   - No configuration changes needed

2. **Verify subgroup migration:**

   ```bash
   # Check migration logs for subgroup handling
   grep -i "subgroup\|parent.*group" migration.log
   grep -i "full_path" migration.log
   ```

3. **Manual verification:**

   ```bash
   # Verify parent groups exist in destination
   curl -H "Private-Token: your-token" \
        "https://destination.gitlab.com/api/v4/groups/enterpriseprojects%2Fshiyao"
   ```

4. **Migration order:**
   - Parent groups are migrated before subgroups
   - Tool maintains proper hierarchy during migration
   - Check that parent groups completed successfully

**Technical Details:**

The issue was caused by improper URL encoding of subgroup paths in GitLab API calls:

- **Before fix:** `/groups/enterpriseprojects/shiyao` (interpreted as separate path segments)
- **After fix:** `/groups/enterpriseprojects%2Fshiyao` (properly encoded full path)

This ensures that GitLab API correctly identifies the subgroup and maintains the parent-child relationship.

### Issue: "Project creation failed"

**Symptoms:**

```
Error: Failed to create project 'projectname': Repository already exists on disk
```

**Solutions:**

1. **Enable unique path generation:**

   - Tool automatically generates unique paths
   - Check project path conflict resolution

2. **Clean destination:**

   - Remove conflicting repositories
   - Use fresh GitLab instance

3. **Skip existing projects:**
   - Tool should detect existing projects
   - Verify project detection logic

### Issue: "Repository migration failed"

**Symptoms:**

```
Error: Git repository migration failed: Permission denied
```

**Solutions:**

1. **Check Git permissions:**

   ```bash
   git clone https://gitlab.example.com/group/project.git
   ```

2. **Verify repository access:**

   - Ensure token has repository access
   - Check project visibility settings

3. **Test Git operations:**
   ```bash
   git ls-remote https://gitlab.example.com/group/project.git
   ```

## Configuration Problems

### Issue: "Invalid configuration values"

**Symptoms:**

```
Error: batch_size must be greater than 0
```

**Solutions:**

1. **Validate configuration:**

   ```bash
   gitlab-migrate validate --config config.yaml
   ```

2. **Check value ranges:**

   ```yaml
   migration:
     batch_size: 5 # Must be > 0
     max_workers: 20 # Must be > 0
     timeout: 600 # Must be > 0
   ```

3. **Use default values:**
   - Remove invalid settings to use defaults
   - Refer to configuration documentation

### Issue: "Environment variable conflicts"

**Symptoms:**

- Configuration values not applied
- Unexpected behavior

**Solutions:**

1. **Check environment variables:**

   ```bash
   env | grep GITLAB
   env | grep MIGRATION
   ```

2. **Unset conflicting variables:**

   ```bash
   unset GITLAB_SOURCE_TOKEN
   unset MIGRATION_DRY_RUN
   ```

3. **Use explicit configuration:**
   - Specify all values in config file
   - Don't rely on environment variables

## Git Repository Issues

### Issue: "Repository disk conflicts"

**Symptoms:**

```
Error: 磁盘上已存在具有该名称的仓库 (Repository with that name already exists on disk)
Error: There is already a repository with that name on disk
Error: uncaught throw :abort
```

**Solutions:**

1. **Automatic unique path generation:**

   - The tool automatically generates unique project paths to avoid conflicts
   - Projects are created with suffixes like `project-name-12345-abc123`
   - This is the default behavior and requires no configuration

2. **Check migration logs:**

   ```bash
   grep -i "disk conflict" migration.log
   grep -i "unique project path" migration.log
   ```

3. **Manual cleanup (if needed):**

   ```bash
   # On GitLab server (admin access required)
   sudo gitlab-rake gitlab:cleanup:repos
   ```

4. **Verify disk space:**
   ```bash
   df -h /var/opt/gitlab/git-data/repositories
   ```

**Note:** This issue commonly occurs when:

- Previous migration attempts left repository files on disk
- GitLab has orphaned repository directories
- Multiple migrations target the same GitLab instance

### Issue: "Git LFS objects not migrated"

**Symptoms:**

- Repository migrated but LFS files missing
- LFS pointers instead of actual files

**Solutions:**

1. **Enable LFS support:**

   ```yaml
   git:
     lfs_enabled: true
   ```

2. **Install Git LFS:**

   ```bash
   git lfs install
   ```

3. **Verify LFS configuration:**
   ```bash
   git lfs env
   ```

### Issue: "Large repository timeout"

**Symptoms:**

```
Error: Git operation timeout after 3600 seconds
```

**Solutions:**

1. **Increase Git timeout:**

   ```yaml
   git:
     timeout: 7200 # 2 hours
   ```

2. **Use shallow clone:**

   - Consider partial migration
   - Clone specific branches only

3. **Split large repositories:**
   - Migrate in smaller chunks
   - Use Git subtree/submodule

### Issue: "Git authentication failed"

**Symptoms:**

```
Error: Authentication failed when cloning repository
```

**Solutions:**

1. **Verify Git credentials:**

   ```bash
   git clone https://oauth2:token@gitlab.example.com/group/project.git
   ```

2. **Check token format:**

   - Use OAuth2 format for Git operations
   - Ensure token has repository access

3. **Test Git access:**
   ```bash
   git ls-remote https://gitlab.example.com/group/project.git
   ```

## Debugging Tips

### Enable Debug Logging

```yaml
logging:
  level: DEBUG
  file: migration-debug.log
```

### Use Dry Run Mode

```yaml
migration:
  dry_run: true
```

### Monitor System Resources

```bash
# Monitor CPU and memory
htop

# Monitor disk usage
watch -n 1 'df -h'

# Monitor network
iftop
```

### Check Log Files

```bash
# View recent logs
tail -f migration.log

# Search for errors
grep -i error migration.log

# Filter by entity type
grep "user" migration.log
```

### Test Individual Components

```python
# Test API connectivity
from gitlab_migrate.api.client import GitLabClient
from gitlab_migrate.config.config import GitLabInstanceConfig

config = GitLabInstanceConfig(
    url="https://gitlab.example.com",
    token="your-token"
)
client = GitLabClient(config)
print(client.test_connection())
```

### Validate Configuration

```bash
# Validate YAML syntax
python -c "import yaml; print(yaml.safe_load(open('config.yaml')))"

# Validate configuration
gitlab-migrate validate --config config.yaml
```

## Getting Help

### Check Documentation

1. [User Guide](user-guide.md) - Complete usage instructions
2. [Configuration Reference](configuration.md) - All configuration options
3. [API Documentation](api.md) - Technical details

### Review Log Files

1. **Enable detailed logging:**

   ```yaml
   logging:
     level: DEBUG
   ```

2. **Check for patterns:**
   - Look for repeated errors
   - Note timing of failures
   - Check entity-specific issues

### Gather System Information

When reporting issues, include:

1. **System details:**

   ```bash
   python --version
   poetry --version
   git --version
   uname -a
   ```

2. **Configuration (sanitized):**

   - Remove sensitive tokens
   - Include relevant settings

3. **Error messages:**
   - Full error stack traces
   - Relevant log entries
   - Steps to reproduce

### Common Diagnostic Commands

```bash
# Test GitLab connectivity
curl -I https://gitlab.example.com

# Test API access
curl -H "Private-Token: your-token" https://gitlab.example.com/api/v4/user

# Check DNS resolution
nslookup gitlab.example.com

# Test network connectivity
ping gitlab.example.com

# Check disk space
df -h

# Check memory usage
free -h

# Check running processes
ps aux | grep gitlab-migrate
```

### Report Issues

When reporting issues:

1. **Search existing issues** first
2. **Provide minimal reproduction case**
3. **Include system information**
4. **Sanitize sensitive data**
5. **Use issue templates** if available

### Community Resources

- **GitHub Issues**: Report bugs and feature requests
- **Documentation**: Check for updates and examples
- **Stack Overflow**: Search for similar problems
- **GitLab Community**: General GitLab questions

Remember to always sanitize sensitive information (tokens, URLs, usernames) before sharing logs or configuration files.
