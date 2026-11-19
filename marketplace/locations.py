from django.core.validators import RegexValidator


INDIA_STATE_UT_NAMES = (
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chhattisgarh",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
    "Andaman and Nicobar Islands",
    "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Jammu and Kashmir",
    "Ladakh",
    "Lakshadweep",
    "Puducherry",
)

INDIA_STATE_UT_CHOICES = tuple((name, name) for name in INDIA_STATE_UT_NAMES)
INDIA_STATE_UT_PLACEHOLDER = "Select State / Union Territory"

_INDIA_STATE_UT_CANONICAL = {name.casefold(): name for name in INDIA_STATE_UT_NAMES}


def canonical_india_state_ut_name(value):
    """Return the canonical display label for a known State/UT value."""
    if value in (None, ""):
        return ""

    value = str(value).strip()
    return _INDIA_STATE_UT_CANONICAL.get(value.casefold(), value)

INDIA_PINCODE_REGEX = r"\A[1-9][0-9]{5}\Z"
INDIA_PINCODE_HTML_PATTERN = "[1-9][0-9]{5}"
validate_indian_pincode = RegexValidator(
    regex=INDIA_PINCODE_REGEX,
    message="Enter a valid 6-digit Indian PIN code.",
    code="invalid_pincode",
)
