from django import forms

from .models import (
    CapacityListing,
    ManufacturerProfile,
    OrderMessage,
    Quotation,
    QuoteRequest,
    Review,
)


class QuoteRequestForm(forms.ModelForm):
    class Meta:
        model = QuoteRequest
        fields = (
            "quantity",
            "requirements",
            "delivery_location",
        )
        widgets = {
            "requirements": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": (
                        "Describe your size, material, or other requirements"
                    ),
                }
            ),
        }

    def __init__(self, *args, listing, **kwargs):
        super().__init__(*args, **kwargs)
        self.listing = listing

        minimum = max(1, listing.minimum_quantity)
        self.fields["quantity"].min_value = minimum
        self.fields["quantity"].widget.attrs["min"] = minimum
        self.fields["quantity"].help_text = (
            f"Minimum order: {minimum} units."
        )

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        minimum = max(1, self.listing.minimum_quantity)

        if quantity < minimum:
            raise forms.ValidationError(
                f"Please request at least {minimum} units."
            )

        return quantity


class CapacityListingForm(forms.ModelForm):
    class Meta:
        model = CapacityListing
        fields = (
            "title",
            "category",
            "description",
            "machine_type",
            "materials",
            "technical_capabilities",
            "image",
            "minimum_quantity",
            "price_per_unit",
            "batch_price",
            "production_days",
            "available_capacity",
            "capacity_period",
            "cluster",
            "availability_status",
        )
        widgets = {
            "description": forms.Textarea(
                attrs={"rows": 4}
            ),
            "technical_capabilities": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": (
                        "Share machine limits, finishing options, tolerances, "
                        "or other production capabilities."
                    ),
                }
            ),
            "image": forms.ClearableFileInput(
                attrs={
                    "accept": "image/jpeg,image/png,image/webp",
                }
            ),
        }
        help_texts = {
            "machine_type": "Optional. Example: offset press, CNC router, stitching line.",
            "materials": "Optional. Example: corrugated board, cotton, mild steel.",
            "batch_price": "Optional. Use this when you price a full batch instead of only per unit.",
            "available_capacity": "Optional. Enter the number of units available in the stated period.",
            "capacity_period": "Optional. Example: per week, June slot, next 30 days.",
            "cluster": "Optional. Manufacturing cluster or industrial area.",
            "image": (
                "Optional. Upload a JPG, PNG, or WebP image "
                "up to 5 MB and 20 megapixels."
            ),
        }

    def clean_image(self):
        image = self.cleaned_data.get("image")

        # Allow an empty image or removal of an existing image.
        if not image:
            return image

        # Validate new uploads. An unchanged saved image has no
        # uploaded image object and does not need revalidation.
        uploaded_image = getattr(image, "image", None)

        if uploaded_image is None:
            return image

        if image.size > 5 * 1024 * 1024:
            raise forms.ValidationError(
                "Please upload an image no larger than 5 MB."
            )

        if uploaded_image.format not in {"JPEG", "PNG", "WEBP"}:
            raise forms.ValidationError(
                "Please upload a JPG, PNG, or WebP image."
            )

        if uploaded_image.width * uploaded_image.height > 20_000_000:
            raise forms.ValidationError(
                "Please use an image with no more than 20 megapixels."
            )

        return image

    def clean(self):
        cleaned_data = super().clean()

        for field in (
            "minimum_quantity",
            "price_per_unit",
            "batch_price",
            "production_days",
            "available_capacity",
        ):
            value = cleaned_data.get(field)

            if value is not None and value <= 0:
                self.add_error(
                    field,
                    "Enter a value greater than zero.",
                )

        return cleaned_data


class CapacityListingEditForm(CapacityListingForm):
    class Meta(CapacityListingForm.Meta):
        fields = CapacityListingForm.Meta.fields + ("is_active",)

class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        fields = (
            "price_per_unit",
            "production_days",
            "message",
        )
        widgets = {
            "message": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": (
                        "Explain what the price includes, delivery "
                        "arrangements, and any additional charges."
                    ),
                }
            ),
        }
        help_texts = {
            "price_per_unit": "Enter the quoted price per unit in rupees.",
            "production_days": "Estimated production time in days.",
        }        

class ManufacturerProfileForm(forms.ModelForm):
    class Meta:
        model = ManufacturerProfile
        fields = (
            "business_name",
            "description",
            "city",
            "state",
        )
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": (
                        "Describe your manufacturing capabilities, "
                        "materials, and services."
                    ),
                }
            ),
        }


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = (
            "quality_rating",
            "timeliness_rating",
            "communication_rating",
            "overall_rating",
            "comment",
        )
        widgets = {
            "quality_rating": forms.NumberInput(attrs={"min": 1, "max": 5}),
            "timeliness_rating": forms.NumberInput(attrs={"min": 1, "max": 5}),
            "communication_rating": forms.NumberInput(attrs={"min": 1, "max": 5}),
            "overall_rating": forms.NumberInput(attrs={"min": 1, "max": 5}),
            "comment": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Share practical feedback for other buyers.",
                }
            ),
        }
        help_texts = {
            "quality_rating": "Rate from 1 to 5.",
            "timeliness_rating": "Rate from 1 to 5.",
            "communication_rating": "Rate from 1 to 5.",
            "overall_rating": "Rate from 1 to 5.",
        }


class OrderMessageForm(forms.ModelForm):
    class Meta:
        model = OrderMessage
        fields = ("body",)
        labels = {
            "body": "Message",
        }
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": (
                        "Send an order-specific update or question."
                    ),
                }
            ),
        }
