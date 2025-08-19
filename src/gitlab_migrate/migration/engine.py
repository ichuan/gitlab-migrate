"""Migration engine - main entry point for migration operations."""

from typing import Optional
from loguru import logger

from ..config.config import Config
from ..api.client import GitLabClientFactory
from .strategy import MigrationContext
from .orchestrator import MigrationOrchestrator, MigrationPlan, MigrationSummary


class MigrationEngine:
    """Main migration engine that coordinates the entire migration process."""

    def __init__(self, config: Config):
        """Initialize migration engine.

        Args:
            config: Migration configuration
        """
        self.config = config
        self.logger = logger.bind(component='MigrationEngine')

        # Initialize GitLab clients
        self.source_client = GitLabClientFactory.create_client(config.source)
        self.destination_client = GitLabClientFactory.create_client(config.destination)

        # Create migration context
        self.context = MigrationContext(
            source_client=self.source_client,
            destination_client=self.destination_client,
            dry_run=config.migration.dry_run,
            batch_size=config.migration.batch_size,
            max_workers=config.migration.max_workers,
        )

        # Initialize orchestrator with git config
        self.orchestrator = MigrationOrchestrator(self.context, self.config.git)

    async def migrate(self, plan: Optional[MigrationPlan] = None) -> MigrationSummary:
        """Execute migration with the given plan.

        Args:
            plan: Migration plan (uses default if not provided)

        Returns:
            Migration summary
        """
        if plan is None:
            plan = self._create_default_plan()

        self.logger.info('Starting GitLab migration')

        try:
            # Test connectivity
            await self._test_connectivity()

            # Execute migration
            summary = await self.orchestrator.execute_migration(plan)

            self.logger.info('Migration completed successfully')
            return summary

        except Exception as e:
            self.logger.error(f'Migration failed: {e}')
            raise
        finally:
            # Clean up clients
            self.source_client.close()
            self.destination_client.close()

    async def dry_run(self, plan: Optional[MigrationPlan] = None) -> MigrationSummary:
        """Perform a dry run of the migration.

        Args:
            plan: Migration plan (uses default if not provided)

        Returns:
            Migration summary (dry run results)
        """
        if plan is None:
            plan = self._create_default_plan()

        self.logger.info('Starting GitLab migration dry run')

        try:
            # Test connectivity
            await self._test_connectivity()

            # Execute dry run
            summary = await self.orchestrator.dry_run_migration(plan)

            self.logger.info('Dry run completed successfully')
            return summary

        except Exception as e:
            self.logger.error(f'Dry run failed: {e}')
            raise
        finally:
            # Clean up clients
            self.source_client.close()
            self.destination_client.close()

    def _create_default_plan(self) -> MigrationPlan:
        """Create default migration plan from configuration.

        Returns:
            Default migration plan
        """
        return MigrationPlan(
            migrate_users=self.config.migration.users,
            migrate_groups=self.config.migration.groups,
            migrate_projects=self.config.migration.projects,
            migrate_repositories=self.config.migration.repositories,
            batch_size=self.config.migration.batch_size,
            max_concurrent_batches=self.config.migration.max_workers,
        )

    async def _test_connectivity(self) -> None:
        """Test connectivity to both GitLab instances.

        Raises:
            ConnectionError: If connectivity test fails
        """
        self.logger.info('Testing connectivity to GitLab instances')

        # Test source connectivity
        if not self.source_client.test_connection():
            raise ConnectionError('Cannot connect to source GitLab instance')

        # Test destination connectivity
        if not self.destination_client.test_connection():
            raise ConnectionError('Cannot connect to destination GitLab instance')

        self.logger.info('Connectivity tests passed')
