from django.core.files.uploadhandler import FileUploadHandler


MAX_LISTING_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
MAX_LISTING_IMAGE_PIXELS = 20_000_000
ALLOWED_LISTING_IMAGE_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
LISTING_IMAGE_TOO_LARGE_MESSAGE = "Please upload an image no larger than 5 MB."


class ListingImageSizeUploadHandler(FileUploadHandler):
    """Stop buffering a listing image once its actual streamed bytes exceed 5 MiB."""

    def new_file(
        self,
        field_name,
        file_name,
        content_type,
        content_length,
        charset=None,
        content_type_extra=None,
    ):
        super().new_file(
            field_name,
            file_name,
            content_type,
            content_length,
            charset,
            content_type_extra,
        )
        self._received = 0
        self._too_large = False

    def receive_data_chunk(self, raw_data, start):
        if self.field_name != "image":
            return raw_data

        if self._too_large:
            return None

        self._received += len(raw_data)
        if self._received > MAX_LISTING_IMAGE_SIZE_BYTES:
            self._too_large = True
            self.request._listing_image_too_large = True
            return None

        return raw_data

    def file_complete(self, file_size):
        return None
