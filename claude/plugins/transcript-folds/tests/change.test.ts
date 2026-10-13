import test from 'node:test'
import assert from 'node:assert/strict'

import { changeOf, changedLines, foldedFileChange, isOverThreshold } from '../hooks/fold/change.ts'

const hunk = (lines: string[], start = 5) => ({
  oldStart: start,
  oldLines: lines.length,
  newStart: start,
  newLines: lines.length,
  lines,
})

test('Edit: counts from the patch, path kept as reported', () => {
  const c = changeOf('Edit', {
    filePath: '/p/a.ts',
    structuredPatch: [hunk([' x', '-a', '+b', '+c'])],
  })
  assert.ok(c)
  assert.equal(c.kind, 'edit')
  assert.equal(c.path, '/p/a.ts')
  assert.deepEqual([c.added, c.removed, c.firstLine, c.files], [2, 1, 6, 1])
})

test('MultiEdit reads like Edit', () => {
  const c = changeOf('MultiEdit', { filePath: '/p/a.ts', structuredPatch: [hunk(['+a'])] })
  assert.equal(c?.added, 1)
})

test('Edit held for review, without a patch, or errored shape: no change', () => {
  assert.equal(changeOf('Edit', { filePath: '/p/a.ts', staged: true, structuredPatch: [hunk(['+a'])] }), null)
  assert.equal(changeOf('Edit', { filePath: '/p/a.ts', structuredPatch: [] }), null)
  assert.equal(changeOf('Edit', 'Error: no match'), null)
  assert.equal(changeOf('Edit', undefined), null)
  assert.equal(changeOf('Edit', { structuredPatch: [hunk(['+a'])] }), null)
})

test('Write: a new file counts its content', () => {
  const c = changeOf('Write', { type: 'create', filePath: '/p/n.md', content: 'a\nb\nc', structuredPatch: [] })
  assert.ok(c)
  assert.equal(c.kind, 'new')
  assert.deepEqual([c.added, c.removed], [3, 0])
})

test('Write: an update counts the patch; none means no change', () => {
  const c = changeOf('Write', { type: 'update', filePath: '/p/n.md', content: 'x', structuredPatch: [hunk(['-a', '+b'])] })
  assert.equal(c?.kind, 'edit')
  assert.equal(changeOf('Write', { type: 'update', filePath: '/p/n.md', content: 'x', structuredPatch: [] }), null)
})

test('NotebookEdit: added, changed and removed cells name the cell', () => {
  const added = changeOf('NotebookEdit', {
    notebook_path: '/p/n.ipynb', edit_mode: 'insert', new_source: 'a\nb', cell_type: 'code',
  })
  assert.ok(added)
  assert.deepEqual([added.kind, added.added, added.removed, added.cell], ['notebook', 2, 0, 'new cell'])

  const changed = changeOf('NotebookEdit', {
    notebook_path: '/p/n.ipynb', edit_mode: 'replace', cell_id: 'c1', old_source: 'a\nb', new_source: 'a\nB',
  })
  assert.deepEqual([changed?.added, changed?.removed, changed?.cell], [1, 1, 'cell c1'])

  const removed = changeOf('NotebookEdit', {
    notebook_path: '/p/n.ipynb', edit_mode: 'delete', cell_id: 'c2', old_source: 'a\nb\nc',
  })
  assert.deepEqual([removed?.added, removed?.removed], [0, 3])
})

test('NotebookEdit with an error: no change', () => {
  assert.equal(changeOf('NotebookEdit', { notebook_path: '/p/n.ipynb', error: 'bad', new_source: 'a' }), null)
})

test('Bash with file edits: files, lines, paths', () => {
  const c = changeOf('Bash', {
    stdout: '',
    stderr: '',
    bashEditDiff: {
      files: [
        { filePath: '/p/a', hunks: [hunk(['+1', '+2'])] },
        { filePath: '/p/b', created: true, hunks: [hunk(['+x'])] },
      ],
      moreFiles: 2,
      changedFiles: ['/p/a', '/p/b', '/p/c'],
    },
  })
  assert.ok(c)
  assert.equal(c.kind, 'bash')
  assert.deepEqual([c.files, c.added, c.removed], [4, 3, 0])
  assert.deepEqual(c.paths, ['/p/a', '/p/b', '/p/c'])
})

test('Bash without edit data, or with it unavailable: no change', () => {
  assert.equal(changeOf('Bash', { stdout: 'x', stderr: '' }), null)
  assert.equal(changeOf('Bash', { bashEditDiff: { files: [], moreFiles: 0 } }), null)
  assert.equal(changeOf('Bash', { bashEditDiff: { files: [], moreFiles: 0, unavailable: true } }), null)
  assert.equal(changeOf('Bash', { bashEditDiff: { files: [{ filePath: '/a', hunks: [] }], moreFiles: 0, skipped: true } }), null)
})

test('PowerShell and other tools carry no change', () => {
  assert.equal(changeOf('PowerShell', { stdout: 'x', stderr: '' }), null)
  assert.equal(changeOf('Read', { filePath: '/a' }), null)
})

test('foldedFileChange: folds over the threshold only, with the switch on, not errored', () => {
  const out = { filePath: '/p/a.ts', structuredPatch: [hunk(['-a', '+b', '+c', '+d', '+e', '+f'])] } // 6 lines
  assert.equal(foldedFileChange('Edit', out, false, true, 5)?.added, 5)
  assert.equal(foldedFileChange('Edit', out, false, true, 6), null)
  assert.equal(foldedFileChange('Edit', out, false, false, 5), null)
  assert.equal(foldedFileChange('Edit', out, true, true, 5), null)
  assert.equal(foldedFileChange('Bash', out, false, true, 0), null)
  assert.equal(foldedFileChange('Edit', 'Error: no match', false, true, 0), null)
})

test('foldedFileChange: threshold 0 folds a one-line edit', () => {
  const out = { filePath: '/p/a.ts', structuredPatch: [hunk(['-a', '+b'])] }
  assert.ok(foldedFileChange('Edit', out, false, true, 0))
})

test('threshold: exactly at the threshold is not folded, one over is', () => {
  const five = { added: 3, removed: 2 }
  assert.equal(changedLines(five), 5)
  assert.equal(isOverThreshold(five, 5), false)
  assert.equal(isOverThreshold({ added: 4, removed: 2 }, 5), true)
  assert.equal(isOverThreshold({ added: 1, removed: 0 }, 0), true)
})

test('threshold 0 folds every diff that changes something, and never an empty one', () => {
  assert.equal(isOverThreshold({ added: 0, removed: 1 }, 0), true)
  assert.equal(isOverThreshold({ added: 0, removed: 0 }, 0), false)
})
