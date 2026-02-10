# apps\accounts\urls.py
from django.urls import path
from . import api

urlpatterns = [
    path("", api.health_check, name="health_check"),
]
