import { onBeforeUnmount, onMounted } from 'vue'

export type HotkeyMap = Record<string, (e: KeyboardEvent) => void>

type KeyInfo = Pick<KeyboardEvent, 'key' | 'code' | 'ctrlKey' | 'metaKey'>

/**
 * Name of a key press as used in a HotkeyMap: `m`, `ArrowLeft`, `mod+z`…
 *
 * Letters are taken from the physical key (`KeyM` → `m`), so shortcuts keep working on
 * non-latin layouts where `e.key` would be `ь` or `ф`.
 */
export function hotkeyName(e: KeyInfo): string {
  let key: string
  if (/^Key[A-Z]$/.test(e.code)) key = e.code.slice(3).toLowerCase()
  else key = e.key.length === 1 ? e.key.toLowerCase() : e.key
  return e.ctrlKey || e.metaKey ? `mod+${key}` : key
}

/**
 * Global hotkeys. Keys are `KeyboardEvent.key` values (letters by physical position),
 * optionally prefixed with `mod+` (Ctrl on Linux/Windows, Cmd on macOS).
 * Ignored while typing in form fields.
 */
export function useHotkeys(map: HotkeyMap) {
  function onKey(e: KeyboardEvent) {
    const target = e.target
    if (
      target instanceof Element &&
      target.closest('input, textarea, select, [contenteditable="true"]')
    )
      return
    if (e.altKey) return
    const handler = map[hotkeyName(e)]
    if (!handler) return
    e.preventDefault()
    handler(e)
  }
  onMounted(() => window.addEventListener('keydown', onKey))
  onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
}
