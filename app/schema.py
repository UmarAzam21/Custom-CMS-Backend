from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional, Any
from datetime import datetime
from .enums import ServiceType

# ---------- Admin User ----------
class AdminUserCreate(BaseModel):
    name: str
    email: str
    password: str

class AdminUserResponse(BaseModel):
    id: int
    email: str
    role: str
    model_config = ConfigDict(from_attributes=True)

# ---------- Login ----------
class LoginRequest(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

# ---------- Page ----------
class PageCreate(BaseModel):
    slug: str
    title: str
    meta_data: Optional[dict] = None

class PageResponse(BaseModel):
    id: int
    slug: str
    title: str
    meta_data: Optional[dict] = None
    model_config = ConfigDict(from_attributes=True)

# ---------- Content Block ----------
class ContentBlockCreate(BaseModel):
    page_id: int
    block_key: str
    block_type: str
    content: dict
    order_index: int = 0
    is_published: bool = True

class ContentBlockResponse(BaseModel):
    id: int
    page_id: int
    block_key: str
    block_type: str
    content: dict
    order_index: int
    model_config = ConfigDict(from_attributes=True)
    is_published: bool     

# ---------- Site Setting ----------
class SiteSettingUpdate(BaseModel):
    value: dict

class SiteSettingResponse(BaseModel):
    key: str
    value: dict
    model_config = ConfigDict(from_attributes=True)
    
    
class MessageCreate(BaseModel):
    name: str
    email: str
    services: Optional[ServiceType] = None
    message: str

class MessageResponse(BaseModel):
    id: int
    name: str
    email: str
    services: Optional[ServiceType] = None
    message: str
    status: str
    created_at: Any
    model_config = ConfigDict(from_attributes=True)

class ReplyRequest(BaseModel):
    reply_message: str
    
class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., alias="newPassword")
    model_config = ConfigDict(populate_by_name=True)


# ---------- Notifications ----------
class NotificationCreate(BaseModel):
    user_id: str
    resource_type: str
    resource_id: Optional[str] = None
    type: str = "system"
    title: str
    message: Optional[str] = None
    data: Optional[dict] = None


class NotificationOut(BaseModel):
    id: str
    user_id: str
    resource_type: str
    resource_id: Optional[str] = None
    type: str
    title: str
    message: Optional[str] = None
    data: Optional[dict] = None
    is_read: bool
    created_at: Any
    read_at: Optional[Any] = None

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    items: list[NotificationOut]
    total: int
    unread_count: int
    page: int
    page_size: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class MarkReadRequest(BaseModel):
    ids: Optional[list[str]] = None
    
    
    
    
class ContactFormIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    subject: str = Field(..., min_length=1, max_length=500)
    message: str = Field(..., min_length=1)


class ContactFormOut(BaseModel):
    ticket_id: int
    status: str


class XlsxImportResponse(BaseModel):
    id: int
    filename: str
    sheet_names: Optional[list] = None
    headers: list
    row_count: int
    status: str
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

