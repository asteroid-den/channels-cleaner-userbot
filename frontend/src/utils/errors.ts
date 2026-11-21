export type ActionErrorKind = 'gone' | 'flood' | 'unknown'

export function actionErrorKind(raw: string | null): ActionErrorKind {
  if (!raw) return 'unknown'
  if (/CHANNEL_(PRIVATE|INVALID)|USER_NOT_PARTICIPANT|CHAT_ID_INVALID/i.test(raw)) return 'gone'
  if (/flood/i.test(raw)) return 'flood'
  return 'unknown'
}
