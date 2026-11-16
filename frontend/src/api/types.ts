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

export interface Channel {
  id: number
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
}

export interface DeckCounts {
  total: number
  undecided: number
  pending: number
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
  decision: ActionDecision
  title: string
  has_photo: boolean
  status: ApplyItemStatus
  error: string | null
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
}
