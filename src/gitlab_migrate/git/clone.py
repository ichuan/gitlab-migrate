"""Git repository cloning operations."""

import asyncio
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

from loguru import logger

from ..api.client import GitLabClient
from ..models.repository import Repository


@dataclass
class CloneResult:
    """Result of a git clone operation."""

    success: bool
    error: Optional[str] = None
    repository_path: Optional[str] = None
    repository_size: Optional[int] = None
    branches_count: int = 0
    tags_count: int = 0
    commits_count: int = 0


class GitCloner:
    """Handles git repository cloning operations."""

    def __init__(self, source_client: GitLabClient, config):
        """Initialize git cloner.

        Args:
            source_client: Source GitLab API client
            config: Git configuration
        """
        self.source_client = source_client
        self.config = config
        self.logger = logger.bind(component='GitCloner')

    async def clone_repository(
        self, project_id: int, destination_path: str, repository: Repository
    ) -> CloneResult:
        """Clone a repository from source GitLab instance.

        Args:
            project_id: Source project ID
            destination_path: Local path to clone to
            repository: Repository metadata

        Returns:
            Clone operation result
        """
        self.logger.info(f'Cloning repository for project {project_id}')

        try:
            # Get project details to determine clone URL
            response = self.source_client.get(f'/projects/{project_id}')
            if not response.success:
                return CloneResult(
                    success=False,
                    error=f'Failed to get project details: {response.data}',
                )

            project_data = response.data
            clone_url = self._get_clone_url(project_data)

            if not clone_url:
                return CloneResult(success=False, error='No suitable clone URL found')

            # Perform git clone with authentication
            clone_success = await self._execute_git_clone(clone_url, destination_path)

            if not clone_success:
                return CloneResult(success=False, error='Git clone operation failed')

            # Get repository statistics
            stats = await self._get_repository_stats(destination_path)

            return CloneResult(
                success=True,
                repository_path=destination_path,
                repository_size=stats['size'],
                branches_count=stats['branches'],
                tags_count=stats['tags'],
                commits_count=stats['commits'],
            )

        except Exception as e:
            error_msg = f'Clone operation failed: {str(e)}'
            self.logger.error(error_msg)
            return CloneResult(success=False, error=error_msg)

    def _get_clone_url(self, project_data: dict) -> Optional[str]:
        """Get appropriate clone URL from project data.

        Args:
            project_data: Project data from GitLab API

        Returns:
            Clone URL or None if not found
        """
        # Prefer HTTP URL with token authentication
        if 'http_url_to_repo' in project_data:
            http_url = project_data['http_url_to_repo']
            # Insert token into URL for authentication
            if self.source_client.config.token:
                # Convert https://gitlab.com/user/repo.git to https://oauth2:token@gitlab.com/user/repo.git
                if http_url.startswith('https://'):
                    return http_url.replace(
                        'https://', f'https://oauth2:{self.source_client.config.token}@'
                    )
                elif http_url.startswith('http://'):
                    return http_url.replace(
                        'http://', f'http://oauth2:{self.source_client.config.token}@'
                    )
            return http_url

        # Fallback to SSH URL (requires SSH key setup)
        if 'ssh_url_to_repo' in project_data:
            return project_data['ssh_url_to_repo']

        return None

    async def _execute_git_clone(self, clone_url: str, destination_path: str) -> bool:
        """Execute git clone command.

        Args:
            clone_url: URL to clone from
            destination_path: Local destination path

        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure destination directory exists
            os.makedirs(destination_path, exist_ok=True)
            self.logger.info(f'Created destination directory: {destination_path}')

            # Generate unique repository directory name using timestamp and random suffix
            import time
            import random
            import string

            timestamp = int(time.time() * 1000)  # milliseconds for uniqueness
            random_suffix = ''.join(
                random.choices(string.ascii_lowercase + string.digits, k=6)
            )
            repo_dir_name = f'repo_{timestamp}_{random_suffix}.git'
            repo_path = os.path.join(destination_path, repo_dir_name)

            self.logger.info(f'Generated unique repository path: {repo_path}')

            # Double-check that the path doesn't exist (extremely unlikely but safe)
            if os.path.exists(repo_path):
                self.logger.warning(
                    f'Repository path {repo_path} already exists, cleaning up...'
                )
                await self._cleanup_existing_repository(repo_path)

            # Configure git for the operation
            await self._configure_git(destination_path)

            # Execute git clone with mirror option to get all branches and tags
            cmd = [
                'git',
                'clone',
                '--mirror',
                clone_url,
                repo_path,
            ]

            # Log the exact git command being executed (mask sensitive token)
            masked_cmd = cmd.copy()
            if len(masked_cmd) >= 4 and 'oauth2:' in masked_cmd[3]:
                # Mask the token in the URL for logging
                masked_url = masked_cmd[3]
                if '@' in masked_url:
                    parts = masked_url.split('@')
                    if len(parts) >= 2:
                        auth_part = parts[0]
                        if 'oauth2:' in auth_part:
                            masked_auth = (
                                auth_part.split('oauth2:')[0] + 'oauth2:***TOKEN***'
                            )
                            masked_url = masked_auth + '@' + '@'.join(parts[1:])
                            masked_cmd[3] = masked_url

            self.logger.info(f'Executing git command: {" ".join(masked_cmd)}')
            self.logger.info(f'Working directory: {destination_path}')
            self.logger.info(f'Target repository path: {repo_path}')

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=destination_path,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.config.timeout
            )

            stdout_text = stdout.decode() if stdout else ''
            stderr_text = stderr.decode() if stderr else ''

            self.logger.info(f'Git command return code: {process.returncode}')
            if stdout_text:
                self.logger.info(f'Git stdout: {stdout_text}')
            if stderr_text:
                self.logger.info(f'Git stderr: {stderr_text}')

            if process.returncode == 0:
                self.logger.info(f'Git clone completed successfully to {repo_path}')

                # Fetch LFS objects if enabled
                if self.config.lfs_enabled:
                    self.logger.info(f'Fetching LFS objects for {repo_path}...')
                    lfs_fetch_cmd = ['git', 'lfs', 'fetch', '--all']
                    lfs_fetch_success = await self._run_git_command(
                        lfs_fetch_cmd, repo_path
                    )
                    if not lfs_fetch_success:
                        self.logger.warning(
                            f'Git LFS fetch failed for {repo_path}. LFS objects may be missing.'
                        )
                return True
            else:
                error_output = stderr_text if stderr_text else 'Unknown error'
                self.logger.error(
                    f'Git clone failed with return code {process.returncode}: {error_output}'
                )

                # Check for various error patterns
                if 'already exists' in error_output.lower():
                    self.logger.error(
                        f'Repository already exists at {repo_path}. This might indicate a cleanup issue. '
                        'Consider using a different temp_dir or ensuring proper cleanup.'
                    )

                # Check for Chinese error patterns
                if '磁盘上已存在' in error_output or '仓库已存在' in error_output:
                    self.logger.error(
                        f'Chinese disk conflict error detected: {error_output}. '
                        f'This suggests GitLab server-side disk conflict, not local path conflict.'
                    )

                return False

        except asyncio.TimeoutError:
            self.logger.error(
                f'Git clone timed out after {self.config.timeout} seconds'
            )
            return False
        except Exception as e:
            self.logger.error(f'Git clone execution failed: {e}')
            return False

    async def _configure_git(self, work_dir: str) -> None:
        """Configure git for the operation.

        Args:
            work_dir: Working directory for git operations
        """
        try:
            self.logger.info(f'Configuring git in directory: {work_dir}')

            # Set git user configuration
            user_name_cmd = [
                'git',
                'config',
                '--global',
                'user.name',
                self.config.user_name,
            ]
            self.logger.info(f'Executing git config command: {" ".join(user_name_cmd)}')
            await self._run_git_command(user_name_cmd, work_dir)

            user_email_cmd = [
                'git',
                'config',
                '--global',
                'user.email',
                self.config.user_email,
            ]
            self.logger.info(
                f'Executing git config command: {" ".join(user_email_cmd)}'
            )
            await self._run_git_command(user_email_cmd, work_dir)

            # Disable SSL verification if needed (for self-signed certificates)
            # This should be configurable in production
            ssl_cmd = ['git', 'config', '--global', 'http.sslVerify', 'false']
            self.logger.info(f'Executing git config command: {" ".join(ssl_cmd)}')
            await self._run_git_command(ssl_cmd, work_dir)

            self.logger.info('Git configuration completed successfully')

        except Exception as e:
            self.logger.warning(f'Git configuration failed: {e}')

    async def _run_git_command(self, cmd: list, work_dir: str) -> bool:
        """Run a git command.

        Args:
            cmd: Git command as list
            work_dir: Working directory

        Returns:
            True if successful
        """
        try:
            self.logger.debug(f'Running git command: {" ".join(cmd)} in {work_dir}')

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
            )

            stdout, stderr = await process.communicate()

            stdout_text = stdout.decode() if stdout else ''
            stderr_text = stderr.decode() if stderr else ''

            self.logger.debug(f'Git command return code: {process.returncode}')
            if stdout_text:
                self.logger.debug(f'Git command stdout: {stdout_text}')
            if stderr_text:
                self.logger.debug(f'Git command stderr: {stderr_text}')

            return process.returncode == 0

        except Exception as e:
            self.logger.error(f'Git command execution failed: {e}')
            return False

    async def _get_repository_stats(self, repo_path: str) -> dict:
        """Get repository statistics.

        Args:
            repo_path: Path to repository

        Returns:
            Dictionary with repository statistics
        """
        stats = {'size': 0, 'branches': 0, 'tags': 0, 'commits': 0}

        try:
            repo_git_path = self._find_git_repo_path(repo_path)

            if not repo_git_path or not os.path.exists(repo_git_path):
                return stats

            stats['size'] = await self._get_directory_size(repo_git_path)

            branches_result = await self._run_git_command_with_output(
                ['git', 'branch', '-r'], repo_git_path
            )
            if branches_result:
                stats['branches'] = len(
                    [line for line in branches_result.split('\n') if line.strip()]
                )

            tags_result = await self._run_git_command_with_output(
                ['git', 'tag'], repo_git_path
            )
            if tags_result:
                stats['tags'] = len(
                    [line for line in tags_result.split('\n') if line.strip()]
                )

            commits_result = await self._run_git_command_with_output(
                ['git', 'rev-list', '--all', '--count'], repo_git_path
            )
            if commits_result and commits_result.strip().isdigit():
                stats['commits'] = int(commits_result.strip())

        except Exception as e:
            self.logger.warning(f'Failed to get repository stats: {e}')

        return stats

    def _find_git_repo_path(self, base_path: str) -> Optional[str]:
        """Find the git repository directory within the base path.

        Args:
            base_path: Base directory to search in

        Returns:
            Path to git repository directory, or None if not found
        """
        try:
            if not os.path.exists(base_path):
                return None

            # Look for directories ending with .git
            for item in os.listdir(base_path):
                item_path = os.path.join(base_path, item)
                if os.path.isdir(item_path) and item.endswith('.git'):
                    return item_path

            return None

        except Exception as e:
            self.logger.warning(f'Error finding git repo path in {base_path}: {e}')
            return None

    async def _get_directory_size(self, path: str) -> int:
        """Get total size of directory in bytes.

        Args:
            path: Directory path

        Returns:
            Size in bytes
        """
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
        except Exception as e:
            self.logger.warning(f'Failed to calculate directory size: {e}')

        return total_size

    async def _run_git_command_with_output(
        self, cmd: list, work_dir: str
    ) -> Optional[str]:
        """Run git command and return output.

        Args:
            cmd: Git command as list
            work_dir: Working directory

        Returns:
            Command output or None if failed
        """
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return stdout.decode().strip()
            else:
                return None

        except Exception:
            return None

    async def _cleanup_existing_repository(self, repo_path: str) -> None:
        """Clean up existing repository directory.

        Args:
            repo_path: Path to existing repository directory
        """
        try:
            import shutil

            if os.path.exists(repo_path):
                # Remove the existing repository directory
                shutil.rmtree(repo_path)
                self.logger.info(f'Cleaned up existing repository at {repo_path}')
        except Exception as e:
            self.logger.warning(
                f'Failed to cleanup existing repository {repo_path}: {e}'
            )
            # Re-raise the exception so the caller knows cleanup failed
            raise
