import io
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
import cloudinary
import cloudinary.uploader
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from .enums import ServiceType
from app.email_utils import send_email
from .db import get_db
from .models import AdminUser, ContentBlock, Page, SiteSetting, Media, Message, PasswordResetToken, Notification
from .schema import (
    ContentBlockCreate,
    ContentBlockResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageCreate,
    MessageResponse,
    ReplyRequest,
    ResetPasswordRequest,
    SiteSettingUpdate,
    SiteSettingResponse,
    Token,
    AdminUserCreate,
    AdminUserResponse,
    PageCreate,
    PageResponse,
    NotificationCreate,
    NotificationOut,
    NotificationListResponse,
    UnreadCountResponse,
    MarkReadRequest,
)

from .auth import hash_password, verify_password, create_access_token, get_current_admin

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file(ENV_FILE)

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)


router = APIRouter()

# ---------------- Notifications (integrated) ----------------
from fastapi import WebSocket, WebSocketDisconnect, Query, BackgroundTasks
from typing import Any, List, Optional
from sqlalchemy import func


NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _read_shared_strings(archive: zipfile.ZipFile) -> List[str]:
    try:
        shared_strings_xml = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []

    root = ET.fromstring(shared_strings_xml)
    items = []
    for si in root.findall(f"{{{NS_MAIN}}}si"):
        texts = []
        for t in si.iter(f"{{{NS_MAIN}}}t"):
            texts.append(t.text or "")
        items.append("".join(texts))
    return items


def _get_cell_value(cell: ET.Element, shared_strings: List[str]) -> str:
    cell_type = cell.attrib.get("t")
    value_elem = cell.find(f"{{{NS_MAIN}}}v")
    if value_elem is None:
        value_elem = cell.find(f"{{{NS_MAIN}}}is")
    if value_elem is None:
        return ""

    raw_value = value_elem.text or ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw_value)]
        except (ValueError, IndexError):
            return raw_value
    return raw_value


def parse_xlsx_upload(file_obj: Any, filename: str) -> dict[str, Any]:
    archive = zipfile.ZipFile(file_obj)
    try:
        workbook_xml = archive.read("xl/workbook.xml")
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid XLSX workbook") from exc

    workbook_root = ET.fromstring(workbook_xml)
    sheet_names: List[str] = []
    sheet_paths: List[str] = []

    for sheet in workbook_root.find(f"{{{NS_MAIN}}}sheets") or []:
        name = sheet.attrib.get("name")
        if name:
            sheet_names.append(name)
        relationship_id = sheet.attrib.get(f"{{{NS_REL}}}id")
        if relationship_id:
            sheet_paths.append(relationship_id)

    relationship_xml = archive.read("xl/_rels/workbook.xml.rels")
    rel_root = ET.fromstring(relationship_xml)
    rel_map = {
        rel.attrib.get("Id"): rel.attrib.get("Target")
        for rel in rel_root.findall(f"{{{NS_PACKAGE_REL}}}Relationship")
        if rel.attrib.get("Id") and rel.attrib.get("Target")
    }

    shared_strings = _read_shared_strings(archive)
    rows: List[List[str]] = []
    sheet_path = None

    if sheet_paths:
        target = rel_map.get(sheet_paths[0], "")
        if target.startswith("/"):
            sheet_path = target.lstrip("/")
        else:
            sheet_path = f"xl/{target}"

    if sheet_path is None:
        raise HTTPException(status_code=400, detail="No worksheet data was found in the uploaded file")

    worksheet_xml = archive.read(sheet_path)
    worksheet_root = ET.fromstring(worksheet_xml)
    sheet_data = worksheet_root.find(f"{{{NS_MAIN}}}sheetData")
    if sheet_data is None:
        return {
            "filename": filename,
            "sheet_names": sheet_names,
            "headers": [],
            "rows": [],
            "row_count": 0,
        }

    for row in sheet_data.findall(f"{{{NS_MAIN}}}row"):
        values = []
        for cell in row.findall(f"{{{NS_MAIN}}}c"):
            values.append(_get_cell_value(cell, shared_strings))
        rows.append(values)

    if not rows:
        return {
            "filename": filename,
            "sheet_names": sheet_names,
            "headers": [],
            "rows": [],
            "row_count": 0,
        }

    headers = [str(value).strip() or f"Column {index + 1}" for index, value in enumerate(rows[0])]
    data_rows = []
    for row in rows[1:]:
        if not row:
            continue
        record = {}
        for index, header in enumerate(headers):
            record[header] = row[index] if index < len(row) else ""
        data_rows.append(record)

    return {
        "filename": filename,
        "sheet_names": sheet_names,
        "headers": headers,
        "rows": data_rows,
        "row_count": len(data_rows),
    }


# Simple in-process WebSocket connection manager keyed by `user_id`.
class _WSManager:
    def __init__(self):
        # user_id -> list[WebSocket]
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.setdefault(user_id, []).append(websocket)

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        conns = self.connections.get(user_id)
        if not conns:
            return
        try:
            conns.remove(websocket)
        except ValueError:
            pass
        if not conns:
            self.connections.pop(user_id, None)

    async def push_to_user(self, user_id: str, payload: dict) -> None:
        conns = list(self.connections.get(user_id, []))
        dead = []
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for d in dead:
            try:
                self.connections.get(user_id, []).remove(d)
            except Exception:
                pass


ws_manager = _WSManager()


async def notify(user_id: str, resource_type: str, title: str, resource_id: Optional[str] = None, type_: str = "system", message: Optional[str] = None, data: Optional[dict] = None, db: Session = None) -> None:
    """Create a notification and push it live to connected WebSocket clients.

    This helper can be imported and awaited from other parts of the application.
    If `db` is not provided, a new session is created for this operation.
    """
    close_db = False
    if db is None:
        db = next(get_db())
        close_db = True

    try:
        payload = NotificationCreate(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            type=type_,
            title=title,
            message=message,
            data=data,
        )
        # persist
        obj = Notification(
            user_id=payload.user_id,
            resource_type=payload.resource_type,
            resource_id=payload.resource_id,
            type=payload.type,
            title=payload.title,
            message=payload.message,
            data=payload.data,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)

        # lightweight push payload
        push = {
            "id": obj.id,
            "title": obj.title,
            "message": obj.message,
            "resource_type": obj.resource_type,
            "resource_id": obj.resource_id,
            "type": obj.type.name if hasattr(obj.type, 'name') else str(obj.type),
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
            "is_read": obj.is_read,
        }
        await ws_manager.push_to_user(user_id, push)
    finally:
        if close_db:
            try:
                db.close()
            except Exception:
                pass


@router.get("/api/notifications", response_model=NotificationListResponse)
def list_notifications(user_id: str = Query(...), unread_only: bool = Query(False), resource_type: Optional[str] = Query(None), page: int = Query(1), page_size: int = Query(25), db: Session = Depends(get_db)):
    q = db.query(Notification).filter(Notification.user_id == user_id)
    if unread_only:
        q = q.filter(Notification.is_read == False)
    if resource_type:
        q = q.filter(Notification.resource_type == resource_type)

    total = q.count()
    unread_count = db.query(func.count()).select_from(Notification).filter(Notification.user_id == user_id, Notification.is_read == False).scalar() or 0
    items = q.order_by(Notification.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return NotificationListResponse(items=items, total=total, unread_count=unread_count, page=page, page_size=page_size)


@router.get("/api/notifications/unread-count", response_model=UnreadCountResponse)
def notifications_unread_count(user_id: str = Query(...), db: Session = Depends(get_db)):
    count = db.query(func.count()).select_from(Notification).filter(Notification.user_id == user_id, Notification.is_read == False).scalar() or 0
    return UnreadCountResponse(unread_count=count)


@router.patch("/api/notifications/read")
def notifications_mark_read(request: MarkReadRequest, user_id: str = Query(...), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    q = db.query(Notification).filter(Notification.user_id == user_id, Notification.is_read == False)
    if request.ids:
        q = q.filter(Notification.id.in_(request.ids))
    updated = q.update({"is_read": True, "read_at": now}, synchronize_session=False)
    db.commit()
    return {"updated": updated}


@router.delete("/api/notifications/{notification_id}")
def notifications_delete(notification_id: str, user_id: str = Query(...), db: Session = Depends(get_db)):
    obj = db.query(Notification).filter(Notification.user_id == user_id, Notification.id == notification_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Notification not found")
    db.delete(obj)
    db.commit()
    return {"deleted": True}


@router.websocket("/api/notifications/ws/{user_id}")
async def websocket_notifications(websocket: WebSocket, user_id: str):
    await ws_manager.connect(user_id, websocket)
    try:
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        await ws_manager.disconnect(user_id, websocket)

# ---------- Create Admin (sirf ek dafa khud use karne ke liye) ----------
@router.post("/api/admin/create-user", response_model=AdminUserResponse)
def create_admin(user: AdminUserCreate, db: Session = Depends(get_db)):
    existing = db.query(AdminUser).filter(AdminUser.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = AdminUser(
        name=user.name,
        email=user.email,
        password_hash=hash_password(user.password),
        role="admin"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

# ---------- Login ----------
@router.post("/api/admin/login", response_model=Token)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(AdminUser).filter(AdminUser.email == credentials.email).first()
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(data={"sub": user.email, "role": user.role})
    return {"access_token": token, "token_type": "bearer"}


        #   Protected Route
          

@router.get("/api/admin/me")
def read_current_admin(current_admin: dict = Depends(get_current_admin)):
    return {"logged_in_as": current_admin}


@router.post("/api/admin/pages", response_model=PageResponse)
def create_page(page: PageCreate, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    existing = db.query(Page).filter(Page.slug == page.slug).first()
    if existing:
        raise HTTPException(status_code=400, detail="Page with this slug already exists")

    new_page = Page(slug=page.slug, title=page.title, meta_data=page.meta_data)
    db.add(new_page)
    db.commit()
    db.refresh(new_page)
    return new_page


@router.get("/api/admin/pages", response_model=list[PageResponse])
def list_pages(db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    return db.query(Page).all()


# ================= CONTENT BLOCKS (Admin - Protected) =================

@router.post("/api/admin/content", response_model=ContentBlockResponse)
def create_content_block(block: ContentBlockCreate, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    new_block = ContentBlock(
        page_id=block.page_id,
        block_key=block.block_key,
        block_type=block.block_type,
        content=block.content,
        order_index=block.order_index
    )
    db.add(new_block)
    db.commit()
    db.refresh(new_block)
    return new_block


@router.get("/api/admin/content/{page_id}", response_model=list[ContentBlockResponse])
def get_page_content_admin(page_id: int, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    return db.query(ContentBlock).filter(ContentBlock.page_id == page_id).order_by(ContentBlock.order_index).all()


@router.put("/api/admin/content/{block_id}", response_model=ContentBlockResponse)
def update_content_block(block_id: int, block: ContentBlockCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    existing_block = db.query(ContentBlock).filter(ContentBlock.id == block_id).first()
    if not existing_block:
        raise HTTPException(status_code=404, detail="Content block not found")

    existing_block.content = block.content
    existing_block.block_type = block.block_type
    existing_block.order_index = block.order_index
    db.commit()
    db.refresh(existing_block)

    background_tasks.add_task(
        notify,
        current_admin.get("email", "admin"),
        "content_block",
        "Content block updated",
        str(existing_block.id),
        "updated",
        f"Block '{existing_block.block_key}' was updated",
        {"page_id": existing_block.page_id, "block_key": existing_block.block_key},
    )

    return existing_block


@router.delete("/api/admin/content/{block_id}")
def delete_content_block(block_id: int, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    existing_block = db.query(ContentBlock).filter(ContentBlock.id == block_id).first()
    if not existing_block:
        raise HTTPException(status_code=404, detail="Content block not found")

    db.delete(existing_block)
    db.commit()
    return {"status": "deleted"}


# ================= PUBLIC ENDPOINTS (No Auth - Frontend Uses These) =================

@router.get("/api/public/pages/{slug}")
def get_public_page(slug: str, db: Session = Depends(get_db)):
    page = db.query(Page).filter(Page.slug == slug).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    blocks = db.query(ContentBlock).filter(ContentBlock.page_id == page.id).order_by(ContentBlock.order_index).all()

    result = {}
    for block in blocks:
        result[block.block_key] = {
            "type": block.block_type,
            "value": block.content.get("value") if isinstance(block.content, dict) else block.content
        }

    return {"page": page.slug, "title": page.title, "blocks": result}


# ================= SITE SETTINGS (Admin - Protected) =================

@router.put("/api/admin/settings/{key}", response_model=SiteSettingResponse)
def update_setting(key: str, setting: SiteSettingUpdate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    existing = db.query(SiteSetting).filter(SiteSetting.key == key).first()

    if existing:
        existing.value = setting.value
        db.commit()
        db.refresh(existing)

        background_tasks.add_task(
            notify,
            current_admin.get("email", "admin"),
            "site_setting",
            f"Site setting '{key}' updated",
            key,
            "updated",
            f"The '{key}' setting was updated",
            {"key": key},
        )

        return existing
    else:
        new_setting = SiteSetting(key=key, value=setting.value)
        db.add(new_setting)
        db.commit()
        db.refresh(new_setting)

        background_tasks.add_task(
            notify,
            current_admin.get("email", "admin"),
            "site_setting",
            f"Site setting '{key}' created",
            key,
            "created",
            f"The '{key}' setting was created",
            {"key": key},
        )

        return new_setting


@router.get("/api/admin/settings", response_model=list[SiteSettingResponse])
def list_settings(db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    return db.query(SiteSetting).all()


# ================= PUBLIC SETTINGS (No Auth) =================

@router.get("/api/public/settings")
def get_public_settings(db: Session = Depends(get_db)):
    settings = db.query(SiteSetting).all()
    result = {}
    for s in settings:
        result[s.key] = s.value
    return result


# ================= ADMIN — Inbox Dekhna =================

@router.get("/api/admin/messages", response_model=list[MessageResponse])
def list_messages(db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    return db.query(Message).order_by(Message.created_at.desc()).all()


@router.get("/api/admin/messages/{message_id}", response_model=MessageResponse)
def get_message(message_id: int, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # Automatically "read" mark kar dein
    if msg.status == "new":
        msg.status = "read"
        db.commit()

    return msg


@router.delete("/api/admin/messages/{message_id}")
def delete_message(message_id: int, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    db.delete(msg)
    db.commit()
    return {"status": "deleted"}


@router.put("/api/admin/pages/{page_id}/meta")
def update_page_meta(page_id: int, meta_data: dict, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    page.meta_data = meta_data
    db.commit()
    db.refresh(page)

    background_tasks.add_task(
        notify,
        current_admin.get("email", "admin"),
        "page",
        f"Page '{page.slug}' metadata updated",
        str(page.id),
        "updated",
        f"The metadata for page '{page.slug}' was updated",
        {"slug": page.slug},
    )

    return page


@router.post("/api/admin/messages/{message_id}/reply")
def reply_to_message(message_id: int, reply: ReplyRequest, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    send_email(
        to_email=msg.email,
        subject=f"Re: {msg.services or 'Your inquiry'}", 
        body=reply.reply_message
    )

    msg.status = "replied"
    db.commit()

    return {"status": "Reply sent successfully"}



@router.get("/api/public/services")
def get_available_services():
    return [{"value": s.name, "label": s.value} for s in ServiceType]



@router.patch("/api/admin/content/{block_id}/toggle-publish")
def toggle_publish(block_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    block = db.query(ContentBlock).filter(ContentBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=404, detail="Content block not found")

    block.is_published = not block.is_published
    db.commit()
    db.refresh(block)

    background_tasks.add_task(
        notify,
        current_admin.get("email", "admin"),
        "content_block",
        f"Content block {'published' if block.is_published else 'unpublished'}",
        str(block.id),
        "updated",
        f"The block '{block.block_key}' was {'published' if block.is_published else 'unpublished'}",
        {"block_key": block.block_key, "page_id": block.page_id},
    )

    return block




@router.post("/api/admin/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(AdminUser).filter(AdminUser.email == request.email).first()
    if not user:
        # Security ke liye hamesha same message dein, chahe email exist kare ya na kare
        return {"status": "If this email exists, a reset link has been sent."}

    token = str(uuid.uuid4())
    expires = datetime.utcnow() + timedelta(minutes=30)

    reset_entry = PasswordResetToken(email=user.email, token=token, expires_at=expires)
    db.add(reset_entry)
    db.commit()

    reset_link = f"http://localhost:3000/reset-password?token={token}"   # frontend URL (jo bhi ho)

    try:
        send_email(
            to_email=user.email,
            subject="Password Reset Request",
            body=f"Click the link to reset your password (valid for 30 minutes):\n\n{reset_link}"
        )
    except Exception as e:
        print(f"Failed to send reset email: {e}")

    return {"status": "If this email exists, a reset link has been sent."}


# ---------- Step B: Naya Password Set Karna ----------
@router.post("/api/admin/reset-password")
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    token_entry = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == request.token,
        PasswordResetToken.used == False
    ).first()

    if not token_entry:
        raise HTTPException(status_code=400, detail="Invalid or already used token")

    expires_at = token_entry.expires_at
    if expires_at is None:
        raise HTTPException(status_code=400, detail="Token has no expiry date")

    if expires_at.tzinfo is not None:
        expires_at = expires_at.replace(tzinfo=None)

    if expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Token has expired")

    user = db.query(AdminUser).filter(AdminUser.email == token_entry.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = hash_password(request.new_password)
    token_entry.used = True
    db.commit()

    return {"status": "Password reset successfully"}














@router.get("/api/admin/media")
def list_media(
    resource_type: Optional[str] = Query(None, description="Filter: 'image' or 'video'"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin),
):
    q = db.query(Media)
    if resource_type:
        q = q.filter(Media.resource_type == resource_type)

    total = q.count()
    items = (
        q.order_by(Media.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }



@router.post("/api/admin/import/xlsx")
async def import_xlsx(
    file: UploadFile = File(...),
    current_admin: dict = Depends(get_current_admin),
):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported")

    contents = await file.read()
    parsed = parse_xlsx_upload(io.BytesIO(contents), file.filename)

    try:
        db = next(get_db())
        db.close()
    except Exception:
        pass

    return {
        "message": "XLSX staged for import",
        "filename": parsed["filename"],
        "sheet_names": parsed["sheet_names"],
        "headers": parsed["headers"],
        "row_count": parsed["row_count"],
        "rows": parsed["rows"],
        "status": "staged",
    }


@router.post("/api/admin/media/upload")
async def upload_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin),
    filename: Optional[str] = Query(None, description="Optional custom filename for the uploaded media")
):
    if not os.getenv("CLOUDINARY_CLOUD_NAME") or not os.getenv("CLOUDINARY_API_KEY") or not os.getenv("CLOUDINARY_API_SECRET"):
        raise HTTPException(
            status_code=500,
            detail="Cloudinary credentials are not configured. Check app/.env for CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET.",
        )

    try:
        # resource_type="auto" => Cloudinary khud detect karega image/video/raw
        result = cloudinary.uploader.upload(
            file.file,
            resource_type="auto",
            folder="filernow",  # organize karne ke liye
            filename=filename if filename else file.filename,
            overwrite=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    media = Media(
        url=result["secure_url"],
        public_id=result["public_id"],
        resource_type=result["resource_type"],   # "image" / "video"
        format=result.get("format"),
        width=result.get("width"),
        height=result.get("height"),
        bytes=result.get("bytes"),
    )
    db.add(media)
    db.commit()
    db.refresh(media)

    await notify(
        user_id=current_admin.get("email", "admin") if current_admin else "admin",
        resource_type="media",
        resource_id=str(media.id),
        type_="created",
        title="New media uploaded",
        message=f"{media.resource_type} uploaded: {media.public_id}",
        db=db,
    )

    return media




@router.delete("/api/admin/media/{media_id}")
async def delete_media(media_id: int, db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)):
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    cloudinary.uploader.destroy(media.public_id, resource_type=media.resource_type)

    db.delete(media)
    db.commit()
    return {"status": "deleted"}



