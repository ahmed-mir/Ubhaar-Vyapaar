#!/usr/bin/env bash

set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --noinput

python manage.py migrate

python manage.py shell -c "from django.contrib.auth.forms import PasswordResetForm; from django.test import RequestFactory; from django.conf import settings; import traceback; f=PasswordResetForm({'email':'mirahmed7801@gmail.com'}); print('FORM VALID:', f.is_valid(), f.errors); rf=RequestFactory(); req=rf.post('/accounts/password/reset/'); req.META['HTTP_HOST']='ubhaar-vyapaar.onrender.com'; req.META['wsgi.url_scheme']='https'; print('BACKEND:', settings.EMAIL_BACKEND); print('FROM:', settings.DEFAULT_FROM_EMAIL); 
try:
    f.save(request=req, use_https=True, email_template_name='accounts/password_reset_email.txt', subject_template_name='accounts/password_reset_subject.txt')
    print('PASSWORD RESET FORM SAVE: SUCCESS')
except Exception as e:
    print('PASSWORD RESET FORM SAVE ERROR:', repr(e))
    traceback.print_exc()"