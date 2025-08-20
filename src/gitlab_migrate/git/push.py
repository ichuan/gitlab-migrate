"""Git repository pushing operations."""

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
class PushResult:
    """Result of a git push operation."""

    success: bool
    error: Optional[str] = None
    branches_pushed: int = 0
    tags_pushed: int = 0


class GitPusher:
    """Handles git repository pushing operations."""

    def __init__(self, destination_client: GitLabClient, config):
        """Initialize git pusher.

        Args:
            destination_client: Destination GitLab API client
            config: Git configuration
        """
        self.destination_client = destination_client
        self.config = config
        self.logger = logger.bind(component='GitPusher')

    async def push_repository(
        self, project_id: int, repository_path: str, repository: Repository
    ) -> PushResult:
        """Push a repository to destination GitLab instance.

        Args:
            project_id: Destination project ID
            repository_path: Local repository path
            repository: Repository metadata

        Returns:
            Push operation result
        """
        self.logger.info(f'Pushing repository to project {project_id}')

        try:
            # Get project details to determine push URL
            response = self.destination_client.get(f'/projects/{project_id}')
            if not response.success:
                return PushResult(
                    success=False,
                    error=f'Failed to get destination project details: {response.data}',
                )

            project_data = response.data
            push_url = self._get_push_url(project_data)

            if not push_url:
                return PushResult(success=False, error='No suitable push URL found')

            # Perform git push with authentication
            push_success = await self._execute_git_push(
                push_url, repository_path, repository
            )

            if not push_success:
                return PushResult(success=False, error='Git push operation failed')

            # Get push statistics
            stats = await self._get_push_stats(repository_path)

            return PushResult(
                success=True,
                branches_pushed=stats['branches'],
                tags_pushed=stats['tags'],
            )

        except Exception as e:
            error_msg = f'Push operation failed: {str(e)}'
            self.logger.error(error_msg)
            return PushResult(success=False, error=error_msg)

    def _get_push_url(self, project_data: dict) -> Optional[str]:
        """Get appropriate push URL from project data.

        Args:
            project_data: Project data from GitLab API

        Returns:
            Push URL or None if not found
        """
        # Prefer HTTP URL with token authentication
        if 'http_url_to_repo' in project_data:
            http_url = project_data['http_url_to_repo']
            # Insert token into URL for authentication
            if self.destination_client.config.token:
                # Convert https://gitlab.com/user/repo.git to https://oauth2:token@gitlab.com/user/repo.git
                if http_url.startswith('https://'):
                    return http_url.replace(
                        'https://',
                        f'https://oauth2:{self.destination_client.config.token}@',
                    )
                elif http_url.startswith('http://'):
                    return http_url.replace(
                        'http://',
                        f'http://oauth2:{self.destination_client.config.token}@',
                    )
            return http_url

        # Fallback to SSH URL (requires SSH key setup)
        if 'ssh_url_to_repo' in project_data:
            return project_data['ssh_url_to_repo']

        return None

    async def _execute_git_push(
        self, push_url: str, repository_path: str, repository: Repository
    ) -> bool:
        """Execute git push command.

        Args:
            push_url: URL to push to
            repository_path: Local repository path
            repository: Repository metadata

        Returns:
            True if successful, False otherwise
        """
        try:
            # Find the actual git repository directory (now has dynamic name)
            repo_git_path = self._find_git_repo_path(repository_path)

            if not repo_git_path or not os.path.exists(repo_git_path):
                self.logger.error(
                    f'Repository path does not exist in: {repository_path}'
                )
                return False

            # Configure git for the operation
            await self._configure_git(repo_git_path)

            # Add remote for destination
            await self._run_git_command(
                ['git', 'remote', 'add', 'destination', push_url], repo_git_path
            )

            # Push all branches and tags
            push_success = await self._push_all_refs(repo_git_path)

            if not push_success:
                return False

            self.logger.info(f'Git push completed successfully from {repo_git_path}')
            return True

        except Exception as e:
            self.logger.error(f'Git push execution failed: {e}')
            return False

    async def _push_all_refs(self, repo_path: str) -> bool:
        """Push all branches, tags, and LFS objects to destination."""
        try:
            # Push LFS objects if enabled
            if self.config.lfs_enabled:
                self.logger.info(f"Pushing LFS objects to destination...")
                lfs_success = await self._run_git_command_with_timeout(
                    ['git', 'lfs', 'push', '--all', 'destination'], repo_path
                )
                if not lfs_success:
                    self.logger.error("Failed to push LFS objects.")
                    return False

            # Push all branches
            self.logger.info(f"Pushing all branches to destination...")
            branches_success = await self._run_git_command_with_timeout(
                ['git', 'push', 'destination', '--all'], repo_path
            )
            if not branches_success:
                self.logger.error("Failed to push branches.")
                return False

            # Push all tags
            self.logger.info(f"Pushing all tags to destination...")
            tags_success = await self._run_git_command_with_timeout(
                ['git', 'push', 'destination', '--tags'], repo_path
            )
            if not tags_success:
                self.logger.error("Failed to push tags.")
                return False

            return True

        except Exception as e:
            self.logger.error(f'Failed to push all refs: {e}')
            return False

    async def _configure_git(self, work_dir: str) -> None:
        """Configure git for the operation.

        Args:
            work_dir: Working directory for git operations
        """
        try:
            # Set git user configuration
            await self._run_git_command(
                ['git', 'config', 'user.name', self.config.user_name], work_dir
            )
            await self._run_git_command(
                ['git', 'config', 'user.email', self.config.user_email], work_dir
            )

            # Disable SSL verification if needed (for self-signed certificates)
            # This should be configurable in production
            await self._run_git_command(
                ['git', 'config', 'http.sslVerify', 'false'], work_dir
            )

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
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return True
            else:
                error_output = stderr.decode() if stderr else 'Unknown error'
                self.logger.warning(
                    f'Git command failed: {" ".join(cmd)} - {error_output}'
                )
                return False

        except Exception as e:
            self.logger.error(f'Git command execution failed: {e}')
            return False

    async def _run_git_command_with_timeout(self, cmd: list, work_dir: str) -> bool:
        """Run git command with timeout.

        Args:
            cmd: Git command as list
            work_dir: Working directory

        Returns:
            True if successful
        """
        self.logger.info(f'_run_git_command_with_timeout({cmd=},{work_dir=})')
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.config.timeout
            )

            if process.returncode == 0:
                return True
            else:
                error_output = stderr.decode() if stderr else 'Unknown error'
                self.logger.error(f'Git push failed: {error_output}')
                return False

        except asyncio.TimeoutError:
            self.logger.error(f'Git push timed out after {self.config.timeout} seconds')
            return False
        except Exception as e:
            self.logger.error(f'Git push execution failed: {e}')
            return False

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

    async def _get_push_stats(self, repo_path: str) -> dict:
        """Get push statistics.

        Args:
            repo_path: Path to repository

        Returns:
            Dictionary with push statistics
        """
        stats = {'branches': 0, 'tags': 0}

        try:
            repo_git_path = self._find_git_repo_path(repo_path)

            if not repo_git_path or not os.path.exists(repo_git_path):
                return stats

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

        except Exception as e:
            self.logger.warning(f'Failed to get push stats: {e}')

        return stats

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
