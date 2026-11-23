import { expect, test } from 'claude-code/testing'

const STOP = { stop_hook_active: false, session_id: 'master-1' }
const HOME = 'C:/Users/rh'
const INSTALLED = `${HOME}/.claude/skills/master-session/scripts/state.py`
const ran = (stdout: string) => ({ value: { exitCode: 0, stdout, stderr: '' } })

// Where the state store is on this PC: 'beside' the plugin (the skill folder
// around it), 'installed' (the skill under ~/.claude), or 'nowhere'.
type On = Parameters<Parameters<typeof test>[1]>[1]
const storeIs = (on: On, where: 'beside' | 'installed' | 'nowhere') => {
  on('env.get', (_, e) => ({ value: e.name === 'USERPROFILE' ? HOME : undefined }))
  on('fs.exists', (_, e) => {
    const installed = e.path.replace(/\\/g, '/').endsWith(INSTALLED.slice(HOME.length))

    return { value: where === 'installed' ? installed : where === 'beside' && !installed }
  })
}

test('a refusal from the state store sends the master back with its reason', async ($, on) => {
  let argv: readonly string[] = []
  let stdin = ''
  storeIs(on, 'beside')
  on('process.run', (_, e) => {
    argv = e.argv
    stdin = e.init?.stdin ?? ''

    return ran(JSON.stringify({ decision: 'refuse', reason: 'a ready step is untouched: Build csv-export' }))
  })
  on('classic.Stop', () => ({}))

  const result = await $.classic.Stop(STOP)

  expect(result.block).toBe('a ready step is untouched: Build csv-export')
  expect(argv.slice(-2).join(' ')).toMatch(/\/\.\.\/scripts\/state\.py stop$/)
  expect(JSON.parse(stdin).session_id).toBe('master-1')
  expect(JSON.parse(stdin).stop_hook_active).toBe(false)
})

test('with no store beside the plugin, the installed skill decides', async ($, on) => {
  let argv: readonly string[] = []
  storeIs(on, 'installed')
  on('process.run', (_, e) => {
    argv = e.argv

    return ran(JSON.stringify({ decision: 'refuse', reason: 'a ready step is untouched' }))
  })
  on('classic.Stop', () => ({}))

  const result = await $.classic.Stop(STOP)

  expect(result.block).toBe('a ready step is untouched')
  expect(argv.slice(-2).join(' ')).toBe(`${INSTALLED} stop`)
  expect(argv.join(' ')).toMatch(/^python -X utf8 -I /)
})

test('with no store anywhere the stop is allowed and nothing is shown', async ($, on) => {
  const shown: string[] = []
  let runs = 0
  let beneath = 0
  storeIs(on, 'nowhere')
  on('process.run', () => {
    runs += 1

    return ran('')
  })
  on('ui.log', (_, e) => {
    shown.push(e.text)

    return { value: undefined }
  })
  on('ui.toast', (_, e) => {
    shown.push(e.text)

    return { value: undefined }
  })
  on('classic.Stop', () => {
    beneath += 1

    return {}
  })

  const result = await $.classic.Stop(STOP)

  expect(result.block).toBe(undefined)
  expect(runs).toBe(0)
  expect(shown.length).toBe(0)
  expect(beneath).toBe(1)
})

test('an allow passes the stop on to the hooks beneath and shows nothing', async ($, on) => {
  const shown: string[] = []
  let beneath = 0
  storeIs(on, 'beside')
  // What the store prints when there is no state file: a plain allow.
  on('process.run', () => ran(JSON.stringify({ decision: 'allow', why: 'no state file' })))
  on('ui.log', (_, e) => {
    shown.push(e.text)

    return { value: undefined }
  })
  on('ui.toast', (_, e) => {
    shown.push(e.text)

    return { value: undefined }
  })
  on('classic.Stop', () => {
    beneath += 1

    return {}
  })

  const result = await $.classic.Stop(STOP)

  expect(result.block).toBe(undefined)
  expect(beneath).toBe(1)
  expect(shown.length).toBe(0)
})

test('a warning from the state store is shown and the stop allowed', async ($, on) => {
  const shown: string[] = []
  storeIs(on, 'beside')
  on('process.run', () => ran(JSON.stringify({ decision: 'allow', warning: 'state file is damaged or unreadable' })))
  on('ui.log', (_, e) => {
    shown.push(e.text)

    return { value: undefined }
  })
  on('ui.toast', () => ({ value: undefined }))
  on('classic.Stop', () => ({}))

  const result = await $.classic.Stop(STOP)

  expect(result.block).toBe(undefined)
  expect(shown.join(' ')).toMatch(/state file is damaged or unreadable/)
})

test('a store that cannot run or prints rubbish never traps the session', async ($, on) => {
  const shown: string[] = []
  let mode = 'rubbish'
  storeIs(on, 'beside')
  on('process.run', () => {
    if (mode === 'throw') throw new Error('python not found')

    return ran('Traceback (most recent call last)')
  })
  on('ui.log', (_, e) => {
    shown.push(e.text)

    return { value: undefined }
  })
  on('ui.toast', () => ({ value: undefined }))
  on('classic.Stop', () => ({}))

  const rubbish = await $.classic.Stop(STOP)
  mode = 'throw'
  const thrown = await $.classic.Stop(STOP)

  expect(rubbish.block).toBe(undefined)
  expect(thrown.block).toBe(undefined)
  expect(shown.length).toBe(2)
  expect(shown.join(' ')).toMatch(/stop allowed/)
})

// --- the turn rules in the system prompt ------------------------------------

const BASE = [{ id: 'intro', text: 'You are Claude Code.', scope: 'shared' as const }]
const STATE_FILE = `${HOME}/.claude/master-session/state.json`
// What the engine hands a prompt.compose hook: the facts one system prompt is composed from.
const COMPOSE = { model: 'claude-test', promptModel: 'claude-test', surfaces: [], tools: [], outputStyle: null, traits: [] }

// The state file as this PC holds it: its text, or 'missing', or 'throws' when it cannot be read.
const stateIs = (on: On, content: string, me = 'master-1', env: Record<string, string> = {}) => {
  const read: string[] = []
  on('env.get', (_, e) => ({ value: e.name === 'USERPROFILE' ? HOME : env[e.name] }))
  on('session.id', () => ({ value: me }))
  on('fs.exists', () => ({ value: content !== 'missing' }))
  on('fs.read', (_, e) => {
    read.push(e.path.replace(/\\/g, '/'))
    if (content === 'throws') throw new Error('EACCES')

    return { value: content }
  })
  on('prompt.compose', () => ({ sections: BASE }))

  return read
}

test('the owning master gets the turn rules as the last section of its prompt', async ($, on) => {
  const read = stateIs(on, JSON.stringify({ owner: 'master-1', paused: false }))

  const { sections } = await $.prompt.compose(COMPOSE)

  const last = sections[sections.length - 1]
  expect(sections.length).toBe(2)
  expect(sections[0].id).toBe('intro')
  expect(last.scope).toBe('session')
  expect(last.id).toBe('master-session-stop:turn-rules')
  expect(read[0]).toBe(STATE_FILE)
  for (const part of [/next-step box/, /Nothing needs you:/, /RH did not start/, /Never restate/, /"Received\."/,
    /state\.py/, /After a compact/, /Ending a turn/, /While RH has an open question/, /State file/]) {
    expect(last.text).toMatch(part)
  }
  expect(last.text.split(/\s+/).length <= 120).toBe(true)
})

test('the state file named by MASTER_SESSION_STATE is the one read', async ($, on) => {
  const read = stateIs(on, JSON.stringify({ owner: 'master-1' }), 'master-1', { MASTER_SESSION_STATE: 'D:/x/state.json' })

  const { sections } = await $.prompt.compose(COMPOSE)

  expect(read[0]).toBe('D:/x/state.json')
  expect(sections.length).toBe(2)
})

test('a session that is not the owner, or a paused master, gets nothing added', async ($, on) => {
  let content = JSON.stringify({ owner: 'someone-else', paused: false })
  on('env.get', (_, e) => ({ value: e.name === 'USERPROFILE' ? HOME : undefined }))
  on('session.id', () => ({ value: 'master-1' }))
  on('fs.exists', () => ({ value: true }))
  on('fs.read', () => ({ value: content }))
  on('prompt.compose', () => ({ sections: BASE }))

  const other = await $.prompt.compose(COMPOSE)
  content = JSON.stringify({ owner: 'master-1', paused: true })
  const paused = await $.prompt.compose(COMPOSE)
  content = JSON.stringify({ owner: null })
  const unowned = await $.prompt.compose(COMPOSE)

  expect(other.sections.length).toBe(1)
  expect(paused.sections.length).toBe(1)
  expect(unowned.sections.length).toBe(1)
})

test('a missing, unreadable or damaged state file adds nothing and never blocks the prompt', async ($, on) => {
  let content = 'missing'
  on('env.get', (_, e) => ({ value: e.name === 'USERPROFILE' ? HOME : undefined }))
  on('session.id', () => ({ value: 'master-1' }))
  on('fs.exists', () => ({ value: content !== 'missing' }))
  on('fs.read', () => {
    if (content === 'throws') throw new Error('EACCES')

    return { value: content }
  })
  on('prompt.compose', () => ({ sections: BASE }))

  const missing = await $.prompt.compose(COMPOSE)
  content = 'throws'
  const unreadable = await $.prompt.compose(COMPOSE)
  content = '{not json'
  const damaged = await $.prompt.compose(COMPOSE)
  content = '[1, 2]'
  const wrong = await $.prompt.compose(COMPOSE)

  for (const got of [missing, unreadable, damaged, wrong]) {
    expect(got.sections.length).toBe(1)
    expect(got.sections[0].id).toBe('intro')
  }
})
