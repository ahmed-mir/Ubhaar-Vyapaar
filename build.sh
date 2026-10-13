#!/usr/bin/env bash

set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --noinput

python manage.py migrate

python manage.py shell -c "import os; from django.contrib.auth import get_user_model; U=get_user_model(); u,_=U.objects.get_or_create(username=os.environ['DJANGO_SUPERUSER_USERNAME'], defaults={'email':os.environ['DJANGO_SUPERUSER_EMAIL']}); u.email=os.environ['DJANGO_SUPERUSER_EMAIL']; u.is_staff=True; u.is_superuser=True; u.set_password(os.environ['DJANGO_SUPERUSER_PASSWORD']); u.save(); print('Production admin reset successfully')"