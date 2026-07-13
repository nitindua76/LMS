"""
Thin wrapper over the `livekit-api` server SDK. Every call here talks to the
LiveKit server over its Room Service HTTP API / mints its own access tokens —
nothing here touches Postgres or any LMS model.
"""
from datetime import timedelta

from livekit import api as lk_api

from .schemas import ParticipantPermissions, ParticipantToken, RoomInfo

DEFAULT_TOKEN_TTL_SEC = 4 * 3600  # generous cap; actual join window is enforced server-side before minting


class ConferencingClient:
    def __init__(self, url: str, api_key: str, api_secret: str):
        self._url = url
        self._api_key = api_key
        self._api_secret = api_secret

    def generate_token(
        self,
        room_name: str,
        identity: str,
        display_name: str,
        permissions: ParticipantPermissions,
        ttl_sec: int = DEFAULT_TOKEN_TTL_SEC,
    ) -> ParticipantToken:
        grants = lk_api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=permissions.can_publish,
            can_subscribe=permissions.can_subscribe,
            can_publish_data=permissions.can_publish_data,
            room_admin=permissions.room_admin,
            hidden=permissions.hidden,
        )
        token = (
            lk_api.AccessToken(self._api_key, self._api_secret)
            .with_identity(identity)
            .with_name(display_name)
            .with_grants(grants)
            .with_ttl(timedelta(seconds=ttl_sec))
            .to_jwt()
        )
        return ParticipantToken(
            token=token, identity=identity, room_name=room_name, expires_in_sec=ttl_sec
        )

    async def create_room(self, room_name: str, empty_timeout_sec: int = 300) -> RoomInfo:
        async with lk_api.LiveKitAPI(self._url, self._api_key, self._api_secret) as client:
            room = await client.room.create_room(
                lk_api.CreateRoomRequest(name=room_name, empty_timeout=empty_timeout_sec)
            )
            return RoomInfo(
                name=room.name,
                num_participants=room.num_participants,
                creation_unix_time=room.creation_time,
            )

    async def end_room(self, room_name: str) -> None:
        async with lk_api.LiveKitAPI(self._url, self._api_key, self._api_secret) as client:
            await client.room.delete_room(lk_api.DeleteRoomRequest(room=room_name))

    async def list_participants(self, room_name: str) -> list[str]:
        async with lk_api.LiveKitAPI(self._url, self._api_key, self._api_secret) as client:
            resp = await client.room.list_participants(
                lk_api.ListParticipantsRequest(room=room_name)
            )
            return [p.identity for p in resp.participants]

    async def remove_participant(self, room_name: str, identity: str) -> None:
        async with lk_api.LiveKitAPI(self._url, self._api_key, self._api_secret) as client:
            await client.room.remove_participant(
                lk_api.RoomParticipantIdentity(room=room_name, identity=identity)
            )
