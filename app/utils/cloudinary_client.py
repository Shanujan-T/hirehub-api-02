import os
from pathlib import Path

import cloudinary
import cloudinary.uploader

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_DOCUMENT_CONTENT_TYPES = ALLOWED_CONTENT_TYPES | {"application/pdf"}
ALLOWED_DOCUMENT_EXTENSIONS = ALLOWED_EXTENSIONS | {".pdf"}
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024


def _configure_cloudinary():
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )


def validate_document_file(file_storage):
    if not file_storage or not file_storage.filename:
        return "No document file provided."

    extension = Path(file_storage.filename).suffix.lower()
    if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        return "Only JPG, PNG, WEBP, and PDF files are allowed."

    content_type = (file_storage.content_type or "").lower()
    if content_type and content_type not in ALLOWED_DOCUMENT_CONTENT_TYPES:
        return "Only JPG, PNG, WEBP, and PDF files are allowed."

    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    if size <= 0:
        return "Uploaded file is empty."
    if size > MAX_FILE_SIZE_BYTES:
        return "File must be 5MB or smaller."

    return None


def validate_image_file(file_storage):
    if not file_storage or not file_storage.filename:
        return "No image file provided."

    extension = Path(file_storage.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        return "Only JPG, PNG, and WEBP images are allowed."

    content_type = (file_storage.content_type or "").lower()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        return "Only JPG, PNG, and WEBP images are allowed."

    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    if size <= 0:
        return "Uploaded file is empty."
    if size > MAX_FILE_SIZE_BYTES:
        return "Image must be 5MB or smaller."

    return None


def upload_image(file_storage, folder: str) -> str:
    _configure_cloudinary()

    if not os.getenv("CLOUDINARY_CLOUD_NAME"):
        raise RuntimeError("Cloudinary is not configured.")

    error = validate_image_file(file_storage)
    if error:
        raise ValueError(error)

    result = cloudinary.uploader.upload(
        file_storage,
        folder=folder,
        resource_type="image",
    )
    return result["secure_url"]


def upload_document(file_storage, folder: str) -> str:
    _configure_cloudinary()

    if not os.getenv("CLOUDINARY_CLOUD_NAME"):
        raise RuntimeError("Cloudinary is not configured.")

    error = validate_document_file(file_storage)
    if error:
        raise ValueError(error)

    extension = Path(file_storage.filename).suffix.lower()
    resource_type = "raw" if extension == ".pdf" else "image"

    result = cloudinary.uploader.upload(
        file_storage,
        folder=folder,
        resource_type=resource_type,
    )
    return result["secure_url"]
