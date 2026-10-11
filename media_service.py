"""Validated originals, private thumbnails and exact-image duplicate detection."""
import hashlib
import io
import uuid
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000


def inspect_image(data):
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError('单张图片不能为空且不能超过 5MB')
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format not in ('JPEG', 'PNG', 'GIF', 'WEBP') or img.width * img.height > MAX_PIXELS:
                raise ValueError('图片格式不支持或分辨率过大')
            ext = {'JPEG': '.jpg', 'PNG': '.png', 'GIF': '.gif', 'WEBP': '.webp'}[img.format]
            img.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('图片内容无效，请选择 JPG、PNG、GIF 或 WebP 图片') from exc
    return ext, hashlib.sha256(data).hexdigest()


def save_image(data, user_id, upload_folder):
    ext, digest = inspect_image(data)
    folder = Path(upload_folder) / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex
    original, thumb = folder / (name + ext), folder / (name + '.thumb.jpg')
    try:
        with Image.open(io.BytesIO(data)) as img:
            preview = ImageOps.exif_transpose(img)
            preview.thumbnail((640, 640))
            preview.convert('RGB').save(thumb, 'JPEG', quality=80, optimize=True)
        original.write_bytes(data)
    except Exception:
        original.unlink(missing_ok=True)
        thumb.unlink(missing_ok=True)
        raise
    return {'image_path': f'static/uploads/{user_id}/{original.name}',
            'thumbnail_path': f'static/uploads/{user_id}/{thumb.name}', 'image_hash': digest}


def local_image(path, upload_folder):
    """Only resolve paths under the configured upload directory."""
    prefix = 'static/uploads/'
    if not path or not path.startswith(prefix):
        return None
    root = Path(upload_folder).resolve()
    target = (root / path[len(prefix):]).resolve()
    return target if target.is_relative_to(root) and target != root else None


def remove_media(record, upload_folder):
    for key in ('image_path', 'thumbnail_path'):
        path = local_image(record.get(key), upload_folder)
        if path:
            path.unlink(missing_ok=True)
