import { onBeforeUnmount, onMounted } from 'vue'

export type HotkeyMap = Record<string, (e: KeyboardEvent) => void>

/**
 * Global hotkeys. Keys are `KeyboardEvent.key` values, optionally prefixed with `mod+`
 * (Ctrl on Linux/Windows, Cmd on macOS). Ignored while typing in form fields.
 */
export function useHotkeys(map: HotkeyMap) {
  function onKey(e: KeyboardEvent) {
    const target = e.target as HTMLElement | null
    if (target?.closest('input, textarea, select, [contenteditable="true"]')) return
    const mod = e.ctrlKey || e.metaKey
    const key = e.key.length === 1 ? e.key.toLowerCase() : e.key
    const handler = map[mod ? `mod+${key}` : key]
    if (!handler || (!mod && e.altKey)) return
    if (!mod && (e.ctrlKey || e.metaKey)) return
    e.preventDefault()
    handler(e)
  }
  onMounted(() => window.addEventListener('keydown', onKey))
  onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
}
