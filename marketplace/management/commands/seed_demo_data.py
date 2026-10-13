from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from marketplace.models import (
    CapacityListing,
    ManufacturerProfile,
    Milestone,
    Order,
    Quotation,
    QuoteRequest,
    Review,
)


DEMO_PASSWORD = "DemoOnlyPass123!"
DEMO_ASSET_ROOT = (
    Path(settings.BASE_DIR)
    / "marketplace"
    / "static"
    / "marketplace"
    / "images"
    / "demo"
)


MANUFACTURERS = [
    {
        "username": "demo_mfr_aarav_forge",
        "email": "manufacturer1@example.com",
        "business_name": "Aarav Forge & Fabrication",
        "description": (
            "Fictional supplier profile for metal fabrication, machined "
            "components, and short-run industrial assemblies."
        ),
        "city": "Pune",
        "state": "Maharashtra",
        "is_verified": True,
    },
    {
        "username": "demo_mfr_nila_pack",
        "email": "manufacturer2@example.com",
        "business_name": "Nila Packworks",
        "description": (
            "Fictional converter profile for corrugated cartons, mailers, "
            "inserts, and printed labels."
        ),
        "city": "Ahmedabad",
        "state": "Gujarat",
        "is_verified": True,
    },
    {
        "username": "demo_mfr_kaveri_textiles",
        "email": "manufacturer3@example.com",
        "business_name": "Kaveri Textile Unit",
        "description": (
            "Fictional apparel and textile production unit with cutting, "
            "stitching, finishing, and dyeing coordination."
        ),
        "city": "Tiruppur",
        "state": "Tamil Nadu",
        "is_verified": True,
    },
    {
        "username": "demo_mfr_circuit_leaf",
        "email": "manufacturer4@example.com",
        "business_name": "CircuitLeaf Assemblies",
        "description": (
            "Fictional electronics assembly team for prototype and "
            "small-batch PCB work."
        ),
        "city": "Bengaluru",
        "state": "Karnataka",
        "is_verified": True,
    },
    {
        "username": "demo_mfr_veer_plastics",
        "email": "manufacturer5@example.com",
        "business_name": "Veer Plastics Studio",
        "description": (
            "Fictional plastics unit profile for injection moulding, tool "
            "trials, and polymer component runs."
        ),
        "city": "Noida",
        "state": "Uttar Pradesh",
        "is_verified": False,
    },
]


LISTINGS = [
    {
        "manufacturer": "demo_mfr_aarav_forge",
        "title": "CNC Machining Capacity for Aluminium Components",
        "category": CapacityListing.Category.METAL,
        "description": (
            "Precision CNC milling and turning capacity for small industrial "
            "parts, brackets, and housings. Suitable for "
            "pilot batches that need inspection reports, deburring, and "
            "repeatable tolerances before larger production runs."
        ),
        "machine_type": "3-axis VMC and CNC turning centre",
        "materials": "Aluminium 6061, mild steel, brass",
        "technical_capabilities": (
            "Typical tolerance up to +/-0.05 mm depending on geometry.\n"
            "Deburring, tapping, countersinking, and basic inspection reports "
            "available for production batches."
        ),
        "minimum_quantity": 50,
        "price_per_unit": Decimal("145.00"),
        "batch_price": Decimal("7250.00"),
        "production_days": 12,
        "available_capacity": 1200,
        "capacity_period": "per month",
        "cluster": "Pimpri-Chinchwad industrial belt",
        "availability_status": CapacityListing.AvailabilityStatus.AVAILABLE,
        "image": "cnc-machining-capacity.webp",
    },
    {
        "manufacturer": "demo_mfr_nila_pack",
        "title": "Custom Corrugated Packaging for D2C Shipments",
        "category": CapacityListing.Category.PACKAGING,
        "description": (
            "Shipper cartons, mailer boxes, and protective inserts for "
            "growing consumer brands. The unit can "
            "support sample approval, kraft or white board options, and "
            "single-colour print runs."
        ),
        "machine_type": "Corrugation, slotting, die-cutting, flexo print",
        "materials": "3-ply and 5-ply corrugated board, kraft liner",
        "technical_capabilities": (
            "Board burst strength and flute selection can be matched to "
            "product weight. Printed cartons available after artwork approval."
        ),
        "minimum_quantity": 500,
        "price_per_unit": Decimal("18.50"),
        "batch_price": Decimal("9250.00"),
        "production_days": 7,
        "available_capacity": 25000,
        "capacity_period": "per week",
        "cluster": "Naroda packaging cluster",
        "availability_status": CapacityListing.AvailabilityStatus.AVAILABLE,
        "image": "corrugated-packaging.webp",
    },
    {
        "manufacturer": "demo_mfr_kaveri_textiles",
        "title": "Cotton Garment Production and Finishing",
        "category": CapacityListing.Category.TEXTILES,
        "description": (
            "Cotton tees, loungewear, and simple woven garments. Best suited "
            "for brands that need fabric sourcing, "
            "cutting, stitching, finishing, packing, and steady repeat lots."
        ),
        "machine_type": "Cutting table, overlock, flatlock, finishing line",
        "materials": "Cotton jersey, interlock, rib, woven cotton",
        "technical_capabilities": (
            "Pattern-based cutting, size grading support, thread trimming, "
            "pressing, folding, and polybag packing. Sampling can be planned "
            "before bulk production."
        ),
        "minimum_quantity": 300,
        "price_per_unit": Decimal("92.00"),
        "batch_price": Decimal("27600.00"),
        "production_days": 14,
        "available_capacity": 6000,
        "capacity_period": "per month",
        "cluster": "Tiruppur apparel cluster",
        "availability_status": CapacityListing.AvailabilityStatus.LIMITED,
        "image": "cotton-garment-production.webp",
    },
    {
        "manufacturer": "demo_mfr_aarav_forge",
        "title": "Sheet Metal Fabrication for Enclosures and Brackets",
        "category": CapacityListing.Category.METAL,
        "description": (
            "Laser-cut, bent, and welded sheet metal parts for equipment "
            "panels, electrical enclosures, "
            "mounting brackets, and low-volume industrial assemblies."
        ),
        "machine_type": "Laser cutting, press brake, MIG welding",
        "materials": "CRCA sheet, stainless steel 304, galvanised sheet",
        "technical_capabilities": (
            "Cutting up to 6 mm mild steel, press brake bends, tack welding, "
            "grinding, and powder-coating coordination available."
        ),
        "minimum_quantity": 40,
        "price_per_unit": Decimal("240.00"),
        "batch_price": Decimal("9600.00"),
        "production_days": 10,
        "available_capacity": 850,
        "capacity_period": "next 30 days",
        "cluster": "Bhosari MIDC",
        "availability_status": CapacityListing.AvailabilityStatus.AVAILABLE,
        "image": "sheet-metal-fabrication.webp",
    },
    {
        "manufacturer": "demo_mfr_veer_plastics",
        "title": "Injection Moulding Trial Slots for Polymer Parts",
        "category": CapacityListing.Category.PLASTICS,
        "description": (
            "Plastic component trials and short production runs for teams "
            "validating tooling, materials, and first-article samples."
        ),
        "machine_type": "120T and 180T injection moulding machines",
        "materials": "PP, ABS, HDPE, nylon",
        "technical_capabilities": (
            "Tool loading, first article samples, colour masterbatch trials, "
            "gate trimming, and basic dimensional checks."
        ),
        "minimum_quantity": 1000,
        "price_per_unit": Decimal("12.75"),
        "batch_price": Decimal("12750.00"),
        "production_days": 9,
        "available_capacity": 18000,
        "capacity_period": "per week",
        "cluster": "Noida Phase II",
        "availability_status": CapacityListing.AvailabilityStatus.AVAILABLE,
        "image": "injection-moulding.webp",
    },
    {
        "manufacturer": "demo_mfr_nila_pack",
        "title": "Custom Printed Labels and Product Stickers",
        "category": CapacityListing.Category.PACKAGING,
        "description": (
            "Roll labels, product stickers, dispatch labels, and barcode "
            "labels for packaging teams that "
            "need predictable repeat orders and quick artwork changes."
        ),
        "machine_type": "Digital label press and roll slitting",
        "materials": "Paper labels, PP labels, adhesive stock",
        "technical_capabilities": (
            "Matte or gloss lamination, die-cut shapes, barcode printing, "
            "roll winding, and SKU-level artwork handling."
        ),
        "minimum_quantity": 2000,
        "price_per_unit": Decimal("1.85"),
        "batch_price": Decimal("3700.00"),
        "production_days": 5,
        "available_capacity": 75000,
        "capacity_period": "per week",
        "cluster": "Ahmedabad print lane",
        "availability_status": CapacityListing.AvailabilityStatus.AVAILABLE,
        "image": "printed-labels.webp",
    },
    {
        "manufacturer": "demo_mfr_circuit_leaf",
        "title": "PCB Assembly for Prototype Electronics",
        "category": CapacityListing.Category.ELECTRONICS,
        "description": (
            "Prototype PCB assembly, small batches, and repair-friendly "
            "builds for hardware teams that "
            "need board bring-up support before production scale-up."
        ),
        "machine_type": "SMT pick-and-place, reflow, bench assembly",
        "materials": "FR4 PCB, SMD components, through-hole connectors",
        "technical_capabilities": (
            "0402 passive placement, IC alignment checks, through-hole hand "
            "soldering, visual inspection, and functional test fixture support."
        ),
        "minimum_quantity": 25,
        "price_per_unit": Decimal("310.00"),
        "batch_price": Decimal("7750.00"),
        "production_days": 8,
        "available_capacity": 400,
        "capacity_period": "per week",
        "cluster": "Peenya electronics cluster",
        "availability_status": CapacityListing.AvailabilityStatus.LIMITED,
        "image": "pcb-assembly.webp",
    },
    {
        "manufacturer": "demo_mfr_aarav_forge",
        "title": "Stainless Steel Components with Polished Finish",
        "category": CapacityListing.Category.METAL,
        "description": (
            "Stainless handles, clamps, spacers, and custom fixtures with "
            "fabrication and finishing coordination "
            "for buyers who need durable parts with presentable surfaces."
        ),
        "machine_type": "CNC turning, TIG welding, polishing station",
        "materials": "SS 304, SS 316",
        "technical_capabilities": (
            "Turning, drilling, welding, brushed finish, mirror polish by "
            "approval, and batch-level visual checks."
        ),
        "minimum_quantity": 75,
        "price_per_unit": Decimal("185.00"),
        "batch_price": Decimal("13875.00"),
        "production_days": 11,
        "available_capacity": 900,
        "capacity_period": "per month",
        "cluster": "Pune metalworks cluster",
        "availability_status": CapacityListing.AvailabilityStatus.AVAILABLE,
        "image": "stainless-steel-components.webp",
    },
    {
        "manufacturer": "demo_mfr_aarav_forge",
        "title": "Industrial Fasteners Sorting and Small-Batch Supply",
        "category": CapacityListing.Category.METAL,
        "description": (
            "Procurement-backed fastener kits sorted by size and finish for "
            "equipment assembly lines. Suitable for "
            "maintenance kits and low-volume equipment assembly."
        ),
        "machine_type": "Fastener sourcing, sorting, kit packing",
        "materials": "MS, stainless steel, zinc plated hardware",
        "technical_capabilities": (
            "Bolt, washer, nut, and spacer kits can be packed against a bill "
            "of materials with lot-level labels."
        ),
        "minimum_quantity": 1000,
        "price_per_unit": Decimal("3.20"),
        "batch_price": Decimal("3200.00"),
        "production_days": 4,
        "available_capacity": 60000,
        "capacity_period": "per week",
        "cluster": "Chakan supply cluster",
        "availability_status": CapacityListing.AvailabilityStatus.AVAILABLE,
        "image": "industrial-fasteners.webp",
    },
    {
        "manufacturer": "demo_mfr_kaveri_textiles",
        "title": "Textile Dyeing Coordination for Small Fabric Lots",
        "category": CapacityListing.Category.TEXTILES,
        "description": (
            "Dyeing coordination, shade matching, and finish planning for "
            "cotton fabric lots. Useful when buyers need "
            "a controlled test run before committing to larger fabric orders."
        ),
        "machine_type": "Dyeing partner network and finishing checks",
        "materials": "Cotton jersey, rib, fleece, woven cotton",
        "technical_capabilities": (
            "Lab dip coordination, shade card approval, wash effect planning, "
            "fabric GSM checks, and batch documentation."
        ),
        "minimum_quantity": 250,
        "price_per_unit": Decimal("38.00"),
        "batch_price": Decimal("9500.00"),
        "production_days": 16,
        "available_capacity": 3500,
        "capacity_period": "per month",
        "cluster": "Tiruppur dyeing support lane",
        "availability_status": CapacityListing.AvailabilityStatus.PAUSED,
        "image": "textile-dyeing.webp",
    },
]


REVIEWS = [
    {
        "listing": "Custom Corrugated Packaging for D2C Shipments",
        "buyer": "demo_buyer_packaging",
        "email": "buyer1@example.com",
        "quantity": 800,
        "comment": (
            "Cartons matched the approved sample and delivery updates were "
            "clear."
        ),
    },
    {
        "listing": "PCB Assembly for Prototype Electronics",
        "buyer": "demo_buyer_electronics",
        "email": "buyer2@example.com",
        "quantity": 40,
        "comment": (
            "Prototype assembly was neatly packed and the team flagged "
            "component substitutions early."
        ),
    },
]


class Command(BaseCommand):
    help = (
        "Seed fictional demo manufacturers, listings, images, and a small "
        "amount of completed-order review data. This command is manual and "
        "does not run during migrate, deploy, or server startup."
    )

    def handle(self, *args, **options):
        with transaction.atomic():
            manufacturers = self.seed_manufacturers()
            listings = self.seed_listings(manufacturers)
            self.seed_reviews(listings)

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded demo data: "
                f"{len(manufacturers)} manufacturers, "
                f"{len(listings)} listings, "
                f"{len(REVIEWS)} reviews."
            )
        )

    def seed_manufacturers(self):
        User = get_user_model()
        manufacturers = {}

        for item in MANUFACTURERS:
            user, _ = User.objects.update_or_create(
                username=item["username"],
                defaults={
                    "email": item["email"],
                    "role": User.Role.MANUFACTURER,
                    "phone": "",
                    "terms_accepted_at": timezone.now(),
                    "privacy_acknowledged_at": timezone.now(),
                    "terms_version": settings.TERMS_VERSION,
                    "privacy_policy_version": settings.PRIVACY_POLICY_VERSION,
                },
            )
            user.set_password(DEMO_PASSWORD)
            user.save(update_fields=["password"])

            profile, _ = ManufacturerProfile.objects.update_or_create(
                user=user,
                defaults={
                    "business_name": item["business_name"],
                    "description": item["description"],
                    "city": item["city"],
                    "state": item["state"],
                    "is_verified": item["is_verified"],
                    "kyc_status": (
                        ManufacturerProfile.KycStatus.VERIFIED
                        if item["is_verified"]
                        else ManufacturerProfile.KycStatus.UNDER_REVIEW
                    ),
                },
            )
            manufacturers[item["username"]] = profile

        return manufacturers

    def seed_listings(self, manufacturers):
        listings = {}

        for item in LISTINGS:
            image_name = self.ensure_demo_image(item["image"])
            listing, _ = CapacityListing.objects.update_or_create(
                manufacturer=manufacturers[item["manufacturer"]],
                title=item["title"],
                defaults={
                    "category": item["category"],
                    "description": item["description"],
                    "machine_type": item["machine_type"],
                    "materials": item["materials"],
                    "technical_capabilities": item["technical_capabilities"],
                    "minimum_quantity": item["minimum_quantity"],
                    "price_per_unit": item["price_per_unit"],
                    "batch_price": item["batch_price"],
                    "production_days": item["production_days"],
                    "available_capacity": item["available_capacity"],
                    "capacity_period": item["capacity_period"],
                    "cluster": item["cluster"],
                    "availability_status": item["availability_status"],
                    "is_active": True,
                    "image": image_name,
                },
            )
            listings[item["title"]] = listing

        return listings

    def ensure_demo_image(self, filename):
        if not filename:
            return ""

        source_path = DEMO_ASSET_ROOT / filename

        if not source_path.exists():
            raise FileNotFoundError(f"Missing demo asset: {source_path}")

        storage_name = f"demo/listings/{filename}"

        if default_storage.exists(storage_name):
            return storage_name

        with source_path.open("rb") as source_file:
            return default_storage.save(storage_name, File(source_file))

    def seed_reviews(self, listings):
        User = get_user_model()

        for item in REVIEWS:
            buyer, _ = User.objects.update_or_create(
                username=item["buyer"],
                defaults={
                    "email": item["email"],
                    "role": User.Role.BUYER,
                    "phone": "",
                    "terms_accepted_at": timezone.now(),
                    "privacy_acknowledged_at": timezone.now(),
                    "terms_version": settings.TERMS_VERSION,
                    "privacy_policy_version": settings.PRIVACY_POLICY_VERSION,
                },
            )
            buyer.set_password(DEMO_PASSWORD)
            buyer.save(update_fields=["password"])

            listing = listings[item["listing"]]
            quote_request, _ = QuoteRequest.objects.update_or_create(
                buyer=buyer,
                listing=listing,
                defaults={
                    "quantity": item["quantity"],
                    "requirements": (
                        "Demo/test quote request for launch-readiness QA."
                    ),
                    "delivery_location": "Demo delivery location",
                    "status": QuoteRequest.Status.ACCEPTED,
                },
            )
            quotation, _ = Quotation.objects.update_or_create(
                quote_request=quote_request,
                defaults={
                    "price_per_unit": listing.price_per_unit,
                    "quantity": item["quantity"],
                    "production_days": listing.production_days,
                    "message": "Demo/test quotation for launch-readiness QA.",
                    "status": Quotation.Status.ACCEPTED,
                    "responded_at": timezone.now(),
                },
            )
            total_amount = listing.price_per_unit * item["quantity"]
            order, _ = Order.objects.update_or_create(
                quotation=quotation,
                defaults={
                    "buyer": buyer,
                    "manufacturer": listing.manufacturer,
                    "listing": listing,
                    "specifications_snapshot": {
                        "listing_title": listing.title,
                        "listing_category": listing.get_category_display(),
                        "requirements": quote_request.requirements,
                        "delivery_location": quote_request.delivery_location,
                        "machine_type": listing.machine_type,
                        "materials": listing.materials,
                    },
                    "quantity": item["quantity"],
                    "agreed_unit_price": listing.price_per_unit,
                    "total_amount": total_amount,
                    "agreed_production_days": listing.production_days,
                    "status": Order.Status.COMPLETED,
                    "terms_locked_at": timezone.now(),
                },
            )
            Milestone.objects.update_or_create(
                order=order,
                title="Demo production completed",
                defaults={
                    "description": (
                        "Demo/test completed milestone for review signals."
                    ),
                    "percentage": 100,
                    "amount": total_amount,
                    "status": Milestone.Status.APPROVED,
                    "funding_status": Milestone.FundingStatus.RELEASED,
                    "funded_at": timezone.now(),
                    "released_at": timezone.now(),
                    "started_at": timezone.now(),
                    "completed_at": timezone.now(),
                    "approved_at": timezone.now(),
                    "buyer_feedback": "Demo/test milestone approved.",
                },
            )
            Review.objects.update_or_create(
                order=order,
                buyer=buyer,
                defaults={
                    "manufacturer": listing.manufacturer,
                    "quality_rating": 5,
                    "timeliness_rating": 4,
                    "communication_rating": 5,
                    "overall_rating": 5,
                    "comment": item["comment"],
                },
            )
