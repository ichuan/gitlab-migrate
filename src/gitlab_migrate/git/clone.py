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

            # Configure git for the operation
            await self._configure_git(destination_path)

            # Execute git clone with mirror option to get all branches and tags
            cmd = [
                'git',
                'clone',
                '--mirror',
                clone_url,
                os.path.join(destination_path, 'repo.git'),
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=destination_path,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.config.git_timeout
            )

            if process.returncode == 0:
                self.logger.info('Git clone completed successfully')
                return True
            else:
                error_output = stderr.decode() if stderr else 'Unknown error'
                self.logger.error(f'Git clone failed: {error_output}')
                return False

        except asyncio.TimeoutError:
            self.logger.error(
                f'Git clone timed out after {self.config.git_timeout} seconds'
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
            # Set git user configuration
            await self._run_git_command(
                ['git', 'config', '--global', 'user.name', self.config.user_name],
                work_dir,
            )
            await self._run_git_command(
                ['git', 'config', '--global', 'user.email', self.config.user_email],
                work_dir,
            )

            # Disable SSL verification if needed (for self-signed certificates)
            # This should be configurable in production
            await self._run_git_command(
                ['git', 'config', '--global', 'http.sslVerify', 'false'], work_dir
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

            await process.communicate()
            return process.returncode == 0

        except Exception:
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
            repo_git_path = os.path.join(repo_path, 'repo.git')

            if not os.path.exists(repo_git_path):
                return stats

            # Get repository size
            stats['size'] = await self._get_directory_size(repo_git_path)

            # Get branch count
            branches_result = await self._run_git_command_with_output(
                ['git', 'branch', '-r'], repo_git_path
            )
            if branches_result:
                stats['branches'] = len(
                    [line for line in branches_result.split('\n') if line.strip()]
                )

            # Get tag count
            tags_result = await self._run_git_command_with_output(
                ['git', 'tag'], repo_git_path
            )
            if tags_result:
                stats['tags'] = len(
                    [line for line in tags_result.split('\n') if line.strip()]
                )

            # Get commit count (approximate)
            commits_result = await self._run_git_command_with_output(
                ['git', 'rev-list', '--all', '--count'], repo_git_path
            )
            if commits_result and commits_result.strip().isdigit():
                stats['commits'] = int(commits_result.strip())

        except Exception as e:
            self.logger.warning(f'Failed to get repository stats: {e}')

        return stats

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
