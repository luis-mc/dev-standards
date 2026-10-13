import type { Register } from 'claude-code'
import { width } from './fold/width.ts'

export const register: Register = on => {
  on('session.start', ($, e, next) => {
    $.ui.toast(String(width('x')))
    return next(e)
  })
}
