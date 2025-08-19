"""Group entity models."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator


class Group(BaseModel):
    """GitLab group model."""

    id: int = Field(..., description='Group ID')
    name: str = Field(..., description='Group name')
    path: str = Field(..., description='Group path')
    description: Optional[str] = Field(default=None, description='Group description')
    visibility: str = Field(
        ..., description='Group visibility (private, internal, public)'
    )

    # URLs and web interface
    web_url: Optional[str] = Field(default=None, description='Web URL')
    avatar_url: Optional[str] = Field(default=None, description='Avatar URL')

    # Hierarchy
    parent_id: Optional[int] = Field(default=None, description='Parent group ID')
    full_name: Optional[str] = Field(
        default=None, description='Full group name with parent'
    )
    full_path: Optional[str] = Field(
        default=None, description='Full group path with parent'
    )

    # Timestamps
    created_at: Optional[datetime] = Field(
        default=None, description='Creation timestamp'
    )
    updated_at: Optional[datetime] = Field(
        default=None, description='Last update timestamp'
    )

    # Settings
    lfs_enabled: Optional[bool] = Field(default=None, description='LFS enabled')
    request_access_enabled: Optional[bool] = Field(
        default=None, description='Request access enabled'
    )
    share_with_group_lock: Optional[bool] = Field(
        default=None, description='Share with group lock'
    )
    visibility_level: Optional[int] = Field(
        default=None, description='Visibility level (numeric)'
    )
    require_two_factor_authentication: Optional[bool] = Field(
        default=None, description='Require 2FA'
    )
    two_factor_grace_period: Optional[int] = Field(
        default=None, description='2FA grace period'
    )
    project_creation_level: Optional[str] = Field(
        default=None, description='Project creation level'
    )
    auto_devops_enabled: Optional[bool] = Field(
        default=None, description='Auto DevOps enabled'
    )
    subgroup_creation_level: Optional[str] = Field(
        default=None, description='Subgroup creation level'
    )
    emails_disabled: Optional[bool] = Field(default=None, description='Emails disabled')
    mentions_disabled: Optional[bool] = Field(
        default=None, description='Mentions disabled'
    )

    # Statistics
    statistics: Optional[Dict[str, Any]] = Field(
        default=None, description='Group statistics'
    )

    # Custom attributes (for migration)
    source_id: Optional[int] = Field(
        default=None, description='Original source group ID'
    )
    migration_notes: Optional[str] = Field(default=None, description='Migration notes')

    @validator('visibility')
    def validate_visibility(cls, v):
        """Validate group visibility."""
        valid_visibility = ['private', 'internal', 'public']
        if v not in valid_visibility:
            raise ValueError(f'Visibility must be one of: {valid_visibility}')
        return v

    @validator('path')
    def validate_path(cls, v):
        """Validate group path format."""
        import re

        if not re.match(r'^[a-zA-Z0-9._-]+$', v):
            raise ValueError(
                'Path can only contain alphanumeric characters, dots, dashes, and underscores'
            )
        return v

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class GroupCreate(BaseModel):
    """Model for creating a new group."""

    name: str = Field(..., description='Group name')
    path: str = Field(..., description='Group path')
    description: Optional[str] = Field(default=None, description='Group description')
    visibility: str = Field(default='private', description='Group visibility')

    # Hierarchy
    parent_id: Optional[int] = Field(default=None, description='Parent group ID')

    # Settings
    lfs_enabled: bool = Field(default=True, description='LFS enabled')
    request_access_enabled: bool = Field(
        default=False, description='Request access enabled'
    )
    share_with_group_lock: bool = Field(
        default=False, description='Share with group lock'
    )
    require_two_factor_authentication: bool = Field(
        default=False, description='Require 2FA'
    )
    two_factor_grace_period: int = Field(
        default=48, description='2FA grace period in hours'
    )
    project_creation_level: str = Field(
        default='maintainer', description='Project creation level'
    )
    auto_devops_enabled: bool = Field(default=True, description='Auto DevOps enabled')
    subgroup_creation_level: str = Field(
        default='maintainer', description='Subgroup creation level'
    )
    emails_disabled: bool = Field(default=False, description='Emails disabled')
    mentions_disabled: bool = Field(default=False, description='Mentions disabled')

    @validator('visibility')
    def validate_visibility(cls, v):
        """Validate group visibility."""
        valid_visibility = ['private', 'internal', 'public']
        if v not in valid_visibility:
            raise ValueError(f'Visibility must be one of: {valid_visibility}')
        return v

    @validator('path')
    def validate_path(cls, v):
        """Validate group path format."""
        import re

        if not re.match(r'^[a-zA-Z0-9._-]+$', v):
            raise ValueError(
                'Path can only contain alphanumeric characters, dots, dashes, and underscores'
            )
        return v

    @validator('project_creation_level')
    def validate_project_creation_level(cls, v):
        """Validate project creation level."""
        valid_levels = ['noone', 'maintainer', 'developer']
        if v not in valid_levels:
            raise ValueError(f'Project creation level must be one of: {valid_levels}')
        return v

    @validator('subgroup_creation_level')
    def validate_subgroup_creation_level(cls, v):
        """Validate subgroup creation level."""
        valid_levels = ['owner', 'maintainer']
        if v not in valid_levels:
            raise ValueError(f'Subgroup creation level must be one of: {valid_levels}')
        return v


class GroupUpdate(BaseModel):
    """Model for updating an existing group."""

    name: Optional[str] = Field(default=None, description='Group name')
    description: Optional[str] = Field(default=None, description='Group description')
    visibility: Optional[str] = Field(default=None, description='Group visibility')

    # Settings
    lfs_enabled: Optional[bool] = Field(default=None, description='LFS enabled')
    request_access_enabled: Optional[bool] = Field(
        default=None, description='Request access enabled'
    )
    share_with_group_lock: Optional[bool] = Field(
        default=None, description='Share with group lock'
    )
    require_two_factor_authentication: Optional[bool] = Field(
        default=None, description='Require 2FA'
    )
    two_factor_grace_period: Optional[int] = Field(
        default=None, description='2FA grace period'
    )
    project_creation_level: Optional[str] = Field(
        default=None, description='Project creation level'
    )
    auto_devops_enabled: Optional[bool] = Field(
        default=None, description='Auto DevOps enabled'
    )
    subgroup_creation_level: Optional[str] = Field(
        default=None, description='Subgroup creation level'
    )
    emails_disabled: Optional[bool] = Field(default=None, description='Emails disabled')
    mentions_disabled: Optional[bool] = Field(
        default=None, description='Mentions disabled'
    )

    @validator('visibility')
    def validate_visibility(cls, v):
        """Validate group visibility."""
        if v is not None:
            valid_visibility = ['private', 'internal', 'public']
            if v not in valid_visibility:
                raise ValueError(f'Visibility must be one of: {valid_visibility}')
        return v


class GroupMember(BaseModel):
    """Group member model."""

    id: int = Field(..., description='User ID')
    username: str = Field(..., description='Username')
    name: str = Field(..., description='Full name')
    email: Optional[str] = Field(default=None, description='Email address')
    state: str = Field(..., description='User state')
    avatar_url: Optional[str] = Field(default=None, description='Avatar URL')
    web_url: Optional[str] = Field(default=None, description='Web URL')

    # Membership details
    access_level: int = Field(
        ...,
        description='Access level (10=Guest, 20=Reporter, 30=Developer, 40=Maintainer, 50=Owner)',
    )
    expires_at: Optional[datetime] = Field(
        default=None, description='Membership expiration'
    )

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class GroupMemberAdd(BaseModel):
    """Model for adding a member to a group."""

    user_id: int = Field(..., description='User ID to add')
    access_level: int = Field(..., description='Access level')
    expires_at: Optional[datetime] = Field(
        default=None, description='Membership expiration'
    )

    @validator('access_level')
    def validate_access_level(cls, v):
        """Validate access level."""
        valid_levels = [
            10,
            20,
            30,
            40,
            50,
        ]  # Guest, Reporter, Developer, Maintainer, Owner
        if v not in valid_levels:
            raise ValueError(f'Access level must be one of: {valid_levels}')
        return v


class GroupMapping(BaseModel):
    """Model for mapping groups between source and destination."""

    source_group_id: int = Field(..., description='Source group ID')
    source_group_path: str = Field(..., description='Source group path')
    source_parent_id: Optional[int] = Field(
        default=None, description='Source parent group ID'
    )

    destination_group_id: Optional[int] = Field(
        default=None, description='Destination group ID'
    )
    destination_group_path: Optional[str] = Field(
        default=None, description='Destination group path'
    )
    destination_parent_id: Optional[int] = Field(
        default=None, description='Destination parent group ID'
    )

    mapping_method: str = Field(..., description='How the mapping was determined')
    confidence: float = Field(
        default=1.0, description='Confidence level of the mapping (0.0-1.0)'
    )

    created_at: datetime = Field(
        default_factory=datetime.now, description='Mapping creation time'
    )
    notes: Optional[str] = Field(
        default=None, description='Additional notes about the mapping'
    )

    @validator('confidence')
    def validate_confidence(cls, v):
        """Validate confidence is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError('Confidence must be between 0.0 and 1.0')
        return v

    @validator('mapping_method')
    def validate_mapping_method(cls, v):
        """Validate mapping method."""
        valid_methods = ['path_match', 'name_match', 'manual', 'create_new']
        if v not in valid_methods:
            raise ValueError(f'Mapping method must be one of: {valid_methods}')
        return v


class GroupHierarchy(BaseModel):
    """Model for representing group hierarchy."""

    group: Group = Field(..., description='The group')
    parent: Optional['GroupHierarchy'] = Field(
        default=None, description='Parent group hierarchy'
    )
    children: List['GroupHierarchy'] = Field(
        default_factory=list, description='Child group hierarchies'
    )
    depth: int = Field(default=0, description='Depth in hierarchy (0 = root)')

    def get_full_path(self) -> str:
        """Get the full path including parent paths."""
        if self.parent:
            return f'{self.parent.get_full_path()}/{self.group.path}'
        return self.group.path

    def get_all_descendants(self) -> List[Group]:
        """Get all descendant groups (recursive)."""
        descendants = []
        for child in self.children:
            descendants.append(child.group)
            descendants.extend(child.get_all_descendants())
        return descendants

    def find_group_by_id(self, group_id: int) -> Optional['GroupHierarchy']:
        """Find a group in the hierarchy by ID."""
        if self.group.id == group_id:
            return self

        for child in self.children:
            found = child.find_group_by_id(group_id)
            if found:
                return found

        return None


# Update forward references
GroupHierarchy.model_rebuild()
