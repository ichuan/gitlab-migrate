"""Migration strategy interfaces and implementations."""

import asyncio
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
    batch_size: int = Field(default=5, description='Batch size for processing')
    max_workers: int = Field(default=20, description='Maximum concurrent workers')

    # Performance batch size settings
    user_batch_size: int = Field(default=5, description='Concurrent users to process')
    group_batch_size: int = Field(default=5, description='Concurrent groups to process')
    project_batch_size: int = Field(
        default=5, description='Concurrent projects to process'
    )
    member_batch_size: int = Field(
        default=5, description='Concurrent members to process'
    )

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

    async def _find_user(
        self,
        search_value: str,
        search_type: str = 'email_or_username',
        user_obj: Optional[User] = None,
    ) -> Optional[User]:
        """Find existing user in destination by various search criteria.

        Args:
            search_value: Value to search for (email, username, etc.)
            search_type: Type of search ('email', 'username', 'email_or_username')
            user_obj: Optional User object for email_or_username search

        Returns:
            Existing user if found, None otherwise
        """
        try:
            if search_type == 'email_or_username' and user_obj:
                # Search by email first
                response = await self.context.destination_client.get_async(
                    '/users', params={'search': user_obj.email}
                )
                if response.success and response.data:
                    for user_data in response.data:
                        if user_data.get('email') == user_obj.email:
                            return User(**user_data)

                # Search by username
                response = await self.context.destination_client.get_async(
                    '/users', params={'username': user_obj.username}
                )
                if response.success and response.data:
                    for user_data in response.data:
                        if user_data.get('username') == user_obj.username:
                            return User(**user_data)

            elif search_type == 'email':
                response = await self.context.destination_client.get_async(
                    '/users', params={'search': search_value}
                )
                if response.success and response.data:
                    for user_data in response.data:
                        if user_data.get('email') == search_value:
                            return User(**user_data)

            elif search_type == 'username':
                response = await self.context.destination_client.get_async(
                    '/users', params={'username': search_value}
                )
                if response.success and response.data:
                    for user_data in response.data:
                        if user_data.get('username') == search_value:
                            return User(**user_data)

            return None

        except Exception as e:
            self.logger.warning(
                f'Error searching for user {search_value} ({search_type}): {e}'
            )
            return None


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

            response = await self.context.destination_client.post_async(
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
        """Migrate a batch of users concurrently.

        Args:
            users: List of users to migrate

        Returns:
            List of migration results
        """
        # Process all users concurrently without sub-batching
        batch_tasks = [self.migrate_entity(user) for user in users]
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

        all_results = []
        # Handle results and exceptions
        for result in batch_results:
            if isinstance(result, Exception):
                # Create a failed result for the exception
                error_result = self.create_result(
                    entity_type='user',
                    entity_id='unknown',
                    status=MigrationStatus.FAILED,
                    success=False,
                    error_message=str(result),
                )
                all_results.append(error_result)
            else:
                all_results.append(result)

        return all_results

    async def validate_prerequisites(self) -> bool:
        """Validate prerequisites for user migration.

        Returns:
            True if prerequisites are met, False otherwise
        """
        try:
            # Test destination client connectivity and permissions
            response = await self.context.destination_client.get_async('/user')
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
        return await self._find_user('', 'email_or_username', user)

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
            if group.parent_id:
                if group.parent_id in self.context.migrated_groups:
                    parent_id = self.context.migrated_groups[group.parent_id]
                    self.logger.info(
                        f'Found migrated parent group: {group.parent_id} -> {parent_id}'
                    )
                else:
                    # Try to find parent group by path in destination
                    parent_group = await self._find_parent_group_in_destination(group)
                    if parent_group:
                        parent_id = parent_group.id
                        # Update the mapping for future use
                        self.context.migrated_groups[group.parent_id] = parent_group.id
                        self.logger.info(
                            f'Found existing parent group in destination: {group.parent_id} -> {parent_id}'
                        )
                    else:
                        self.logger.warning(
                            f'Parent group {group.parent_id} not found for sub-group {group.path}. Creating as root-level group.'
                        )

            # Create group in destination
            group_create = GroupCreate(
                name=group.name,
                path=group.path,
                description=group.description,
                visibility=group.visibility,
                parent_id=parent_id,
            )

            response = await self.context.destination_client.post_async(
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
        """Migrate a batch of groups concurrently.

        Args:
            groups: List of groups to migrate

        Returns:
            List of migration results
        """
        # Process all groups concurrently without sub-batching
        batch_tasks = [self.migrate_entity(group) for group in groups]
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

        all_results = []
        # Handle results and exceptions
        for result in batch_results:
            if isinstance(result, Exception):
                # Create a failed result for the exception
                error_result = self.create_result(
                    entity_type='group',
                    entity_id='unknown',
                    status=MigrationStatus.FAILED,
                    success=False,
                    error_message=str(result),
                )
                all_results.append(error_result)
            else:
                all_results.append(result)

        return all_results

    async def validate_prerequisites(self) -> bool:
        """Validate prerequisites for group migration.

        Returns:
            True if prerequisites are met, False otherwise
        """
        try:
            # Test destination client connectivity
            response = await self.context.destination_client.get_async('/groups')
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
            # First try to find by full path if available
            if group.full_path:
                # URL encode the full path to handle special characters and slashes
                encoded_full_path = group.full_path.replace('/', '%2F')
                response = await self.context.destination_client.get_async(
                    f'/groups/{encoded_full_path}'
                )
                if response.success:
                    return Group(**response.data)

            # Then try by path only (for root-level groups)
            response = await self.context.destination_client.get_async(
                f'/groups/{group.path}'
            )
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
        """Migrate group members from source to destination using batch processing.

        Args:
            source_group_id: Source group ID
            destination_group_id: Destination group ID

        Returns:
            Number of members successfully migrated
        """
        try:
            # Get group members from source
            source_members = await self._get_group_members(source_group_id)

            if not source_members:
                self.logger.info(f'No members found for group {source_group_id}')
                return 0

            self.logger.info(
                f'Migrating {len(source_members)} members for group {source_group_id}'
            )

            # Process members in batches for better performance
            batch_size = getattr(
                self.context, 'member_batch_size', 20
            )  # Use configurable batch size
            members_migrated = 0

            # Split members into batches
            member_batches = [
                source_members[i : i + batch_size]
                for i in range(0, len(source_members), batch_size)
            ]

            for batch in member_batches:
                # Process batch concurrently
                batch_tasks = []
                for member_data in batch:
                    task = self._migrate_single_group_member(
                        member_data, destination_group_id
                    )
                    batch_tasks.append(task)

                # Wait for all members in batch to complete
                batch_results = await asyncio.gather(
                    *batch_tasks, return_exceptions=True
                )

                # Count successful migrations
                for result in batch_results:
                    if isinstance(result, bool) and result:
                        members_migrated += 1
                    elif isinstance(result, Exception):
                        self.logger.error(f'Batch member migration error: {result}')

            return members_migrated

        except Exception as e:
            self.logger.error(
                f'Error migrating members for group {source_group_id}: {e}'
            )
            return 0

    async def _migrate_single_group_member(
        self, member_data: Dict[str, Any], destination_group_id: int
    ) -> bool:
        """Migrate a single group member.

        Args:
            member_data: Member data from source
            destination_group_id: Destination group ID

        Returns:
            True if migration was successful
        """
        try:
            source_user_id = member_data.get('id')
            access_level = member_data.get('access_level')
            expires_at = member_data.get('expires_at')

            if not source_user_id or not access_level:
                self.logger.warning(f'Invalid member data: {member_data}')
                return False

            # Check if user was migrated
            if source_user_id not in self.context.migrated_users:
                self.logger.warning(
                    f'User {source_user_id} ({member_data.get("username", "unknown")}) '
                    f'not found in migrated users, skipping group membership'
                )
                return False

            destination_user_id = self.context.migrated_users[source_user_id]

            # Check if user is already a member of the destination group
            if await self._is_user_group_member(
                destination_group_id, destination_user_id
            ):
                self.logger.debug(
                    f'User {destination_user_id} is already a member of group {destination_group_id}'
                )
                return True

            # Add user to destination group
            member_add_data = {
                'user_id': destination_user_id,
                'access_level': access_level,
            }

            if expires_at:
                member_add_data['expires_at'] = expires_at

            response = await self.context.destination_client.post_async(
                f'/groups/{destination_group_id}/members', data=member_add_data
            )

            if response.success:
                self.logger.debug(
                    f'Added user {destination_user_id} ({member_data.get("username", "unknown")}) '
                    f'to group {destination_group_id} with access level {access_level}'
                )
                return True
            else:
                self.logger.warning(
                    f'Failed to add user {destination_user_id} to group {destination_group_id}: '
                    f'{response.data}'
                )
                return False

        except Exception as e:
            self.logger.error(f'Error migrating group member {member_data}: {e}')
            return False

    async def _is_user_group_member(self, group_id: int, user_id: int) -> bool:
        """Check if user is already a member of the group.

        Args:
            group_id: Group ID
            user_id: User ID

        Returns:
            True if user is already a member
        """
        try:
            response = await self.context.destination_client.get_async(
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
            # Try to get group by full path with proper URL encoding
            encoded_group_path = group_path.replace('/', '%2F')
            response = await self.context.destination_client.get_async(
                f'/groups/{encoded_group_path}'
            )
            if response.success:
                return Group(**response.data)

            # If not found by direct path, try searching
            response = await self.context.destination_client.get_async(
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
        return await self._find_user(username, 'username')

    async def _find_parent_group_in_destination(self, group: Group) -> Optional[Group]:
        """Find parent group in destination for a sub-group.

        Args:
            group: Sub-group whose parent we need to find

        Returns:
            Parent group if found, None otherwise
        """
        try:
            if not group.parent_id:
                return None

            # Get parent group info from source to find it in destination
            parent_response = self.context.source_client.get(
                f'/groups/{group.parent_id}'
            )
            if not parent_response.success:
                self.logger.warning(
                    f'Could not get parent group {group.parent_id} from source'
                )
                return None

            parent_group_data = parent_response.data
            parent_path = parent_group_data.get('path')
            parent_full_path = parent_group_data.get('full_path', parent_path)

            if not parent_path:
                self.logger.warning(f'Parent group {group.parent_id} has no path')
                return None

            # Try to find parent group in destination by full path first
            if parent_full_path:
                parent_group = await self._find_group_by_path(parent_full_path)
                if parent_group:
                    self.logger.info(
                        f'Found parent group by full path: {parent_full_path} -> {parent_group.id}'
                    )
                    return parent_group

            # Try to find by path only
            parent_group = await self._find_group_by_path(parent_path)
            if parent_group:
                self.logger.info(
                    f'Found parent group by path: {parent_path} -> {parent_group.id}'
                )
                return parent_group

            self.logger.warning(
                f'Parent group not found in destination: path={parent_path}, full_path={parent_full_path}'
            )
            return None

        except Exception as e:
            self.logger.error(f'Error finding parent group for {group.path}: {e}')
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

            # Use original project path initially - only generate unique path if there's a conflict
            project_path = project.path
            project_name = project.name

            self.logger.info(f'Using original project path: {project_path}')
            self.logger.info(f'Using original project name: {project_name}')

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

            # Log the exact project creation request
            project_data = project_create.dict(exclude_none=True)
            self.logger.info(f'Creating project with data: {project_data}')
            self.logger.info(f'Project creation API endpoint: POST /projects')
            self.logger.info(f'Original project path: {project.path}')
            self.logger.info(f'Generated unique path: {project_path}')
            self.logger.info(f'Project name: {project_name}')
            self.logger.info(f'Namespace ID: {namespace_id}')

            # Implement robust retry logic for disk conflicts
            max_retries = 5
            retry_count = 0
            current_project_path = project_path
            current_project_name = project_name

            while retry_count <= max_retries:
                # Update project data for current attempt
                project_data = ProjectCreate(
                    name=current_project_name,
                    path=current_project_path,
                    namespace_id=namespace_id,
                    description=project.description,
                    visibility=project.visibility,
                    issues_enabled=project.issues_enabled or True,
                    merge_requests_enabled=project.merge_requests_enabled or True,
                    wiki_enabled=project.wiki_enabled or True,
                    jobs_enabled=project.jobs_enabled or True,
                    snippets_enabled=project.snippets_enabled or True,
                ).dict(exclude_none=True)

                self.logger.info(
                    f'Attempt {retry_count + 1}/{max_retries + 1}: Creating project with path: {current_project_path}'
                )
                self.logger.info(f'Project data being sent: {project_data}')

                response = await self.context.destination_client.post_async(
                    '/projects', data=project_data
                )

                self.logger.info(f'API Response - Success: {response.success}')
                self.logger.info(f'API Response - Data: {response.data}')

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

                    success_msg = f'Successfully migrated project {project.path}'
                    if current_project_path != project.path:
                        success_msg += f' -> {current_project_path}'
                    success_msg += (
                        f' (ID {new_project.id}) with {members_migrated} members'
                    )
                    if retry_count > 0:
                        success_msg += f' after {retry_count} retries'

                    self.logger.info(success_msg)

                    metadata: Dict[str, Any] = {'members_migrated': members_migrated}
                    if current_project_path != project.path:
                        metadata['path_changed'] = True
                        metadata['original_path'] = project.path
                        metadata['final_path'] = current_project_path
                        metadata['retries_needed'] = retry_count

                    return self.create_result(
                        entity_type='project',
                        entity_id=str(project.id),
                        status=MigrationStatus.COMPLETED,
                        success=True,
                        source_data=project.dict(),
                        destination_data=new_project.dict(),
                        metadata=metadata,
                    )

                # Check if this is a disk conflict that we can retry
                elif self._is_repository_disk_conflict(response.data):
                    retry_count += 1

                    if retry_count <= max_retries:
                        self.logger.warning(
                            f'Repository disk conflict detected for project {project.path} (attempt {retry_count}/{max_retries + 1}), generating new unique path'
                        )

                        # Generate a new unique path for retry
                        current_project_path = await self._generate_unique_project_path(
                            project
                        )
                        # Keep the same name, only change path
                        current_project_name = project_name

                        # Add a small delay to avoid rapid retries
                        await asyncio.sleep(0.1 * retry_count)  # Progressive delay
                        continue
                    else:
                        # Max retries exceeded, but still mark as skipped rather than failed
                        # since this is a server-side disk conflict issue, not a code bug
                        error_msg = f'Repository disk conflict persists after {max_retries} retries for project {project.path}. Skipping to avoid blocking migration.'
                        self.logger.error(error_msg)
                        return self.create_result(
                            entity_type='project',
                            entity_id=str(project.id),
                            status=MigrationStatus.SKIPPED,
                            success=True,  # Mark as success since we're intentionally skipping
                            source_data=project.dict(),
                            metadata={
                                'reason': 'persistent_disk_conflict',
                                'retries_attempted': max_retries,
                                'skip_reason': 'server_disk_conflict_unresolvable',
                            },
                            warnings=[error_msg],
                        )
                else:
                    # Non-disk-conflict error, fail immediately
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

            # This should never be reached due to the logic above, but just in case
            error_msg = f'Unexpected end of retry loop for project {project.path}'
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
        """Migrate a batch of projects concurrently.

        Args:
            projects: List of projects to migrate

        Returns:
            List of migration results
        """
        # Process all projects concurrently without sub-batching
        batch_tasks = [self.migrate_entity(project) for project in projects]
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

        all_results = []
        # Handle results and exceptions
        for result in batch_results:
            if isinstance(result, Exception):
                # Create a failed result for the exception
                error_result = self.create_result(
                    entity_type='project',
                    entity_id='unknown',
                    status=MigrationStatus.FAILED,
                    success=False,
                    error_message=str(result),
                )
                all_results.append(error_result)
            else:
                all_results.append(result)

        return all_results

    async def validate_prerequisites(self) -> bool:
        """Validate prerequisites for project migration.

        Returns:
            True if prerequisites are met, False otherwise
        """
        try:
            # Test destination client connectivity
            response = await self.context.destination_client.get_async('/projects')
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

            self.logger.info(f'COLLISION DEBUG: Checking error data: {error_data}')
            self.logger.info(f'COLLISION DEBUG: Error data type: {type(error_data)}')
            self.logger.info(f'COLLISION DEBUG: Error string: {error_str}')

            # Handle structured error responses (dict format)
            if isinstance(error_data, dict):
                self.logger.info(f'COLLISION DEBUG: Processing dict format error')
                # Check for base errors
                if 'base' in error_data and isinstance(error_data['base'], list):
                    for error_msg in error_data['base']:
                        error_msg_str = str(error_msg).lower()
                        if (
                            'repository' in error_msg_str
                            and (
                                'disk' in error_msg_str
                                or 'already' in error_msg_str
                                or '已存在' in error_msg_str  # Chinese: already exists
                                or '磁盘' in error_msg_str  # Chinese: disk
                            )
                        ) or 'uncaught throw :abort' in error_msg_str:
                            return True

                # Check for path errors
                if 'path' in error_data and isinstance(error_data['path'], list):
                    for error_msg in error_data['path']:
                        error_msg_str = str(error_msg).lower()
                        if (
                            'taken' in error_msg_str
                            or 'already' in error_msg_str
                            or '已存在' in error_msg_str  # Chinese: already exists
                        ):
                            return True

                # Check for name errors
                if 'name' in error_data and isinstance(error_data['name'], list):
                    for error_msg in error_data['name']:
                        error_msg_str = str(error_msg).lower()
                        if (
                            'taken' in error_msg_str
                            or 'already' in error_msg_str
                            or '已存在' in error_msg_str  # Chinese: already exists
                        ):
                            return True

            # Check for common disk conflict error patterns in string format
            disk_conflict_patterns = [
                # English patterns
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
                'already exists',
                'already taken',
                # Chinese patterns
                '磁盘上已存在具有该名称的仓库',  # Repository with that name already exists on disk
                '磁盘上已存在',  # Already exists on disk
                '仓库已存在',  # Repository already exists
                '名称已被占用',  # Name already taken
                '路径已存在',  # Path already exists
                '已存在具有该名称',  # Already exists with that name
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
        """Migrate project members from source to destination using batch processing.

        Args:
            source_project_id: Source project ID
            destination_project_id: Destination project ID

        Returns:
            Number of members successfully migrated
        """
        try:
            # Get project members from source
            source_members = await self._get_project_members(source_project_id)

            if not source_members:
                self.logger.info(f'No members found for project {source_project_id}')
                return 0

            self.logger.info(
                f'Migrating {len(source_members)} members for project {source_project_id}'
            )

            # Process members in batches for better performance
            batch_size = getattr(
                self.context, 'member_batch_size', 20
            )  # Use configurable batch size
            members_migrated = 0

            # Split members into batches
            member_batches = [
                source_members[i : i + batch_size]
                for i in range(0, len(source_members), batch_size)
            ]

            for batch in member_batches:
                # Process batch concurrently
                batch_tasks = []
                for member_data in batch:
                    task = self._migrate_single_project_member(
                        member_data, destination_project_id
                    )
                    batch_tasks.append(task)

                # Wait for all members in batch to complete
                batch_results = await asyncio.gather(
                    *batch_tasks, return_exceptions=True
                )

                # Count successful migrations
                for result in batch_results:
                    if isinstance(result, bool) and result:
                        members_migrated += 1
                    elif isinstance(result, Exception):
                        self.logger.error(f'Batch member migration error: {result}')

            return members_migrated

        except Exception as e:
            self.logger.error(
                f'Error migrating members for project {source_project_id}: {e}'
            )
            return 0

    async def _migrate_single_project_member(
        self, member_data: Dict[str, Any], destination_project_id: int
    ) -> bool:
        """Migrate a single project member.

        Args:
            member_data: Member data from source
            destination_project_id: Destination project ID

        Returns:
            True if migration was successful
        """
        try:
            source_user_id = member_data.get('id')
            access_level = member_data.get('access_level')
            expires_at = member_data.get('expires_at')

            if not source_user_id or not access_level:
                self.logger.warning(f'Invalid member data: {member_data}')
                return False

            # Check if user was migrated
            if source_user_id not in self.context.migrated_users:
                self.logger.warning(
                    f'User {source_user_id} ({member_data.get("username", "unknown")}) '
                    f'not found in migrated users, skipping project membership'
                )
                return False

            destination_user_id = self.context.migrated_users[source_user_id]

            # Check if user is already a member of the destination project
            member_info = await self._get_user_project_member_info(
                destination_project_id, destination_user_id
            )
            if member_info:
                current_access_level = member_info.get('access_level', 0)
                source_access_level = access_level

                # Check if user has inherited permissions that are higher or equal
                if member_info.get('created_at') and member_info.get('created_by'):
                    # This is an inherited membership, check if we need to update
                    self.logger.debug(
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
                            self.logger.debug(
                                f'Updated user {destination_user_id} access level from {current_access_level} to {source_access_level} '
                                f'in project {destination_project_id}'
                            )
                            return True
                        else:
                            self.logger.warning(
                                f'Failed to update user {destination_user_id} access level in project {destination_project_id}: '
                                f'{update_response.data}'
                            )
                            return False
                    else:
                        self.logger.debug(
                            f'User {destination_user_id} already has sufficient access level ({current_access_level}) '
                            f'in project {destination_project_id}, skipping update'
                        )
                        return True
                else:
                    self.logger.debug(
                        f'User {destination_user_id} is already a member of project {destination_project_id} '
                        f'with access level {current_access_level}'
                    )
                    return True

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
                self.logger.debug(
                    f'Added user {destination_user_id} ({member_data.get("username", "unknown")}) '
                    f'to project {destination_project_id} with access level {access_level}'
                )
                return True
            else:
                # Handle specific case of inherited permissions
                error_data = response.data
                if isinstance(error_data, dict) and 'access_level' in error_data:
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
                        return (
                            True  # Count as migrated since it's handled by inheritance
                        )

                self.logger.warning(
                    f'Failed to add user {destination_user_id} to project {destination_project_id}: '
                    f'{response.data}'
                )
                return False

        except Exception as e:
            self.logger.error(f'Error migrating project member {member_data}: {e}')
            return False

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

        Always generates a unique path to proactively avoid disk conflicts,
        since GitLab can have repository disk conflicts even when projects
        don't exist in the API.

        Args:
            project: Source project

        Returns:
            Unique project path for destination
        """
        try:
            original_path = project.path
            
            # Generate a highly random path to guarantee uniqueness
            random_part = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
            unique_path = f"{original_path}-migrated-{random_part}"

            self.logger.info(
                f"Generated unique project path to proactively avoid disk conflicts: {original_path} -> {unique_path}"
            )
            return unique_path

        except Exception as e:
            self.logger.error(
                f"CRITICAL ERROR: Failed to generate unique project path for {project.path}: {e}"
            )
            # Fallback to a simpler random path
            random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            fallback_path = f"{project.path}-{random_suffix}"
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
            response = self.context.destination_client.get(f'/groups/{group_path}')
            if response.success:
                return Group(**response.data)

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
