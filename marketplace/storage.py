import posixpath

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.storage import Storage
from django.utils.crypto import get_random_string


class PublicMarketplaceCloudinaryStorage(Storage):
    """Public media storage for marketplace listing images."""

    def _cloudinary(self):
        try:
            import cloudinary
            import cloudinary.uploader
            import cloudinary.utils
        except ImportError as exc:
            raise ImproperlyConfigured(
                "Cloudinary media storage requires the cloudinary package."
            ) from exc

        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )
        return cloudinary

    def _public_id(self, name):
        cleaned_name = name.strip("/").replace("\\", "/")

        if settings.CLOUDINARY_MEDIA_PREFIX:
            return posixpath.join(
                settings.CLOUDINARY_MEDIA_PREFIX,
                cleaned_name,
            )

        return cleaned_name

    def get_available_name(self, name, max_length=None):
        name = name.strip("/").replace("\\", "/")
        root, extension = posixpath.splitext(name)
        candidate = f"{root}_{get_random_string(7)}{extension}"
        prefix_length = (
            len(settings.CLOUDINARY_MEDIA_PREFIX) + 1
            if settings.CLOUDINARY_MEDIA_PREFIX
            else 0
        )
        available_max_length = (
            max_length - prefix_length
            if max_length is not None
            else None
        )

        if (
            available_max_length is not None
            and len(candidate) > available_max_length
        ):
            trimmed_root_length = available_max_length - len(extension) - 8

            if trimmed_root_length <= 0:
                raise SuspiciousFileOperation(
                    "Storage name cannot fit within max_length."
                )

            candidate = (
                f"{root[:trimmed_root_length]}_"
                f"{get_random_string(7)}{extension}"
            )

        return candidate

    def _save(self, name, content):
        cloudinary = self._cloudinary()
        public_id = self._public_id(name)

        if hasattr(content, "open"):
            content.open()

        result = cloudinary.uploader.upload(
            content,
            public_id=public_id,
            resource_type="image",
            overwrite=False,
            unique_filename=False,
        )

        return result.get("public_id", public_id)

    def exists(self, name):
        return False

    def url(self, name):
        cloudinary = self._cloudinary()
        url, _options = cloudinary.utils.cloudinary_url(
            name,
            resource_type="image",
            secure=True,
        )
        return url

    def delete(self, name):
        cloudinary = self._cloudinary()
        cloudinary.uploader.destroy(name, resource_type="image")
