import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

import { api, ApiError, subscribe } from '@/api/client'
import type {
  Channel,
  ChannelsResponse,
  Decision,
  DeckCounts,
  Prefs,
  SortMode,
  SyncState,
} from '@/api/types'
import { i18n } from '@/i18n'

import { useUiStore } from './ui'

const PREFETCH_AHEAD = 8
const ACTIONS: Decision[] = ['unsubscribe', 'mute', 'archive']

export interface HistoryEntry {
  channel: Channel
  decision: Decision
}

export const useDeckStore = defineStore('deck', () => {
  const ui = useUiStore()

  const items = ref<Channel[]>([])
  const history = ref<HistoryEntry[]>([])
  const counts = ref<DeckCounts>({
    total: 0,
    undecided: 0,
    pending: 0,
    by_decision: { keep: 0, unsubscribe: 0, mute: 0, archive: 0 },
  })
  const sync = ref<SyncState | null>(null)
  const prefs = ref<Prefs>({ sort: 'dead', reverse: false })
  const loaded = ref(false)
  const loading = ref(false)
  /** Set right after undo so the card can animate back in from where it left. */
  const returning = ref<HistoryEntry | null>(null)

  /** "+1" chips on their way to the progress bar; the bar waits for them to land. */
  const chipsInFlight = ref(0)
  /** Bumped when a chip lands, so the progress counter can pulse. */
  const landed = ref(0)
  /** Timestamps of this session's decisions, for the ETA. */
  const stamps = ref<number[]>([])

  const current = computed(() => items.value[0] ?? null)
  const decided = computed(() => counts.value.total - counts.value.undecided)

  /** Remaining time at the user's own pace (median gap between the last decisions), minutes. */
  const eta = computed(() => {
    const s = stamps.value
    if (s.length < 4) return null
    const gaps = s
      .slice(-11)
      .map((ts, i, arr) => (i ? ts - arr[i - 1]! : 0))
      .slice(1)
      .sort((a, b) => a - b)
    const median = Math.min(gaps[Math.floor(gaps.length / 2)]!, 30_000)
    return Math.round((median * counts.value.undecided) / 60_000)
  })
  const position = computed(() =>
    Math.min(counts.value.total - counts.value.undecided + 1, counts.value.total),
  )
  const syncing = computed(() => sync.value?.running ?? false)

  let stopSync: (() => void) | null = null
  const inflight = new Set<number>()

  function report(err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    ui.toast(i18n.global.t('login.errors.generic', { msg }))
  }

  async function loadPrefs() {
    try {
      prefs.value = await api.get<Prefs>('/api/prefs')
    } catch {
      /* defaults are fine */
    }
  }

  async function load() {
    loading.value = true
    try {
      if (!loaded.value) await loadPrefs()
      const params = new URLSearchParams({
        sort: prefs.value.sort,
        reverse: String(prefs.value.reverse),
      })
      const data = await api.get<ChannelsResponse>(`/api/channels?${params}`)
      items.value = data.items
      counts.value = data.counts
      sync.value = data.sync
      loaded.value = true
    } catch (err) {
      report(err)
    } finally {
      loading.value = false
    }
  }

  async function savePrefs(next: Prefs) {
    prefs.value = next
    try {
      await api.put('/api/prefs', next)
    } catch {
      /* not critical */
    }
    await load()
  }

  const setSort = (sort: SortMode) => savePrefs({ ...prefs.value, sort })
  const toggleReverse = () => savePrefs({ ...prefs.value, reverse: !prefs.value.reverse })

  async function decide(decision: Decision) {
    const channel = items.value.shift()
    if (!channel) return
    if (decision === 'skip') items.value.push(channel)
    history.value.push({ channel, decision })
    returning.value = null
    const before = { ...counts.value, by_decision: { ...counts.value.by_decision } }
    if (decision !== 'skip') {
      counts.value.undecided -= 1
      counts.value.by_decision[decision] += 1
      if (ACTIONS.includes(decision)) counts.value.pending += 1
      stamps.value.push(Date.now())
    }
    try {
      const res = await api.put<{ counts: DeckCounts }>(`/api/decisions/${channel.id}`, {
        decision,
      })
      counts.value = res.counts
    } catch (err) {
      history.value.pop()
      if (decision === 'skip') items.value.pop()
      items.value.unshift(channel)
      counts.value = before
      report(err)
    }
  }

  async function undo() {
    const entry = history.value.pop()
    if (!entry) return
    try {
      const res = await api.del<{ counts: DeckCounts }>(`/api/decisions/${entry.channel.id}`)
      counts.value = res.counts
    } catch (err) {
      history.value.push(entry)
      report(err)
      return
    }
    if (entry.decision === 'skip') {
      const idx = items.value.findIndex((c) => c.id === entry.channel.id)
      if (idx >= 0) items.value.splice(idx, 1)
    }
    items.value.unshift({ ...entry.channel, decision: null })
    returning.value = entry
  }

  /** Called from the review screen: a channel was put back into the deck. */
  function forget(channelId: number) {
    history.value = history.value.filter((h) => h.channel.id !== channelId)
  }

  async function prefetch(channel: Channel) {
    // Rows cached before the pulse existed are "loaded" but still need the pulse.
    if ((channel.full_loaded && channel.pulse) || inflight.has(channel.id)) return
    inflight.add(channel.id)
    try {
      const full = await api.get<Channel>(`/api/channels/${channel.id}/full`)
      const idx = items.value.findIndex((c) => c.id === channel.id)
      if (idx >= 0) items.value[idx] = { ...items.value[idx]!, ...full, decision: null }
    } catch (err) {
      if (err instanceof ApiError && err.code === 'flood_wait') {
        // Back off quietly; the card simply shows without a description for now.
        setTimeout(() => inflight.delete(channel.id), (err.retryAfter ?? 10) * 1000)
        return
      }
    }
    inflight.delete(channel.id)
  }

  watch(
    () => items.value.slice(0, PREFETCH_AHEAD).map((c) => c.id),
    async () => {
      for (const channel of items.value.slice(0, PREFETCH_AHEAD)) {
        await prefetch(channel) // sequential: the backend serialises GetFullChannel anyway
      }
    },
  )

  function watchSync() {
    if (stopSync) return
    stopSync = subscribe('/api/channels/sync/events', {
      snapshot: (s: SyncState) => (sync.value = s),
      progress: (s: SyncState) => (sync.value = s),
      flood_wait: (s: SyncState) => (sync.value = s),
      error: (s: SyncState) => (sync.value = s),
      done: (s: SyncState) => {
        sync.value = s
        void load()
      },
    })
  }

  function unwatchSync() {
    stopSync?.()
    stopSync = null
  }

  async function resync() {
    try {
      sync.value = await api.post<SyncState>('/api/channels/sync')
    } catch (err) {
      report(err)
    }
  }

  async function reset(only: Decision | null) {
    try {
      await api.post('/api/decisions/reset', { only })
      history.value = []
      await load()
    } catch (err) {
      report(err)
    }
  }

  function clear() {
    items.value = []
    history.value = []
    loaded.value = false
    returning.value = null
  }

  return {
    items,
    history,
    counts,
    sync,
    prefs,
    loaded,
    loading,
    returning,
    chipsInFlight,
    landed,
    current,
    decided,
    eta,
    position,
    syncing,
    load,
    setSort,
    toggleReverse,
    decide,
    undo,
    forget,
    watchSync,
    unwatchSync,
    resync,
    reset,
    clear,
  }
})
