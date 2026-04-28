#!/bin/bash
set -e
python manage.py migrate --noinput
python manage.py seed_merchants
exec gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120
