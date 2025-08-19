"""Main CLI entry point for GitLab Migration Tool."""

import sys
import asyncio
from typing import Optional
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
)
from rich.table import Table

from ..config.config import Config
from ..utils.logging import setup_logging
from ..migration.engine import MigrationEngine

console = Console()


@click.group()
@click.version_option(version='0.1.0', prog_name='gitlab-migrate')
@click.option(
    '--config',
    '-c',
    type=click.Path(exists=True),
    help='Path to configuration file',
)
@click.option(
    '--verbose',
    '-v',
    is_flag=True,
    help='Enable verbose logging',
)
@click.pass_context
def cli(ctx: click.Context, config: Optional[str], verbose: bool) -> None:
    """GitLab Migration Tool - Migrate users, groups, projects, and repositories between GitLab instances."""
    ctx.ensure_object(dict)

    # Store config path and verbose flag
    if config:
        ctx.obj['config_path'] = config
    ctx.obj['verbose'] = verbose

    # Setup basic logging first (will be enhanced later with config)
    log_level = 'DEBUG' if verbose else 'INFO'
    setup_logging(log_level)


@cli.command()
@click.option(
    '--output',
    '-o',
    default='config.yaml',
    help='Output configuration file path',
)
@click.pass_context
def init(ctx: click.Context, output: str) -> None:
    """Initialize a new configuration file."""
    console.print(
        Panel.fit(
            '[bold green]GitLab Migration Tool[/bold green]\n'
            'Initializing configuration...',
            border_style='green',
        )
    )

    try:
        # Create configuration template directly
        _create_config_template(output)

        console.print(f'[green]✓[/green] Configuration template created at: {output}')
        console.print(
            f'[yellow]Please edit {output} with your GitLab instance details[/yellow]'
        )

    except Exception as e:
        console.print(f'[red]✗[/red] Failed to create configuration: {e}')
        sys.exit(1)


@cli.command()
@click.option(
    '--dry-run',
    is_flag=True,
    help='Perform a dry run without making changes',
)
@click.pass_context
def migrate(ctx: click.Context, dry_run: bool) -> None:
    """Start the migration process."""
    console.print(
        Panel.fit(
            '[bold blue]GitLab Migration Tool[/bold blue]\n'
            'Starting migration process...',
            border_style='blue',
        )
    )

    if dry_run:
        console.print(
            '[yellow]Running in dry-run mode - no changes will be made[/yellow]'
        )

    try:
        # Load configuration
        config = _load_config(ctx)

        # Setup logging with config file settings
        _setup_logging_with_config(ctx, config)

        if dry_run:
            config.migration.dry_run = True

        # Run migration
        asyncio.run(_run_migration(config, dry_run))

    except Exception as e:
        console.print(f'[red]✗[/red] Migration failed: {e}')
        if ctx.obj.get('verbose'):
            console.print_exception()
        sys.exit(1)


@cli.command()
@click.pass_context
def validate(ctx: click.Context) -> None:
    """Validate the migration results."""
    console.print(
        Panel.fit(
            '[bold cyan]GitLab Migration Tool[/bold cyan]\nValidating migration...',
            border_style='cyan',
        )
    )

    try:
        # Load configuration
        config = _load_config(ctx)

        # Test connectivity to both instances
        engine = MigrationEngine(config)
        asyncio.run(engine._test_connectivity())

        console.print('[green]✓[/green] Connectivity validation passed')
        console.print('[green]✓[/green] Configuration validation completed')

    except Exception as e:
        console.print(f'[red]✗[/red] Validation failed: {e}')
        if ctx.obj.get('verbose'):
            console.print_exception()
        sys.exit(1)


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show migration status and progress."""
    console.print(
        Panel.fit(
            '[bold magenta]GitLab Migration Tool[/bold magenta]\nMigration Status',
            border_style='magenta',
        )
    )

    try:
        # Load configuration
        config = _load_config(ctx)

        # Setup logging with config file settings
        _setup_logging_with_config(ctx, config)

        # Create status table
        table = Table(title='Migration Configuration')
        table.add_column('Setting', style='cyan')
        table.add_column('Value', style='green')

        table.add_row('Source URL', config.source.url)
        table.add_row('Destination URL', config.destination.url)
        table.add_row('Migrate Users', '✓' if config.migration.users else '✗')
        table.add_row('Migrate Groups', '✓' if config.migration.groups else '✗')
        table.add_row('Migrate Projects', '✓' if config.migration.projects else '✗')
        table.add_row(
            'Migrate Repositories', '✓' if config.migration.repositories else '✗'
        )
        table.add_row('Batch Size', str(config.migration.batch_size))
        table.add_row('Max Workers', str(config.migration.max_workers))

        console.print(table)

    except Exception as e:
        console.print(f'[red]✗[/red] Failed to load status: {e}')
        if ctx.obj.get('verbose'):
            console.print_exception()
        sys.exit(1)


def _load_config(ctx: click.Context) -> Config:
    """Load configuration from file or environment."""
    config_path = ctx.obj.get('config_path')

    if config_path:
        if not Path(config_path).exists():
            raise FileNotFoundError(f'Configuration file not found: {config_path}')
        return Config.from_file(config_path)
    else:
        # Try to load from default locations
        default_paths = ['config.yaml', 'config.yml', '.gitlab-migrate.yaml']
        for path in default_paths:
            if Path(path).exists():
                return Config.from_file(path)

        # Fall back to environment variables
        try:
            return Config.from_env()
        except Exception:
            raise FileNotFoundError(
                'No configuration found. Use --config to specify a file or run "gitlab-migrate init" to create one.'
            )


def _setup_logging_with_config(ctx: click.Context, config: Config) -> None:
    """Setup logging with configuration from config file."""
    verbose = ctx.obj.get('verbose', False)

    # Use config logging settings, but allow verbose flag to override level
    log_level = 'DEBUG' if verbose else config.logging.level
    log_file = config.logging.file if hasattr(config.logging, 'file') else None
    log_format = config.logging.format if hasattr(config.logging, 'format') else None

    # Setup logging with file support
    setup_logging(level=log_level, log_file=log_file, log_format=log_format)


async def _run_migration(config: Config, dry_run: bool = False) -> None:
    """Run the migration process with progress display."""
    engine = MigrationEngine(config)

    with Progress(
        SpinnerColumn(),
        TextColumn('[progress.description]{task.description}'),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        # Create a progress callback to update the progress bar
        def update_progress(current: int, total: int, description: str):
            if hasattr(update_progress, 'task_id'):
                progress.update(
                    update_progress.task_id,
                    completed=current,
                    total=total,
                    description=description,
                )

        # Add migration task - will be updated with real totals
        task = progress.add_task(
            f'{"[yellow]Dry run" if dry_run else "[blue]Migration"} initializing...',
            total=1,
        )
        update_progress.task_id = task

        try:
            if dry_run:
                summary = await _run_migration_with_progress(
                    engine.dry_run(), progress, task, 'Dry run'
                )
                console.print(f'[green]✓[/green] Dry run completed successfully')
            else:
                summary = await _run_migration_with_progress(
                    engine.migrate(), progress, task, 'Migration'
                )
                console.print(f'[green]✓[/green] Migration completed successfully')

            # Display summary
            _display_migration_summary(summary)

        except Exception as e:
            progress.update(task, description=f'[red]Failed: {e}')
            raise


async def _run_migration_with_progress(
    migration_coro, progress, task_id, operation_name
):
    """Run migration with progress tracking."""
    # Start the migration
    progress.update(task_id, description=f'[blue]{operation_name} starting...')

    # For now, we'll simulate progress since the engine doesn't have built-in progress callbacks
    # In a future enhancement, we could modify the engine to accept progress callbacks
    import asyncio

    # Create a task for the actual migration
    migration_task = asyncio.create_task(migration_coro)

    # Simulate progress updates while migration runs
    completed = 0
    while not migration_task.done():
        await asyncio.sleep(0.5)  # Update every 500ms
        completed = min(completed + 1, 95)  # Don't go to 100% until actually done
        progress.update(
            task_id,
            completed=completed,
            total=100,
            description=f'[blue]{operation_name} in progress...',
        )

    # Get the result
    summary = await migration_task

    # Mark as complete
    progress.update(
        task_id,
        completed=100,
        total=100,
        description=f'[green]{operation_name} completed',
    )

    return summary


def _display_migration_summary(summary) -> None:
    """Display migration summary results."""
    # Create summary table
    table = Table(title='Migration Summary')
    table.add_column('Entity Type', style='cyan')
    table.add_column('Total', style='blue')
    table.add_column('Successful', style='green')
    table.add_column('Failed', style='red')
    table.add_column('Skipped', style='yellow')

    # Add rows for each entity type from the actual summary
    if hasattr(summary, 'results_by_type') and summary.results_by_type:
        for entity_type, counts in summary.results_by_type.items():
            table.add_row(
                entity_type.title(),
                str(counts.get('total', 0)),
                str(counts.get('successful', 0)),
                str(counts.get('failed', 0)),
                str(counts.get('skipped', 0)),
            )
    else:
        # Fallback if no detailed results available
        table.add_row(
            'Total',
            str(getattr(summary, 'total_entities', 0)),
            str(getattr(summary, 'successful_migrations', 0)),
            str(getattr(summary, 'failed_migrations', 0)),
            str(getattr(summary, 'skipped_migrations', 0)),
        )

    console.print(table)

    # Display timing information if available
    if (
        hasattr(summary, 'started_at')
        and hasattr(summary, 'completed_at')
        and summary.completed_at
    ):
        duration = summary.completed_at - summary.started_at
        console.print(f'\n[blue]Migration Duration:[/blue] {duration}')

    # Display any warnings or errors
    if hasattr(summary, 'all_results'):
        warnings = []
        errors = []
        for result in summary.all_results:
            if hasattr(result, 'warnings') and result.warnings:
                warnings.extend(result.warnings)
            if hasattr(result, 'error_message') and result.error_message:
                errors.append(
                    f'{result.entity_type} {result.entity_id}: {result.error_message}'
                )

        if warnings:
            console.print(f'\n[yellow]Warnings ({len(warnings)}):[/yellow]')
            for warning in warnings[:5]:  # Show first 5 warnings
                console.print(f'  • {warning}')
            if len(warnings) > 5:
                console.print(f'  ... and {len(warnings) - 5} more warnings')

        if errors:
            console.print(f'\n[red]Errors ({len(errors)}):[/red]')
            for error in errors[:5]:  # Show first 5 errors
                console.print(f'  • {error}')
            if len(errors) > 5:
                console.print(f'  ... and {len(errors) - 5} more errors')


def _create_config_template(output_path: str) -> None:
    """Create a configuration template file."""
    import yaml
    from pathlib import Path

    template_config = {
        'source': {
            'url': 'https://gitlab-source.example.com',
            'token': 'your-source-personal-access-token',
            'api_version': 'v4',
            'timeout': 30,
        },
        'destination': {
            'url': 'https://gitlab-dest.example.com',
            'token': 'your-destination-personal-access-token',
            'api_version': 'v4',
            'timeout': 30,
        },
        'migration': {
            'users': True,
            'groups': True,
            'projects': True,
            'repositories': True,
            'batch_size': 50,
            'max_workers': 5,
            'timeout': 300,
            'dry_run': False,
        },
        'logging': {
            'level': 'INFO',
            'file': 'migration.log',
            'format': '{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}',
        },
    }

    config_file = Path(output_path)
    config_file.parent.mkdir(parents=True, exist_ok=True)

    with open(config_file, 'w', encoding='utf-8') as f:
        yaml.dump(
            template_config, f, default_flow_style=False, indent=2, sort_keys=False
        )


def main() -> None:
    """Main entry point for the CLI application."""
    try:
        cli()
    except KeyboardInterrupt:
        console.print('\n[red]Migration interrupted by user[/red]')
        sys.exit(1)
    except Exception as e:
        console.print(f'[red]Error: {e}[/red]')
        sys.exit(1)


if __name__ == '__main__':
    main()
