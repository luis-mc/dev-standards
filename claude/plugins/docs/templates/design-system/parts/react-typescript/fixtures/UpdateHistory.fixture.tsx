import { mount } from './_fixture';
import { UpdateHistory } from '../UpdateHistory';

mount([
  ['empty', <UpdateHistory events={[]} />],
  ['rows', <UpdateHistory events={[
    { at: '21 Nov, 09:12', actor: 'owner', action: 'Installed 2.4.0', result: 'ok' },
    { at: '20 Nov, 02:03', actor: 'the updater', action: 'Rolled back 2.3.9', result: 'failed' },
    { at: '19 Nov, 02:00', actor: 'the updater', action: 'Skipped 2.3.8', result: 'skipped' },
  ]} />],
]);
