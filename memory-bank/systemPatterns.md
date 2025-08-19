# System Patterns - GitLab Migration Tool

## Overall Architecture Pattern

### Layered Architecture

The system follows a clean layered architecture with clear separation of concerns:

```
┌─────────────────────────────────────┐
│           CLI Interface             │  ← User interaction layer
├─────────────────────────────────────┤
│        Migration Orchestrator       │  ← Business logic layer
├─────────────────────────────────────┤
│         Service Layer               │  ← Application services
│  ┌─────────┬─────────┬─────────────┐ │
│  │ User    │ Group   │ Project     │ │
│  │ Service │ Service │ Service     │ │
│  └─────────┴─────────┴─────────────┘ │
├─────────────────────────────────────┤
│         Data Access Layer           │  ← API clients and data access
│  ┌─────────────┬─────────────────────┐ │
│  │ GitLab API  │ Configuration       │ │
│  │ Client      │ Manager             │ │
│  └─────────────┴─────────────────────┘ │
└─────────────────────────────────────┘
```

## Core Design Patterns

### 1. Command Pattern - CLI Operations

Each CLI command is implemented as a discrete command object:

```python
class MigrateCommand:
    def __init__(self, config: Config, migrator: Migrator):
        self.config = config
        self.migrator = migrator

    def execute(self) -> Result:
        return self.migrator.migrate_all()

class ValidateCommand:
    def __init__(self, config: Config, validator: Validator):
        self.config = config
        self.validator = validator

    def execute(self) -> Result:
        return self.validator.validate_migration()
```

### 2. Strategy Pattern - Migration Strategies

Different migration approaches for different entity types:

```python
class MigrationStrategy(ABC):
    @abstractmethod
    def migrate(self, entity: Entity) -> MigrationResult:
        pass

class UserMigrationStrategy(MigrationStrategy):
    def migrate(self, user: User) -> MigrationResult:
        # User-specific migration logic
        pass

class GroupMigrationStrategy(MigrationStrategy):
    def migrate(self, group: Group) -> MigrationResult:
        # Group-specific migration logic
        pass
```

### 3. Factory Pattern - API Client Creation

Centralized creation of API clients with proper configuration:

```python
class GitLabClientFactory:
    @staticmethod
    def create_client(config: InstanceConfig) -> GitLabClient:
        if config.auth_type == "token":
            return TokenAuthClient(config)
        elif config.auth_type == "oauth":
            return OAuthClient(config)
        else:
            raise ValueError(f"Unsupported auth type: {config.auth_type}")
```

### 4. Observer Pattern - Progress Tracking

Event-driven progress reporting and logging:

```python
class MigrationObserver(ABC):
    @abstractmethod
    def on_migration_start(self, event: MigrationStartEvent):
        pass

    @abstractmethod
    def on_migration_progress(self, event: ProgressEvent):
        pass

    @abstractmethod
    def on_migration_complete(self, event: CompletionEvent):
        pass

class ProgressBarObserver(MigrationObserver):
    def on_migration_progress(self, event: ProgressEvent):
        self.progress_bar.update(event.completed_items)
```

### 5. Repository Pattern - Data Access

Abstract data access for different GitLab entities:

```python
class UserRepository(ABC):
    @abstractmethod
    def get_all_users(self) -> List[User]:
        pass

    @abstractmethod
    def create_user(self, user: User) -> User:
        pass

class GitLabUserRepository(UserRepository):
    def __init__(self, client: GitLabClient):
        self.client = client

    def get_all_users(self) -> List[User]:
        return self.client.get("/users")
```

## Component Interaction Patterns

### 1. Migration Orchestration Flow

```
Configuration → Validation → Planning → Execution → Verification
      ↓              ↓           ↓          ↓           ↓
   Load Config → Check Access → Build Plan → Run Tasks → Validate Results
```

### 2. Error Handling Chain

```python
class ErrorHandler:
    def __init__(self, next_handler: Optional['ErrorHandler'] = None):
        self.next_handler = next_handler

    def handle(self, error: Exception) -> bool:
        if self.can_handle(error):
            return self.process_error(error)
        elif self.next_handler:
            return self.next_handler.handle(error)
        return False

# Chain: RateLimitHandler → NetworkHandler → APIHandler → GenericHandler
```

### 3. Batch Processing Pattern

```python
class BatchProcessor:
    def __init__(self, batch_size: int = 50, max_workers: int = 5):
        self.batch_size = batch_size
        self.max_workers = max_workers

    async def process_batches(self, items: List[T], processor: Callable) -> List[Result]:
        batches = self.create_batches(items)
        semaphore = asyncio.Semaphore(self.max_workers)

        tasks = [self.process_batch(batch, processor, semaphore) for batch in batches]
        return await asyncio.gather(*tasks)
```

## Data Flow Patterns

### 1. ETL Pattern for Migration

```
Extract (Source) → Transform (Mapping) → Load (Destination)
      ↓                    ↓                    ↓
  GitLab API A → Data Transformation → GitLab API B
```

### 2. State Management Pattern

```python
class MigrationState:
    def __init__(self):
        self.current_phase: MigrationPhase = MigrationPhase.INIT
        self.completed_entities: Set[str] = set()
        self.failed_entities: Dict[str, Exception] = {}
        self.progress: Dict[str, int] = {}

    def save_checkpoint(self, path: str):
        # Persist state for resume capability
        pass

    def load_checkpoint(self, path: str):
        # Restore state from checkpoint
        pass
```

### 3. Configuration Cascade Pattern

```
CLI Args → Environment Variables → Config File → Defaults
   ↓              ↓                    ↓           ↓
Priority 1    Priority 2         Priority 3   Priority 4
```

## Concurrency Patterns

### 1. Producer-Consumer Pattern

```python
class MigrationQueue:
    def __init__(self, max_size: int = 1000):
        self.queue = asyncio.Queue(maxsize=max_size)
        self.workers = []

    async def producer(self, entities: List[Entity]):
        for entity in entities:
            await self.queue.put(entity)

    async def consumer(self, migrator: EntityMigrator):
        while True:
            entity = await self.queue.get()
            await migrator.migrate(entity)
            self.queue.task_done()
```

### 2. Circuit Breaker Pattern

```python
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED

    async def call(self, func: Callable, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.timeout:
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerOpenError()

        try:
            result = await func(*args, **kwargs)
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise e
```

## Security Patterns

### 1. Credential Management Pattern

```python
class CredentialManager:
    def __init__(self, encryption_key: bytes):
        self.cipher = Fernet(encryption_key)

    def store_credential(self, key: str, value: str):
        encrypted_value = self.cipher.encrypt(value.encode())
        # Store in secure location

    def retrieve_credential(self, key: str) -> str:
        encrypted_value = self.load_from_storage(key)
        return self.cipher.decrypt(encrypted_value).decode()
```

### 2. Rate Limiting Pattern

```python
class RateLimiter:
    def __init__(self, requests_per_second: int = 10):
        self.requests_per_second = requests_per_second
        self.tokens = requests_per_second
        self.last_update = time.time()

    async def acquire(self):
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.requests_per_second,
                         self.tokens + elapsed * self.requests_per_second)
        self.last_update = now

        if self.tokens >= 1:
            self.tokens -= 1
            return True
        else:
            sleep_time = (1 - self.tokens) / self.requests_per_second
            await asyncio.sleep(sleep_time)
            self.tokens = 0
            return True
```

## Validation Patterns

### 1. Chain of Responsibility for Validation

```python
class ValidationRule(ABC):
    def __init__(self, next_rule: Optional['ValidationRule'] = None):
        self.next_rule = next_rule

    def validate(self, context: ValidationContext) -> ValidationResult:
        result = self.check(context)
        if result.is_valid and self.next_rule:
            return self.next_rule.validate(context)
        return result

# Chain: ConnectivityRule → PermissionRule → VersionRule → CapacityRule
```

### 2. Specification Pattern for Complex Validation

```python
class ValidationSpecification(ABC):
    @abstractmethod
    def is_satisfied_by(self, entity: Entity) -> bool:
        pass

    def and_(self, other: 'ValidationSpecification') -> 'AndSpecification':
        return AndSpecification(self, other)

    def or_(self, other: 'ValidationSpecification') -> 'OrSpecification':
        return OrSpecification(self, other)
```

## Logging and Monitoring Patterns

### 1. Structured Logging Pattern

```python
class StructuredLogger:
    def __init__(self, logger_name: str):
        self.logger = loguru.logger.bind(component=logger_name)

    def log_migration_event(self, event_type: str, entity_type: str,
                           entity_id: str, **kwargs):
        self.logger.info(
            "Migration event",
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            **kwargs
        )
```

### 2. Metrics Collection Pattern

```python
class MetricsCollector:
    def __init__(self):
        self.counters: Dict[str, int] = defaultdict(int)
        self.timers: Dict[str, List[float]] = defaultdict(list)

    def increment(self, metric: str, value: int = 1):
        self.counters[metric] += value

    def time_operation(self, operation: str):
        return Timer(operation, self)
```

These patterns provide a solid foundation for building a maintainable, scalable, and robust GitLab migration tool.
