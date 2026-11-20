/**
 * The API's types, named as the UI uses them. Generated from the server's OpenAPI schema
 * (`schema.d.ts`, see `npm run api:types`); only the names and a few narrowings live here.
 */
import type { components } from './schema'

type Schemas = components['schemas']

export type AuthStatus = Schemas['AuthStateOut']['status']
export type TgUser = Schemas['TgUserOut']
export type AuthState = Schemas['AuthStateOut']

export type Decision = Schemas['Decision']
export type ActionDecision = Extract<Decision, 'unsubscribe' | 'mute' | 'archive'>
export type FinalDecision = Exclude<Decision, 'skip'>
export type SortMode = Schemas['SortMode']
export type ChatKind = Schemas['ChatKind']
/** What the user is in that chat. */
export type ChatRole = Schemas['ChatRole']
/** Two decks: chats the user is just in, and the ones they run (admin or owner). */
export type RoleFilter = Schemas['RoleFilter']
/** Which part of the list the deck shows: everything, the main list only, or the archive only. */
export type ArchiveFilter = Schemas['ArchiveFilter']

export type Pulse = Schemas['Pulse']
export type Channel = Schemas['ChannelOut']
export type SyncState = Schemas['SyncStateOut']

/** OpenAPI has no enum-keyed maps: the keys are spelled out here. */
export type DeckCounts = Omit<
  Schemas['DeckCounts'],
  'kind_totals' | 'role_totals' | 'archive_totals' | 'by_decision'
> & {
  kind_totals: Record<ChatKind, number>
  role_totals: Record<RoleFilter, Record<ChatKind, number>>
  archive_totals: Record<ArchiveFilter, number>
  by_decision: Record<FinalDecision, number>
}

export type ChannelsResponse = Omit<Schemas['ChannelsOut'], 'counts'> & { counts: DeckCounts }

export type ApplyItemStatus = Schemas['ApplyItemOut']['status']
export type ApplyItem = Schemas['ApplyItemOut']
export type ApplyState = Schemas['ApplyStateOut']

export type Stats = Schemas['StatsOut']
export type Prefs = Schemas['Prefs']
export type ErrorBody = Schemas['ErrorOut']
