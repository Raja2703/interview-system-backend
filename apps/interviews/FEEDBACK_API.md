# Interviewer Feedback API

## Overview

This endpoint allows interviewers (takers) to submit mandatory feedback after conducting an interview. Feedback submission is required for credit payout.

## Endpoint

```
POST /api/interviews/{interview_id}/feedback/interviewer/
GET  /api/interviews/{interview_id}/feedback/interviewer/
```

## Rules & Validation

1. **Only the taker (interviewer)** can submit feedback
2. Feedback can be submitted **once per interview**
3. Interview status must be **accepted** or **completed**
4. **All 4 questions** require both numeric rating (1-5) AND text explanation
5. **Overall feedback** text is required

## Request Body

```json
{
    "problem_understanding_rating": 4,
    "problem_understanding_text": "Candidate quickly understood the problem requirements...",
    
    "solution_approach_rating": 5,
    "solution_approach_text": "Excellent approach using efficient algorithms...",
    
    "implementation_skill_rating": 4,
    "implementation_skill_text": "Clean code with proper error handling...",
    
    "communication_rating": 5,
    "communication_text": "Clearly explained thought process throughout...",
    
    "overall_feedback": "Strong candidate with excellent technical skills. Would recommend for senior positions."
}
```

## Field Validation

| Field | Type | Constraints |
|-------|------|-------------|
| `*_rating` | Integer | Required, 1-5 |
| `*_text` | String | Required, min 10 chars |
| `overall_feedback` | String | Required, min 20 chars |

## Response

### Success (201 Created)

```json
{
    "detail": "Feedback submitted successfully. Credit payout triggered.",
    "feedback": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "interview_uuid": "123e4567-e89b-12d3-a456-426614174000",
        "interviewer_email": "taker@example.com",
        "status": "submitted",
        "status_display": "Submitted",
        "problem_understanding_rating": 4,
        "problem_understanding_text": "...",
        "solution_approach_rating": 5,
        "solution_approach_text": "...",
        "implementation_skill_rating": 4,
        "implementation_skill_text": "...",
        "communication_rating": 5,
        "communication_text": "...",
        "overall_feedback": "...",
        "average_rating": 4.5,
        "is_complete": true,
        "submitted_at": "2026-02-05T09:30:00Z",
        "created_at": "2026-02-05T09:25:00Z",
        "updated_at": "2026-02-05T09:30:00Z"
    },
    "credits_pending": 100
}
```

### Error Responses

| Status | Reason |
|--------|--------|
| 400 | Validation error or already submitted |
| 403 | Not the interviewer |
| 404 | Interview not found |

---

## cURL Commands

### 1. Get Auth Token (Login)

```bash
# Login to get access token
ACCESS_TOKEN=$(curl -s -X POST "http://localhost:8000/api/auth/login/" \
    -H "Content-Type: application/json" \
    -d '{"email": "taker@example.com", "password": "yourpassword"}' \
    | jq -r '.access')

echo "Access Token: $ACCESS_TOKEN"
```

### 2. Submit Interviewer Feedback

```bash
# Replace {INTERVIEW_UUID} with actual interview ID
INTERVIEW_UUID="your-interview-uuid-here"

curl -X POST "http://localhost:8000/api/interviews/${INTERVIEW_UUID}/feedback/interviewer/" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -d '{
        "problem_understanding_rating": 4,
        "problem_understanding_text": "The candidate demonstrated a solid understanding of the problem requirements. They asked clarifying questions before starting to code.",
        
        "solution_approach_rating": 5,
        "solution_approach_text": "Excellent approach! The candidate chose an optimal algorithm with O(n log n) time complexity and explained their reasoning clearly.",
        
        "implementation_skill_rating": 4,
        "implementation_skill_text": "Clean implementation with proper variable naming. Added edge case handling. Could improve code organization slightly.",
        
        "communication_rating": 5,
        "communication_text": "Outstanding communication throughout the interview. Clearly articulated thought process and was receptive to hints.",
        
        "overall_feedback": "Strong candidate with excellent technical skills and communication abilities. I would recommend hiring for senior developer positions. Shows great potential for growth and team collaboration."
    }'
```

### 3. Get Feedback (View)

```bash
curl -X GET "http://localhost:8000/api/interviews/${INTERVIEW_UUID}/feedback/interviewer/" \
    -H "Authorization: Bearer $ACCESS_TOKEN"
```

---

## Windows PowerShell Commands

### Login

```powershell
$response = Invoke-RestMethod -Uri "http://localhost:8000/api/auth/login/" `
    -Method POST `
    -ContentType "application/json" `
    -Body '{"email": "taker@example.com", "password": "yourpassword"}'

$token = $response.access
Write-Host "Token: $token"
```

### Submit Feedback

```powershell
$interviewId = "your-interview-uuid-here"
$body = @{
    problem_understanding_rating = 4
    problem_understanding_text = "The candidate demonstrated solid understanding of the problem requirements."
    solution_approach_rating = 5
    solution_approach_text = "Excellent approach with optimal algorithm selection."
    implementation_skill_rating = 4
    implementation_skill_text = "Clean code with proper error handling."
    communication_rating = 5
    communication_text = "Outstanding communication throughout the interview."
    overall_feedback = "Strong candidate with excellent technical skills. Would recommend for senior positions."
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/interviews/$interviewId/feedback/interviewer/" `
    -Method POST `
    -ContentType "application/json" `
    -Headers @{Authorization = "Bearer $token"} `
    -Body $body
```

---

## Credit Payout Hook

When feedback is submitted, a Django signal is triggered:

```python
# In your credit service, listen to this signal:
from apps.interviews.feedback_signals import feedback_submitted

@receiver(feedback_submitted)
def handle_credit_payout(sender, feedback, interview_request, interviewer, **kwargs):
    """
    Release credits to interviewer after feedback submission.
    
    Args:
        feedback: InterviewerFeedback instance
        interview_request: InterviewRequest instance
        interviewer: User instance (the taker)
    """
    credits = interview_request.credits
    # Implement your payout logic here
    logger.info(f"Releasing {credits} credits to {interviewer.email}")
```

---

## Migration Notes

### New Table Created

```sql
-- Table: interviews_interviewer_feedback
CREATE TABLE interviews_interviewer_feedback (
    id UUID PRIMARY KEY,
    interview_request_id UUID UNIQUE NOT NULL,  -- OneToOne
    interviewer_id INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    
    -- Q1: Problem Understanding
    problem_understanding_rating SMALLINT CHECK (value >= 1 AND value <= 5),
    problem_understanding_text TEXT,
    
    -- Q2: Solution Approach
    solution_approach_rating SMALLINT,
    solution_approach_text TEXT,
    
    -- Q3: Implementation Skill
    implementation_skill_rating SMALLINT,
    implementation_skill_text TEXT,
    
    -- Q4: Communication
    communication_rating SMALLINT,
    communication_text TEXT,
    
    -- Overall
    overall_feedback TEXT,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    submitted_at TIMESTAMP,
    
    FOREIGN KEY (interview_request_id) REFERENCES interviews_interviewrequest(uuid_id),
    FOREIGN KEY (interviewer_id) REFERENCES accounts_user(id)
);

-- Indexes
CREATE INDEX idx_feedback_status ON interviews_interviewer_feedback(status, created_at);
CREATE INDEX idx_feedback_interviewer ON interviews_interviewer_feedback(interviewer_id, status);
```

### Apply Migration

```bash
python manage.py makemigrations interviews
python manage.py migrate interviews
```

---

## Swagger UI

The endpoint is documented in Swagger UI at `/swagger/` under the **Interview - Feedback** tag.

Navigate to:
- `POST /api/interviews/{interview_id}/feedback/interviewer/`
- Click "Try it out"
- Enter interview UUID
- Fill in the request body
- Execute

---

## Files Created

| File | Purpose |
|------|---------|
| `apps/interviews/feedback_models.py` | InterviewerFeedback model |
| `apps/interviews/feedback_signals.py` | Credit payout hook signal |
| `apps/interviews/feedback_serializers.py` | DRF serializers |
| `apps/interviews/feedback_api.py` | API view |
| `apps/interviews/feedback_admin.py` | Django admin |

---

# Candidate Feedback API (Optional)

## Overview

This endpoint allows candidates (attenders) to submit **optional** feedback about the interviewer. All fields are optional, and this feedback does **NOT** affect credit payouts.

## Endpoint

```
POST /api/interviews/{interview_id}/feedback/candidate/
GET  /api/interviews/{interview_id}/feedback/candidate/
```

## Rules & Validation

1. **Only the candidate (attender)** can submit feedback
2. Feedback can be **updated** (not one-time only)
3. Interview status must be **accepted**, **completed**, or **not_attended**
4. **All fields are optional** but at least one must be provided
5. **Does NOT affect credit payouts**

## Request Body

All fields are optional:

```json
{
    "overall_experience_rating": 4,
    "professionalism_rating": 5,
    "question_clarity_rating": 4,
    "feedback_quality_rating": 5,
    "comments": "Great interviewer, very helpful and professional.",
    "would_recommend": true
}
```

## Field Validation

| Field | Type | Constraints |
|-------|------|-------------|
| `overall_experience_rating` | Integer | Optional, 1-5 |
| `professionalism_rating` | Integer | Optional, 1-5 |
| `question_clarity_rating` | Integer | Optional, 1-5 |
| `feedback_quality_rating` | Integer | Optional, 1-5 |
| `comments` | String | Optional |
| `would_recommend` | Boolean | Optional |

## Response

### Success (201 Created / 200 Updated)

```json
{
    "detail": "Feedback submitted successfully.",
    "feedback": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "interview_uuid": "123e4567-e89b-12d3-a456-426614174000",
        "candidate_email": "candidate@example.com",
        "overall_experience_rating": 4,
        "professionalism_rating": 5,
        "question_clarity_rating": 4,
        "feedback_quality_rating": 5,
        "comments": "Great interviewer, very helpful.",
        "would_recommend": true,
        "average_rating": 4.5,
        "has_any_rating": true,
        "created_at": "2026-02-05T09:30:00Z",
        "updated_at": "2026-02-05T09:30:00Z"
    }
}
```

---

## cURL Commands

### Submit Candidate Feedback

```bash
INTERVIEW_UUID="your-interview-uuid-here"

curl -X POST "http://localhost:8000/api/interviews/${INTERVIEW_UUID}/feedback/candidate/" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -d '{
        "overall_experience_rating": 4,
        "professionalism_rating": 5,
        "comments": "Great experience! The interviewer was very professional and gave helpful feedback.",
        "would_recommend": true
    }'
```

### Get Candidate Feedback

```bash
curl -X GET "http://localhost:8000/api/interviews/${INTERVIEW_UUID}/feedback/candidate/" \
    -H "Authorization: Bearer $ACCESS_TOKEN"
```

---

## Comparison: Interviewer vs Candidate Feedback

| Aspect | Interviewer Feedback | Candidate Feedback |
|--------|---------------------|-------------------|
| Who submits | Taker (receiver) | Attender (sender) |
| Required | **Yes** (for credits) | No (optional) |
| All fields required | Yes | No (at least 1) |
| Can update | No (one-time) | Yes (updateable) |
| Affects credits | **Yes** | No |
| Questions | 4 rating+text | 4 ratings only |

