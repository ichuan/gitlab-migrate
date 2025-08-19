"""Migration orchestrator for coordinating entity migrations."""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from loguru import logger
from pydantic import BaseModel, Field

from .strategy import (
    MigrationStrategy,
    MigrationResult,
    MigrationContext,
    MigrationStatus,
    UserMigrationStrategy,
    GroupMigrationStrategy,
    ProjectMigrationStrategy,
    RepositoryMigrationStrategy,
)
from ..models.user import User
from ..models.group import Group
from ..models.project import Project
from ..models.repository import Repository


class MigrationPlan(BaseModel):
    """Migration execution plan."""

    migrate_users: bool = Field(default=True, description='Migrate users')
    migrate_groups: bool = Field(default=True, description='Migrate groups')
    migrate_projects: bool = Field(default=True, description='Migrate projects')
    migrate_repositories: bool = Field(default=True, description='Migrate repositories')

    # Execution order (dependencies)
    execution_order: List[str] = Field(
        default=['users', 'groups', 'projects', 'repositories'],
        description='Order of entity migration',
    )

    # Batch settings - smaller batches for more concurrency
    batch_size: int = Field(default=20, description='Batch size for processing')
    max_concurrent_batches: int = Field(
        default=5, description='Maximum concurrent batches'
    )


class MigrationSummary(BaseModel):
    """Summary of migration results."""

    total_entities: int = Field(..., description='Total entities processed')
    successful_migrations: int = Field(..., description='Successful migrations')
    failed_migrations: int = Field(..., description='Failed migrations')
    skipped_migrations: int = Field(..., description='Skipped migrations')

    # Timing
    started_at: datetime = Field(..., description='Migration start time')
    completed_at: Optional[datetime] = Field(
        default=None, description='Migration completion time'
    )

    # Results by entity type
    results_by_type: Dict[str, Dict[str, int]] = Field(
        default_factory=dict, description='Results grouped by entity type'
    )

    # Detailed results
    all_results: List[MigrationResult] = Field(
        default_factory=list, description='All migration results'
    )

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class MigrationOrchestrator:
    """Orchestrates the migration of entities between GitLab instances."""

    def __init__(self, context: MigrationContext, git_config=None):
        """Initialize migration orchestrator.

        Args:
            context: Migration context with clients and settings
            git_config: Git configuration for repository operations
        """
        self.context = context
        self.git_config = git_config
        self.logger = logger.bind(component='MigrationOrchestrator')

        # Initialize strategies
        self.strategies = {
            'users': UserMigrationStrategy(context),
            'groups': GroupMigrationStrategy(context),
            'projects': ProjectMigrationStrategy(context),
            'repositories': RepositoryMigrationStrategy(context, git_config),
        }

    async def execute_migration(self, plan: MigrationPlan) -> MigrationSummary:
        """Execute migration according to the plan.

        Args:
            plan: Migration execution plan

        Returns:
            Migration summary with results
        """
        self.logger.info('Starting migration execution')
        started_at = datetime.now()

        all_results = []
        results_by_type = {}

        try:
            # Validate prerequisites for all enabled migrations
            await self._validate_prerequisites(plan)

            # Execute migrations in order
            for entity_type in plan.execution_order:
                if not self._should_migrate_entity_type(entity_type, plan):
                    self.logger.info(
                        f'Skipping {entity_type} migration (disabled in plan)'
                    )
                    continue

                self.logger.info(f'Starting {entity_type} migration')

                # Get entities to migrate
                entities = await self._get_entities_to_migrate(entity_type)

                if not entities:
                    self.logger.info(f'No {entity_type} found to migrate')
                    continue

                # Migrate entities in batches
                entity_results = await self._migrate_entities_in_batches(
                    entity_type, entities, plan.batch_size, plan.max_concurrent_batches
                )

                all_results.extend(entity_results)

                # Summarize results for this entity type
                type_summary = self._summarize_results_by_type(entity_results)
                results_by_type[entity_type] = type_summary

                self.logger.info(
                    f'Completed {entity_type} migration: '
                    f'{type_summary["successful"]} successful, '
                    f'{type_summary["failed"]} failed, '
                    f'{type_summary["skipped"]} skipped'
                )

            completed_at = datetime.now()

            # Create summary
            summary = MigrationSummary(
                total_entities=len(all_results),
                successful_migrations=sum(1 for r in all_results if r.success),
                failed_migrations=sum(1 for r in all_results if not r.success),
                skipped_migrations=sum(
                    1 for r in all_results if r.status == MigrationStatus.SKIPPED
                ),
                started_at=started_at,
                completed_at=completed_at,
                results_by_type=results_by_type,
                all_results=all_results,
            )

            self.logger.info(
                f'Migration completed: {summary.successful_migrations} successful, '
                f'{summary.failed_migrations} failed, {summary.skipped_migrations} skipped'
            )

            return summary

        except Exception as e:
            self.logger.error(f'Migration execution failed: {e}')
            raise

    async def _validate_prerequisites(self, plan: MigrationPlan) -> None:
        """Validate prerequisites for all enabled migrations.

        Args:
            plan: Migration plan

        Raises:
            ValueError: If prerequisites are not met
        """
        self.logger.info('Validating migration prerequisites')

        for entity_type in plan.execution_order:
            if not self._should_migrate_entity_type(entity_type, plan):
                continue

            strategy = self.strategies.get(entity_type)
            if not strategy:
                raise ValueError(f'No strategy found for entity type: {entity_type}')

            if not await strategy.validate_prerequisites():
                raise ValueError(f'Prerequisites not met for {entity_type} migration')

        self.logger.info('All prerequisites validated successfully')

    def _should_migrate_entity_type(
        self, entity_type: str, plan: MigrationPlan
    ) -> bool:
        """Check if entity type should be migrated according to plan.

        Args:
            entity_type: Type of entity
            plan: Migration plan

        Returns:
            True if entity type should be migrated
        """
        migration_flags = {
            'users': plan.migrate_users,
            'groups': plan.migrate_groups,
            'projects': plan.migrate_projects,
            'repositories': plan.migrate_repositories,
        }

        return migration_flags.get(entity_type, False)

    async def _get_entities_to_migrate(self, entity_type: str) -> List[Any]:
        """Get entities to migrate for the given type.

        Args:
            entity_type: Type of entity

        Returns:
            List of entities to migrate
        """

        if entity_type == 'users':
            # Fetch users from source
            try:
                users_data = self.context.source_client.get_paginated('/users')
                users = []
                for user_data in users_data:
                    try:
                        user = User(**user_data)
                        users.append(user)
                    except Exception as e:
                        self.logger.warning(f'Failed to parse user data: {e}')
                        continue
                return users
            except Exception as e:
                self.logger.error(f'Failed to fetch users: {e}')
                return []

        elif entity_type == 'groups':
            # Fetch groups from source
            try:
                groups_data = self.context.source_client.get_paginated('/groups')
                groups = []
                for group_data in groups_data:
                    try:
                        group = Group(**group_data)
                        groups.append(group)
                    except Exception as e:
                        self.logger.warning(f'Failed to parse group data: {e}')
                        continue
                return groups
            except Exception as e:
                self.logger.error(f'Failed to fetch groups: {e}')
                return []

        elif entity_type == 'projects':
            # Fetch projects from source
            try:
                projects_data = self.context.source_client.get_paginated('/projects')
                projects = []
                for project_data in projects_data:
                    try:
                        project = Project(**project_data)
                        projects.append(project)
                    except Exception as e:
                        self.logger.warning(f'Failed to parse project data: {e}')
                        continue
                return projects
            except Exception as e:
                self.logger.error(f'Failed to fetch projects: {e}')
                return []

        elif entity_type == 'repositories':
            # Repositories are tied to projects, so we create Repository objects for migrated projects
            repositories = []
            for (
                source_project_id,
                dest_project_id,
            ) in self.context.migrated_projects.items():
                try:
                    # Fetch project details to create repository object
                    response = self.context.source_client.get(
                        f'/projects/{source_project_id}'
                    )
                    if response.success:
                        project_data = response.data

                        # Create repository object from project data
                        repository = Repository(
                            project_id=source_project_id,
                            name=project_data.get('name', ''),
                            path=project_data.get('path', ''),
                            http_url_to_repo=project_data.get('http_url_to_repo', ''),
                            ssh_url_to_repo=project_data.get('ssh_url_to_repo', ''),
                            default_branch=project_data.get('default_branch', 'main'),
                            empty_repo=project_data.get('empty_repo', False),
                            size=project_data.get('repository_size', 0),
                            lfs_enabled=project_data.get('lfs_enabled', False),
                        )
                        repositories.append(repository)
                    else:
                        self.logger.warning(
                            f'Failed to fetch project {source_project_id} details'
                        )
                except Exception as e:
                    self.logger.warning(
                        f'Failed to create repository object for project {source_project_id}: {e}'
                    )
                    continue

            return repositories

        return []

    async def _migrate_entities_in_batches(
        self,
        entity_type: str,
        entities: List[Any],
        batch_size: int,
        max_concurrent_batches: int,
    ) -> List[MigrationResult]:
        """Migrate entities in batches with concurrency control.

        Args:
            entity_type: Type of entity
            entities: List of entities to migrate
            batch_size: Size of each batch
            max_concurrent_batches: Maximum concurrent batches

        Returns:
            List of migration results
        """
        strategy = self.strategies[entity_type]

        # Split entities into batches
        batches = [
            entities[i : i + batch_size] for i in range(0, len(entities), batch_size)
        ]

        self.logger.info(
            f'Migrating {len(entities)} {entity_type} in {len(batches)} batches'
        )

        all_results = []

        # Process batches with concurrency limit
        semaphore = asyncio.Semaphore(max_concurrent_batches)

        async def process_batch(batch_entities):
            async with semaphore:
                return await strategy.migrate_batch(batch_entities)

        # Execute all batches
        batch_tasks = [process_batch(batch) for batch in batches]
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

        # Collect results
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                self.logger.error(f'Batch {i} failed: {result}')
                # Create failure results for the batch
                batch_entities = batches[i]
                for entity in batch_entities:
                    entity_id = getattr(entity, 'id', str(i))
                    failure_result = MigrationResult(
                        entity_type=entity_type,
                        entity_id=str(entity_id),
                        status=MigrationStatus.FAILED,
                        started_at=datetime.now(),
                        completed_at=datetime.now(),
                        success=False,
                        error_message=f'Batch processing failed: {result}',
                    )
                    all_results.append(failure_result)
            elif isinstance(result, list):
                all_results.extend(result)
            else:
                self.logger.warning(
                    f'Unexpected result type from batch {i}: {type(result)}'
                )

        return all_results

    def _summarize_results_by_type(
        self, results: List[MigrationResult]
    ) -> Dict[str, int]:
        """Summarize migration results by status.

        Args:
            results: List of migration results

        Returns:
            Summary dictionary with counts
        """
        summary = {
            'total': len(results),
            'successful': 0,
            'failed': 0,
            'skipped': 0,
        }

        for result in results:
            if result.status == MigrationStatus.COMPLETED:
                summary['successful'] += 1
            elif result.status == MigrationStatus.FAILED:
                summary['failed'] += 1
            elif result.status == MigrationStatus.SKIPPED:
                summary['skipped'] += 1

        return summary

    async def dry_run_migration(self, plan: MigrationPlan) -> MigrationSummary:
        """Perform a dry run of the migration.

        Args:
            plan: Migration execution plan

        Returns:
            Migration summary (dry run results)
        """
        # Set dry run mode
        original_dry_run = self.context.dry_run
        self.context.dry_run = True

        try:
            self.logger.info('Starting migration dry run')
            return await self.execute_migration(plan)
        finally:
            # Restore original dry run setting
            self.context.dry_run = original_dry_run
