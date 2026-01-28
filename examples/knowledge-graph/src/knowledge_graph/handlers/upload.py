import logging
import mimetypes
import shutil
from pathlib import Path

from fastapi import File, UploadFile

from kaig.db import DB

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


async def upload_handler(db: DB, file: UploadFile = File(...)) -> None:  # pyright: ignore[reportCallInDefaultInitializer]
    if file.filename is None:
        # raise HTTPException(status_code=400, detail="No file selected")
        logger.error("No file selected")
        return

    logger.info("Starting upload...")

    try:
        file_path = UPLOAD_DIR / file.filename
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        await file.seek(0)
        content = await file.read()
        content_type = file.content_type
        if (
            not content_type
            or content_type == "unknown"
            or content_type == "application/octet-stream"
        ):
            guessed, _ = mimetypes.guess_type(file.filename)
            content_type = guessed or "application/octet-stream"
        _doc, _cached = db.store_original_document_from_bytes(
            file.filename, content_type, content
        )
        logger.info(f"File stored: {_doc.id}")
    except Exception as e:
        # raise HTTPException(
        #     status_code=500, detail=f"Something went wrong: {e}"
        # )
        logger.error(f"Error storing file: {e}")
    finally:
        await file.close()
