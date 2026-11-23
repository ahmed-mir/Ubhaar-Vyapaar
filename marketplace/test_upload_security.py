from io import BytesIO
from types import SimpleNamespace

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import CapacityListingForm
from .models import CapacityListing, ManufacturerProfile
from .upload_security import (
    LISTING_IMAGE_TOO_LARGE_MESSAGE,
    MAX_LISTING_IMAGE_PIXELS,
    MAX_LISTING_IMAGE_SIZE_BYTES,
    ListingImageSizeUploadHandler,
)


class ListingImageValidationTests(TestCase):
    def image_bytes(self, image_format, size=(24, 18)):
        output = BytesIO()
        Image.new("RGB", size, (25, 80, 120)).save(output, format=image_format)
        return output.getvalue()

    def form_data(self):
        return {
            "title": "Capacity image test",
            "category": CapacityListing.Category.OTHER,
            "description": "A listing with an uploaded image.",
            "machine_type": "",
            "materials": "",
            "technical_capabilities": "",
            "minimum_quantity": "1",
            "price_per_unit": "10.00",
            "batch_price": "",
            "production_days": "3",
            "available_capacity": "",
            "capacity_period": "",
            "cluster": "",
            "availability_status": CapacityListing.AvailabilityStatus.AVAILABLE,
        }

    def make_form(self, content, filename="capacity.jpg"):
        return CapacityListingForm(
            self.form_data(),
            {
                "image": SimpleUploadedFile(
                    filename,
                    content,
                    content_type="application/octet-stream",
                )
            },
        )

    def test_jpeg_png_and_webp_uploads_remain_valid(self):
        for image_format, extension in (
            ("JPEG", ".jpg"),
            ("PNG", ".png"),
            ("WEBP", ".webp"),
        ):
            with self.subTest(image_format=image_format):
                form = self.make_form(
                    self.image_bytes(image_format), f"capacity{extension}"
                )
                self.assertTrue(form.is_valid(), form.errors)

    def test_renamed_non_image_and_corrupt_or_truncated_images_are_rejected(self):
        for content in (b"not an image", self.image_bytes("PNG")[:-12]):
            form = self.make_form(content, "renamed.jpg")
            self.assertFalse(form.is_valid())
            self.assertIn("image", form.errors)

    def test_gif_and_bmp_are_rejected_even_when_pillow_can_decode_them(self):
        for image_format, extension in (("GIF", ".gif"), ("BMP", ".bmp")):
            with self.subTest(image_format=image_format):
                form = self.make_form(
                    self.image_bytes(image_format), f"unsupported{extension}"
                )
                self.assertFalse(form.is_valid())
                self.assertIn("JPG, PNG, or WebP", str(form.errors["image"]))

    def test_file_size_is_checked_from_uploaded_file_bytes(self):
        valid_image = self.image_bytes("JPEG")
        padding_size = MAX_LISTING_IMAGE_SIZE_BYTES + 1 - len(valid_image)
        form = self.make_form(valid_image + (b"x" * padding_size), "large.jpg")
        self.assertFalse(form.is_valid())
        self.assertIn("5 MB", str(form.errors["image"]))

    def test_decoded_pixel_limit_rejects_image_above_20_megapixels(self):
        # Mode 1 keeps the synthetic over-limit fixture small in memory.
        width, height = 5000, MAX_LISTING_IMAGE_PIXELS // 5000 + 1
        output = BytesIO()
        Image.new("1", (width, height), 0).save(output, format="PNG", optimize=True)
        form = self.make_form(output.getvalue(), "large-dimensions.png")
        self.assertFalse(form.is_valid())
        self.assertIn("20 megapixels", str(form.errors["image"]))

    def test_unusual_filename_is_accepted_without_using_filename_as_path(self):
        form = self.make_form(
            self.image_bytes("PNG"), "..\\..//unusual name #?.png"
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn("..", form.cleaned_data["image"].name)
        self.assertNotIn("/", form.cleaned_data["image"].name)
        self.assertNotIn("\\", form.cleaned_data["image"].name)

    def test_streaming_handler_uses_actual_bytes_not_content_length(self):
        request = SimpleNamespace()
        handler = ListingImageSizeUploadHandler(request)
        handler.new_file(
            "image", "small.jpg", "image/jpeg", content_length=1
        )
        self.assertIsNotNone(handler.receive_data_chunk(b"x" * MAX_LISTING_IMAGE_SIZE_BYTES, 0))
        self.assertIsNone(handler.receive_data_chunk(b"x", MAX_LISTING_IMAGE_SIZE_BYTES))
        self.assertTrue(request._listing_image_too_large)

    @override_settings(
        PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
    )
    def test_oversized_multipart_image_gets_a_form_error_and_is_not_saved(self):
        user = get_user_model().objects.create_user(
            username="upload-maker",
            password="not-a-real-password",
            role="MANUFACTURER",
        )
        ManufacturerProfile.objects.create(
            user=user,
            business_name="Upload Works",
            city="Pune",
            state="Maharashtra",
        )
        self.client.force_login(user)
        image = self.image_bytes("JPEG")
        image += b"x" * (MAX_LISTING_IMAGE_SIZE_BYTES + 1 - len(image))
        response = self.client.post(
            reverse("create_listing"),
            {
                **self.form_data(),
                "image": SimpleUploadedFile(
                    "large.jpg", image, content_type="image/jpeg"
                ),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, LISTING_IMAGE_TOO_LARGE_MESSAGE)
        self.assertEqual(CapacityListing.objects.count(), 0)
