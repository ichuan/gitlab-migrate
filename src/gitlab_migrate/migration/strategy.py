"""Migration strategy interfaces and implementations."""

import time
import random
import string
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Type, TypeVar
from enum import Enum

from pydantic import BaseModel, Field
from loguru import logger

from ..api.client import GitLabClient
from ..models.user import User, UserCreate, UserMapping
from ..models.group import Group, GroupCreate, GroupMapping
from ..models.project import Project, ProjectCreate, ProjectMapping
from ..models.repository import Repository, RepositoryMapping, RepositoryMigrationResult


class MigrationStatus(str, Enum):
    """Migration status enumeration."""

    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    FAILED = 'failed'
    SKIPPED = 'skipped'


class MigrationResult(BaseModel):
    """Result of a migration operation."""

    entity_type: str = Field(..., description='Type of entity migrated')
    entity_id: str = Field(..., description='ID of the entity')
    status: MigrationStatus = Field(..., description='Migration status')

    # Timing information
    started_at: datetime = Field(..., description='Migration start time')
    completed_at: Optional[datetime] = Field(
        default=None, description='Migration completion time'
    )

    # Results
    success: bool = Field(..., description='Migration was successful')
    source_data: Optional[Dict[str, Any]] = Field(
        default=None, description='Source entity data'
    )
    destination_data: Optional[Dict[str, Any]] = Field(
        default=None, description='Destination entity data'
    )

    # Error information
    error_message: Optional[str] = Field(
        default=None, description='Error message if failed'
    )
    warnings: List[str] = Field(default_factory=list, description='Warning messages')

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description='Additional metadata'
    )

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class MigrationContext(BaseModel):
    """Context for migration operations."""

    source_client: GitLabClient = Field(..., description='Source GitLab client')
    destination_client: GitLabClient = Field(
        ..., description='Destination GitLab client'
    )

    # Migration settings
    dry_run: bool = Field(default=False, description='Perform dry run without changes')
    batch_size: int = Field(default=50, description='Batch size for processing')
    max_workers: int = Field(default=5, description='Maximum concurrent workers')

    # Mappings
    user_mappings: Dict[int, UserMapping] = Field(
        default_factory=dict, description='User ID mappings'
    )
    group_mappings: Dict[int, GroupMapping] = Field(
        default_factory=dict, description='Group ID mappings'
    )
    project_mappings: Dict[int, ProjectMapping] = Field(
        default_factory=dict, description='Project ID mappings'
    )

    # State tracking
    migrated_users: Dict[int, int] = Field(
        default_factory=dict, description='Source to destination user ID mapping'
    )
    migrated_groups: Dict[int, int] = Field(
        default_factory=dict, description='Source to destination group ID mapping'
    )
    migrated_projects: Dict[int, int] = Field(
        default_factory=dict, description='Source to destination project ID mapping'
    )

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True


# Type variable for entity types
EntityType = TypeVar('EntityType')


class MigrationStrategy(ABC):
    """Abstract base class for migration strategies."""

    def __init__(self, context: MigrationContext):
        """Initialize migration strategy.

        Args:
            context: Migration context with clients and settings
        """
        self.context = context
        self.logger = logger.bind(strategy=self.__class__.__name__)

    @abstractmethod
    async def migrate_entity(self, entity: EntityType) -> MigrationResult:
        """Migrate a single entity.

        Args:
            entity: Entity to migrate

        Returns:
            Migration result
        """
        pass

    @abstractmethod
    async def migrate_batch(self, entities: List[EntityType]) -> List[MigrationResult]:
        """Migrate a batch of entities.

        Args:
            entities: List of entities to migrate

        Returns:
            List of migration results
        """
        pass

    @abstractmethod
    async def validate_prerequisites(self) -> bool:
        """Validate prerequisites for migration.

        Returns:
            True if prerequisites are met, False otherwise
        """
        pass

    def create_result(
        self,
        entity_type: str,
        entity_id: str,
        status: MigrationStatus,
        success: bool = True,
        error_message: Optional[str] = None,
        **kwargs,
    ) -> MigrationResult:
        """Create a migration result.

        Args:
            entity_type: Type of entity
            entity_id: Entity ID
            status: Migration status
            success: Whether migration was successful
            error_message: Error message if failed
            **kwargs: Additional fields for the result

        Returns:
            Migration result
        """
        return MigrationResult(
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            started_at=datetime.now(),
            completed_at=datetime.now()
            if status in [MigrationStatus.COMPLETED, MigrationStatus.FAILED]
            else None,
            success=success,
            error_message=error_message,
            **kwargs,
        )


class UserMigrationStrategy(MigrationStrategy):
    """Strategy for migrating users."""

    async def migrate_entity(self, user: User) -> MigrationResult:
        """Migrate a single user.

        Args:
            user: User to migrate

        Returns:
            Migration result
        """
        self.logger.info(f'Migrating user: {user.username} (ID: {user.id})')

        try:
            # Check if user already exists in destination
            existing_user = await self._find_existing_user(user)

            if existing_user:
                self.logger.info(f'User {user.username} already exists in destination')
                self.context.migrated_users[user.id] = existing_user.id
                return self.create_result(
                    entity_type='user',
                    entity_id=str(user.id),
                    status=MigrationStatus.SKIPPED,
                    success=True,
                    source_data=user.dict(),
                    destination_data=existing_user.dict(),
                    metadata={'reason': 'user_already_exists'},
                )

            if self.context.dry_run:
                self.logger.info(f'Dry run: Would create user {user.username}')
                return self.create_result(
                    entity_type='user',
                    entity_id=str(user.id),
                    status=MigrationStatus.COMPLETED,
                    success=True,
                    source_data=user.dict(),
                    metadata={'dry_run': True},
                )

            # Skip bot users and system users that can't be migrated
            if self._should_skip_user(user):
                self.logger.info(f'Skipping system/bot user: {user.username}')
                return self.create_result(
                    entity_type='user',
                    entity_id=str(user.id),
                    status=MigrationStatus.SKIPPED,
                    success=True,
                    source_data=user.dict(),
                    metadata={'reason': 'system_or_bot_user'},
                )

            # Create user in destination
            user_create_data = {
                'username': user.username,
                'name': user.name,
                'email': user.email,
                'skip_confirmation': True,
            }

            # Add optional fields if they exist
            if user.bio:
                user_create_data['bio'] = user.bio
            if user.location:
                user_create_data['location'] = user.location
            if user.organization:
                user_create_data['organization'] = user.organization
            if user.can_create_group is not None:
                user_create_data['can_create_group'] = user.can_create_group
            if user.can_create_project is not None:
                user_create_data['can_create_project'] = user.can_create_project
            if user.external is not None:
                user_create_data['external'] = user.external

            # Set default password for new users (they'll need to reset it)
            user_create_data['password'] = 'TempPassword123!'
            user_create_data['force_random_password'] = True

            response = self.context.destination_client.post(
                '/users', data=user_create_data
            )

            if response.success:
                new_user_data = response.data
                new_user = User(**new_user_data)
                self.context.migrated_users[user.id] = new_user.id

                self.logger.info(
                    f'Successfully migrated user {user.username} -> ID {new_user.id}'
                )
                return self.create_result(
                    entity_type='user',
                    entity_id=str(user.id),
                    status=MigrationStatus.COMPLETED,
                    success=True,
                    source_data=user.dict(),
                    destination_data=new_user.dict(),
                )
            else:
                error_msg = f'Failed to create user {user.username}: {response.data}'
                self.logger.error(error_msg)
                return self.create_result(
                    entity_type='user',
                    entity_id=str(user.id),
                    status=MigrationStatus.FAILED,
                    success=False,
                    error_message=error_msg,
                    source_data=user.dict(),
                )

        except Exception as e:
            error_msg = f'Error migrating user {user.username}: {str(e)}'
            self.logger.error(error_msg)
            return self.create_result(
                entity_type='user',
                entity_id=str(user.id),
                status=MigrationStatus.FAILED,
                success=False,
                error_message=error_msg,
                source_data=user.dict(),
            )

    async def migrate_batch(self, users: List[User]) -> List[MigrationResult]:
        """Migrate a batch of users.

        Args:
            users: List of users to migrate

        Returns:
            List of migration results
        """
        results = []
        for user in users:
            result = await self.migrate_entity(user)
            results.append(result)
        return results

    async def validate_prerequisites(self) -> bool:
        """Validate prerequisites for user migration.

        Returns:
            True if prerequisites are met, False otherwise
        """
        try:
            # Test destination client connectivity and permissions
            response = self.context.destination_client.get('/user')
            if not response.success:
                self.logger.error('Cannot connect to destination GitLab instance')
                return False

            # Check if we have admin permissions (needed to create users)
            user_data = response.data
            if not user_data.get('is_admin', False):
                self.logger.warning(
                    'Destination user is not admin - user creation may fail'
                )

            return True

        except Exception as e:
            self.logger.error(f'Error validating user migration prerequisites: {e}')
            return False

    async def _find_existing_user(self, user: User) -> Optional[User]:
        """Find existing user in destination by email or username.

        Args:
            user: User to search for

        Returns:
            Existing user if found, None otherwise
        """
        try:
            # Search by email first
            response = self.context.destination_client.get(
                '/users', params={'search': user.email}
            )
            if response.success and response.data:
                for user_data in response.data:
                    if user_data.get('email') == user.email:
                        return User(**user_data)

            # Search by username
            response = self.context.destination_client.get(
                '/users', params={'username': user.username}
            )
            if response.success and response.data:
                for user_data in response.data:
                    if user_data.get('username') == user.username:
                        return User(**user_data)

            return None

        except Exception as e:
            self.logger.warning(
                f'Error searching for existing user {user.username}: {e}'
            )
            return None

    def _should_skip_user(self, user: User) -> bool:
        """Check if user should be skipped (bot users, system users, etc.).

        Args:
            user: User to check

        Returns:
            True if user should be skipped
        """
        # Skip bot users (usually have _bot in username or specific patterns)
        if '_bot' in user.username.lower():
            return True

        # Skip users with blocked_pending_approval state (can't be migrated)
        if user.state == 'blocked_pending_approval':
            return True

        # Skip system users (root, ghost, etc.)
        system_usernames = ['root', 'ghost', 'support-bot', 'alert-bot']
        if user.username.lower() in system_usernames:
            return True

        # Skip users with invalid email formats that can't be migrated
        if not user.email or '@' not in user.email:
            return True

        return False


class GroupMigrationStrategy(MigrationStrategy):
    """Strategy for migrating groups."""

    async def migrate_entity(self, group: Group) -> MigrationResult:
        """Migrate a single group.

        Args:
            group: Group to migrate

        Returns:
            Migration result
        """
        self.logger.info(f'Migrating group: {group.path} (ID: {group.id})')

        try:
            # Check if group already exists
            existing_group = await self._find_existing_group(group)

            if existing_group:
                self.logger.info(f'Group {group.path} already exists in destination')
                self.context.migrated_groups[group.id] = existing_group.id

                # Still migrate members for existing groups
                await self._migrate_group_members(group.id, existing_group.id)

                return self.create_result(
                    entity_type='group',
                    entity_id=str(group.id),
                    status=MigrationStatus.SKIPPED,
                    success=True,
                    source_data=group.dict(),
                    destination_data=existing_group.dict(),
                    metadata={'reason': 'group_already_exists'},
                )

            if self.context.dry_run:
                self.logger.info(f'Dry run: Would create group {group.path}')
                # In dry run, also simulate member migration
                members = await self._get_group_members(group.id)
                return self.create_result(
                    entity_type='group',
                    entity_id=str(group.id),
                    status=MigrationStatus.COMPLETED,
                    success=True,
                    source_data=group.dict(),
                    metadata={
                        'dry_run': True,
                        'members_to_migrate': len(members),
                        'member_usernames': [
                            m.get('username', 'unknown') for m in members
                        ],
                    },
                )

            # Resolve parent group if needed
            parent_id = None
            if group.parent_id and group.parent_id in self.context.migrated_groups:
                parent_id = self.context.migrated_groups[group.parent_id]

            # Create group in destination
            group_create = GroupCreate(
                name=group.name,
                path=group.path,
                description=group.description,
                visibility=group.visibility,
                parent_id=parent_id,
            )

            response = self.context.destination_client.post(
                '/groups', data=group_create.dict(exclude_none=True)
            )

            if response.success:
                new_group_data = response.data
                new_group = Group(**new_group_data)
                self.context.migrated_groups[group.id] = new_group.id

                # Migrate group members after creating the group
                members_migrated = await self._migrate_group_members(
                    group.id, new_group.id
                )

                self.logger.info(
                    f'Successfully migrated group {group.path} -> ID {new_group.id} with {members_migrated} members'
                )
                return self.create_result(
                    entity_type='group',
                    entity_id=str(group.id),
                    status=MigrationStatus.COMPLETED,
                    success=True,
                    source_data=group.dict(),
                    destination_data=new_group.dict(),
                    metadata={'members_migrated': members_migrated},
                )
            else:
                error_msg = f'Failed to create group {group.path}: {response.data}'
                self.logger.error(error_msg)
                return self.create_result(
                    entity_type='group',
                    entity_id=str(group.id),
                    status=MigrationStatus.FAILED,
                    success=False,
                    error_message=error_msg,
                    source_data=group.dict(),
                )

        except Exception as e:
            error_msg = f'Error migrating group {group.path}: {str(e)}'
            self.logger.error(error_msg)
            return self.create_result(
                entity_type='group',
                entity_id=str(group.id),
                status=MigrationStatus.FAILED,
                success=False,
                error_message=error_msg,
                source_data=group.dict(),
            )

    async def migrate_batch(self, groups: List[Group]) -> List[MigrationResult]:
        """Migrate a batch of groups.

        Args:
            groups: List of groups to migrate

        Returns:
            List of migration results
        """
        results = []
        for group in groups:
            result = await self.migrate_entity(group)
            results.append(result)
        return results

    async def validate_prerequisites(self) -> bool:
        """Validate prerequisites for group migration.

        Returns:
            True if prerequisites are met, False otherwise
        """
        try:
            # Test destination client connectivity
            response = self.context.destination_client.get('/groups')
            return response.success

        except Exception as e:
            self.logger.error(f'Error validating group migration prerequisites: {e}')
            return False

    async def _find_existing_group(self, group: Group) -> Optional[Group]:
        """Find existing group in destination by path.

        Args:
            group: Group to search for

        Returns:
            Existing group if found, None otherwise
        """
        try:
            response = self.context.destination_client.get(f'/groups/{group.path}')
            if response.success:
                return Group(**response.data)
            return None

        except Exception as e:
            self.logger.warning(f'Error searching for existing group {group.path}: {e}')
            return None

    async def _get_group_members(self, source_group_id: int) -> List[Dict[str, Any]]:
        """Get group members from source GitLab instance.

        Args:
            source_group_id: Source group ID

        Returns:
            List of group member data
        """
        try:
            members_data = self.context.source_client.get_paginated(
                f'/groups/{source_group_id}/members'
            )
            return list(members_data)
        except Exception as e:
            self.logger.warning(
                f'Error fetching members for group {source_group_id}: {e}'
            )
            return []

    async def _migrate_group_members(
        self, source_group_id: int, destination_group_id: int
    ) -> int:
        """Migrate group members from source to destination.

        Args:
            source_group_id: Source group ID
            destination_group_id: Destination group ID

        Returns:
            Number of members successfully migrated
        """
        members_migrated = 0

        try:
            # Get group members from source
            source_members = await self._get_group_members(source_group_id)

            if not source_members:
                self.logger.info(f'No members found for group {source_group_id}')
                return 0

            self.logger.info(
                f'Migrating {len(source_members)} members for group {source_group_id}'
            )

            for member_data in source_members:
                try:
                    source_user_id = member_data.get('id')
                    access_level = member_data.get('access_level')
                    expires_at = member_data.get('expires_at')

                    if not source_user_id or not access_level:
                        self.logger.warning(f'Invalid member data: {member_data}')
                        continue

                    # Check if user was migrated
                    if source_user_id not in self.context.migrated_users:
                        self.logger.warning(
                            f'User {source_user_id} ({member_data.get("username", "unknown")}) '
                            f'not found in migrated users, skipping group membership'
                        )
                        continue

                    destination_user_id = self.context.migrated_users[source_user_id]

                    # Check if user is already a member of the destination group
                    if await self._is_user_group_member(
                        destination_group_id, destination_user_id
                    ):
                        self.logger.info(
                            f'User {destination_user_id} is already a member of group {destination_group_id}'
                        )
                        members_migrated += 1
                        continue

                    # Add user to destination group
                    member_add_data = {
                        'user_id': destination_user_id,
                        'access_level': access_level,
                    }

                    if expires_at:
                        member_add_data['expires_at'] = expires_at

                    response = self.context.destination_client.post(
                        f'/groups/{destination_group_id}/members', data=member_add_data
                    )

                    if response.success:
                        members_migrated += 1
                        self.logger.info(
                            f'Added user {destination_user_id} ({member_data.get("username", "unknown")}) '
                            f'to group {destination_group_id} with access level {access_level}'
                        )
                    else:
                        self.logger.warning(
                            f'Failed to add user {destination_user_id} to group {destination_group_id}: '
                            f'{response.data}'
                        )

                except Exception as e:
                    self.logger.error(
                        f'Error migrating group member {member_data}: {e}'
                    )
                    continue

        except Exception as e:
            self.logger.error(
                f'Error migrating members for group {source_group_id}: {e}'
            )

        return members_migrated

    async def _is_user_group_member(self, group_id: int, user_id: int) -> bool:
        """Check if user is already a member of the group.

        Args:
            group_id: Group ID
            user_id: User ID

        Returns:
            True if user is already a member
        """
        try:
            response = self.context.destination_client.get(
                f'/groups/{group_id}/members/{user_id}'
            )
            return response.success
        except Exception:
            return False

    async def _find_group_by_path(self, group_path: str) -> Optional[Group]:
        """Find existing group in destination by full path.

        Args:
            group_path: Full group path to search for

        Returns:
            Existing group if found, None otherwise
        """
        try:
            # Try to get group by full path
            response = self.context.destination_client.get(f'/groups/{group_path}')
            if response.success:
                return Group(**response.data)

            # If not found by direct path, try searching
            response = self.context.destination_client.get(
                '/groups', params={'search': group_path}
            )
            if response.success and response.data:
                for group_data in response.data:
                    if (
                        group_data.get('full_path') == group_path
                        or group_data.get('path') == group_path
                    ):
                        return Group(**group_data)

            return None

        except Exception as e:
            self.logger.warning(f'Error searching for group by path {group_path}: {e}')
            return None

    async def _find_existing_user_by_username(self, username: str) -> Optional[User]:
        """Find existing user in destination by username.

        Args:
            username: Username to search for

        Returns:
            Existing user if found, None otherwise
        """
        try:
            # Search by username
            response = self.context.destination_client.get(
                '/users', params={'username': username}
            )
            if response.success and response.data:
                for user_data in response.data:
                    if user_data.get('username') == username:
                        return User(**user_data)

            return None

        except Exception as e:
            self.logger.warning(
                f'Error searching for existing user by username {username}: {e}'
            )
            return None


class ProjectMigrationStrategy(MigrationStrategy):
    """Strategy for migrating projects."""

    async def migrate_entity(self, project: Project) -> MigrationResult:
        """Migrate a single project.

        Args:
            project: Project to migrate

        Returns:
            Migration result
        """
        self.logger.info(f'Migrating project: {project.path} (ID: {project.id})')

        try:
            if self.context.dry_run:
                self.logger.info(f'Dry run: Would create project {project.path}')
                return self.create_result(
                    entity_type='project',
                    entity_id=str(project.id),
                    status=MigrationStatus.COMPLETED,
                    success=True,
                    source_data=project.dict(),
                    metadata={'dry_run': True},
                )

            # Check if project already exists to avoid conflicts
            existing_project = await self._find_existing_project(project)
            if existing_project:
                self.logger.info(
                    f'Project {project.path} already exists in destination'
                )
                self.context.migrated_projects[project.id] = existing_project.id
                return self.create_result(
                    entity_type='project',
                    entity_id=str(project.id),
                    status=MigrationStatus.SKIPPED,
                    success=True,
                    source_data=project.dict(),
                    destination_data=existing_project.dict(),
                    metadata={'reason': 'project_already_exists'},
                )

            # Resolve namespace (group or user) with proper owner mapping
            namespace_id = await self._resolve_project_namespace(project)

            # If namespace resolution fails, skip this project
            if namespace_id is None and project.namespace:
                error_msg = f'Cannot resolve namespace for project {project.path}. Namespace owner not migrated.'
                self.logger.warning(error_msg)
                return self.create_result(
                    entity_type='project',
                    entity_id=str(project.id),
                    status=MigrationStatus.SKIPPED,
                    success=True,  # Mark as success since we're intentionally skipping
                    source_data=project.dict(),
                    metadata={
                        'reason': 'namespace_owner_not_migrated',
                        'skip_reason': 'missing_namespace_owner',
                    },
                    warnings=[error_msg],
                )

            # Check if we need to generate a unique path to avoid disk conflicts
            project_path = project.path
            project_name = project.name

            # Only generate unique path if there's a conflict
            if await self._path_exists_in_destination(project.path, project.namespace):
                self.logger.info(
                    f'Project path {project.path} exists, generating unique path'
                )
                project_path = await self._generate_unique_project_path(project)

                # If path was changed, also update the project name to match
                if project_path != project.path:
                    # Extract the suffix from the unique path
                    suffix = (
                        project_path[len(project.path) + 1 :]
                        if len(project_path) > len(project.path)
                        else project_path.split('-')[-1]
                    )
                    project_name = f'{project.name}-{suffix}'
                    self.logger.info(
                        f'Generated unique project name: {project.name} -> {project_name}'
                    )
            else:
                self.logger.info(f'Using original project path: {project.path}')

            project_create = ProjectCreate(
                name=project_name,
                path=project_path,
                namespace_id=namespace_id,
                description=project.description,
                visibility=project.visibility,
                issues_enabled=project.issues_enabled or True,
                merge_requests_enabled=project.merge_requests_enabled or True,
                wiki_enabled=project.wiki_enabled or True,
                jobs_enabled=project.jobs_enabled or True,
                snippets_enabled=project.snippets_enabled or True,
            )

            response = self.context.destination_client.post(
                '/projects', data=project_create.dict(exclude_none=True)
            )

            if response.success:
                new_project_data = response.data
                new_project = Project(**new_project_data)
                self.context.migrated_projects[project.id] = new_project.id

                # Migrate project members after creating the project
                members_migrated = await self._migrate_project_members(
                    project.id, new_project.id
                )

                # Set the correct owner if different from namespace owner
                await self._set_project_owner(project, new_project.id)

                self.logger.info(
                    f'Successfully migrated project {project.path} -> ID {new_project.id} with {members_migrated} members'
                )
                return self.create_result(
                    entity_type='project',
                    entity_id=str(project.id),
                    status=MigrationStatus.COMPLETED,
                    success=True,
                    source_data=project.dict(),
                    destination_data=new_project.dict(),
                    metadata={'members_migrated': members_migrated},
                )
            else:
                # Check for repository disk conflict error
                if self._is_repository_disk_conflict(response.data):
                    error_msg = f'Repository disk conflict for project {project.path}: {response.data}'
                    self.logger.warning(
                        f'Skipping project due to disk conflict: {project.path}'
                    )
                    return self.create_result(
                        entity_type='project',
                        entity_id=str(project.id),
                        status=MigrationStatus.SKIPPED,
                        success=True,  # Mark as success since we're intentionally skipping
                        source_data=project.dict(),
                        metadata={
                            'reason': 'repository_disk_conflict',
                            'skip_reason': 'disk_conflict',
                        },
                        warnings=[error_msg],
                    )
                else:
                    error_msg = (
                        f'Failed to create project {project.path}: {response.data}'
                    )
                    self.logger.error(error_msg)
                    return self.create_result(
                        entity_type='project',
                        entity_id=str(project.id),
                        status=MigrationStatus.FAILED,
                        success=False,
                        error_message=error_msg,
                        source_data=project.dict(),
                    )

        except Exception as e:
            error_msg = f'Error migrating project {project.path}: {str(e)}'
            self.logger.error(error_msg)
            return self.create_result(
                entity_type='project',
                entity_id=str(project.id),
                status=MigrationStatus.FAILED,
                success=False,
                error_message=error_msg,
                source_data=project.dict(),
            )

    async def migrate_batch(self, projects: List[Project]) -> List[MigrationResult]:
        """Migrate a batch of projects.

        Args:
            projects: List of projects to migrate

        Returns:
            List of migration results
        """
        results = []
        for project in projects:
            result = await self.migrate_entity(project)
            results.append(result)
        return results

    async def validate_prerequisites(self) -> bool:
        """Validate prerequisites for project migration.

        Returns:
            True if prerequisites are met, False otherwise
        """
        try:
            # Test destination client connectivity
            response = self.context.destination_client.get('/projects')
            return response.success

        except Exception as e:
            self.logger.error(f'Error validating project migration prerequisites: {e}')
            return False

    async def _find_existing_project(self, project: Project) -> Optional[Project]:
        """Find existing project in destination by path and namespace.

        Args:
            project: Project to search for

        Returns:
            Existing project if found, None otherwise
        """
        try:
            # Try to find project by full path (namespace/project)
            if project.namespace and project.namespace.get('path'):
                full_path = f'{project.namespace["path"]}/{project.path}'
                response = self.context.destination_client.get(
                    f'/projects/{full_path.replace("/", "%2F")}'
                )
                if response.success:
                    return Project(**response.data)

            # Search by project path only
            response = self.context.destination_client.get(
                '/projects', params={'search': project.path}
            )
            if response.success and response.data:
                for project_data in response.data:
                    if project_data.get('path') == project.path:
                        return Project(**project_data)

            return None

        except Exception as e:
            # Only log as warning if it's not a "Resource not found" error
            error_str = str(e).lower()
            if 'resource not found' not in error_str and '404' not in error_str:
                self.logger.warning(
                    f'Error searching for existing project {project.path}: {e}'
                )
            else:
                self.logger.debug(
                    f'Project {project.path} not found in destination (expected for new projects)'
                )
            return None

    async def _resolve_project_namespace(self, project: Project) -> Optional[int]:
        """Resolve the namespace ID for the project, handling user-owned projects.

        Args:
            project: Project to resolve namespace for

        Returns:
            Namespace ID for the destination, or None for root namespace
        """
        try:
            if not project.namespace:
                return None

            namespace_data = project.namespace
            namespace_kind = namespace_data.get('kind', 'user')
            source_namespace_id = namespace_data.get('id')
            namespace_path = namespace_data.get('path', '')
            namespace_full_path = namespace_data.get('full_path', namespace_path)

            self.logger.info(
                f'Resolving namespace for project {project.path}: '
                f'kind={namespace_kind}, id={source_namespace_id}, '
                f'path={namespace_path}, full_path={namespace_full_path}'
            )

            if namespace_kind == 'group':
                # Handle group projects - use existing group mapping logic
                if source_namespace_id in self.context.migrated_groups:
                    destination_group_id = self.context.migrated_groups[
                        source_namespace_id
                    ]
                    self.logger.info(
                        f'Found migrated group mapping: {source_namespace_id} -> {destination_group_id}'
                    )
                    return destination_group_id
                else:
                    # Try to find the group by path in destination
                    destination_group = await self._find_group_by_path(
                        namespace_full_path
                    )
                    if destination_group:
                        self.logger.info(
                            f'Found existing group by path: {namespace_full_path} -> {destination_group.id}'
                        )
                        # Update the mapping for future use
                        if (
                            destination_group.id is not None
                            and source_namespace_id is not None
                        ):
                            self.context.migrated_groups[source_namespace_id] = (
                                destination_group.id
                            )
                        return destination_group.id
                    else:
                        self.logger.warning(
                            f'Group namespace {source_namespace_id} ({namespace_full_path}) not found in migrated groups for project {project.path}'
                        )
                        return None
            else:
                # Handle user-owned projects - map to migrated user
                if source_namespace_id in self.context.migrated_users:
                    destination_user_id = self.context.migrated_users[
                        source_namespace_id
                    ]

                    # Get the user's namespace ID in destination
                    user_namespace_id = await self._get_user_namespace_id(
                        destination_user_id
                    )
                    if user_namespace_id:
                        self.logger.info(
                            f'Mapped user-owned project {project.path} to user namespace {user_namespace_id}'
                        )
                        return user_namespace_id
                    else:
                        self.logger.warning(
                            f'Could not find namespace for migrated user {destination_user_id} for project {project.path}'
                        )
                        return None
                else:
                    # User not in migrated_users - try to find existing user in destination by username
                    self.logger.info(
                        f'User namespace {source_namespace_id} not found in migrated users, searching for existing user by path: {namespace_path}'
                    )

                    existing_user = await self._find_existing_user_by_username(
                        namespace_path
                    )
                    if existing_user:
                        self.logger.info(
                            f'Found existing user {namespace_path} in destination with ID {existing_user.id}'
                        )
                        # Update the mapping for future use - ensure source_namespace_id is not None
                        if source_namespace_id is not None:
                            self.context.migrated_users[source_namespace_id] = (
                                existing_user.id
                            )

                        # Get the user's namespace ID in destination
                        user_namespace_id = await self._get_user_namespace_id(
                            existing_user.id
                        )
                        if user_namespace_id:
                            self.logger.info(
                                f'Mapped user-owned project {project.path} to existing user namespace {user_namespace_id}'
                            )
                            return user_namespace_id
                        else:
                            self.logger.warning(
                                f'Could not find namespace for existing user {existing_user.id} for project {project.path}'
                            )
                            return None
                    else:
                        self.logger.warning(
                            f'User namespace {source_namespace_id} ({namespace_path}) not found in migrated users and does not exist in destination for project {project.path}'
                        )
                        return None

        except Exception as e:
            self.logger.error(
                f'Error resolving namespace for project {project.path}: {e}'
            )
            return None

    async def _get_user_namespace_id(self, user_id: int) -> Optional[int]:
        """Get the namespace ID for a user.

        Args:
            user_id: User ID in destination GitLab

        Returns:
            User's namespace ID, or None if not found
        """
        try:
            # Get user details to find their namespace
            response = self.context.destination_client.get(f'/users/{user_id}')
            if response.success:
                user_data = response.data
                # In GitLab, user's namespace ID is typically the same as user ID
                # but we should check if there's a specific namespace field
                return user_data.get('namespace_id', user_id)

            return None

        except Exception as e:
            self.logger.warning(f'Error getting namespace for user {user_id}: {e}')
            return None

    def _is_repository_disk_conflict(self, error_data: Any) -> bool:
        """Check if the error indicates a repository disk conflict.

        Args:
            error_data: Error response data from GitLab API

        Returns:
            True if this is a repository disk conflict error
        """
        try:
            # Handle different error data formats
            error_str = str(error_data).lower()

            # Handle structured error responses (dict format)
            if isinstance(error_data, dict):
                # Check for base errors
                if 'base' in error_data and isinstance(error_data['base'], list):
                    for error_msg in error_data['base']:
                        if 'repository' in str(error_msg).lower() and (
                            'disk' in str(error_msg).lower()
                            or 'already' in str(error_msg).lower()
                        ):
                            return True

                # Check for path errors
                if 'path' in error_data and isinstance(error_data['path'], list):
                    for error_msg in error_data['path']:
                        if (
                            'taken' in str(error_msg).lower()
                            or 'already' in str(error_msg).lower()
                        ):
                            return True

            # Check for common disk conflict error patterns in string format
            disk_conflict_patterns = [
                'there is already a repository with that name on disk',
                'repository with that name on disk',
                'uncaught throw :abort',
                'repository already exists on disk',
                'disk conflict',
                'repository path conflict',
                'path has already been taken',
                'has already been taken',
                'repository storage path',
                'storage path conflict',
                'name can contain only',
                'name is too long',
                'invalid path',
            ]

            return any(pattern in error_str for pattern in disk_conflict_patterns)

        except Exception:
            return False

    async def _get_project_members(
        self, source_project_id: int
    ) -> List[Dict[str, Any]]:
        """Get project members from source GitLab instance.

        Args:
            source_project_id: Source project ID

        Returns:
            List of project member data
        """
        try:
            members_data = self.context.source_client.get_paginated(
                f'/projects/{source_project_id}/members'
            )
            return list(members_data)
        except Exception as e:
            self.logger.warning(
                f'Error fetching members for project {source_project_id}: {e}'
            )
            return []

    async def _migrate_project_members(
        self, source_project_id: int, destination_project_id: int
    ) -> int:
        """Migrate project members from source to destination.

        Args:
            source_project_id: Source project ID
            destination_project_id: Destination project ID

        Returns:
            Number of members successfully migrated
        """
        members_migrated = 0

        try:
            # Get project members from source
            source_members = await self._get_project_members(source_project_id)

            if not source_members:
                self.logger.info(f'No members found for project {source_project_id}')
                return 0

            self.logger.info(
                f'Migrating {len(source_members)} members for project {source_project_id}'
            )

            for member_data in source_members:
                try:
                    source_user_id = member_data.get('id')
                    access_level = member_data.get('access_level')
                    expires_at = member_data.get('expires_at')

                    if not source_user_id or not access_level:
                        self.logger.warning(f'Invalid member data: {member_data}')
                        continue

                    # Check if user was migrated
                    if source_user_id not in self.context.migrated_users:
                        self.logger.warning(
                            f'User {source_user_id} ({member_data.get("username", "unknown")}) '
                            f'not found in migrated users, skipping project membership'
                        )
                        continue

                    destination_user_id = self.context.migrated_users[source_user_id]

                    # Check if user is already a member of the destination project
                    member_info = await self._get_user_project_member_info(
                        destination_project_id, destination_user_id
                    )
                    if member_info:
                        current_access_level = member_info.get('access_level', 0)
                        source_access_level = access_level

                        # Check if user has inherited permissions that are higher or equal
                        if member_info.get('created_at') and member_info.get(
                            'created_by'
                        ):
                            # This is an inherited membership, check if we need to update
                            self.logger.info(
                                f'User {destination_user_id} has inherited membership in project {destination_project_id} '
                                f'with access level {current_access_level}'
                            )

                            # Only attempt to update if the source access level is higher
                            if source_access_level > current_access_level:
                                # Try to update the access level
                                update_response = self.context.destination_client.put(
                                    f'/projects/{destination_project_id}/members/{destination_user_id}',
                                    data={'access_level': source_access_level},
                                )

                                if update_response.success:
                                    members_migrated += 1
                                    self.logger.info(
                                        f'Updated user {destination_user_id} access level from {current_access_level} to {source_access_level} '
                                        f'in project {destination_project_id}'
                                    )
                                else:
                                    self.logger.warning(
                                        f'Failed to update user {destination_user_id} access level in project {destination_project_id}: '
                                        f'{update_response.data}'
                                    )
                            else:
                                self.logger.info(
                                    f'User {destination_user_id} already has sufficient access level ({current_access_level}) '
                                    f'in project {destination_project_id}, skipping update'
                                )
                                members_migrated += 1
                        else:
                            self.logger.info(
                                f'User {destination_user_id} is already a member of project {destination_project_id} '
                                f'with access level {current_access_level}'
                            )
                            members_migrated += 1
                        continue

                    # Add user to destination project
                    member_add_data = {
                        'user_id': destination_user_id,
                        'access_level': access_level,
                    }

                    if expires_at:
                        member_add_data['expires_at'] = expires_at

                    response = self.context.destination_client.post(
                        f'/projects/{destination_project_id}/members',
                        data=member_add_data,
                    )

                    if response.success:
                        members_migrated += 1
                        self.logger.info(
                            f'Added user {destination_user_id} ({member_data.get("username", "unknown")}) '
                            f'to project {destination_project_id} with access level {access_level}'
                        )
                    else:
                        # Handle specific case of inherited permissions
                        error_data = response.data
                        if (
                            isinstance(error_data, dict)
                            and 'access_level' in error_data
                        ):
                            error_messages = error_data.get('access_level', [])
                            if any(
                                'greater than or equal to Maintainer inherited membership'
                                in str(msg)
                                for msg in error_messages
                            ):
                                self.logger.warning(
                                    f'User {destination_user_id} has inherited permissions that prevent setting access level {access_level}. '
                                    f'This is expected behavior when user has higher inherited permissions.'
                                )
                                members_migrated += 1  # Count as migrated since it's handled by inheritance
                                continue

                        self.logger.warning(
                            f'Failed to add user {destination_user_id} to project {destination_project_id}: '
                            f'{response.data}'
                        )

                except Exception as e:
                    self.logger.error(
                        f'Error migrating project member {member_data}: {e}'
                    )
                    continue

        except Exception as e:
            self.logger.error(
                f'Error migrating members for project {source_project_id}: {e}'
            )

        return members_migrated

    async def _is_user_project_member(self, project_id: int, user_id: int) -> bool:
        """Check if user is already a member of the project.

        Args:
            project_id: Project ID
            user_id: User ID

        Returns:
            True if user is already a member
        """
        try:
            response = self.context.destination_client.get(
                f'/projects/{project_id}/members/{user_id}'
            )
            return response.success
        except Exception:
            return False

    async def _get_user_project_member_info(
        self, project_id: int, user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get detailed information about a user's project membership.

        Args:
            project_id: Project ID
            user_id: User ID

        Returns:
            Member information if user is a member, None otherwise
        """
        try:
            response = self.context.destination_client.get(
                f'/projects/{project_id}/members/{user_id}'
            )
            if response.success:
                return response.data
            return None
        except Exception:
            return None

    async def _set_project_owner(
        self, source_project: Project, destination_project_id: int
    ) -> None:
        """Set the correct project owner based on source project information.

        Args:
            source_project: Source project data
            destination_project_id: Destination project ID
        """
        try:
            # Get the source project's owner information
            source_owner_id = None

            # Check for creator_id field
            if source_project.creator_id:
                source_owner_id = source_project.creator_id
            # Check for owner in namespace (for user-owned projects)
            elif (
                source_project.namespace
                and source_project.namespace.get('kind') == 'user'
            ):
                source_owner_id = source_project.namespace.get('id')

            if not source_owner_id:
                self.logger.debug(
                    f'No specific owner found for project {source_project.path}'
                )
                return

            # Check if the owner was migrated
            if source_owner_id not in self.context.migrated_users:
                self.logger.warning(
                    f'Project owner {source_owner_id} not found in migrated users for project {source_project.path}'
                )
                return

            destination_owner_id = self.context.migrated_users[source_owner_id]

            # Try to set the project owner by adding them as owner if not already
            try:
                # First check if they're already an owner
                response = self.context.destination_client.get(
                    f'/projects/{destination_project_id}/members/{destination_owner_id}'
                )

                if response.success:
                    current_access_level = response.data.get('access_level', 0)
                    if current_access_level >= 50:  # Already owner (50) or higher
                        self.logger.info(
                            f'User {destination_owner_id} is already owner of project {destination_project_id}'
                        )
                        return
                    else:
                        # Update access level to owner
                        update_response = self.context.destination_client.put(
                            f'/projects/{destination_project_id}/members/{destination_owner_id}',
                            data={'access_level': 50},
                        )
                        if update_response.success:
                            self.logger.info(
                                f'Updated user {destination_owner_id} to owner of project {destination_project_id}'
                            )
                        else:
                            self.logger.warning(
                                f'Failed to update user {destination_owner_id} to owner: {update_response.data}'
                            )
                else:
                    # Add as owner
                    add_response = self.context.destination_client.post(
                        f'/projects/{destination_project_id}/members',
                        data={'user_id': destination_owner_id, 'access_level': 50},
                    )
                    if add_response.success:
                        self.logger.info(
                            f'Added user {destination_owner_id} as owner of project {destination_project_id}'
                        )
                    else:
                        self.logger.warning(
                            f'Failed to add user {destination_owner_id} as owner: {add_response.data}'
                        )

            except Exception as e:
                self.logger.warning(f'Error setting project owner: {e}')

        except Exception as e:
            self.logger.error(f'Error in _set_project_owner: {e}')

    async def _generate_unique_project_path(self, project: Project) -> str:
        """Generate a unique project path to avoid repository disk conflicts.

        Only generates a unique path when necessary to avoid disk conflicts.

        Args:
            project: Source project

        Returns:
            Project path (potentially unique) for destination
        """
        try:
            original_path = project.path

            # First check if the original path already exists
            if not await self._path_exists_in_destination(
                original_path, project.namespace
            ):
                # Path doesn't exist, use original path
                self.logger.info(
                    f'Using original project path (no conflict): {original_path}'
                )
                return original_path

            # Path exists, generate a unique suffix to avoid disk conflicts
            # GitLab disk conflicts can happen even when projects don't exist in API
            max_attempts = 10
            for attempt in range(max_attempts):
                timestamp = int(time.time() % 10000)  # Last 4 digits of timestamp
                random_suffix = ''.join(random.choices(string.ascii_lowercase, k=4))
                unique_suffix = f'{timestamp}{random_suffix}'
                unique_path = f'{original_path}-{unique_suffix}'

                # Check if the generated unique path also exists (should be rare but possible)
                if not await self._path_exists_in_destination(
                    unique_path, project.namespace
                ):
                    self.logger.info(
                        f'Generated unique project path to avoid disk conflicts: {original_path} -> {unique_path}'
                    )
                    return unique_path

            # If we couldn't generate a unique path after max attempts, use timestamp + attempt
            timestamp_full = int(time.time())
            fallback_path = f'{original_path}-{timestamp_full}'
            self.logger.warning(
                f'Using fallback unique path after {max_attempts} attempts: {original_path} -> {fallback_path}'
            )
            return fallback_path

        except Exception as e:
            self.logger.error(
                f'CRITICAL ERROR: Failed to generate unique project path for {project.path}: {e}'
            )
            # Fallback to timestamp-based path
            timestamp = int(time.time())
            fallback_path = f'{project.path}-{timestamp}'
            return fallback_path

    async def _path_exists_in_destination(
        self, path: str, namespace: Optional[Dict[str, Any]]
    ) -> bool:
        """Check if a project path already exists in the destination.

        Args:
            path: Project path to check
            namespace: Project namespace information

        Returns:
            True if path exists, False otherwise
        """
        try:
            # Try to find project by full path (namespace/project)
            if namespace and namespace.get('path'):
                full_path = f'{namespace["path"]}/{path}'
                response = self.context.destination_client.get(
                    f'/projects/{full_path.replace("/", "%2F")}'
                )
                if response.success:
                    self.logger.debug(
                        f'Found existing project by full path: {full_path}'
                    )
                    return True

            # Search by project path only
            response = self.context.destination_client.get(
                '/projects', params={'search': path}
            )
            if response.success and response.data:
                for project_data in response.data:
                    if project_data.get('path') == path:
                        self.logger.debug(
                            f'Found existing project by path search: {path}'
                        )
                        return True

            self.logger.debug(f'Project path does not exist in destination: {path}')
            return False

        except Exception as e:
            self.logger.warning(f'Error checking if path {path} exists: {e}')
            # If we can't check, assume it doesn't exist to avoid blocking migration
            return False

    async def _find_group_by_path(self, group_path: str) -> Optional[Group]:
        """Find existing group in destination by full path.

        Args:
            group_path: Full group path to search for

        Returns:
            Existing group if found, None otherwise
        """
        try:
            # Try to get group by full path
            response = self.context.destination_client.get(f'/groups/{group_path}')
            if response.success:
                return Group(**response.data)

            # If not found by direct path, try searching
            response = self.context.destination_client.get(
                '/groups', params={'search': group_path}
            )
            if response.success and response.data:
                for group_data in response.data:
                    if (
                        group_data.get('full_path') == group_path
                        or group_data.get('path') == group_path
                    ):
                        return Group(**group_data)

            return None

        except Exception as e:
            self.logger.warning(f'Error searching for group by path {group_path}: {e}')
            return None

    async def _find_existing_user_by_username(self, username: str) -> Optional[User]:
        """Find existing user in destination by username.

        Args:
            username: Username to search for

        Returns:
            Existing user if found, None otherwise
        """
        try:
            # Search by username
            response = self.context.destination_client.get(
                '/users', params={'username': username}
            )
            if response.success and response.data:
                for user_data in response.data:
                    if user_data.get('username') == username:
                        return User(**user_data)

            return None

        except Exception as e:
            self.logger.warning(
                f'Error searching for existing user by username {username}: {e}'
            )
            return None


class RepositoryMigrationStrategy(MigrationStrategy):
    """Strategy for migrating repositories."""

    def __init__(self, context: MigrationContext, git_config=None):
        """Initialize repository migration strategy.

        Args:
            context: Migration context with clients and settings
            git_config: Git configuration (optional, will use defaults if not provided)
        """
        super().__init__(context)

        # Import here to avoid circular imports
        from ..git.operations import GitOperations
        from ..config.config import GitConfig

        # Use provided git_config or create default one
        if git_config is None:
            git_config = GitConfig(lfs_enabled=True, cleanup_temp=True, timeout=3600)

        self.git_operations = GitOperations(
            source_client=context.source_client,
            destination_client=context.destination_client,
            config=git_config,
        )

    async def migrate_entity(self, repository: Repository) -> MigrationResult:
        """Migrate a single repository.

        Args:
            repository: Repository to migrate

        Returns:
            Migration result
        """
        self.logger.info(
            f'Migrating repository for project ID: {repository.project_id}'
        )

        try:
            if self.context.dry_run:
                self.logger.info(
                    f'Dry run: Would migrate repository for project {repository.project_id}'
                )
                return self.create_result(
                    entity_type='repository',
                    entity_id=str(repository.project_id),
                    status=MigrationStatus.COMPLETED,
                    success=True,
                    source_data=repository.dict(),
                    metadata={'dry_run': True},
                )

            # Check if project was migrated
            if repository.project_id not in self.context.migrated_projects:
                error_msg = (
                    f'Project {repository.project_id} not found in migrated projects'
                )
                self.logger.error(error_msg)
                return self.create_result(
                    entity_type='repository',
                    entity_id=str(repository.project_id),
                    status=MigrationStatus.FAILED,
                    success=False,
                    error_message=error_msg,
                    source_data=repository.dict(),
                )

            destination_project_id = self.context.migrated_projects[
                repository.project_id
            ]

            # Perform actual Git repository migration
            migration_result = await self.git_operations.migrate_repository(
                source_project_id=repository.project_id,
                destination_project_id=destination_project_id,
                repository=repository,
            )

            if migration_result.success:
                self.logger.info(
                    f'Repository migration completed successfully: '
                    f'{repository.project_id} -> {destination_project_id}'
                )

                return self.create_result(
                    entity_type='repository',
                    entity_id=str(repository.project_id),
                    status=MigrationStatus.COMPLETED,
                    success=True,
                    source_data=repository.dict(),
                    metadata={
                        'destination_project_id': destination_project_id,
                        'branches_migrated': migration_result.branches_migrated,
                        'tags_migrated': migration_result.tags_migrated,
                        'commits_migrated': migration_result.commits_migrated,
                        'lfs_objects_migrated': migration_result.lfs_objects_migrated,
                        'repository_size_bytes': migration_result.repository_size_bytes,
                        'lfs_size_bytes': migration_result.lfs_size_bytes,
                        'migration_method': migration_result.migration_method,
                    },
                )
            else:
                error_msg = f'Git repository migration failed: {"; ".join(migration_result.errors)}'
                warnings = migration_result.warnings

                self.logger.error(error_msg)
                if warnings:
                    for warning in warnings:
                        self.logger.warning(warning)

                return self.create_result(
                    entity_type='repository',
                    entity_id=str(repository.project_id),
                    status=MigrationStatus.FAILED,
                    success=False,
                    error_message=error_msg,
                    source_data=repository.dict(),
                    warnings=warnings,
                )

        except Exception as e:
            error_msg = f'Error migrating repository for project {repository.project_id}: {str(e)}'
            self.logger.error(error_msg)
            return self.create_result(
                entity_type='repository',
                entity_id=str(repository.project_id),
                status=MigrationStatus.FAILED,
                success=False,
                error_message=error_msg,
                source_data=repository.dict(),
            )

    async def migrate_batch(
        self, repositories: List[Repository]
    ) -> List[MigrationResult]:
        """Migrate a batch of repositories.

        Args:
            repositories: List of repositories to migrate

        Returns:
            List of migration results
        """
        results = []
        for repository in repositories:
            result = await self.migrate_entity(repository)
            results.append(result)
        return results

    async def validate_prerequisites(self) -> bool:
        """Validate prerequisites for repository migration.

        Returns:
            True if prerequisites are met, False otherwise
        """
        try:
            # Test both source and destination connectivity
            source_response = self.context.source_client.get('/projects')
            dest_response = self.context.destination_client.get('/projects')

            return source_response.success and dest_response.success

        except Exception as e:
            self.logger.error(
                f'Error validating repository migration prerequisites: {e}'
            )
            return False
