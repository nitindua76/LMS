import { client } from "./client";

export interface RoomMember {
  id: number;
  user_id: number;
  name: string;
  email: string;
  added_via_cpf: boolean;
}

export interface RoomGroupTarget {
  id: number;
  group_id: number;
  group_name: string;
  member_count: number;
}

export interface GroupSearchResult {
  id: number;
  name: string;
  member_count: number;
}

export interface InstantRoom {
  id: number;
  owner_user_id: number;
  owner_name: string;
  name: string;
  room_name: string;
  admit_mode: "automatic" | "manual";
  is_standing_room: boolean;
  active: boolean;
  created_at: string;
  members: RoomMember[];
  group_targets: RoomGroupTarget[];
  is_owner: boolean;
  join_url: string;
}

export interface RoomJoinResponse {
  livekit_url: string;
  token: string;
  room_name: string;
  identity: string;
  is_host: boolean;
  admitted: boolean;
}

export interface PendingParticipant {
  user_id: number;
  name: string;
  email: string;
  joined_at: string;
}

export const roomsApi = {
  list: () => client.get<InstantRoom[]>("/my/rooms").then((r) => r.data),

  get: (roomId: number) => client.get<InstantRoom>(`/my/rooms/${roomId}`).then((r) => r.data),

  create: (data: { name: string; admit_mode?: "automatic" | "manual"; is_standing_room?: boolean }) =>
    client.post<InstantRoom>("/my/rooms", data).then((r) => r.data),

  delete: (roomId: number) => client.delete(`/my/rooms/${roomId}`),

  addMemberByUser: (roomId: number, userId: number) =>
    client.post<RoomMember>(`/my/rooms/${roomId}/members`, { user_id: userId }).then((r) => r.data),

  addMemberByCpf: (roomId: number, cpf: string) =>
    client.post<RoomMember>(`/my/rooms/${roomId}/members/by-cpf`, { cpf }).then((r) => r.data),

  removeMember: (roomId: number, memberId: number) =>
    client.delete(`/my/rooms/${roomId}/members/${memberId}`),

  listGroupTargets: (roomId: number) =>
    client.get<RoomGroupTarget[]>(`/my/rooms/${roomId}/group-targets`).then((r) => r.data),

  addGroupTarget: (roomId: number, groupId: number) =>
    client.post<RoomGroupTarget>(`/my/rooms/${roomId}/group-targets`, { group_id: groupId }).then((r) => r.data),

  removeGroupTarget: (roomId: number, targetId: number) =>
    client.delete(`/my/rooms/${roomId}/group-targets/${targetId}`),

  searchGroups: (q: string) =>
    client.get<GroupSearchResult[]>("/my/rooms/groups/search", { params: { q } }).then((r) => r.data),

  join: (roomId: number) => client.post<RoomJoinResponse>(`/my/rooms/${roomId}/join`).then((r) => r.data),

  listPending: (roomId: number) =>
    client.get<PendingParticipant[]>(`/my/rooms/${roomId}/pending`).then((r) => r.data),

  admit: (roomId: number, userId: number) => client.post(`/my/rooms/${roomId}/admit/${userId}`),

  decline: (roomId: number, userId: number) => client.post(`/my/rooms/${roomId}/decline/${userId}`),

  leave: (roomId: number) => client.post(`/my/rooms/${roomId}/leave`),

  end: (roomId: number) => client.post(`/my/rooms/${roomId}/end`),
};
