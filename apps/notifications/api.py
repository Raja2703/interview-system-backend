# apps/notifications/api.py
"""
REST API endpoints for Notifications.

Endpoints:
1) GET  /api/notifications/              - List user's notifications
2) GET  /api/notifications/{id}/         - Get notification detail
3) POST /api/notifications/mark-read/    - Mark notifications as read
4) GET  /api/notifications/unread-count/ - Get unread count
5) DELETE /api/notifications/{id}/       - Delete a notification
"""
import logging
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .models import Notification
from .serializers import (
    NotificationSerializer,
    NotificationListSerializer,
    NotificationMarkReadSerializer,
)

logger = logging.getLogger(__name__)


class NotificationListAPI(generics.ListAPIView):
    """
    List notifications for the current user.
    
    GET /api/notifications/
    
    Query Parameters:
    - is_read: true|false - Filter by read status
    - type: Filter by notification type
    - limit: Number of results (default: 10, max: 100)
    - offset: Starting position
    
    Returns paginated list of notifications ordered by creation date (newest first).
    """
    serializer_class = NotificationListSerializer
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        tags=["Notifications"],
        operation_summary="List Notifications",
        operation_description="Get list of notifications for the current user.",
        manual_parameters=[
            openapi.Parameter(
                'is_read',
                openapi.IN_QUERY,
                type=openapi.TYPE_BOOLEAN,
                description="Filter by read status",
            ),
            openapi.Parameter(
                'type',
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Filter by notification type",
                enum=[choice[0] for choice in Notification.TYPE_CHOICES],
            ),
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
    
    def get_queryset(self):
        user = self.request.user
        queryset = Notification.objects.filter(recipient=user)
        
        # Filter by read status
        is_read = self.request.query_params.get('is_read')
        if is_read is not None:
            is_read_bool = is_read.lower() == 'true'
            queryset = queryset.filter(is_read=is_read_bool)
        
        # Filter by type
        notification_type = self.request.query_params.get('type')
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)
        
        return queryset.select_related(
            'actor', 'actor__profile',
            'interview_request'
        ).order_by('-created_at')


class NotificationDetailAPI(generics.RetrieveDestroyAPIView):
    """
    Get or delete a notification.
    
    GET    /api/notifications/{id}/ - Get notification details
    DELETE /api/notifications/{id}/ - Delete notification
    
    Automatically marks notification as read when viewed.
    """
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'
    
    @swagger_auto_schema(
        tags=["Notifications"],
        operation_summary="Get Notification",
        operation_description="Get notification details. Marks notification as read.",
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
    
    @swagger_auto_schema(
        tags=["Notifications"],
        operation_summary="Delete Notification",
        operation_description="Delete a notification.",
    )
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)
    
    def get_queryset(self):
        return Notification.objects.filter(
            recipient=self.request.user
        ).select_related(
            'actor', 'actor__profile',
            'interview_request'
        )
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Mark as read when viewed
        if not instance.is_read:
            instance.mark_as_read()
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class NotificationMarkReadAPI(APIView):
    """
    Mark notifications as read.
    
    POST /api/notifications/mark-read/
    
    Request Body:
    - notification_ids: List of notification IDs to mark as read
    - mark_all: If true, marks all notifications as read
    
    Either notification_ids or mark_all must be provided.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        tags=["Notifications"],
        operation_summary="Mark Notifications as Read",
        operation_description="Mark specific notifications or all notifications as read.",
        request_body=NotificationMarkReadSerializer,
        responses={
            200: openapi.Response(
                description="Success",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'marked_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                    }
                )
            ),
        }
    )
    def post(self, request):
        serializer = NotificationMarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = request.user
        notification_ids = serializer.validated_data.get('notification_ids', [])
        mark_all = serializer.validated_data.get('mark_all', False)
        
        if mark_all:
            # Mark all notifications as read
            count = Notification.mark_all_as_read(user)
            return Response({
                'marked_count': count,
                'message': f'All {count} unread notifications marked as read.'
            })
        
        if notification_ids:
            # Mark specific notifications as read
            notifications = Notification.objects.filter(
                recipient=user,
                id__in=notification_ids,
                is_read=False
            )
            count = 0
            for notification in notifications:
                notification.mark_as_read()
                count += 1
            
            return Response({
                'marked_count': count,
                'message': f'{count} notifications marked as read.'
            })
        
        return Response({
            'marked_count': 0,
            'message': 'No notifications specified to mark as read.'
        })


class NotificationUnreadCountAPI(APIView):
    """
    Get unread notification count.
    
    GET /api/notifications/unread-count/
    
    Returns the count of unread notifications for the current user.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        tags=["Notifications"],
        operation_summary="Get Unread Count",
        operation_description="Get count of unread notifications.",
        responses={
            200: openapi.Response(
                description="Success",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'unread_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                    }
                )
            ),
        }
    )
    def get(self, request):
        count = Notification.get_unread_count(request.user)
        return Response({'unread_count': count})
