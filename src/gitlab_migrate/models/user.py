"""User entity models."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator


class User(BaseModel):
    """GitLab user model."""

    id: int = Field(..., description='User ID')
    username: str = Field(..., description='Username')
    name: str = Field(..., description='Full name')
    email: str = Field(..., description='Email address')
    state: str = Field(..., description='User state (active, blocked, etc.)')
    avatar_url: Optional[str] = Field(default=None, description='Avatar URL')
    web_url: Optional[str] = Field(default=None, description='Web URL')

    # Profile information
    bio: Optional[str] = Field(default=None, description='User bio')
    location: Optional[str] = Field(default=None, description='Location')
    public_email: Optional[str] = Field(default=None, description='Public email')
    skype: Optional[str] = Field(default=None, description='Skype username')
    linkedin: Optional[str] = Field(default=None, description='LinkedIn profile')
    twitter: Optional[str] = Field(default=None, description='Twitter handle')
    website_url: Optional[str] = Field(default=None, description='Website URL')
    organization: Optional[str] = Field(default=None, description='Organization')

    # Timestamps
    created_at: Optional[datetime] = Field(
        default=None, description='Creation timestamp'
    )
    updated_at: Optional[datetime] = Field(
        default=None, description='Last update timestamp'
    )
    last_sign_in_at: Optional[datetime] = Field(
        default=None, description='Last sign-in timestamp'
    )
    current_sign_in_at: Optional[datetime] = Field(
        default=None, description='Current sign-in timestamp'
    )

    # Access control
    can_create_group: Optional[bool] = Field(
        default=None, description='Can create groups'
    )
    can_create_project: Optional[bool] = Field(
        default=None, description='Can create projects'
    )
    two_factor_enabled: Optional[bool] = Field(
        default=None, description='Two-factor authentication enabled'
    )
    external: Optional[bool] = Field(default=None, description='External user')
    private_profile: Optional[bool] = Field(default=None, description='Private profile')

    # Additional fields
    projects_limit: Optional[int] = Field(default=None, description='Project limit')
    current_sign_in_ip: Optional[str] = Field(
        default=None, description='Current sign-in IP'
    )
    last_sign_in_ip: Optional[str] = Field(default=None, description='Last sign-in IP')
    theme_id: Optional[int] = Field(default=None, description='Theme ID')
    color_scheme_id: Optional[int] = Field(default=None, description='Color scheme ID')

    # Custom attributes (for migration mapping)
    source_id: Optional[int] = Field(
        default=None, description='Original source user ID'
    )
    migration_notes: Optional[str] = Field(default=None, description='Migration notes')

    @validator('email')
    def validate_email(cls, v):
        """Basic email validation."""
        if '@' not in v:
            raise ValueError('Invalid email format')
        return v.lower()

    @validator('state')
    def validate_state(cls, v):
        """Validate user state."""
        valid_states = [
            'active',
            'blocked',
            'deactivated',
            'blocked_pending_approval',
            'ldap_blocked',
        ]
        if v not in valid_states:
            raise ValueError(f'State must be one of: {valid_states}')
        return v

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class UserCreate(BaseModel):
    """Model for creating a new user."""

    username: str = Field(..., description='Username')
    name: str = Field(..., description='Full name')
    email: str = Field(..., description='Email address')
    password: Optional[str] = Field(
        default=None, description='Password (if not using external auth)'
    )

    # Optional profile information
    bio: Optional[str] = Field(default=None, description='User bio')
    location: Optional[str] = Field(default=None, description='Location')
    public_email: Optional[str] = Field(default=None, description='Public email')
    skype: Optional[str] = Field(default=None, description='Skype username')
    linkedin: Optional[str] = Field(default=None, description='LinkedIn profile')
    twitter: Optional[str] = Field(default=None, description='Twitter handle')
    website_url: Optional[str] = Field(default=None, description='Website URL')
    organization: Optional[str] = Field(default=None, description='Organization')

    # Access control
    can_create_group: bool = Field(default=True, description='Can create groups')
    can_create_project: bool = Field(default=True, description='Can create projects')
    external: bool = Field(default=False, description='External user')
    private_profile: bool = Field(default=False, description='Private profile')

    # Limits
    projects_limit: Optional[int] = Field(default=None, description='Project limit')

    # Admin options
    admin: bool = Field(default=False, description='Admin user')
    skip_confirmation: bool = Field(default=True, description='Skip email confirmation')

    @validator('email')
    def validate_email(cls, v):
        """Basic email validation."""
        if '@' not in v:
            raise ValueError('Invalid email format')
        return v.lower()

    @validator('username')
    def validate_username(cls, v):
        """Validate username format."""
        if len(v) < 2:
            raise ValueError('Username must be at least 2 characters')
        # GitLab username rules: alphanumeric, dots, dashes, underscores
        import re

        if not re.match(r'^[a-zA-Z0-9._-]+$', v):
            raise ValueError(
                'Username can only contain alphanumeric characters, dots, dashes, and underscores'
            )
        return v


class UserUpdate(BaseModel):
    """Model for updating an existing user."""

    name: Optional[str] = Field(default=None, description='Full name')
    email: Optional[str] = Field(default=None, description='Email address')

    # Profile information
    bio: Optional[str] = Field(default=None, description='User bio')
    location: Optional[str] = Field(default=None, description='Location')
    public_email: Optional[str] = Field(default=None, description='Public email')
    skype: Optional[str] = Field(default=None, description='Skype username')
    linkedin: Optional[str] = Field(default=None, description='LinkedIn profile')
    twitter: Optional[str] = Field(default=None, description='Twitter handle')
    website_url: Optional[str] = Field(default=None, description='Website URL')
    organization: Optional[str] = Field(default=None, description='Organization')

    # Access control
    can_create_group: Optional[bool] = Field(
        default=None, description='Can create groups'
    )
    can_create_project: Optional[bool] = Field(
        default=None, description='Can create projects'
    )
    external: Optional[bool] = Field(default=None, description='External user')
    private_profile: Optional[bool] = Field(default=None, description='Private profile')

    # Limits
    projects_limit: Optional[int] = Field(default=None, description='Project limit')

    @validator('email')
    def validate_email(cls, v):
        """Basic email validation."""
        if v and '@' not in v:
            raise ValueError('Invalid email format')
        return v.lower() if v else v


class UserMapping(BaseModel):
    """Model for mapping users between source and destination."""

    source_user_id: int = Field(..., description='Source user ID')
    source_username: str = Field(..., description='Source username')
    source_email: str = Field(..., description='Source email')

    destination_user_id: Optional[int] = Field(
        default=None, description='Destination user ID'
    )
    destination_username: Optional[str] = Field(
        default=None, description='Destination username'
    )
    destination_email: Optional[str] = Field(
        default=None, description='Destination email'
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
        valid_methods = ['email_match', 'username_match', 'manual', 'create_new']
        if v not in valid_methods:
            raise ValueError(f'Mapping method must be one of: {valid_methods}')
        return v
