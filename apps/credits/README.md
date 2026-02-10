# Credits System

A credit-based marketplace for interview transactions.

## Overview

The credit system handles:
- **Initial Credits**: 1000 credits awarded to attenders on first login
- **Interview Debits**: Credits moved to escrow when requesting interviews
- **Credit Release**: Credits released to takers after feedback submission
- **Refunds**: Credits returned on interview rejection/cancellation

## Models

### CreditBalance
Tracks available and escrow balances for attenders.

### CreditTransaction
Immutable audit log for all credit movements.

### TakerEarnings
Tracks total earnings and pending credits for interviewers.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/credits/balance/` | GET | Get current credit balance |
| `/api/credits/earnings/` | GET | Get taker earnings summary |
| `/api/credits/transactions/` | GET | Get transaction history |
| `/api/credits/summary/` | GET | Get combined summary |
| `/api/credits/check/` | GET | Check interview affordability |

## Credit Flow

```
1. Attender signs up → +1000 initial credits
2. Attender requests interview → credits moved to escrow
3. Interview completed + Taker submits feedback → credits released
4. Interview rejected/cancelled → credits refunded
```

## Integration

Feedback is handled in `apps.interviews.feedback_models.InterviewerFeedback`.

The credit system listens to the `feedback_submitted` signal to release credits.

## cURL Examples

### Get Balance
```bash
curl -X GET "http://localhost:8000/api/credits/balance/" \
    -H "Authorization: Bearer $TOKEN"
```

### Get Transaction History
```bash
curl -X GET "http://localhost:8000/api/credits/transactions/?limit=10" \
    -H "Authorization: Bearer $TOKEN"
```

### Check Affordability
```bash
curl -X GET "http://localhost:8000/api/credits/check/?taker_uuid=<profile-uuid>" \
    -H "Authorization: Bearer $TOKEN"
```
