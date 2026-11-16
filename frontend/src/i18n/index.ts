import { createI18n } from 'vue-i18n'

import en from './en'
import ru from './ru'

export type Locale = 'en' | 'ru'
export const LOCALES: Locale[] = ['en', 'ru']
const STORAGE_KEY = 'cc.locale'

function readStored(): Locale | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'en' || value === 'ru' ? value : null
  } catch {
    return null
  }
}

export function initialLocale(): Locale {
  return readStored() ?? (navigator.language.toLowerCase().startsWith('ru') ? 'ru' : 'en')
}

export function storeLocale(locale: Locale): void {
  try {
    localStorage.setItem(STORAGE_KEY, locale)
  } catch {
    /* storage unavailable — fine */
  }
  document.documentElement.lang = locale
}

/** Russian has one/few/many forms; choice 0 is the "zero" message when 4 variants exist. */
function russianPlural(choice: number, choicesLength: number): number {
  const zeroOffset = choicesLength === 4 ? 1 : 0
  if (choice === 0 && zeroOffset) return 0
  const mod10 = choice % 10
  const mod100 = choice % 100
  let form: number
  if (mod10 === 1 && mod100 !== 11) form = 0
  else if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) form = 1
  else form = 2
  return Math.min(form + zeroOffset, choicesLength - 1)
}

/** English: optional zero form when 3 variants exist. */
function englishPlural(choice: number, choicesLength: number): number {
  if (choicesLength === 3) return choice === 0 ? 0 : choice === 1 ? 1 : 2
  return choice === 1 ? 0 : 1
}

export const i18n = createI18n({
  legacy: false,
  locale: initialLocale(),
  fallbackLocale: 'en',
  messages: { en, ru },
  pluralRules: { ru: russianPlural, en: englishPlural },
})
