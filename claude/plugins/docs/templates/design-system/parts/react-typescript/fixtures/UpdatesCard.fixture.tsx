import { mount } from './_fixture';
import { UpdatesCard } from '../UpdatesCard';

mount([
  ['automatic', <UpdatesCard policy="automatic_when_idle" channel="stable" waitForRunningWork lastCheck="Today, 09:12" window={{ from: '01:00', to: '05:00' }} />],
  ['ask first', <UpdatesCard policy="ask_first" channel="stable" waitForRunningWork={false} lastCheck="Yesterday, 21:40" />],
  ['admin lock', <UpdatesCard policy="ask_first" channel="stable" waitForRunningWork lastCheck="Today, 09:12" lockedBy="an administrator" />],
]);
