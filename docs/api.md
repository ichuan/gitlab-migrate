# API Documentation

This document provides technical documentation for the GitLab Migration Tool's internal API and architecture.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Components](#core-components)
3. [Migration Strategies](#migration-strategies)
4. [API Client](#api-client)
5. [Data Models](#data-models)
6. [Configuration System](#configuration-system)
7. [Error Handling](#error-handling)
8. [Extending the Tool](#extending-the-tool)

## Architecture Overview

The GitLab Migration Tool follows a modular architecture with clear separation of concerns:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   CLI Layer     │    │  Configuration  │    │    Logging      │
│                 │    │     System      │    │     System      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────────┐
│                    Migration Engine                             │
└─────────────────────────────────────────────────────────────────┘
         │                       │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Migration     │    │   API Client    │    │   Git Operations│
│   Strategies    │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Data Models    │    │  Rate Limiting  │    │  Error Handling │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Core Components

### Migration Engine

The central orchestrator that coordinates the entire migration process.

**Location**: `src/gitlab_migrate/migration/engine.py`

```python
class MigrationEngine:
    """Main migration engine that orchestrates the migration process."""

    async def migrate(self, config: MigrationConfig) -> MigrationResult:
        """Execute the complete migration process."""

    async def validate_prerequisites(self) -> bool:
        """Validate that migration can proceed."""

    async def _migrate_users(self) -> List[MigrationResult]:
        """Migrate all users from source to destination."""

    async def _migrate_groups(self) -> List[MigrationResult]:
        """Migrate all groups from source to destination."""

    async def _migrate_projects(self) -> List[MigrationResult]:
        """Migrate all projects from source to destination."""

    async def _migrate_repositories(self) -> List[MigrationResult]:
        """Migrate all repositories from source to destination."""
```

### Migration Orchestrator

Handles batch processing and concurrent execution of migration tasks.

**Location**: `src/gitlab_migrate/migration/orchestrator.py`

```python
class MigrationOrchestrator:
    """Orchestrates migration execution with batching and concurrency."""

    async def migrate_entities(
        self,
        entities: List[Any],
        strategy: MigrationStrategy,
        batch_size: int = 5
    ) -> List[MigrationResult]:
        """Migrate entities using the specified strategy."""
```

## Migration Strategies

Each entity type has its own migration strategy implementing the `MigrationStrategy` interface.

### Base Strategy Interface

```python
class MigrationStrategy(ABC):
    """Abstract base class for migration strategies."""

    @abstractmethod
    async def migrate_entity(self, entity: EntityType) -> MigrationResult:
        """Migrate a single entity."""

    @abstractmethod
    async def migrate_batch(self, entities: List[EntityType]) -> List[MigrationResult]:
        """Migrate a batch of entities."""

    @abstractmethod
    async def validate_prerequisites(self) -> bool:
        """Validate prerequisites for migration."""
```

### User Migration Strategy

**Location**: `src/gitlab_migrate/migration/strategy.py`

```python
class UserMigrationStrategy(MigrationStrategy):
    """Strategy for migrating users."""

    async def migrate_entity(self, user: User) -> MigrationResult:
        """Migrate a single user with conflict resolution."""

    async def _find_existing_user(self, user: User) -> Optional[User]:
        """Find existing user by email or username."""

    def _should_skip_user(self, user: User) -> bool:
        """Determine if user should be skipped (bots, system users)."""
```

### Group Migration Strategy

```python
class GroupMigrationStrategy(MigrationStrategy):
    """Strategy for migrating groups."""

    async def migrate_entity(self, group: Group) -> MigrationResult:
        """Migrate a single group with hierarchy preservation."""

    async def _migrate_group_members(
        self,
        source_group_id: int,
        destination_group_id: int
    ) -> int:
        """Migrate group members with batch processing."""
```

### Project Migration Strategy

```python
class ProjectMigrationStrategy(MigrationStrategy):
    """Strategy for migrating projects."""

    async def migrate_entity(self, project: Project) -> MigrationResult:
        """Migrate a single project with namespace resolution."""

    async def _resolve_project_namespace(self, project: Project) -> Optional[int]:
        """Resolve namespace ID for user-owned and group-owned projects."""

    async def _generate_unique_project_path(self, project: Project) -> str:
        """Generate unique project path to avoid conflicts."""
```

### Repository Migration Strategy

```python
class RepositoryMigrationStrategy(MigrationStrategy):
    """Strategy for migrating repositories."""

    async def migrate_entity(self, repository: Repository) -> MigrationResult:
        """Migrate a single repository with full Git history."""
```

## API Client

The GitLab API client provides both synchronous and asynchronous methods for interacting with GitLab instances.

**Location**: `src/gitlab_migrate/api/client.py`

### Core Methods

```python
class GitLabClient:
    """GitLab API client with authentication and rate limiting."""

    # Synchronous methods
    def get(self, endpoint: str, params: Optional[Dict] = None) -> APIResponse:
        """Make synchronous GET request."""

    def post(self, endpoint: str, data: Optional[Dict] = None) -> APIResponse:
        """Make synchronous POST request."""

    # Asynchronous methods
    async def get_async(self, endpoint: str, params: Optional[Dict] = None) -> APIResponse:
        """Make asynchronous GET request."""

    async def post_async(self, endpoint: str, data: Optional[Dict] = None) -> APIResponse:
        """Make asynchronous POST request."""

    # Utility methods
    def get_paginated(self, endpoint: str, per_page: int = 100) -> List[Dict]:
        """Get all pages of a paginated endpoint."""

    def test_connection(self) -> bool:
        """Test connection to GitLab instance."""
```

### Response Format

```python
class APIResponse(BaseModel):
    """Standard API response wrapper."""

    status_code: int
    data: Any
    headers: Dict[str, str]
    success: bool
```

### Rate Limiting

The client includes built-in rate limiting:

**Location**: `src/gitlab_migrate/api/rate_limiter.py`

```python
class RateLimiter:
    """Token bucket rate limiter for API requests."""

    async def acquire(self) -> None:
        """Acquire permission to make a request."""

    def set_rate(self, requests_per_second: float) -> None:
        """Update the rate limit."""
```

## Data Models

All data models are defined using Pydantic for validation and serialization.

### Base Models

**Location**: `src/gitlab_migrate/models/`

#### User Model

```python
class User(BaseModel):
    """GitLab user model."""

    id: int
    username: str
    name: str
    email: str
    state: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    organization: Optional[str] = None
    can_create_group: Optional[bool] = None
    can_create_project: Optional[bool] = None
    external: Optional[bool] = None
    creator_id: Optional[int] = None

class UserCreate(BaseModel):
    """Model for creating users."""

    username: str
    name: str
    email: str
    password: str
    skip_confirmation: bool = True
    # ... additional fields
```

#### Group Model

```python
class Group(BaseModel):
    """GitLab group model."""

    id: int
    name: str
    path: str
    description: Optional[str] = None
    visibility: str = 'private'
    parent_id: Optional[int] = None
    full_path: Optional[str] = None

class GroupCreate(BaseModel):
    """Model for creating groups."""

    name: str
    path: str
    description: Optional[str] = None
    visibility: str = 'private'
    parent_id: Optional[int] = None
```

#### Project Model

```python
class Project(BaseModel):
    """GitLab project model."""

    id: int
    name: str
    path: str
    description: Optional[str] = None
    visibility: str = 'private'
    namespace: Optional[Dict[str, Any]] = None
    creator_id: Optional[int] = None
    # ... additional fields

class ProjectCreate(BaseModel):
    """Model for creating projects."""

    name: str
    path: str
    namespace_id: Optional[int] = None
    description: Optional[str] = None
    visibility: str = 'private'
    # ... additional fields
```

### Migration Results

```python
class MigrationResult(BaseModel):
    """Result of a migration operation."""

    entity_type: str
    entity_id: str
    status: MigrationStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    success: bool
    source_data: Optional[Dict[str, Any]] = None
    destination_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class MigrationStatus(str, Enum):
    """Migration status enumeration."""

    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    FAILED = 'failed'
    SKIPPED = 'skipped'
```

## Configuration System

The configuration system supports YAML files and environment variable overrides.

**Location**: `src/gitlab_migrate/config/config.py`

### Configuration Models

```python
class GitLabInstanceConfig(BaseModel):
    """Configuration for a GitLab instance."""

    url: str
    token: str
    api_version: str = 'v4'
    timeout: int = 60
    rate_limit_per_second: float = 10.0

class MigrationSettings(BaseModel):
    """Migration behavior settings."""

    users: bool = True
    groups: bool = True
    projects: bool = True
    repositories: bool = True
    batch_size: int = 5
    max_workers: int = 20
    timeout: int = 600
    dry_run: bool = False
    # ... batch size settings

class MigrationConfig(BaseModel):
    """Complete migration configuration."""

    source: GitLabInstanceConfig
    destination: GitLabInstanceConfig
    migration: MigrationSettings
    logging: LoggingConfig
    git: GitConfig
```

### Configuration Loading

```python
def load_config(config_path: str) -> MigrationConfig:
    """Load configuration from YAML file with environment overrides."""

def validate_config(config: MigrationConfig) -> List[str]:
    """Validate configuration and return list of errors."""
```

## Error Handling

The tool uses a comprehensive error handling system with custom exceptions.

**Location**: `src/gitlab_migrate/api/exceptions.py`

### Exception Hierarchy

```python
class GitLabAPIError(Exception):
    """Base exception for GitLab API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code

class GitLabAuthenticationError(GitLabAPIError):
    """Authentication failed."""

class GitLabNotFoundError(GitLabAPIError):
    """Resource not found."""

class GitLabRateLimitError(GitLabAPIError):
    """Rate limit exceeded."""

    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after
```

### Error Recovery

The migration engine includes automatic retry logic for transient errors:

```python
async def _retry_with_backoff(
    self,
    operation: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0
) -> Any:
    """Retry operation with exponential backoff."""
```

## Extending the Tool

### Adding New Migration Strategies

1. **Create Strategy Class**:

   ```python
   class CustomMigrationStrategy(MigrationStrategy):
       async def migrate_entity(self, entity: CustomEntity) -> MigrationResult:
           # Implementation
           pass
   ```

2. **Register Strategy**:
   ```python
   # In migration engine
   self.strategies['custom'] = CustomMigrationStrategy(context)
   ```

### Adding New Data Models

1. **Define Model**:

   ```python
   class CustomEntity(BaseModel):
       id: int
       name: str
       # Additional fields
   ```

2. **Add Validation**:
   ```python
   @validator('name')
   def validate_name(cls, v):
       if not v.strip():
           raise ValueError('Name cannot be empty')
       return v
   ```

### Custom API Endpoints

```python
class CustomAPIClient(GitLabClient):
    async def get_custom_data(self, entity_id: int) -> APIResponse:
        """Get custom data from GitLab API."""
        return await self.get_async(f'/custom/{entity_id}')
```

### Plugin System

The tool supports plugins for extending functionality:

```python
class MigrationPlugin(ABC):
    """Base class for migration plugins."""

    @abstractmethod
    def pre_migration_hook(self, context: MigrationContext) -> None:
        """Called before migration starts."""

    @abstractmethod
    def post_migration_hook(self, results: List[MigrationResult]) -> None:
        """Called after migration completes."""
```

## Performance Considerations

### Async/Await Pattern

The tool uses async/await throughout for optimal performance:

```python
# Concurrent processing
async def process_batch(entities: List[Entity]) -> List[MigrationResult]:
    tasks = [migrate_entity(entity) for entity in entities]
    return await asyncio.gather(*tasks, return_exceptions=True)
```

### Memory Management

- Streaming data processing for large datasets
- Automatic cleanup of temporary resources
- Configurable batch sizes to control memory usage

### Network Optimization

- Connection pooling for HTTP requests
- Automatic retry with exponential backoff
- Rate limiting to prevent API abuse

## Testing

### Unit Tests

```python
@pytest.mark.asyncio
async def test_user_migration():
    """Test user migration strategy."""
    strategy = UserMigrationStrategy(mock_context)
    result = await strategy.migrate_entity(mock_user)
    assert result.success
```

### Integration Tests

```python
@pytest.mark.integration
async def test_full_migration():
    """Test complete migration process."""
    engine = MigrationEngine(test_config)
    results = await engine.migrate()
    assert all(r.success for r in results)
```

### Mock Objects

The test suite includes comprehensive mocks for GitLab API responses:

```python
@pytest.fixture
def mock_gitlab_client():
    """Mock GitLab client for testing."""
    client = Mock(spec=GitLabClient)
    client.get_async.return_value = APIResponse(
        status_code=200,
        data={'id': 1, 'username': 'test'},
        headers={},
        success=True
    )
    return client
```

## Logging and Monitoring

### Structured Logging

```python
from loguru import logger

logger.bind(
    migration_id=migration_id,
    entity_type='user',
    entity_id=user.id
).info('Starting user migration')
```

### Progress Tracking

```python
class ProgressTracker:
    """Track migration progress."""

    def update_progress(self, completed: int, total: int) -> None:
        """Update progress information."""

    def get_progress_report(self) -> Dict[str, Any]:
        """Get current progress report."""
```

### Metrics Collection

The tool can export metrics for monitoring:

```python
class MetricsCollector:
    """Collect migration metrics."""

    def record_migration_time(self, entity_type: str, duration: float) -> None:
        """Record migration timing."""

    def record_error(self, error_type: str) -> None:
        """Record error occurrence."""
```
