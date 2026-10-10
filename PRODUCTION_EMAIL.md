# Production Email Setup

This project keeps Django's console email backend as the default so local
development and automated tests do not send external email by accident.

For production password reset and system emails, configure these environment
variables in Render using Brevo SMTP:

```text
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=<Brevo SMTP login>
EMAIL_HOST_PASSWORD=<Brevo SMTP key>
DEFAULT_FROM_EMAIL=<verified sender address>
SERVER_EMAIL=<system sender address>
```

`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`, and
`SERVER_EMAIL` must come from the deployment environment. Do not commit those
values to source control or store them in project documentation.

The password-reset flow continues to use Django's built-in views and templates.
Use the SMTP backend only in production-like environments; tests should override
email delivery with Django's local memory backend.
