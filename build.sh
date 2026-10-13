#!/usr/bin/env bash

set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --noinput

python manage.py migrate

python manage.py shell -c "from django.core.mail import send_mail; from django.conf import settings; print('EMAIL_BACKEND=', settings.EMAIL_BACKEND); print('EMAIL_HOST=', settings.EMAIL_HOST); print('DEFAULT_FROM_EMAIL=', settings.DEFAULT_FROM_EMAIL); result=send_mail('Ubhaar-Vyapaar SMTP test','This is a production SMTP test email.',settings.DEFAULT_FROM_EMAIL,['mirahmed7801@gmail.com'],fail_silently=False); print('Emails sent:', result)"