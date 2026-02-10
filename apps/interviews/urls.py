# apps/interviews/urls.py
"""
URL configuration for interviews app.

New endpoints:
- /api/interviews/requests/ - Interview request management
- /api/interviews/{id}/join/ - Join interview room
- /api/interviews/requests/{id}/complete/ - Mark as completed (taker only)
- /api/interviews/requests/{id}/not-attended/ - Mark as not attended (taker only)

NEW LiveKit Room Control endpoints:
- /api/interviews/{id}/room/controls/ - Mute/unmute/eject/end room controls
- /api/interviews/{id}/room/info/ - Get live room info
- /api/interviews/{id}/room/ensure/ - Ensure room exists before joining
- /api/interviews/rooms/active/ - List all active rooms (admin only)

Legacy endpoints maintained for backward compatibility.
"""
from django.urls import path
from . import api
from .api import (
    InterviewJoinAPI,
    InterviewDashboardAPI,
    InterviewMarkCompleteAPI,
    InterviewMarkNotAttendedAPI,
    # NEW: LiveKit room control APIs
    InterviewRoomControlsAPI,
    InterviewRoomInfoAPI,
    ActiveRoomsAPI,
    EnsureInterviewRoomAPI,
)
from .feedback_api import InterviewerFeedbackAPI, CandidateFeedbackAPI


app_name = 'interviews'

urlpatterns = [

        path('requests/', api.InterviewRequestCreateAPI.as_view(), name='request_create'),
    
    # GET  /api/interviews/requests/list/ - List interview requests
    path('requests/list/', api.InterviewRequestListAPI.as_view(), name='request_list'),
    
    # GET  /api/interviews/requests/{id}/ - Get interview details
    path('requests/<uuid:id>/', api.InterviewRequestDetailAPI.as_view(), name='request_detail'),
    
    # POST /api/interviews/requests/{id}/accept/ - Accept request
    path('requests/<uuid:id>/accept/', api.InterviewRequestAcceptAPI.as_view(), name='request_accept'),
    
    # POST /api/interviews/requests/{id}/reject/ - Reject request
    path('requests/<uuid:id>/reject/', api.InterviewRequestRejectAPI.as_view(), name='request_reject'),
    
    # POST /api/interviews/requests/{id}/cancel/ - Cancel request
    path('requests/<uuid:id>/cancel/', api.InterviewRequestCancelAPI.as_view(), name='request_cancel'),
    
    # POST /api/interviews/requests/{id}/complete/ - Mark as completed (taker only)
    path('requests/<uuid:id>/complete/', InterviewMarkCompleteAPI.as_view(), name='request_complete'),
    
    # POST /api/interviews/requests/{id}/not-attended/ - Mark as not attended (taker only)
    path('requests/<uuid:id>/not-attended/', InterviewMarkNotAttendedAPI.as_view(), name='request_not_attended'),
    
    # ========== INTERVIEW JOIN API ==========
    path(
        "<uuid:id>/join/",
        InterviewJoinAPI.as_view(),
        name="interview_join"
    ),

    # ========== NEW LIVEKIT ROOM CONTROL APIs ==========
    # POST /api/interviews/{id}/room/controls/ - Mute/unmute/eject/end (interviewer only)
    path(
        "<uuid:id>/room/controls/",
        InterviewRoomControlsAPI.as_view(),
        name="room_controls"
    ),
    
    # GET /api/interviews/{id}/room/info/ - Get live room info (participants only)
    path(
        "<uuid:id>/room/info/",
        InterviewRoomInfoAPI.as_view(),
        name="room_info"
    ),
    
    # POST /api/interviews/{id}/room/ensure/ - Ensure room exists before joining
    path(
        "<uuid:id>/room/ensure/",
        EnsureInterviewRoomAPI.as_view(),
        name="room_ensure"
    ),
    
    # GET /api/interviews/rooms/active/ - List all active rooms (admin only)
    path(
        "rooms/active/",
        ActiveRoomsAPI.as_view(),
        name="active_rooms"
    ),

    # ========== DASHBOARD API ==========
    path("dashboard/", InterviewDashboardAPI.as_view(), name='dashboard'),

    # ========== INTERVIEWER FEEDBACK API ==========
    # POST /api/interviews/{id}/feedback/interviewer/ - Submit feedback (taker only, MANDATORY)
    # GET  /api/interviews/{id}/feedback/interviewer/ - Get feedback (participants only)
    path(
        "<uuid:interview_id>/feedback/interviewer/",
        InterviewerFeedbackAPI.as_view(),
        name="interviewer_feedback"
    ),
    
    # ========== CANDIDATE FEEDBACK API (OPTIONAL) ==========
    # POST /api/interviews/{id}/feedback/candidate/ - Submit feedback (attender only, OPTIONAL)
    # GET  /api/interviews/{id}/feedback/candidate/ - Get feedback (participants only)
    path(
        "<uuid:interview_id>/feedback/candidate/",
        CandidateFeedbackAPI.as_view(),
        name="candidate_feedback"
    ),
]

