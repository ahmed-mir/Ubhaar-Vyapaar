from decimal import Decimal

from django import forms

from .models import (
    CapacityListing,
    ContactSubmission,
    ManufacturerProfile,
    OrderMessage,
    Quotation,
    QuoteRequest,
    Review,
    WaitlistEntry,
)
from .upload_security import (
    ALLOWED_LISTING_IMAGE_FORMATS,
    LISTING_IMAGE_TOO_LARGE_MESSAGE,
    MAX_LISTING_IMAGE_PIXELS,
    MAX_LISTING_IMAGE_SIZE_BYTES,
)
from .locations import (
    INDIA_PINCODE_HTML_PATTERN,
    INDIA_STATE_UT_CHOICES,
    INDIA_STATE_UT_PLACEHOLDER,
    validate_indian_pincode,
)


class ContactSubmissionForm(forms.ModelForm):
    company_website = forms.CharField(
        required=False,
        label="Website",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "tabindex": "-1",
                "aria-hidden": "true",
            }
        ),
    )

    class Meta:
        model = ContactSubmission
        fields = ("name", "email", "role", "message")
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "message": forms.Textarea(attrs={"rows": 6, "maxlength": 5000}),
        }
        labels = {
            "role": "I am a...",
            "message": "How can we help?",
        }
        help_texts = {
            "message": "Please do not include passwords, payment credentials, or other sensitive information.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(("name", "email", "role", "message", "company_website"))
        for name in ("name", "email", "role", "message"):
            field = self.fields[name]
            field.widget.attrs["aria-required"] = "true"
            if self.is_bound and self[name].errors:
                field.widget.attrs["aria-invalid"] = "true"
                field.widget.attrs["aria-describedby"] = f"id_{name}_error"

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class WaitlistEntryForm(forms.ModelForm):
    website = forms.CharField(
        required=False,
        label="Website",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "tabindex": "-1",
                "aria-hidden": "true",
            }
        ),
    )

    class Meta:
        model = WaitlistEntry
        fields = ("email", "role", "note")
        widgets = {
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "note": forms.Textarea(attrs={"rows": 3, "maxlength": 1000}),
        }
        labels = {"role": "I am a...", "note": "Optional note"}
        help_texts = {"note": "Optional. Up to 1,000 characters."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(("email", "role", "note", "website"))
        for name in ("email", "role", "note"):
            field = self.fields[name]
            described_by = []
            if field.help_text:
                described_by.append(f"id_{name}_helptext")
            if name != "note":
                field.required = True
                field.widget.attrs["aria-required"] = "true"
            if self.is_bound and self[name].errors:
                field.widget.attrs["aria-invalid"] = "true"
                described_by.append(f"id_{name}_error")
            if described_by:
                field.widget.attrs["aria-describedby"] = " ".join(described_by)

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def validate_constraints(self):
        # Duplicate membership is resolved by the POST handler with a neutral
        # PRG response; the database constraint remains the race-safe backstop.
        return


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


class BuyNowForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        label="Quantity",
        widget=forms.NumberInput(attrs={"inputmode": "numeric"}),
    )
    delivery_location = forms.CharField(
        max_length=200,
        label="Delivery location",
        widget=forms.TextInput(attrs={"autocomplete": "shipping locality"}),
    )

    def __init__(self, *args, listing, **kwargs):
        super().__init__(*args, **kwargs)
        self.listing = listing
        minimum = max(1, listing.minimum_quantity)
        self.fields["quantity"].min_value = minimum
        self.fields["quantity"].widget.attrs.update({"min": minimum, "step": 1})
        self.fields["quantity"].initial = minimum
        self.fields["quantity"].help_text = f"Minimum order: {minimum} units."
        if listing.available_capacity is not None:
            self.fields["quantity"].max_value = listing.available_capacity
            self.fields["quantity"].widget.attrs["max"] = listing.available_capacity
            self.fields["quantity"].help_text += (
                f" Available in this period: {listing.available_capacity} units."
            )

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity < max(1, self.listing.minimum_quantity):
            raise forms.ValidationError(
                f"Please order at least {self.listing.minimum_quantity} units."
            )
        if (
            self.listing.available_capacity is not None
            and quantity > self.listing.available_capacity
        ):
            raise forms.ValidationError(
                "The requested quantity exceeds the listed available capacity."
            )
        if self.listing.price_per_unit * quantity > Decimal("9999999999.99"):
            raise forms.ValidationError(
                "The calculated order total is above the supported order limit."
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

        if image.size > MAX_LISTING_IMAGE_SIZE_BYTES:
            raise forms.ValidationError(LISTING_IMAGE_TOO_LARGE_MESSAGE)

        if uploaded_image.format not in ALLOWED_LISTING_IMAGE_FORMATS:
            raise forms.ValidationError(
                "Please upload a JPG, PNG, or WebP image."
            )

        if uploaded_image.width * uploaded_image.height > MAX_LISTING_IMAGE_PIXELS:
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
    state = forms.ChoiceField(
        label="State",
        choices=(
            ("", INDIA_STATE_UT_PLACEHOLDER),
            *INDIA_STATE_UT_CHOICES,
        ),
    )
    pincode = forms.CharField(
        label="PIN code",
        required=False,
        strip=False,
        validators=[validate_indian_pincode],
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "inputmode": "numeric",
                "maxlength": "6",
                "autocomplete": "postal-code",
                "pattern": INDIA_PINCODE_HTML_PATTERN,
            }
        ),
    )

    class Meta:
        model = ManufacturerProfile
        fields = (
            "business_name",
            "description",
            "city",
            "state",
            "pincode",
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
