import { mount } from './_fixture';
import { UpdateBanner } from '../UpdateBanner';

mount([
  ['ready', <UpdateBanner state="ready" version="Version 2.4.0 is ready" />],
  ['running', <UpdateBanner state="running" version="Version 2.4.0" percent={40} />],
  ['done', <UpdateBanner state="done" version="Now running 2.4.0" />],
  ['failed', <UpdateBanner state="failed" version="Version 2.4.0" reason="The download could not be checked. The old version still runs." />],
]);
