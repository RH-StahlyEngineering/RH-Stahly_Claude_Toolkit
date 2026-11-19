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
