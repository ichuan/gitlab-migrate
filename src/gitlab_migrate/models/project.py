"""Project entity models."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator


class Project(BaseModel):
    """GitLab project model."""

    id: int = Field(..., description='Project ID')
    name: str = Field(..., description='Project name')
    path: str = Field(..., description='Project path')
    description: Optional[str] = Field(default=None, description='Project description')
    visibility: str = Field(
        ..., description='Project visibility (private, internal, public)'
    )

    # URLs and web interface
    web_url: Optional[str] = Field(default=None, description='Web URL')
    avatar_url: Optional[str] = Field(default=None, description='Avatar URL')
    ssh_url_to_repo: Optional[str] = Field(default=None, description='SSH clone URL')
    http_url_to_repo: Optional[str] = Field(default=None, description='HTTP clone URL')

    # Namespace (group or user)
    namespace: Optional[Dict[str, Any]] = Field(
        default=None, description='Project namespace'
    )

    # Timestamps
    created_at: Optional[datetime] = Field(
        default=None, description='Creation timestamp'
    )
    updated_at: Optional[datetime] = Field(
        default=None, description='Last update timestamp'
    )
    last_activity_at: Optional[datetime] = Field(
        default=None, description='Last activity timestamp'
    )

    # Repository information
    default_branch: Optional[str] = Field(
        default=None, description='Default branch name'
    )
    tag_list: List[str] = Field(default_factory=list, description='Project tags')
    topics: List[str] = Field(default_factory=list, description='Project topics')

    # Settings
    issues_enabled: Optional[bool] = Field(default=None, description='Issues enabled')
    merge_requests_enabled: Optional[bool] = Field(
        default=None, description='Merge requests enabled'
    )
    wiki_enabled: Optional[bool] = Field(default=None, description='Wiki enabled')
    jobs_enabled: Optional[bool] = Field(default=None, description='CI/CD jobs enabled')
    snippets_enabled: Optional[bool] = Field(
        default=None, description='Snippets enabled'
    )
    container_registry_enabled: Optional[bool] = Field(
        default=None, description='Container registry enabled'
    )
    service_desk_enabled: Optional[bool] = Field(
        default=None, description='Service desk enabled'
    )

    # Access and permissions
    can_create_merge_request_in: Optional[bool] = Field(
        default=None, description='Can create MR'
    )
    issues_access_level: Optional[str] = Field(
        default=None, description='Issues access level'
    )
    repository_access_level: Optional[str] = Field(
        default=None, description='Repository access level'
    )
    merge_requests_access_level: Optional[str] = Field(
        default=None, description='MR access level'
    )
    forking_access_level: Optional[str] = Field(
        default=None, description='Forking access level'
    )
    wiki_access_level: Optional[str] = Field(
        default=None, description='Wiki access level'
    )
    builds_access_level: Optional[str] = Field(
        default=None, description='Builds access level'
    )
    snippets_access_level: Optional[str] = Field(
        default=None, description='Snippets access level'
    )
    pages_access_level: Optional[str] = Field(
        default=None, description='Pages access level'
    )

    # Repository settings
    resolve_outdated_diff_discussions: Optional[bool] = Field(
        default=None, description='Resolve outdated discussions'
    )
    container_expiration_policy: Optional[Dict[str, Any]] = Field(
        default=None, description='Container expiration policy'
    )

    # CI/CD settings
    shared_runners_enabled: Optional[bool] = Field(
        default=None, description='Shared runners enabled'
    )
    lfs_enabled: Optional[bool] = Field(default=None, description='LFS enabled')
    creator_id: Optional[int] = Field(default=None, description='Creator user ID')

    # Fork information
    forked_from_project: Optional[Dict[str, Any]] = Field(
        default=None, description='Forked from project'
    )
    forks_count: Optional[int] = Field(default=None, description='Number of forks')

    # Statistics
    star_count: Optional[int] = Field(default=None, description='Number of stars')
    open_issues_count: Optional[int] = Field(
        default=None, description='Open issues count'
    )

    # Import/export
    import_status: Optional[str] = Field(default=None, description='Import status')
    import_error: Optional[str] = Field(
        default=None, description='Import error message'
    )

    # Custom attributes (for migration)
    source_id: Optional[int] = Field(
        default=None, description='Original source project ID'
    )
    migration_notes: Optional[str] = Field(default=None, description='Migration notes')

    @validator('visibility')
    def validate_visibility(cls, v):
        """Validate project visibility."""
        valid_visibility = ['private', 'internal', 'public']
        if v not in valid_visibility:
            raise ValueError(f'Visibility must be one of: {valid_visibility}')
        return v

    @validator('path')
    def validate_path(cls, v):
        """Validate project path format."""
        import re

        if not re.match(r'^[a-zA-Z0-9._-]+$', v):
            raise ValueError(
                'Path can only contain alphanumeric characters, dots, dashes, and underscores'
            )
        return v

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class ProjectCreate(BaseModel):
    """Model for creating a new project."""

    name: str = Field(..., description='Project name')
    path: Optional[str] = Field(
        default=None, description='Project path (defaults to name)'
    )
    namespace_id: Optional[int] = Field(
        default=None, description='Namespace (group) ID'
    )
    description: Optional[str] = Field(default=None, description='Project description')
    visibility: str = Field(default='private', description='Project visibility')

    # Repository settings
    default_branch: Optional[str] = Field(
        default='main', description='Default branch name'
    )
    initialize_with_readme: bool = Field(
        default=False, description='Initialize with README'
    )

    # Feature settings
    issues_enabled: bool = Field(default=True, description='Issues enabled')
    merge_requests_enabled: bool = Field(
        default=True, description='Merge requests enabled'
    )
    wiki_enabled: bool = Field(default=True, description='Wiki enabled')
    jobs_enabled: bool = Field(default=True, description='CI/CD jobs enabled')
    snippets_enabled: bool = Field(default=True, description='Snippets enabled')
    container_registry_enabled: bool = Field(
        default=True, description='Container registry enabled'
    )

    # Access levels
    issues_access_level: str = Field(
        default='enabled', description='Issues access level'
    )
    repository_access_level: str = Field(
        default='enabled', description='Repository access level'
    )
    merge_requests_access_level: str = Field(
        default='enabled', description='MR access level'
    )
    forking_access_level: str = Field(
        default='enabled', description='Forking access level'
    )
    wiki_access_level: str = Field(default='enabled', description='Wiki access level')
    builds_access_level: str = Field(
        default='enabled', description='Builds access level'
    )
    snippets_access_level: str = Field(
        default='enabled', description='Snippets access level'
    )
    pages_access_level: str = Field(default='enabled', description='Pages access level')

    # CI/CD settings
    shared_runners_enabled: bool = Field(
        default=True, description='Shared runners enabled'
    )
    lfs_enabled: bool = Field(default=True, description='LFS enabled')

    # Import settings
    import_url: Optional[str] = Field(
        default=None, description='Import URL for repository'
    )

    @validator('visibility')
    def validate_visibility(cls, v):
        """Validate project visibility."""
        valid_visibility = ['private', 'internal', 'public']
        if v not in valid_visibility:
            raise ValueError(f'Visibility must be one of: {valid_visibility}')
        return v

    @validator('path')
    def validate_path(cls, v):
        """Validate project path format."""
        if v is not None:
            import re

            if not re.match(r'^[a-zA-Z0-9._-]+$', v):
                raise ValueError(
                    'Path can only contain alphanumeric characters, dots, dashes, and underscores'
                )
        return v


class ProjectUpdate(BaseModel):
    """Model for updating an existing project."""

    name: Optional[str] = Field(default=None, description='Project name')
    description: Optional[str] = Field(default=None, description='Project description')
    visibility: Optional[str] = Field(default=None, description='Project visibility')
    default_branch: Optional[str] = Field(
        default=None, description='Default branch name'
    )

    # Feature settings
    issues_enabled: Optional[bool] = Field(default=None, description='Issues enabled')
    merge_requests_enabled: Optional[bool] = Field(
        default=None, description='Merge requests enabled'
    )
    wiki_enabled: Optional[bool] = Field(default=None, description='Wiki enabled')
    jobs_enabled: Optional[bool] = Field(default=None, description='CI/CD jobs enabled')
    snippets_enabled: Optional[bool] = Field(
        default=None, description='Snippets enabled'
    )
    container_registry_enabled: Optional[bool] = Field(
        default=None, description='Container registry enabled'
    )

    # CI/CD settings
    shared_runners_enabled: Optional[bool] = Field(
        default=None, description='Shared runners enabled'
    )
    lfs_enabled: Optional[bool] = Field(default=None, description='LFS enabled')

    @validator('visibility')
    def validate_visibility(cls, v):
        """Validate project visibility."""
        if v is not None:
            valid_visibility = ['private', 'internal', 'public']
            if v not in valid_visibility:
                raise ValueError(f'Visibility must be one of: {valid_visibility}')
        return v


class ProjectMember(BaseModel):
    """Project member model."""

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


class ProjectMemberAdd(BaseModel):
    """Model for adding a member to a project."""

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


class ProjectMapping(BaseModel):
    """Model for mapping projects between source and destination."""

    source_project_id: int = Field(..., description='Source project ID')
    source_project_path: str = Field(..., description='Source project path')
    source_namespace_id: Optional[int] = Field(
        default=None, description='Source namespace ID'
    )

    destination_project_id: Optional[int] = Field(
        default=None, description='Destination project ID'
    )
    destination_project_path: Optional[str] = Field(
        default=None, description='Destination project path'
    )
    destination_namespace_id: Optional[int] = Field(
        default=None, description='Destination namespace ID'
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


class ProjectIssue(BaseModel):
    """Project issue model."""

    id: int = Field(..., description='Issue ID')
    iid: int = Field(..., description='Issue internal ID')
    project_id: int = Field(..., description='Project ID')
    title: str = Field(..., description='Issue title')
    description: Optional[str] = Field(default=None, description='Issue description')
    state: str = Field(..., description='Issue state (opened, closed)')

    # Author and assignee
    author: Dict[str, Any] = Field(..., description='Issue author')
    assignees: List[Dict[str, Any]] = Field(
        default_factory=list, description='Issue assignees'
    )

    # Timestamps
    created_at: Optional[datetime] = Field(
        default=None, description='Creation timestamp'
    )
    updated_at: Optional[datetime] = Field(
        default=None, description='Last update timestamp'
    )
    closed_at: Optional[datetime] = Field(default=None, description='Closed timestamp')

    # Labels and milestone
    labels: List[str] = Field(default_factory=list, description='Issue labels')
    milestone: Optional[Dict[str, Any]] = Field(
        default=None, description='Issue milestone'
    )

    # Metrics
    upvotes: int = Field(default=0, description='Number of upvotes')
    downvotes: int = Field(default=0, description='Number of downvotes')
    user_notes_count: int = Field(default=0, description='Number of comments')

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class ProjectMergeRequest(BaseModel):
    """Project merge request model."""

    id: int = Field(..., description='MR ID')
    iid: int = Field(..., description='MR internal ID')
    project_id: int = Field(..., description='Project ID')
    title: str = Field(..., description='MR title')
    description: Optional[str] = Field(default=None, description='MR description')
    state: str = Field(..., description='MR state (opened, closed, merged)')

    # Branch information
    source_branch: str = Field(..., description='Source branch')
    target_branch: str = Field(..., description='Target branch')

    # Author and assignee
    author: Dict[str, Any] = Field(..., description='MR author')
    assignees: List[Dict[str, Any]] = Field(
        default_factory=list, description='MR assignees'
    )
    reviewers: List[Dict[str, Any]] = Field(
        default_factory=list, description='MR reviewers'
    )

    # Timestamps
    created_at: Optional[datetime] = Field(
        default=None, description='Creation timestamp'
    )
    updated_at: Optional[datetime] = Field(
        default=None, description='Last update timestamp'
    )
    merged_at: Optional[datetime] = Field(default=None, description='Merged timestamp')
    closed_at: Optional[datetime] = Field(default=None, description='Closed timestamp')

    # Labels and milestone
    labels: List[str] = Field(default_factory=list, description='MR labels')
    milestone: Optional[Dict[str, Any]] = Field(
        default=None, description='MR milestone'
    )

    # Merge information
    merge_commit_sha: Optional[str] = Field(
        default=None, description='Merge commit SHA'
    )
    squash_commit_sha: Optional[str] = Field(
        default=None, description='Squash commit SHA'
    )

    # Metrics
    upvotes: int = Field(default=0, description='Number of upvotes')
    downvotes: int = Field(default=0, description='Number of downvotes')
    user_notes_count: int = Field(default=0, description='Number of comments')

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat() if v else None}
