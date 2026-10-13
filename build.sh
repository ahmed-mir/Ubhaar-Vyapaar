#!/usr/bin/env bash

set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --noinput

python manage.py migrate

python manage.py shell -c "from django.contrib.auth import get_user_model; U=get_user_model(); qs=U.objects.filter(email__iexact='mirahmed7801@gmail.com'); print('PASSWORD RESET USERS:', [(u.pk,u.username,u.is_active,u.has_usable_password(),u.email) for u in qs])"