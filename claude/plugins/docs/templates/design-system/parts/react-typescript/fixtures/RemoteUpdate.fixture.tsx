import { mount } from './_fixture';
import { RemoteUpdate } from '../RemoteUpdate';

mount((['ready', 'running', 'done', 'failed'] as const).map((s) =>
  [s, <RemoteUpdate machine="Office desktop" from="2.3.9" to="2.4.0" state={s} percent={55} />] as const));
