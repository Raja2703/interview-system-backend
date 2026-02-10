# apps/credits/urls.py
"""
URL configuration for credits API.

Endpoints:
- /api/credits/balance/               - GET credit balance (attenders)
- /api/credits/earnings/              - GET taker earnings
- /api/credits/transactions/          - GET transaction history
- /api/credits/summary/               - GET combined summary
- /api/credits/check/                 - GET check affordability

Note: Feedback endpoints have been moved to apps.interviews
Note: Admin endpoints have been removed
"""

from django.urls import path
from .api import (
    CreditBalanceAPI,
    TakerEarningsAPI,
    CreditTransactionListAPI,
    CreditSummaryAPI,
    CheckCreditsAPI,
)

app_name = 'credits'

urlpatterns = [
    # Balance and earnings
    path('balance/', CreditBalanceAPI.as_view(), name='balance'),
    path('earnings/', TakerEarningsAPI.as_view(), name='earnings'),
    path('transactions/', CreditTransactionListAPI.as_view(), name='transactions'),
    path('summary/', CreditSummaryAPI.as_view(), name='summary'),
    path('check/', CheckCreditsAPI.as_view(), name='check'),
]
