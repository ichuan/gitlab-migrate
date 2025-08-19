"""Main Git operations orchestrator."""

import asyncio
import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from loguru import logger

from .clone import GitCloner
from .push import GitPusher
from .lfs import LFSHandler
from ..models.repository import Repository, RepositoryMigrationResult
from ..api.client import GitLabClient


@dataclass
class GitConfig:
    """Git configuration for operations."""

    user_name: str = 'GitLab Migration Tool'
    user_email: str = 'migration@gitlab.local'
    temp_dir: Optional[str] = None
    cleanup_temp: bool = True
    git_timeout: int = 3600  # 1 hour timeout for git operations
    lfs_enabled: bool = True
    preserve_lfs: bool = True


class GitOperations:
    """Main orchestrator for Git repository operations."""

    def __init__(
        self,
        source_client: GitLabClient,
        destination_client: GitLabClient,
        config: Optional[GitConfig] = None,
    ):
        """Initialize Git operations.

        Args:
            source_client: Source GitLab API client
            destination_client: Destination GitLab API client
            config: Git configuration options
        """
        self.source_client = source_client
        self.destination_client = destination_client
        self.config = config or GitConfig()

        self.cloner = GitCloner(source_client, self.config)
        self.pusher = GitPusher(destination_client, self.config)
        self.lfs_handler = LFSHandler(self.config)

        self.logger = logger.bind(component='GitOperations')

    async def migrate_repository(
        self,
        source_project_id: int,
        destination_project_id: int,
        repository: Repository,
    ) -> RepositoryMigrationResult:
        """Migrate a complete repository from source to destination.

        Args:
            source_project_id: Source project ID
            destination_project_id: Destination project ID
            repository: Repository metadata

        Returns:
            Repository migration result
        """
        self.logger.info(
            f'Starting repository migration: {source_project_id} -> {destination_project_id}'
        )

        from datetime import datetime

        result = RepositoryMigrationResult(
            source_project_id=source_project_id,
            destination_project_id=destination_project_id,
            migration_method='git_clone_push',
            started_at=repository.created_at
            or repository.last_activity_at
            or datetime.now(),
            status='in_progress',
            success=False,
        )

        temp_repo_path = None

        try:
            # Create temporary directory for repository
            temp_repo_path = await self._create_temp_directory()
            self.logger.info(f'Created temporary directory: {temp_repo_path}')

            # Step 1: Clone repository from source
            clone_result = await self.cloner.clone_repository(
                source_project_id, temp_repo_path, repository
            )

            if not clone_result.success:
                result.errors.append(f'Clone failed: {clone_result.error}')
                result.status = 'failed'
                # Cleanup on failure
                await self._cleanup_failed_migration(
                    temp_repo_path, destination_project_id
                )
                return result

            result.branches_migrated = clone_result.branches_count
            result.tags_migrated = clone_result.tags_count
            result.commits_migrated = clone_result.commits_count
            result.repository_size_bytes = clone_result.repository_size

            # Step 2: Handle LFS objects if enabled
            if self.config.lfs_enabled and repository.lfs_enabled:
                lfs_result = await self.lfs_handler.migrate_lfs_objects(
                    temp_repo_path, source_project_id, destination_project_id
                )

                if lfs_result.success:
                    result.lfs_objects_migrated = lfs_result.objects_migrated
                    result.lfs_size_bytes = lfs_result.total_size
                else:
                    result.warnings.append(f'LFS migration warning: {lfs_result.error}')

            # Step 3: Push repository to destination
            push_result = await self.pusher.push_repository(
                destination_project_id, temp_repo_path, repository
            )

            if not push_result.success:
                result.errors.append(f'Push failed: {push_result.error}')
                result.status = 'failed'
                # Cleanup on failure
                await self._cleanup_failed_migration(
                    temp_repo_path, destination_project_id
                )
                return result

            # Step 4: Migrate repository settings and hooks
            settings_result = await self._migrate_repository_settings(
                source_project_id, destination_project_id, repository
            )

            if not settings_result:
                result.warnings.append('Repository settings migration had issues')

            # Success!
            result.status = 'completed'
            result.success = True
            result.completed_at = repository.last_activity_at

            self.logger.info(
                f'Repository migration completed successfully: '
                f'{result.branches_migrated} branches, {result.tags_migrated} tags, '
                f'{result.commits_migrated} commits'
            )

        except Exception as e:
            error_msg = f'Repository migration failed: {str(e)}'
            self.logger.error(error_msg)
            result.errors.append(error_msg)
            result.status = 'failed'
            # Cleanup on exception
            await self._cleanup_failed_migration(temp_repo_path, destination_project_id)

        finally:
            # Always cleanup temporary directory
            if temp_repo_path and self.config.cleanup_temp:
                await self._cleanup_temp_directory(temp_repo_path)

        return result

    async def validate_repository_access(
        self, source_project_id: int, destination_project_id: int
    ) -> Dict[str, bool]:
        """Validate access to both source and destination repositories.

        Args:
            source_project_id: Source project ID
            destination_project_id: Destination project ID

        Returns:
            Dictionary with validation results
        """
        results = {
            'source_readable': False,
            'destination_writable': False,
            'git_available': False,
        }

        try:
            # Check source repository access
            source_response = self.source_client.get(f'/projects/{source_project_id}')
            results['source_readable'] = source_response.success

            # Check destination repository access
            dest_response = self.destination_client.get(
                f'/projects/{destination_project_id}'
            )
            results['destination_writable'] = dest_response.success

            # Check git command availability
            results['git_available'] = await self._check_git_availability()

        except Exception as e:
            self.logger.error(f'Repository access validation failed: {e}')

        return results

    async def _create_temp_directory(self) -> str:
        """Create temporary directory for repository operations.

        Returns:
            Path to temporary directory
        """
        if self.config.temp_dir:
            base_dir = Path(self.config.temp_dir)
            base_dir.mkdir(parents=True, exist_ok=True)
            temp_dir = tempfile.mkdtemp(dir=base_dir)
        else:
            temp_dir = tempfile.mkdtemp(prefix='gitlab_migrate_')

        return temp_dir

    async def _cleanup_temp_directory(self, temp_path: str) -> None:
        """Clean up temporary directory.

        Args:
            temp_path: Path to temporary directory
        """
        try:
            if os.path.exists(temp_path):
                shutil.rmtree(temp_path)
                self.logger.debug(f'Cleaned up temporary directory: {temp_path}')
        except Exception as e:
            self.logger.warning(
                f'Failed to cleanup temporary directory {temp_path}: {e}'
            )

    async def _check_git_availability(self) -> bool:
        """Check if git command is available.

        Returns:
            True if git is available, False otherwise
        """
        try:
            process = await asyncio.create_subprocess_exec(
                'git',
                '--version',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
            return process.returncode == 0
        except Exception:
            return False

    async def _migrate_repository_settings(
        self,
        source_project_id: int,
        destination_project_id: int,
        repository: Repository,
    ) -> bool:
        """Migrate repository settings like protected branches, hooks, etc.

        Args:
            source_project_id: Source project ID
            destination_project_id: Destination project ID
            repository: Repository metadata

        Returns:
            True if settings migration was successful
        """
        success = True

        try:
            # Migrate protected branches
            protected_branches_success = await self._migrate_protected_branches(
                source_project_id, destination_project_id
            )
            success = success and protected_branches_success

            # Migrate repository hooks
            hooks_success = await self._migrate_repository_hooks(
                source_project_id, destination_project_id
            )
            success = success and hooks_success

            # Update repository settings (default branch, etc.)
            settings_success = await self._update_repository_settings(
                destination_project_id, repository
            )
            success = success and settings_success

        except Exception as e:
            self.logger.error(f'Repository settings migration failed: {e}')
            success = False

        return success

    async def _migrate_protected_branches(
        self, source_project_id: int, destination_project_id: int
    ) -> bool:
        """Migrate protected branch configurations.

        Args:
            source_project_id: Source project ID
            destination_project_id: Destination project ID

        Returns:
            True if successful
        """
        try:
            # Get protected branches from source
            response = self.source_client.get(
                f'/projects/{source_project_id}/protected_branches'
            )

            if not response.success:
                return False

            protected_branches = response.data

            # Create protected branches in destination
            for branch in protected_branches:
                branch_data = {
                    'name': branch['name'],
                    'push_access_level': branch.get('push_access_levels', [{}])[0].get(
                        'access_level', 40
                    ),
                    'merge_access_level': branch.get('merge_access_levels', [{}])[
                        0
                    ].get('access_level', 40),
                    'code_owner_approval_required': branch.get(
                        'code_owner_approval_required', False
                    ),
                }

                self.destination_client.post(
                    f'/projects/{destination_project_id}/protected_branches',
                    data=branch_data,
                )

            return True

        except Exception as e:
            self.logger.warning(f'Protected branches migration failed: {e}')
            return False

    async def _migrate_repository_hooks(
        self, source_project_id: int, destination_project_id: int
    ) -> bool:
        """Migrate repository webhooks.

        Args:
            source_project_id: Source project ID
            destination_project_id: Destination project ID

        Returns:
            True if successful
        """
        try:
            # Get hooks from source
            response = self.source_client.get(f'/projects/{source_project_id}/hooks')

            if not response.success:
                return False

            hooks = response.data

            # Create hooks in destination
            for hook in hooks:
                hook_data = {
                    'url': hook['url'],
                    'push_events': hook.get('push_events', True),
                    'issues_events': hook.get('issues_events', False),
                    'merge_requests_events': hook.get('merge_requests_events', False),
                    'tag_push_events': hook.get('tag_push_events', False),
                    'note_events': hook.get('note_events', False),
                    'job_events': hook.get('job_events', False),
                    'pipeline_events': hook.get('pipeline_events', False),
                    'wiki_page_events': hook.get('wiki_page_events', False),
                    'deployment_events': hook.get('deployment_events', False),
                    'releases_events': hook.get('releases_events', False),
                    'enable_ssl_verification': hook.get(
                        'enable_ssl_verification', True
                    ),
                    'token': hook.get('token'),
                    'push_events_branch_filter': hook.get('push_events_branch_filter'),
                }

                self.destination_client.post(
                    f'/projects/{destination_project_id}/hooks',
                    data={k: v for k, v in hook_data.items() if v is not None},
                )

            return True

        except Exception as e:
            self.logger.warning(f'Repository hooks migration failed: {e}')
            return False

    async def _update_repository_settings(
        self, destination_project_id: int, repository: Repository
    ) -> bool:
        """Update repository settings like default branch.

        Args:
            destination_project_id: Destination project ID
            repository: Repository metadata

        Returns:
            True if successful
        """
        try:
            if repository.default_branch:
                # Update default branch
                self.destination_client.put(
                    f'/projects/{destination_project_id}',
                    data={'default_branch': repository.default_branch},
                )

            return True

        except Exception as e:
            self.logger.warning(f'Repository settings update failed: {e}')
            return False

    async def _cleanup_failed_migration(
        self, temp_repo_path: Optional[str], destination_project_id: int
    ) -> None:
        """Clean up artifacts from a failed migration.

        Args:
            temp_repo_path: Path to temporary repository directory
            destination_project_id: Destination project ID to clean up
        """
        try:
            # Clean up temporary directory
            if temp_repo_path:
                await self._cleanup_temp_directory(temp_repo_path)

            # Note: We don't delete the destination project here because:
            # 1. The project creation might have succeeded even if repo migration failed
            # 2. The user might want to retry just the repository part
            # 3. Deleting projects requires careful consideration of dependencies

            self.logger.info(
                f'Cleaned up failed migration artifacts for project {destination_project_id}'
            )

        except Exception as e:
            self.logger.warning(
                f'Failed to cleanup migration artifacts for project {destination_project_id}: {e}'
            )
