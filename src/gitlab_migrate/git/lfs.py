"""Git LFS (Large File Storage) operations."""

import asyncio
import os
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from loguru import logger


@dataclass
class LFSResult:
    """Result of an LFS operation."""

    success: bool
    error: Optional[str] = None
    objects_migrated: int = 0
    total_size: int = 0


class LFSHandler:
    """Handles Git LFS operations for repository migration."""

    def __init__(self, config):
        """Initialize LFS handler.

        Args:
            config: Git configuration
        """
        self.config = config
        self.logger = logger.bind(component='LFSHandler')

    async def migrate_lfs_objects(
        self,
        repository_path: str,
        source_project_id: int,
        destination_project_id: int,
    ) -> LFSResult:
        """Migrate LFS objects from source to destination.

        Args:
            repository_path: Local repository path
            source_project_id: Source project ID
            destination_project_id: Destination project ID

        Returns:
            LFS migration result
        """
        self.logger.info(
            f'Migrating LFS objects: {source_project_id} -> {destination_project_id}'
        )

        try:
            repo_git_path = os.path.join(repository_path, 'repo.git')

            if not os.path.exists(repo_git_path):
                return LFSResult(success=False, error='Repository path does not exist')

            # Check if LFS is enabled and has objects
            lfs_objects = await self._get_lfs_objects(repo_git_path)

            if not lfs_objects:
                self.logger.info('No LFS objects found, skipping LFS migration')
                return LFSResult(success=True, objects_migrated=0, total_size=0)

            # Fetch LFS objects from source
            fetch_success = await self._fetch_lfs_objects(repo_git_path)

            if not fetch_success:
                return LFSResult(
                    success=False, error='Failed to fetch LFS objects from source'
                )

            # Push LFS objects to destination
            push_success = await self._push_lfs_objects(repo_git_path)

            if not push_success:
                return LFSResult(
                    success=False, error='Failed to push LFS objects to destination'
                )

            # Calculate statistics
            total_size = await self._calculate_lfs_size(lfs_objects)

            self.logger.info(
                f'LFS migration completed: {len(lfs_objects)} objects, {total_size} bytes'
            )

            return LFSResult(
                success=True,
                objects_migrated=len(lfs_objects),
                total_size=total_size,
            )

        except Exception as e:
            error_msg = f'LFS migration failed: {str(e)}'
            self.logger.error(error_msg)
            return LFSResult(success=False, error=error_msg)

    async def _get_lfs_objects(self, repo_path: str) -> List[Dict[str, Any]]:
        """Get list of LFS objects in repository.

        Args:
            repo_path: Path to git repository

        Returns:
            List of LFS object information
        """
        try:
            # Check if git-lfs is available
            lfs_available = await self._check_lfs_availability()
            if not lfs_available:
                self.logger.warning('Git LFS not available, skipping LFS operations')
                return []

            # Get LFS objects list
            result = await self._run_git_lfs_command_with_output(
                ['git', 'lfs', 'ls-files', '--json'], repo_path
            )

            if not result:
                return []

            # Parse JSON output
            lfs_objects = []
            for line in result.strip().split('\n'):
                if line.strip():
                    try:
                        obj = json.loads(line)
                        lfs_objects.append(obj)
                    except json.JSONDecodeError:
                        continue

            return lfs_objects

        except Exception as e:
            self.logger.warning(f'Failed to get LFS objects: {e}')
            return []

    async def _fetch_lfs_objects(self, repo_path: str) -> bool:
        """Fetch LFS objects from source.

        Args:
            repo_path: Path to git repository

        Returns:
            True if successful
        """
        try:
            # Fetch all LFS objects
            success = await self._run_git_lfs_command(
                ['git', 'lfs', 'fetch', '--all'], repo_path
            )

            if success:
                self.logger.info('LFS objects fetched successfully')
            else:
                self.logger.error('Failed to fetch LFS objects')

            return success

        except Exception as e:
            self.logger.error(f'LFS fetch failed: {e}')
            return False

    async def _push_lfs_objects(self, repo_path: str) -> bool:
        """Push LFS objects to destination.

        Args:
            repo_path: Path to git repository

        Returns:
            True if successful
        """
        try:
            # Push all LFS objects to destination remote
            success = await self._run_git_lfs_command(
                ['git', 'lfs', 'push', 'destination', '--all'], repo_path
            )

            if success:
                self.logger.info('LFS objects pushed successfully')
            else:
                self.logger.error('Failed to push LFS objects')

            return success

        except Exception as e:
            self.logger.error(f'LFS push failed: {e}')
            return False

    async def _calculate_lfs_size(self, lfs_objects: List[Dict[str, Any]]) -> int:
        """Calculate total size of LFS objects.

        Args:
            lfs_objects: List of LFS object information

        Returns:
            Total size in bytes
        """
        total_size = 0
        try:
            for obj in lfs_objects:
                if 'size' in obj:
                    total_size += int(obj['size'])
        except Exception as e:
            self.logger.warning(f'Failed to calculate LFS size: {e}')

        return total_size

    async def _check_lfs_availability(self) -> bool:
        """Check if git-lfs is available.

        Returns:
            True if git-lfs is available
        """
        try:
            process = await asyncio.create_subprocess_exec(
                'git',
                'lfs',
                'version',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await process.communicate()
            return process.returncode == 0

        except Exception:
            return False

    async def _run_git_lfs_command(self, cmd: list, work_dir: str) -> bool:
        """Run a git LFS command.

        Args:
            cmd: Git LFS command as list
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

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.config.git_timeout
            )

            if process.returncode == 0:
                return True
            else:
                error_output = stderr.decode() if stderr else 'Unknown error'
                self.logger.warning(
                    f'Git LFS command failed: {" ".join(cmd)} - {error_output}'
                )
                return False

        except asyncio.TimeoutError:
            self.logger.error(
                f'Git LFS command timed out after {self.config.git_timeout} seconds'
            )
            return False
        except Exception as e:
            self.logger.error(f'Git LFS command execution failed: {e}')
            return False

    async def _run_git_lfs_command_with_output(
        self, cmd: list, work_dir: str
    ) -> Optional[str]:
        """Run git LFS command and return output.

        Args:
            cmd: Git LFS command as list
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

    async def setup_lfs_tracking(self, repo_path: str, patterns: List[str]) -> bool:
        """Setup LFS tracking for specific file patterns.

        Args:
            repo_path: Path to git repository
            patterns: List of file patterns to track with LFS

        Returns:
            True if successful
        """
        try:
            for pattern in patterns:
                success = await self._run_git_lfs_command(
                    ['git', 'lfs', 'track', pattern], repo_path
                )
                if not success:
                    self.logger.warning(
                        f'Failed to setup LFS tracking for pattern: {pattern}'
                    )
                    return False

            self.logger.info(f'LFS tracking setup for patterns: {patterns}')
            return True

        except Exception as e:
            self.logger.error(f'LFS tracking setup failed: {e}')
            return False

    async def migrate_existing_files_to_lfs(
        self, repo_path: str, patterns: List[str]
    ) -> bool:
        """Migrate existing files to LFS based on patterns.

        Args:
            repo_path: Path to git repository
            patterns: List of file patterns to migrate to LFS

        Returns:
            True if successful
        """
        try:
            # Setup tracking first
            tracking_success = await self.setup_lfs_tracking(repo_path, patterns)
            if not tracking_success:
                return False

            # Migrate existing files
            success = await self._run_git_lfs_command(
                ['git', 'lfs', 'migrate', 'import', '--include'] + patterns, repo_path
            )

            if success:
                self.logger.info(f'Migrated existing files to LFS: {patterns}')
            else:
                self.logger.error('Failed to migrate existing files to LFS')

            return success

        except Exception as e:
            self.logger.error(f'LFS migration of existing files failed: {e}')
            return False

    async def get_lfs_info(self, repo_path: str) -> Dict[str, Any]:
        """Get LFS information for repository.

        Args:
            repo_path: Path to git repository

        Returns:
            Dictionary with LFS information
        """
        info = {
            'lfs_available': False,
            'lfs_enabled': False,
            'tracked_patterns': [],
            'object_count': 0,
            'total_size': 0,
        }

        try:
            info['lfs_available'] = await self._check_lfs_availability()

            if not info['lfs_available']:
                return info

            gitattributes_path = os.path.join(repo_path, '.gitattributes')
            if os.path.exists(gitattributes_path):
                with open(gitattributes_path, 'r') as f:
                    content = f.read()
                    if 'filter=lfs' in content:
                        info['lfs_enabled'] = True

            if info['lfs_enabled']:
                patterns_result = await self._run_git_lfs_command_with_output(
                    ['git', 'lfs', 'track'], repo_path
                )
                if patterns_result:
                    info['tracked_patterns'] = [
                        line.strip()
                        for line in patterns_result.split('\n')
                        if line.strip() and not line.startswith('Listing')
                    ]

            lfs_objects = await self._get_lfs_objects(repo_path)
            info['object_count'] = len(lfs_objects)
            info['total_size'] = await self._calculate_lfs_size(lfs_objects)

        except Exception as e:
            self.logger.warning(f'Failed to get LFS info: {e}')

        return info
