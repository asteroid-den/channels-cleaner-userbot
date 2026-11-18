export type AuthStatus = 'starting' | 'unauthorized' | 'qr' | 'code' | 'password' | 'authorized'

export interface TgUser {
  id: number
  first_name: string
  last_name: string | null
  username: string | null
}

export interface AuthState {
  status: AuthStatus
  user: TgUser | null
  qr_url: string | null
  qr_expires_at: string | null
  password_hint: string | null
  phone: string | null
  error: string | null
}

export type Decision = 'keep' | 'unsubscribe' | 'mute' | 'archive' | 'skip'
export type ActionDecision = 'unsubscribe' | 'mute' | 'archive'
export type SortMode = 'dead' | 'unread'
export type ChatKind = 'channel' | 'supergroup'
/** Which part of the list the deck shows: everything, the main list only, or the archive only. */
export type ArchiveFilter = 'all' | 'active' | 'archived'

export interface Pulse {
  /** 26 weekly post counts, oldest first; null = week not covered by the fetched history. */
  weeks: (number | null)[]
  per_week: number
  truncated: boolean
  sample: number
}

export interface Channel {
  id: number
  kind: ChatKind
  title: string
  username: string | null
  link: string | null
  about: string | null
  members_count: number | null
  unread_count: number
  is_muted: boolean
  is_archived: boolean
  avatar_url: string | null
  thumb_url: string | null
  last_post_at: string | null
  last_post_text: string | null
  last_post_media: string | null
  full_loaded: boolean
  decision: Decision | null
  decision_status: 'pending' | 'applied' | 'failed' | null
  error: string | null
  pulse: Pulse | null
  /** an applied mute/archive this (changed) decision will take back */
  reverts?: 'mute' | 'archive' | null
}

export type FinalDecision = Exclude<Decision, 'skip'>

export interface DeckCounts {
  total: number
  undecided: number
  pending: number
  /** Pending actions of the other kind: review and apply cover both. */
  pending_other: number
  /** Final decisions per kind for channels still in the list. */
  by_decision: Record<FinalDecision, number>
  /** Final decisions in the order they were made: k(eep) u(nsubscribe) m(ute) a(rchive). */
  trail: string
}

export interface SyncState {
  running: boolean
  fetched: number
  total: number | null
  last_synced_at: string | null
  flood_wait: number | null
  error: string | null
}

export interface ChannelsResponse {
  items: Channel[]
  counts: DeckCounts
  sync: SyncState
}

export type ApplyItemStatus = 'queued' | 'running' | 'done' | 'failed'

export interface ApplyItem {
  channel_id: number
  decision: Decision
  title: string
  has_photo: boolean
  status: ApplyItemStatus
  error: string | null
  /** an applied mute/archive taken back first */
  reverts: 'mute' | 'archive' | null
}

export interface ApplyState {
  job_id: number | null
  status: 'idle' | 'running' | 'finished' | 'cancelled' | 'error'
  total: number
  done: number
  failed: number
  current: number | null
  flood_wait_until: number | null
  items: ApplyItem[]
}

export interface Stats {
  subscribed: number
  unread_total: number
  unread_cleared: number
  decisions: Record<string, Record<string, number>>
  last_post_age: Record<string, number>
}

export interface Prefs {
  sort: SortMode
  reverse: boolean
  archive: ArchiveFilter
}
