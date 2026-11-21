import { mount } from './_fixture';
import { FleetRows } from '../FleetRows';

mount([
  ['rows', <FleetRows rows={[
    { machine: 'Office desktop', version: '2.4.0', state: 'up_to_date' },
    { machine: 'A laptop with a rather long display name that has to wrap', version: '2.3.9', state: 'waiting' },
    { machine: 'Build server', version: '2.3.1', state: 'needs_you' },
  ]} />],
]);
