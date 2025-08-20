"""Repository entity models."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator


class Repository(BaseModel):
    """GitLab repository model."""

    project_id: int = Field(..., description='Project ID')
    name: str = Field(..., description='Repository name')
    path: str = Field(..., description='Repository path')

    # Clone URLs
    ssh_url_to_repo: Optional[str] = Field(default=None, description='SSH clone URL')
    http_url_to_repo: Optional[str] = Field(default=None, description='HTTP clone URL')

    # Branch information
    default_branch: Optional[str] = Field(
        default=None, description='Default branch name'
    )
    branches: List[Dict[str, Any]] = Field(
        default_factory=list, description='Repository branches'
    )
    tags: List[Dict[str, Any]] = Field(
        default_factory=list, description='Repository tags'
    )

    # Repository statistics
    size: Optional[int] = Field(default=None, description='Repository size in bytes')
    commit_count: Optional[int] = Field(default=None, description='Total commit count')

    # Repository settings
    lfs_enabled: Optional[bool] = Field(default=None, description='LFS enabled')
    empty_repo: Optional[bool] = Field(default=None, description='Repository is empty')
    archived: Optional[bool] = Field(default=None, description='Repository is archived')

    # Timestamps
    created_at: Optional[datetime] = Field(
        default=None, description='Creation timestamp'
    )
    last_activity_at: Optional[datetime] = Field(
        default=None, description='Last activity timestamp'
    )

    # Custom attributes (for migration)
    source_project_id: Optional[int] = Field(
        default=None, description='Original source project ID'
    )
    migration_notes: Optional[str] = Field(default=None, description='Migration notes')

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class RepositoryCreate(BaseModel):
    """Model for creating/initializing a repository."""

    project_id: int = Field(..., description='Project ID')
    initialize_with_readme: bool = Field(
        default=False, description='Initialize with README'
    )
    default_branch: str = Field(default='main', description='Default branch name')

    # Import settings
    import_url: Optional[str] = Field(
        default=None, description='Import URL for repository'
    )
    mirror: bool = Field(default=False, description='Mirror repository')

    @validator('default_branch')
    def validate_default_branch(cls, v):
        """Validate default branch name."""
        import re

        if not re.match(r'^[a-zA-Z0-9._/-]+$', v):
            raise ValueError(
                'Branch name can only contain alphanumeric characters, dots, dashes, slashes, and underscores'
            )
        return v


class RepositoryBranch(BaseModel):
    """Repository branch model."""

    name: str = Field(..., description='Branch name')
    commit: Dict[str, Any] = Field(..., description='Latest commit information')
    merged: Optional[bool] = Field(default=None, description='Branch is merged')
    protected: Optional[bool] = Field(default=None, description='Branch is protected')
    developers_can_push: Optional[bool] = Field(
        default=None, description='Developers can push'
    )
    developers_can_merge: Optional[bool] = Field(
        default=None, description='Developers can merge'
    )
    can_push: Optional[bool] = Field(default=None, description='Current user can push')
    default: Optional[bool] = Field(default=None, description='Is default branch')
    web_url: Optional[str] = Field(default=None, description='Web URL')


class RepositoryTag(BaseModel):
    """Repository tag model."""

    name: str = Field(..., description='Tag name')
    message: Optional[str] = Field(default=None, description='Tag message')
    target: str = Field(..., description='Target commit SHA')
    commit: Dict[str, Any] = Field(..., description='Commit information')
    release: Optional[Dict[str, Any]] = Field(
        default=None, description='Release information'
    )
    protected: Optional[bool] = Field(default=None, description='Tag is protected')


class RepositoryCommit(BaseModel):
    """Repository commit model."""

    id: str = Field(..., description='Commit SHA')
    short_id: str = Field(..., description='Short commit SHA')
    title: str = Field(..., description='Commit title')
    message: str = Field(..., description='Full commit message')

    # Author information
    author_name: str = Field(..., description='Author name')
    author_email: str = Field(..., description='Author email')
    authored_date: datetime = Field(..., description='Authored date')

    # Committer information
    committer_name: str = Field(..., description='Committer name')
    committer_email: str = Field(..., description='Committer email')
    committed_date: datetime = Field(..., description='Committed date')

    # Commit details
    parent_ids: List[str] = Field(
        default_factory=list, description='Parent commit SHAs'
    )
    web_url: Optional[str] = Field(default=None, description='Web URL')

    # Statistics
    stats: Optional[Dict[str, Any]] = Field(
        default=None, description='Commit statistics'
    )

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class RepositoryFile(BaseModel):
    """Repository file model."""

    file_name: str = Field(..., description='File name')
    file_path: str = Field(..., description='File path')
    size: int = Field(..., description='File size in bytes')
    encoding: str = Field(..., description='File encoding')
    content: Optional[str] = Field(default=None, description='File content (if text)')
    content_sha256: Optional[str] = Field(
        default=None, description='Content SHA256 hash'
    )
    ref: str = Field(..., description='Git reference (branch/tag/commit)')
    blob_id: str = Field(..., description='Blob ID')
    commit_id: str = Field(..., description='Last commit ID')
    last_commit_id: str = Field(..., description='Last commit ID for this file')

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class RepositoryTree(BaseModel):
    """Repository tree (directory listing) model."""

    id: str = Field(..., description='Tree ID')
    name: str = Field(..., description='File/directory name')
    type: str = Field(..., description='Type (tree, blob)')
    path: str = Field(..., description='Full path')
    mode: str = Field(..., description='File mode')


class RepositoryMirror(BaseModel):
    """Repository mirror configuration model."""

    id: int = Field(..., description='Mirror ID')
    url: str = Field(..., description='Mirror URL')
    enabled: bool = Field(..., description='Mirror is enabled')
    update_status: str = Field(..., description='Last update status')
    last_update_at: Optional[datetime] = Field(
        default=None, description='Last update timestamp'
    )
    last_successful_update_at: Optional[datetime] = Field(
        default=None, description='Last successful update'
    )
    last_error: Optional[str] = Field(default=None, description='Last error message')
    only_protected_branches: bool = Field(
        default=False, description='Mirror only protected branches'
    )
    keep_divergent_refs: bool = Field(default=False, description='Keep divergent refs')

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class RepositoryHook(BaseModel):
    """Repository webhook model."""

    id: int = Field(..., description='Hook ID')
    url: str = Field(..., description='Hook URL')
    project_id: int = Field(..., description='Project ID')

    # Trigger events
    push_events: bool = Field(default=True, description='Trigger on push events')
    issues_events: bool = Field(default=False, description='Trigger on issue events')
    merge_requests_events: bool = Field(
        default=False, description='Trigger on MR events'
    )
    tag_push_events: bool = Field(
        default=False, description='Trigger on tag push events'
    )
    note_events: bool = Field(default=False, description='Trigger on note events')
    job_events: bool = Field(default=False, description='Trigger on job events')
    pipeline_events: bool = Field(
        default=False, description='Trigger on pipeline events'
    )
    wiki_page_events: bool = Field(default=False, description='Trigger on wiki events')
    deployment_events: bool = Field(
        default=False, description='Trigger on deployment events'
    )
    releases_events: bool = Field(
        default=False, description='Trigger on release events'
    )

    # Configuration
    push_events_branch_filter: Optional[str] = Field(
        default=None, description='Branch filter for push events'
    )
    enable_ssl_verification: bool = Field(
        default=True, description='Enable SSL verification'
    )
    token: Optional[str] = Field(default=None, description='Secret token')

    # Timestamps
    created_at: Optional[datetime] = Field(
        default=None, description='Creation timestamp'
    )

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class RepositoryProtectedBranch(BaseModel):
    """Protected branch configuration model."""

    id: int = Field(..., description='Protected branch ID')
    name: str = Field(..., description='Branch name')
    push_access_levels: List[Dict[str, Any]] = Field(
        default_factory=list, description='Push access levels'
    )
    merge_access_levels: List[Dict[str, Any]] = Field(
        default_factory=list, description='Merge access levels'
    )
    unprotect_access_levels: List[Dict[str, Any]] = Field(
        default_factory=list, description='Unprotect access levels'
    )
    code_owner_approval_required: bool = Field(
        default=False, description='Code owner approval required'
    )
    allow_force_push: bool = Field(default=False, description='Allow force push')


class RepositoryMapping(BaseModel):
    """Model for mapping repositories between source and destination."""

    source_project_id: int = Field(..., description='Source project ID')
    source_repository_path: str = Field(..., description='Source repository path')

    destination_project_id: Optional[int] = Field(
        default=None, description='Destination project ID'
    )
    destination_repository_path: Optional[str] = Field(
        default=None, description='Destination repository path'
    )

    mapping_method: str = Field(..., description='How the mapping was determined')
    confidence: float = Field(
        default=1.0, description='Confidence level of the mapping (0.0-1.0)'
    )

    # Migration status
    migration_status: str = Field(default='pending', description='Migration status')
    migration_progress: float = Field(
        default=0.0, description='Migration progress (0.0-1.0)'
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

    @validator('migration_progress')
    def validate_migration_progress(cls, v):
        """Validate migration progress is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError('Migration progress must be between 0.0 and 1.0')
        return v

    @validator('mapping_method')
    def validate_mapping_method(cls, v):
        """Validate mapping method."""
        valid_methods = ['project_match', 'manual', 'create_new']
        if v not in valid_methods:
            raise ValueError(f'Mapping method must be one of: {valid_methods}')
        return v

    @validator('migration_status')
    def validate_migration_status(cls, v):
        """Validate migration status."""
        valid_statuses = ['pending', 'in_progress', 'completed', 'failed', 'cancelled']
        if v not in valid_statuses:
            raise ValueError(f'Migration status must be one of: {valid_statuses}')
        return v


class RepositoryMigrationResult(BaseModel):
    """Result of repository migration operation."""

    source_project_id: int = Field(..., description='Source project ID')
    destination_project_id: int = Field(..., description='Destination project ID')

    migration_method: str = Field(..., description='Migration method used')
    started_at: datetime = Field(..., description='Migration start time')
    completed_at: Optional[datetime] = Field(
        default=None, description='Migration completion time'
    )

    status: str = Field(..., description='Migration status')
    success: bool = Field(..., description='Migration was successful')

    branches_migrated: int = Field(default=0, description='Number of branches migrated')
    tags_migrated: int = Field(default=0, description='Number of tags migrated')
    commits_migrated: int = Field(default=0, description='Number of commits migrated')
    lfs_objects_migrated: int = Field(
        default=0, description='Number of LFS objects migrated'
    )

    repository_size_bytes: Optional[int] = Field(
        default=None, description='Repository size in bytes'
    )
    lfs_size_bytes: Optional[int] = Field(default=None, description='LFS size in bytes')

    errors: List[str] = Field(default_factory=list, description='Migration errors')
    warnings: List[str] = Field(default_factory=list, description='Migration warnings')

    notes: Optional[str] = Field(default=None, description='Additional notes')

    @validator('migration_method')
    def validate_migration_method(cls, v):
        """Validate migration method."""
        valid_methods = ['git_clone_push', 'api_export_import', 'direct_transfer']
        if v not in valid_methods:
            raise ValueError(f'Migration method must be one of: {valid_methods}')
        return v

    @validator('status')
    def validate_status(cls, v):
        """Validate migration status."""
        valid_statuses = ['pending', 'in_progress', 'completed', 'failed', 'cancelled']
        if v not in valid_statuses:
            raise ValueError(f'Status must be one of: {valid_statuses}')
        return v

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat() if v else None}
