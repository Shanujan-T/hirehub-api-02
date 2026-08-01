import logging

import os

from pathlib import Path



import cloudinary

import cloudinary.uploader

from cloudinary.exceptions import Error as CloudinaryError



logger = logging.getLogger(__name__)



ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024





def _configure_cloudinary():

    cloudinary.config(

        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),

        api_key=os.getenv("CLOUDINARY_API_KEY"),

        api_secret=os.getenv("CLOUDINARY_API_SECRET"),

        secure=True,

    )





def _read_file_storage(file_storage) -> bytes:

    file_storage.stream.seek(0)

    data = file_storage.read()

    file_storage.stream.seek(0)

    return data





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



    try:

        result = cloudinary.uploader.upload(

            _read_file_storage(file_storage),

            folder=folder,

            resource_type="image",

        )

    except CloudinaryError:

        logger.exception("Cloudinary avatar/image upload failed")

        raise



    return result["secure_url"]

