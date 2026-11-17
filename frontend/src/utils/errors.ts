export type ActionErrorKind = 'gone' | 'flood' | 'unknown'

/** Map a raw Telegram/apply error to something we can explain to the user. */
export function actionErrorKind(raw: string | null): ActionErrorKind {
  if (!raw) return 'unknown'
  if (/CHANNEL_(PRIVATE|INVALID)|USER_NOT_PARTICIPANT|CHAT_ID_INVALID/i.test(raw)) return 'gone'
  if (/flood/i.test(raw)) return 'flood'
  return 'unknown'
}
