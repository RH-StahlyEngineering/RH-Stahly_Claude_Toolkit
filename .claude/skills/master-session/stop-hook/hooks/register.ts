import type { Register } from 'claude-code'

// Two thin hooks around the skill's state file.
//
// Stop: the decision lives in the skill's state store (scripts/state.py
// stop): the app's Stop message goes in on stdin, one JSON verdict comes out.
// The store is looked for beside this plugin first (the skill folder around
// it), then in the installed skill. Found nowhere: the stop is allowed and
// nothing is shown. Any failure here allows the stop and shows a warning.
//
// prompt.compose: the skill's text is summarised away by a compaction; the
// state file is not. While this session is the state file's owner and not
// paused, the fixed turn rules ride in the system prompt, where a compaction
// cannot reach them. Any other session, and any failure, adds nothing.

type Verdict = { decision?: string; reason?: string; warning?: string }

const FAILED = 'master-session Stop hook failed, stop allowed: '
const INSTALLED = '.claude/skills/master-session/scripts/state.py'
const STATE = '.claude/master-session/state.json'

const TURN_RULES = {
  id: 'master-session-stop:turn-rules',
  scope: 'session',
  text: [
    '# Master session: turn rules',
    'Your state file names you as the master. These rules hold every turn, also after a compact.',
    '- End every turn with the open question in the next-step box (short form, answer buttons), or the line "Nothing needs you: <what runs>."',
    '- On a turn RH did not start: one short line of text at most. Never restate the open question in prose.',
    '- A session you start gets a pointer brief, answers "Received.", then gets its command.',
    '- Record with `state.py` as you go.',
    '- After a compact, before you act, read these master-session SKILL.md sections again: While RH has an open question, Ending a turn, State file.',
  ].join('\n'),
} as const

export const register: Register = on => {
  on('prompt.compose', async ($, e, next) => {
    const composed = await next(e)
    try {
      const traits: readonly string[] = e.traits ?? []
      if (['bare', 'teammate', 'analysis'].some(t => traits.includes(t))) return composed
      const home = (await $.env.get('USERPROFILE')) ?? (await $.env.get('HOME'))
      const path = (await $.env.get('MASTER_SESSION_STATE')) ?? (home ? `${home}/${STATE}` : '')
      if (path === '' || !(await $.fs.exists(path))) return composed
      const state = JSON.parse(await $.fs.read(path)) as { owner?: unknown; paused?: unknown }
      const me = await $.session.id()
      if (typeof state.owner !== 'string' || state.owner === '' || state.owner !== me) return composed
      if (state.paused !== false && state.paused !== undefined) return composed

      return { sections: [...composed.sections.filter(s => s.id !== TURN_RULES.id), TURN_RULES] }
    } catch {
      return composed
    }
  })

  on('classic.Stop', async ($, e, next) => {
    let verdict: Verdict = {}
    let warning = ''
    try {
      const home = (await $.env.get('USERPROFILE')) ?? (await $.env.get('HOME'))
      const places = [`${$.plugin.root}/../scripts/state.py`]
      if (home) places.push(`${home}/${INSTALLED}`)
      let store = ''
      for (const place of places) {
        if (store === '' && (await $.fs.exists(place))) store = place
      }
      if (store !== '') {
        const run = await $.process.run(['python', '-X', 'utf8', '-I', store, 'stop'], {
          stdin: JSON.stringify(e),
          timeoutMs: 15000,
        })
        verdict = JSON.parse(run.stdout) as Verdict
        warning = typeof verdict.warning === 'string' ? verdict.warning : ''
      }
    } catch (err) {
      verdict = {}
      warning = FAILED + String(err)
    }

    if (warning !== '') {
      try {
        $.ui.log(warning)
        $.ui.toast(warning, { timeoutMs: 10000 })
      } catch {}
    }
    if (verdict.decision === 'refuse' && typeof verdict.reason === 'string' && verdict.reason !== '') {
      return { block: verdict.reason }
    }

    return next(e)
  }).catch(($, e, next) => {
    $.ui.log(FAILED + String(next.error))

    return next(e)
  })
}
