import type { Register } from 'claude-code'

// Only these commands may be started by another session's message.
// Built-ins such as /clear or /compact are never reachable from a peer.
const ALLOWED = [/^mattpocock-skills:[a-z0-9-]+$/, /^peer-slash-canary$/]

// Origins that are another session or agent talking to this one.
const PEER_KINDS = new Set(['peer', 'peer-send-message', 'coordinator', 'projects-relay'])

// A leading "/name args", optionally inside a <cross-session-message ...> wrapper.
// The desktop app puts its own <system-reminder> notes (such as "Linked sessions now")
// ahead of a message to a session another session started; those are skipped.
const LEADING_SLASH =
  /^\s*(?:<system-reminder>[\s\S]*?<\/system-reminder>\s*)*(?:<cross-session-message\b[^>]*>\s*)?\/([a-z0-9][a-z0-9:_-]*)(?:[ \t]+([\s\S]*?))?\s*(?:<\/cross-session-message>\s*)?$/i

// The same message as it reaches prompt.submit, framed by the engine's own lead-in.
const WRAPPED_SLASH =
  /<cross-session-message\b[^>]*>\s*\/([a-z0-9][a-z0-9:_-]*)(?:[ \t]+([\s\S]*?))?\s*<\/cross-session-message>/i

// A whole prompt as the desktop app delivers a session's message: its own
// <system-reminder> notes, then one wrapped command from a local session.
const DESKTOP_SLASH =
  /^\s*(?:<system-reminder>[\s\S]*?<\/system-reminder>\s*)*<cross-session-message\b[^>]*\bfrom="local_[0-9a-f-]+"[^>]*>\s*\/([a-z0-9][a-z0-9:_-]*)(?:[ \t]+([\s\S]*?))?\s*<\/cross-session-message>\s*$/i

const key = (command: string, args: string) => `${command}\u0000${args.trim()}`

export const register: Register = on => {
  // Messages turned into commands, waiting for their plain-text copy to be dropped.
  const pending = new Set<string>()

  on('session.receive', async ($, e, next) => {
    if (!PEER_KINDS.has(e.origin.kind)) return next(e)

    const m = LEADING_SLASH.exec(e.text)
    if (!m) return next(e)

    const command = m[1]
    const args = (m[2] ?? '').trim()
    if (!ALLOWED.some(re => re.test(command))) return next(e)

    // Deliver the message untouched: consuming or rewriting it here makes the
    // app record the delivery as refused, and the sender may retry.
    pending.add(key(command, args))
    const res = await next(e)

    // Then run the command; queued until the session is idle, not awaited.
    $.command.run({ command, args }).catch(err =>
      $.ui.toast(`peer-slash: /${command} failed to run: ${String(err)}`),
    )
    return res
  })

  // The delivery is already recorded as delivered; stop its plain-text copy from
  // starting a turn, so the session sees only the command run.
  on('prompt.submit', ($, e, next) => {
    if (e.command) return next(e)

    // The desktop app hands another session's message straight to the prompt
    // (origin "sdk"), with no session.receive first: the whole prompt must be the
    // app's notes and one wrapped command, nothing else.
    if (e.origin.kind === 'sdk') {
      const d = DESKTOP_SLASH.exec(e.text)
      if (!d || !ALLOWED.some(re => re.test(d[1]))) return next(e)
      const command = d[1]
      const args = (d[2] ?? '').trim()
      // $.command.run is refused inside a hook the turn waits on, so run it
      // from a timer once this hook has answered.
      $.clock.after(100, () => {
        $.command.run({ command, args }).catch(err =>
          $.ui.toast(`peer-slash: /${command} failed to run: ${String(err)}`),
        )
      })
      const from = /from-name="([^"]*)"/.exec(d[0])?.[1] || 'another session'
      return { drop: `Sent by "${from}", not typed by you: running /${command} as a command` }
    }

    if (!PEER_KINDS.has(e.origin.kind)) return next(e)
    const m = WRAPPED_SLASH.exec(e.text)
    if (!m) return next(e)
    const k = key(m[1], m[2] ?? '')
    if (!pending.has(k)) return next(e)
    pending.delete(k)
    const from = /from-name="([^"]*)"/.exec(m[0])?.[1] || 'another session'
    return { drop: `Sent by "${from}", not typed by you: running /${m[1]} as a command` }
  })
}
