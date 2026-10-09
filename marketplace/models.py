from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal


class ManufacturerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="manufacturer_profile",
        limit_choices_to={"role": "MANUFACTURER"},
    )

    business_name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return self.business_name


class CapacityListing(models.Model):
    class Category(models.TextChoices):
        PACKAGING = "PACKAGING", "Packaging"
        TEXTILES = "TEXTILES", "Textiles & Apparel"
        METAL = "METAL", "Metal & Fabrication"
        PLASTICS = "PLASTICS", "Plastics"
        WOOD = "WOOD", "Wood & Furniture"
        ELECTRONICS = "ELECTRONICS", "Electronics"
        OTHER = "OTHER", "Other"

    class AvailabilityStatus(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        LIMITED = "LIMITED", "Limited capacity"
        PAUSED = "PAUSED", "Temporarily paused"

    category = models.CharField(
        max_length=30,
        choices=Category.choices,
        default=Category.OTHER,
    )

    manufacturer = models.ForeignKey(
        ManufacturerProfile,
        on_delete=models.CASCADE,
        related_name="listings",
    )

    title = models.CharField(max_length=200)
    description = models.TextField()
    machine_type = models.CharField(max_length=160, blank=True)
    materials = models.CharField(max_length=240, blank=True)
    technical_capabilities = models.TextField(blank=True)
    minimum_quantity = models.PositiveIntegerField(default=100)
    price_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )
    batch_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    production_days = models.PositiveIntegerField(default=7)
    available_capacity = models.PositiveIntegerField(
        null=True,
        blank=True,
    )
    capacity_period = models.CharField(max_length=120, blank=True)
    cluster = models.CharField(max_length=120, blank=True)
    availability_status = models.CharField(
        max_length=20,
        choices=AvailabilityStatus.choices,
        default=AvailabilityStatus.AVAILABLE,
    )
    is_active = models.BooleanField(default=True)

    image = models.ImageField(
        upload_to="listings/",
        blank=True,
    )

    def __str__(self):
        return self.title


class QuoteRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        REJECTED = "REJECTED", "Rejected"

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="quote_requests",
        limit_choices_to={"role": "BUYER"},
    )

    listing = models.ForeignKey(
        CapacityListing,
        on_delete=models.PROTECT,
        related_name="quote_requests",
    )

    quantity = models.PositiveIntegerField()
    requirements = models.TextField()
    delivery_location = models.CharField(max_length=200)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Quote #{self.pk} — {self.listing.title}"

class Quotation(models.Model):
    class Status(models.TextChoices):
        SENT = "SENT", "Awaiting buyer response"
        ACCEPTED = "ACCEPTED", "Accepted by buyer"
        DECLINED = "DECLINED", "Declined by buyer"

    quote_request = models.OneToOneField(
        QuoteRequest,
        on_delete=models.PROTECT,
        related_name="quotation",
    )

    price_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )

    production_days = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )

    message = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SENT,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    @property
    def subtotal(self):
        return self.price_per_unit * self.quantity

    def __str__(self):
        return f"Quotation for request #{self.quote_request_id}"    


class Order(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "CONFIRMED", "Confirmed"
        AWAITING_FUNDING = "AWAITING_FUNDING", "Awaiting demo funding"
        FUNDED = "FUNDED", "Demo funded"
        IN_PRODUCTION = "IN_PRODUCTION", "In production"
        MILESTONE_PENDING = "MILESTONE_PENDING", "Milestone pending review"
        READY_TO_SHIP = "READY_TO_SHIP", "Ready to ship"
        SHIPPED = "SHIPPED", "Shipped"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"
        DISPUTED = "DISPUTED", "Disputed"

    quotation = models.OneToOneField(
        Quotation,
        on_delete=models.PROTECT,
        related_name="order",
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
        limit_choices_to={"role": "BUYER"},
    )
    manufacturer = models.ForeignKey(
        ManufacturerProfile,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    listing = models.ForeignKey(
        CapacityListing,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    specifications_snapshot = models.JSONField(default=dict)
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )
    agreed_unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    agreed_production_days = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.CONFIRMED,
    )
    terms_locked_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"Order #{self.pk} - {self.listing.title}"


class Milestone(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Awaiting buyer approval"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Changes requested"
        DISPUTED = "DISPUTED", "Disputed"

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="milestones",
    )
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    percentage = models.PositiveSmallIntegerField(default=0)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    buyer_feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return f"{self.title} for order #{self.order_id}"
    
class SavedListing(models.Model):
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_listings",
        limit_choices_to={"role": "BUYER"},
    )

    listing = models.ForeignKey(
        CapacityListing,
        on_delete=models.CASCADE,
        related_name="saved_by",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["buyer", "listing"],
                name="unique_buyer_saved_listing",
            ),
        ]

    def __str__(self):
        return f"{self.buyer_id} saved listing {self.listing_id}"    
class Notification(models.Model):
    class Destination(models.TextChoices):
        BUYER_REQUESTS = "BUYER_REQUESTS", "Buyer quote requests"
        BUYER_DASHBOARD = "BUYER_DASHBOARD", "Buyer dashboard"
        MANUFACTURER_DASHBOARD = (
            "MANUFACTURER_DASHBOARD",
            "Manufacturer dashboard",
        )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    message = models.CharField(max_length=255)

    destination = models.CharField(
        max_length=30,
        choices=Destination.choices,
    )

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return self.message    
