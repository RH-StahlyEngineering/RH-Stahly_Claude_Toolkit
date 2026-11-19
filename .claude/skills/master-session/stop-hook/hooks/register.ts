import type { Register } from 'claude-code'

// A thin shim. The decision lives in the skill's state store (scripts/state.py
// stop): the app's Stop message goes in on stdin, one JSON verdict comes out.
// The store is looked for beside this plugin first (the skill folder around
// it), then in the installed skill. Found nowhere: the stop is allowed and
// nothing is shown. Any failure here allows the stop and shows a warning.

type Verdict = { decision?: string; reason?: string; warning?: string }

const FAILED = 'master-session Stop hook failed, stop allowed: '
const INSTALLED = '.claude/skills/master-session/scripts/state.py'

export const register: Register = on => {
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
