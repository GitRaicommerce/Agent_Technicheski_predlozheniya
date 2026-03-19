import hashlib
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Generation, Project, ProjectFile
from app.core.storage import storage

router = APIRouter()

ALLOWED_MODULES = {"examples", "tender_docs", "schedule", "legislation"}
ALLOWED_MIMETYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.ms-project",
    # Excel formats (needed for schedule uploads)
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}


class FileResponse(BaseModel):
    id: str
    project_id: str
    module: str
    filename: str
    file_hash: str
    ingest_status: str
    ingest_error: Optional[str] = None

    model_config = {"from_attributes": True}


@router.post(
    "/{project_id}/upload",
    response_model=FileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    project_id: str,
    module: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if module not in ALLOWED_MODULES:
        raise HTTPException(
            status_code=400, detail=f"Invalid module. Must be one of: {ALLOWED_MODULES}"
        )

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIMETYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{content_type}'. Allowed: PDF, DOCX, DOC, MPP, XLSX, XLS.",
        )

    content = await file.read()
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 50 MB.")
    file_hash = hashlib.sha256(content).hexdigest()
    file_id = str(uuid.uuid4())
    storage_key = f"projects/{project_id}/{module}/{file_id}/{file.filename}"

    await storage.put_object(
        storage_key, content, file.content_type or "application/octet-stream"
    )

    project_file = ProjectFile(
        id=file_id,
        project_id=project_id,
        module=module,
        filename=file.filename,
        storage_key=storage_key,
        file_hash=file_hash,
        ingest_status="pending",
    )
    db.add(project_file)
    await db.flush()

    # Enqueue ingest job
    from app.ingestion.worker import enqueue_ingest

    enqueue_ingest(file_id)

    # Mark existing generations as stale — evidence base has changed
    # (schedule uploads don't directly affect existing text generations)
    if module in ("tender_docs", "examples", "legislation"):
        await db.execute(
            update(Generation)
            .where(
                Generation.project_id == project_id,
                Generation.evidence_status == "ok",
            )
            .values(evidence_status="stale")
        )

    await db.refresh(project_file)
    return project_file


@router.get("/{project_id}/files", response_model=list[FileResponse])
async def list_files(
    project_id: str,
    module: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(ProjectFile).where(ProjectFile.project_id == project_id)
    if module:
        query = query.where(ProjectFile.module == module)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{project_id}/files/{file_id}/status", response_model=FileResponse)
async def get_file_status(
    project_id: str,
    file_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Polls ingest status for a single file — used by frontend polling."""
    file = await db.get(ProjectFile, file_id)
    if not file or file.project_id != project_id:
        raise HTTPException(status_code=404, detail="File not found")
    return file


@router.delete(
    "/{project_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_file(
    project_id: str,
    file_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Deletes a file record and its MinIO object."""
    file = await db.get(ProjectFile, file_id)
    if not file or file.project_id != project_id:
        raise HTTPException(status_code=404, detail="File not found")
    await storage.delete_object(file.storage_key)
    await db.delete(file)
