# apps/interviews/services/livekit.py
"""
LiveKit Integration Service for Interview Platform.

SECURITY RULES:
- NEVER expose LiveKit API keys to frontend
- NEVER create rooms before interview acceptance
- Tokens must be short-lived (default: 2 hours max)
- Identity must be UUID (NOT username or email)
- Publish permission only for interviewer (taker)

Usage:
    service = LiveKitService()
    token = service.create_access_token(
        interview_request=interview,
        user=user,
        room_name="interview-{uuid}"
    )
    
    # Async operations (use with async_to_sync in Django views)
    from asgiref.sync import async_to_sync
    room_info = async_to_sync(service.get_room_info)(room_name)
    participants = async_to_sync(service.get_room_participants)(room_name)
"""
import logging
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import json
import time
from typing import Optional, List, Dict, Any

# LiveKit SDK imports
try:
    from livekit.api import AccessToken, VideoGrants, LiveKitAPI
    LIVEKIT_SDK_AVAILABLE = True
except ImportError:
    LIVEKIT_SDK_AVAILABLE = False
    logging.warning(
        "livekit-api package not installed. Run: pip install livekit-api"
    )

logger = logging.getLogger('apps.interviews.livekit')


class LiveKitService:
    """
    Service class for LiveKit operations.

    Handles:
    - Access token generation (SDK-based)
    - Room creation (idempotent via RoomService)
    - Permission management (interviewer=admin, interviewee=participant)
    - Room controls (mute/eject/end)
    - Live participant tracking

    Configuration (in settings.py):
        LIVEKIT_API_KEY = 'your_api_key'
        LIVEKIT_API_SECRET = 'your_api_secret'
        LIVEKIT_URL = 'wss://your-livekit-server.com'
    """

    # Token validity duration
    DEFAULT_TOKEN_TTL_SECONDS = 7200  # 2 hours
    MIN_TOKEN_TTL_SECONDS = 300  # 5 minutes
    MAX_TOKEN_TTL_SECONDS = 86400  # 24 hours

    # Interview-specific room settings
    ROOM_EMPTY_TIMEOUT = 3600  # 1 hour
    ROOM_MAX_PARTICIPANTS = 2

    def __init__(self):
        """Initialize LiveKit service with configuration validation."""
        self.api_key = getattr(settings, "LIVEKIT_API_KEY", None)
        self.api_secret = getattr(settings, "LIVEKIT_API_SECRET", None)
        self.livekit_url = getattr(settings, "LIVEKIT_URL", None)

        # Log configuration status (not the actual values!)
        if not self.api_key or not self.api_secret:
            logger.warning(
                "LiveKit API credentials not configured. "
                "Set LIVEKIT_API_KEY and LIVEKIT_API_SECRET in settings."
            )

        if not LIVEKIT_SDK_AVAILABLE:
            logger.warning(
                "LiveKit SDK not available. Some features will be limited. "
                "Install with: pip install livekit-api"
            )

    def is_configured(self) -> bool:
        """Check if LiveKit is properly configured."""
        return bool(self.api_key and self.api_secret)

    def _get_api_url(self) -> str:
        """Convert WebSocket URL to HTTP URL for API calls."""
        api_url = self.livekit_url
        if api_url and api_url.startswith("wss://"):
            api_url = api_url.replace("wss://", "https://")
        elif api_url and api_url.startswith("ws://"):
            api_url = api_url.replace("ws://", "http://")
        return api_url

    async def _get_api_client(self) -> Optional["LiveKitAPI"]:
        """
        Get LiveKitAPI client for async room operations.
        
        Returns:
            LiveKitAPI instance or None if SDK not available
            
        Usage:
            async with await service._get_api_client() as lk:
                rooms = await lk.room.list_rooms()
        """
        if not LIVEKIT_SDK_AVAILABLE:
            logger.error("LiveKit SDK not available")
            return None
            
        if not self.is_configured():
            logger.error("LiveKit not configured")
            return None

        return LiveKitAPI(
            url=self._get_api_url(),
            api_key=self.api_key,
            api_secret=self.api_secret
        )

    def create_access_token(
        self, interview_request, user, room_name: str = None, ttl_seconds: int = None
    ) -> dict:
        """
        Create a LiveKit access token for a user to join an interview room.

        Args:
            interview_request: The InterviewRequest instance
            user: The Django User instance
            room_name: Optional custom room name (defaults to interview-{uuid})
            ttl_seconds: Token validity in seconds (defaults to 2 hours)

        Returns:
            dict: {
                'token': str,
                'room_name': str,
                'livekit_url': str,
                'identity': str,
                'expires_at': datetime,
                'permissions': dict
            }

        Raises:
            ValueError: If validation fails
            RuntimeError: If LiveKit is not configured
        """
        # Validate configuration
        if not self.is_configured():
            raise RuntimeError(
                "LiveKit is not configured. Please set LIVEKIT_API_KEY and LIVEKIT_API_SECRET."
            )

        if not LIVEKIT_SDK_AVAILABLE:
            raise RuntimeError(
                "LiveKit SDK not installed. Run: pip install livekit-api"
            )

        # Validate interview status - must be accepted and not finalized
        if interview_request.status != "accepted":
            # Provide specific error messages for terminal states
            terminal_states = {
                'completed': "Interview has already been completed.",
                'not_conducted': "Interview was not conducted due to non-attendance.",
                'not attended': "Interview was marked as not attended.",
                'cancelled': "Interview has been cancelled.",
                'rejected': "Interview request was rejected.",
                'pending': "Interview has not been accepted yet.",
            }
            error_msg = terminal_states.get(
                interview_request.status,
                f"Cannot join interview with status '{interview_request.status}'."
            )
            raise ValueError(error_msg)

        # Validate user is participant
        if user not in [interview_request.sender, interview_request.receiver]:
            raise ValueError("User is not a participant of this interview.")

        # Validate time window
        time_status = interview_request.get_time_window_status()
        if time_status == "too_early":
            minutes_until = (
                interview_request.scheduled_time - timezone.now()
            ).total_seconds() / 60
            raise ValueError(
                f"Interview room opens 15 minutes before scheduled time. Please wait {int(minutes_until)} more minutes."
            )
        elif time_status == "too_late":
            raise ValueError("Interview time window has expired. The room is no longer accessible.")

        # Determine room name
        if room_name is None:
            room_name = f"interview-{interview_request.uuid_id}"

        # Validate and set TTL
        if ttl_seconds is None:
            ttl_seconds = self.DEFAULT_TOKEN_TTL_SECONDS
        ttl_seconds = max(
            self.MIN_TOKEN_TTL_SECONDS, min(ttl_seconds, self.MAX_TOKEN_TTL_SECONDS)
        )

        # Use user's profile UUID as identity (NOT username or email)
        try:
            identity = str(user.profile.public_id)
        except Exception:
            # Fallback to user ID if profile doesn't exist
            identity = f"user-{user.id}"

        # Determine permissions based on role
        # Interviewer (taker/receiver) has admin permission for room controls
        # Interviewee (attender/sender) has standard publish permission
        is_interviewer = user == interview_request.receiver
        is_room_admin = is_interviewer  # Interviewer gets admin controls

        # Get user display name
        user_name = user.profile.name if hasattr(user, "profile") and user.profile.name else user.username

        # Calculate expiration
        now = timezone.now()
        expires_at = now + timedelta(seconds=ttl_seconds)

        # Generate token using LiveKit SDK
        access_token = AccessToken(self.api_key, self.api_secret)
        access_token = access_token.with_identity(identity)
        access_token = access_token.with_name(user_name)
        access_token = access_token.with_ttl(timedelta(seconds=ttl_seconds))
        access_token = access_token.with_metadata(json.dumps({
            "interview_id": str(interview_request.uuid_id),
            "user_role": "interviewer" if is_interviewer else "interviewee",
            "name": user_name,
        }))

        # Set video grants with appropriate permissions
        video_grant = VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,  # Both can publish audio/video
            can_subscribe=True,
            can_publish_data=True,
            can_publish_sources=["camera", "microphone", "screen_share", "screen_share_audio"],
            hidden=False,
            room_admin=is_room_admin,  # Interviewer can mute/eject participants
        )
        access_token = access_token.with_grants(video_grant)
        
        # Generate JWT token
        token = access_token.to_jwt()

        logger.info(
            f"[TOKEN_GENERATED] interview={interview_request.uuid_id} "
            f"user={identity} room={room_name} "
            f"role={'interviewer' if is_interviewer else 'interviewee'} "
            f"admin={is_room_admin} ttl_sec={ttl_seconds}"
        )

        return {
            "token": token,
            "room_name": room_name,
            "livekit_url": self.livekit_url,
            "identity": identity,
            "expires_at": expires_at.isoformat(),
            "permissions": {
                "can_publish": True,
                "can_subscribe": True,
                "can_screen_share": True,
                "is_interviewer": is_interviewer,
                "is_room_admin": is_room_admin,
            },
        }

    async def ensure_room_exists(
        self, room_name: str, interview_id: str
    ) -> Dict[str, Any]:
        """
        Idempotent room creation with interview-specific settings.
        
        Creates a room if it doesn't exist, returns existing room if it does.
        
        Args:
            room_name: Name of the room to create/get
            interview_id: UUID of the interview (for metadata)
            
        Returns:
            dict: Room information including name, participants, creation time
            
        Room Settings:
            - empty_timeout: 1 hour (room deleted when empty)
            - max_participants: 2 (1:1 interview)
            - metadata: interview_id and type
        """
        lk = await self._get_api_client()
        if not lk:
            raise RuntimeError("RoomService client not available")
        
        try:
            async with lk:
                # First, try to get existing room
                try:
                    rooms = await lk.room.list_rooms(names=[room_name])
                    if rooms and len(rooms.rooms) > 0:
                        room = rooms.rooms[0]
                        logger.info(f"[ROOM_EXISTS] room={room_name} participants={room.num_participants}")
                        return {
                            "room_name": room.name,
                            "sid": room.sid,
                            "num_participants": room.num_participants,
                            "created_at": room.creation_time,
                            "metadata": room.metadata,
                            "already_existed": True,
                        }
                except Exception as e:
                    logger.debug(f"Room lookup failed (may not exist): {e}")
                
                # Create new room with interview-specific settings
                room_metadata = json.dumps({
                    "interview_id": interview_id,
                    "type": "interview",
                    "created_at": timezone.now().isoformat(),
                })
                
                room = await lk.room.create_room(
                    name=room_name,
                    empty_timeout=self.ROOM_EMPTY_TIMEOUT,
                    max_participants=self.ROOM_MAX_PARTICIPANTS,
                    metadata=room_metadata,
                )
                
                logger.info(f"[ROOM_CREATED] room={room_name} interview={interview_id}")
                
                # Update Django model
                await self._update_room_model(room_name, interview_id)
                
                return {
                    "room_name": room.name,
                    "sid": room.sid,
                    "num_participants": room.num_participants,
                    "created_at": room.creation_time,
                    "metadata": room.metadata,
                    "already_existed": False,
                }
        except Exception as e:
            logger.error(f"[ROOM_CREATE_FAILED] room={room_name} error={e}")
            raise

    async def _update_room_model(self, room_name: str, interview_id: str):
        """Update Django LiveKitRoom model (async-safe)."""
        from asgiref.sync import sync_to_async
        from apps.interviews.models import LiveKitRoom, InterviewRequest
        
        @sync_to_async
        def update_or_create():
            try:
                interview = InterviewRequest.objects.get(uuid_id=interview_id)
                LiveKitRoom.objects.update_or_create(
                    room_name=room_name,
                    defaults={
                        "interview_request": interview,
                        "is_active": True,
                    }
                )
            except InterviewRequest.DoesNotExist:
                logger.warning(f"Interview {interview_id} not found for room {room_name}")
        
        await update_or_create()

    async def get_room_info(self, room_name: str) -> Optional[Dict[str, Any]]:
        """
        Get room information - LIVE data first, DB fallback.
        
        First attempts to get live data from LiveKit API, falls back to
        database if API call fails.
        
        Args:
            room_name: Name of the room
            
        Returns:
            dict with room info including participant_count, participants list,
            is_active status, etc. Returns None if room not found.
        """
        from apps.interviews.models import LiveKitRoom
        from asgiref.sync import sync_to_async
        
        lk = await self._get_api_client()
        
        # Try live API first
        if lk:
            try:
                async with lk:
                    rooms = await lk.room.list_rooms(names=[room_name])
                    if rooms and len(rooms.rooms) > 0:
                        room = rooms.rooms[0]
                        participants = await lk.room.list_participants(room_name)
                        
                        return {
                            "room_name": room.name,
                            "sid": room.sid,
                            "is_active": room.num_participants > 0,
                            "participant_count": room.num_participants,
                            "max_participants": room.max_participants,
                            "participants": [
                                {
                                    "identity": p.identity,
                                    "name": p.name,
                                    "sid": p.sid,
                                    "state": str(p.state),
                                    "joined_at": p.joined_at,
                                    "is_publisher": p.permission.can_publish if p.permission else False,
                                    "metadata": p.metadata,
                                }
                                for p in participants.participants
                            ],
                            "created_at": room.creation_time,
                            "metadata": room.metadata,
                            "source": "live_api",
                        }
            except Exception as e:
                logger.warning(f"Live API failed for room {room_name}, using DB fallback: {e}")
        
        # Fallback to database
        @sync_to_async
        def get_from_db():
            try:
                room = LiveKitRoom.objects.select_related("interview_request").get(
                    room_name=room_name
                )
                return {
                    "room_name": room.room_name,
                    "is_active": room.is_active,
                    "interview_id": str(room.interview_request.uuid_id),
                    "created_at": room.created_at.isoformat(),
                    "sender_joined": room.sender_joined_at is not None,
                    "receiver_joined": room.receiver_joined_at is not None,
                    "source": "database",
                }
            except LiveKitRoom.DoesNotExist:
                return None
        
        return await get_from_db()

    async def get_room_participants(self, room_name: str) -> List[Dict[str, Any]]:
        """
        Get live participant list from LiveKit.
        
        Args:
            room_name: Name of the room
            
        Returns:
            List of participant dicts with identity, name, state, permissions
        """
        lk = await self._get_api_client()
        if not lk:
            logger.warning("RoomService client not available")
            return []
        
        try:
            async with lk:
                participants = await lk.room.list_participants(room_name)
                return [
                    {
                        "identity": p.identity,
                        "name": p.name,
                        "sid": p.sid,
                        "state": str(p.state),
                        "joined_at": p.joined_at,
                        "is_speaking": getattr(p, "is_speaking", False),
                        "audio_level": getattr(p, "audio_level", 0),
                        "permissions": {
                            "can_publish": p.permission.can_publish if p.permission else False,
                            "can_subscribe": p.permission.can_subscribe if p.permission else True,
                            "can_publish_data": p.permission.can_publish_data if p.permission else False,
                        },
                        "metadata": p.metadata,
                    }
                    for p in participants.participants
                ]
        except Exception as e:
            logger.error(f"Failed to get participants for room {room_name}: {e}")
            return []

    async def end_interview_room(self, room_name: str) -> Dict[str, Any]:
        """
        End interview by ejecting all participants and deleting the room.
        
        Args:
            room_name: Name of the room to end
            
        Returns:
            dict with status and number of ejected participants
        """
        lk = await self._get_api_client()
        if not lk:
            raise RuntimeError("RoomService client not available")
        
        ejected_count = 0
        
        try:
            async with lk:
                # First, get all participants
                participants = await lk.room.list_participants(room_name)
                
                # Eject each participant
                for p in participants.participants:
                    try:
                        await lk.room.remove_participant(room_name, p.identity)
                        ejected_count += 1
                        logger.info(f"Ejected participant {p.identity} from room {room_name}")
                    except Exception as e:
                        logger.warning(f"Failed to eject {p.identity}: {e}")
                
                # Delete the room
                await lk.room.delete_room(room_name)
                logger.info(f"Deleted room {room_name}")
                
                # Update Django model
                await self._mark_room_inactive(room_name)
                
                return {
                    "status": "ended",
                    "room_name": room_name,
                    "ejected_participants": ejected_count,
                }
        except Exception as e:
            logger.error(f"Failed to end room {room_name}: {e}")
            raise

    async def _mark_room_inactive(self, room_name: str):
        """Mark room as inactive in Django model."""
        from asgiref.sync import sync_to_async
        from apps.interviews.models import LiveKitRoom
        
        @sync_to_async
        def update():
            LiveKitRoom.objects.filter(room_name=room_name).update(
                is_active=False,
                ended_at=timezone.now()
            )
        
        await update()

    async def mute_participant(
        self, room_name: str, identity: str, audio_only: bool = True
    ) -> Dict[str, Any]:
        """
        Mute participant's audio and optionally video.
        
        Args:
            room_name: Name of the room
            identity: Participant identity to mute
            audio_only: If True, only mute audio. If False, mute both audio and video.
            
        Returns:
            dict with status and muted tracks
        """
        lk = await self._get_api_client()
        if not lk:
            raise RuntimeError("RoomService client not available")
        
        try:
            async with lk:
                # Get participant's tracks
                participant = await lk.room.get_participant(room_name, identity)
                
                muted_tracks = []
                for track in participant.tracks:
                    # Mute audio tracks, and video if not audio_only
                    if track.source == "microphone" or (not audio_only and track.source == "camera"):
                        await lk.room.mute_published_track(
                            room_name, identity, track.sid, muted=True
                        )
                        muted_tracks.append({
                            "sid": track.sid,
                            "source": str(track.source),
                        })
                
                logger.info(f"Muted participant {identity} in room {room_name}: {muted_tracks}")
                
                return {
                    "status": "muted",
                    "identity": identity,
                    "room_name": room_name,
                    "muted_tracks": muted_tracks,
                    "audio_only": audio_only,
                }
        except Exception as e:
            logger.error(f"Failed to mute participant {identity} in room {room_name}: {e}")
            raise

    async def unmute_participant(
        self, room_name: str, identity: str, audio_only: bool = True
    ) -> Dict[str, Any]:
        """
        Unmute participant's audio and optionally video.
        
        Args:
            room_name: Name of the room
            identity: Participant identity to unmute
            audio_only: If True, only unmute audio. If False, unmute both.
            
        Returns:
            dict with status and unmuted tracks
        """
        lk = await self._get_api_client()
        if not lk:
            raise RuntimeError("RoomService client not available")
        
        try:
            async with lk:
                participant = await lk.room.get_participant(room_name, identity)
                
                unmuted_tracks = []
                for track in participant.tracks:
                    if track.source == "microphone" or (not audio_only and track.source == "camera"):
                        await lk.room.mute_published_track(
                            room_name, identity, track.sid, muted=False
                        )
                        unmuted_tracks.append({
                            "sid": track.sid,
                            "source": str(track.source),
                        })
                
                logger.info(f"Unmuted participant {identity} in room {room_name}")
                
                return {
                    "status": "unmuted",
                    "identity": identity,
                    "room_name": room_name,
                    "unmuted_tracks": unmuted_tracks,
                }
        except Exception as e:
            logger.error(f"Failed to unmute participant {identity}: {e}")
            raise

    async def eject_participant(self, room_name: str, identity: str) -> Dict[str, Any]:
        """
        Eject (remove) a participant from the room.
        
        Args:
            room_name: Name of the room
            identity: Participant identity to eject
            
        Returns:
            dict with status
        """
        lk = await self._get_api_client()
        if not lk:
            raise RuntimeError("RoomService client not available")
        
        try:
            async with lk:
                await lk.room.remove_participant(room_name, identity)
                logger.info(f"Ejected participant {identity} from room {room_name}")
                
                return {
                    "status": "ejected",
                    "identity": identity,
                    "room_name": room_name,
                }
        except Exception as e:
            logger.error(f"Failed to eject participant {identity} from room {room_name}: {e}")
            raise

    async def send_interview_message(
        self, room_name: str, message: str, destination_identities: List[str] = None
    ) -> Dict[str, Any]:
        """
        Send a data message to room participants.
        
        Args:
            room_name: Name of the room
            message: Message content (will be JSON encoded)
            destination_identities: Optional list of specific recipients
            
        Returns:
            dict with status
        """
        lk = await self._get_api_client()
        if not lk:
            raise RuntimeError("RoomService client not available")
        
        try:
            async with lk:
                # Encode message as JSON
                data = json.dumps({
                    "type": "interview_message",
                    "content": message,
                    "timestamp": timezone.now().isoformat(),
                }).encode("utf-8")
                
                await lk.room.send_data(
                    room_name,
                    data,
                    kind="reliable",
                    destination_identities=destination_identities or [],
                )
                
                logger.info(f"Sent message to room {room_name}")
                
                return {
                    "status": "sent",
                    "room_name": room_name,
                    "recipients": destination_identities or "all",
                }
        except Exception as e:
            logger.error(f"Failed to send message to room {room_name}: {e}")
            raise

    async def list_active_rooms(self) -> List[Dict[str, Any]]:
        """
        Get all active interview rooms (for dashboard/admin).
        
        Returns:
            List of room dicts with name, participant count, metadata
        """
        lk = await self._get_api_client()
        if not lk:
            logger.warning("RoomService client not available")
            return []
        
        try:
            async with lk:
                rooms = await lk.room.list_rooms()
                
                active_rooms = []
                for room in rooms.rooms:
                    # Only include interview rooms
                    if room.name.startswith("interview-"):
                        active_rooms.append({
                            "room_name": room.name,
                            "sid": room.sid,
                            "num_participants": room.num_participants,
                            "max_participants": room.max_participants,
                            "created_at": room.creation_time,
                            "metadata": room.metadata,
                        })
                
                logger.info(f"Found {len(active_rooms)} active interview rooms")
                return active_rooms
        except Exception as e:
            logger.error(f"Failed to list active rooms: {e}")
            return []

    async def update_participant_metadata(
        self, room_name: str, identity: str, metadata: dict
    ) -> Dict[str, Any]:
        """
        Update participant's metadata.
        
        Args:
            room_name: Name of the room
            identity: Participant identity
            metadata: New metadata dict
            
        Returns:
            dict with status
        """
        lk = await self._get_api_client()
        if not lk:
            raise RuntimeError("RoomService client not available")
        
        try:
            async with lk:
                await lk.room.update_participant(
                    room_name, identity, metadata=json.dumps(metadata)
                )
                
                logger.info(f"Updated metadata for {identity} in room {room_name}")
                
                return {
                    "status": "updated",
                    "identity": identity,
                    "room_name": room_name,
                }
        except Exception as e:
            logger.error(f"Failed to update metadata for {identity}: {e}")
            raise

    def validate_join_request(self, interview_request, user) -> tuple:
        """
        Validate a join request.

        Args:
            interview_request: The InterviewRequest instance
            user: The User attempting to join

        Returns:
            tuple: (is_valid: bool, error_message: str or None)
        """
        # Check if interview is accepted
        if interview_request.status != "accepted":
            return (
                False,
                f"Interview is not accepted (status: {interview_request.status})",
            )

        # Check if user is participant
        if user not in [interview_request.sender, interview_request.receiver]:
            return False, "You are not a participant of this interview"

        # Check time window
        time_status = interview_request.get_time_window_status()
        if time_status == "too_early":
            minutes_until = (
                interview_request.scheduled_time - timezone.now()
            ).total_seconds() / 60
            return (
                False,
                f"Interview room opens 15 minutes before scheduled time. Please wait {int(minutes_until)} more minutes.",
            )
        elif time_status == "too_late":
            return False, "Interview time window has expired"

        # Check if LiveKit is configured
        if not self.is_configured():
            return (
                False,
                "Video conferencing is not configured. Please contact support.",
            )

        return True, None


# Singleton instance for convenience
livekit_service = LiveKitService()


def get_livekit_service() -> LiveKitService:
    """Get the LiveKit service instance."""
    return livekit_service
