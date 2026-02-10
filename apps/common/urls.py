# apps/common/urls.py
from django.urls import path
from . import api

urlpatterns = [
    path('enums/', api.enums_api, name='enums'),
]
