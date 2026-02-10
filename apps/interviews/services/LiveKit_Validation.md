---
description: 
---

# LiveKit Integration & Room Controls Validation

## 1. Overview of Changes

We have significantly enhanced the LiveKit integration to support robust room management, improved security, and new features for interview control.

### **Key Improvements:**
*   **SDK-Based Tokens:** Replaced manual JWT generation with the official `livekit-api` SDK for better security and maintainability.
*   **Room Controls:** Added ability for **Interviewers** (Takers) to:
    *   Mute participants (audio/video).
    *   Eject participants.
    *   End the entire interview session.
*   **Live Room Info:** Real-time participant status (who is speaking, who is muted, etc.) fetched directly from LiveKit.
*   **Admin Dashboard:** New endpoint for **Superusers** to see *all* active interview rooms across the platform.
*   **Idempotency:** `ensure_room_exists` prevents duplicate room creation errors.

---

## 2. API Endpoint Reference

| Feature | HTTP Method | Endpoint | Required Role | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Join Room** | `POST` | `/api/interviews/{id}/join/` | Participant | Get access token to join the room. |
| **Ensure Room** | `POST` | `/api/interviews/{id}/room/ensure/` | Participant | Creates room if missing (call before joining). |
| **Room Info** | `GET` | `/api/interviews/{id}/room/info/` | Participant | Get live participant list & status. |
| **Room Controls** | `POST` | `/api/interviews/{id}/room/controls/` | **Interviewer ONLY** | Mute, Unmute, Eject, End Room. |
| **Active Rooms** | `GET` | `/api/interviews/rooms/active/` | **Superuser ONLY** | List all active interviews on platform. |
| **Feedback (Interviewer)** | `POST` | `/api/interviews/{id}/feedback/interviewer/` | Interviewer | Submit mandatory feedback. |
| **Feedback (Candidate)** | `POST` | `/api/interviews/{id}/feedback/candidate/` | Candidate | Submit optional feedback. |

---

## 3. Role Verification (Who is "Admin"?)

It is crucial to understand the two types of "Admin" privileges in this system:

### **A. Interview Room Admin (The Interviewer)**
*   **Who:** The user with the `Taker` role who **received** the interview request.
*   **Power:** Complete control over *their specific interview room*.
*   **Capabilities:**
    *   Can **MUTE** the candidate.
    *   Can **EJECT** the candidate.
    *   Can **END** the meeting for everyone.
*   **Limitation:** Cannot see or control *other people's* interviews.

### **B. System Admin (The Superuser)**
*   **Who:** A user with `is_superuser=True` or `is_staff=True` in Django.
*   **Power:** Global visibility.
*   **Capabilities:**
    *   Can **LIST ALL** active rooms (`/rooms/active/`).
    *   Can forcefully cancel any interview via Admin APIs.
*   **Limitation:** Cannot join interview rooms directly (for privacy).

---

## 4. Testing Guide (Curl Commands)

### **Prerequisite: Authenticate**
You need tokens for two different users to test fully:
1.  **Interviewer Token:** Login as the Taker (Receiver).
2.  **Superuser Token:** Login as a Django Superuser (for Admin APIs).

### **Test 1: Ensure Room Exists (Any Participant)**
*Call this before joining to make sure the room is ready.*
```bash
curl -X POST http://localhost:8000/api/interviews/{INTERVIEW_UUID}/room/ensure/ \
  -H "Authorization: Bearer {INTERVIEWER_TOKEN}"
```

### **Test 2: Get Room Info (Any Participant)**
*See who is currently in the room.*
```bash
curl http://localhost:8000/api/interviews/{INTERVIEW_UUID}/room/info/ \
  -H "Authorization: Bearer {INTERVIEWER_TOKEN}"
```

### **Test 3: Mute Candidate (Interviewer ONLY)**
*Mute the candidate's audio.*
```bash
curl -X POST http://localhost:8000/api/interviews/{INTERVIEW_UUID}/room/controls/ \
  -H "Authorization: Bearer {INTERVIEWER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"action": "mute", "identity": "{CANDIDATE_IDENTITY_UUID}", "audio_only": true}'
```
*Note: You can get the `identity` from the "Get Room Info" response.*

### **Test 4: End Interview (Interviewer ONLY)**
*Kick everyone out and close the room.*
```bash
curl -X POST http://localhost:8000/api/interviews/{INTERVIEW_UUID}/room/controls/ \
  -H "Authorization: Bearer {INTERVIEWER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"action": "end"}'
```

### **Test 5: List All Active Rooms (Superuser ONLY)**
*See platform-wide activity.*
```bash
curl http://localhost:8000/api/interviews/rooms/active/ \
  -H "Authorization: Bearer {SUPERUSER_TOKEN}"
```

---

## 5. Troubleshooting

**Error: "LiveKit SDK not available"**
*   **Fix:** Ensure you installed the packages:
    `pip install livekit-api aiohttp`
*   **Verify:** Run `pip show livekit-api` to check version (should be >= 1.1.0).

**Error: 403 Forbidden on Room Controls**
*   **Cause:** You are trying to use these endpoints as the **Candidate** (Sender).
*   **Fix:** Only the **Interviewer** (Receiver) has permission to mute/eject/end. Log in as the Taker.

**Error: 403 Forbidden on Active Rooms**
*   **Cause:** You are using a regular user token.
*   **Fix:** You must use a token from a **Superuser** account.

**Error: "Room does not exist"**
*   **Cause:** Use `ensure_room_exists` first! The room is created lazily.
*   **Fix:** Call the `/room/ensure/` endpoint before attempting to control it.



Use this json structure for frontend integration

{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ...",
  "room_name": "interview-123e4567-e89b-12d3-a456-426614174000",
  "livekit_url": "wss://your-livekit-server.com",
  "identity": "user-98765432-10ab-cdef-0123-456789abcdef",
  "expires_at": "2026-02-09T12:52:13.123456+00:00",
  "is_interviewer": true,  // Handy flag for frontend UI logic
  
  "permissions": {
    "can_publish": true,
    "can_subscribe": true,
    "can_screen_share": true,
    "is_interviewer": true, 
    "is_room_admin": true    // <--- ONLY TRUE FOR INTERVIEWER (Taker)
  },

  "interview": {
    "uuid_id": "123e4567-e89b-12d3-a456-426614174000",
    "status": "accepted",
    "topic": "Backend Engineer Interview",
    "scheduled_time": "2026-02-10T14:00:00Z",
    "duration_minutes": 60,
    "sender": { ... },
    "receiver": { ... }
  }
}
