import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../contexts/AuthContext";
import { roomsApi } from "../api/rooms";
import { getErrorMessage } from "../api/client";
import RoomCall from "../components/RoomCall";

/**
 * Landing page for a shared Instant Room link (roomsApi's join_url, e.g.
 * ".../join/42"). Deliberately NOT nested under either role's layout —
 * unlike every other route in the app, a meeting link has to work for
 * whichever role the recipient happens to be, without them picking a
 * "section" of the app first. Not-yet-authenticated visitors are bounced
 * to /login?next=/join/{id} and land back here once signed in.
 */
export default function JoinRoom() {
  const { roomId } = useParams<{ roomId: string }>();
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!loading && !user) {
      navigate(`/login?next=${encodeURIComponent(`/join/${roomId}`)}`, { replace: true });
    }
  }, [loading, user, roomId, navigate]);

  const { data: room, isLoading, error } = useQuery({
    queryKey: ["room", roomId],
    queryFn: () => roomsApi.get(Number(roomId)),
    enabled: !!user && !!roomId,
    retry: false,
  });

  if (loading || !user || isLoading) {
    return (
      <div className="center" style={{ height: "100vh" }}>
        <div className="spinner" />
      </div>
    );
  }

  if (error || !room) {
    return (
      <div className="center" style={{ height: "100vh", flexDirection: "column", gap: 14 }}>
        <p className="error-msg">{error ? getErrorMessage(error) : "This room could not be found."}</p>
        <button className="btn-ghost" onClick={() => navigate(user.role === "admin" ? "/admin/my-rooms" : "/my/rooms")}>
          Back to My Rooms
        </button>
      </div>
    );
  }

  return (
    <RoomCall
      room={room}
      onLeave={() => navigate(user.role === "admin" ? "/admin/my-rooms" : "/my/rooms")}
    />
  );
}
