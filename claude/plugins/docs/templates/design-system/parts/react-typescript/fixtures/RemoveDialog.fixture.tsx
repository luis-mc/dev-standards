import { mount } from './_fixture';
import { RemoveDialog } from '../RemoveDialog';

mount([
  ['no choice', <RemoveDialog size="1.4 GB" path="/home/user/.local/share/the-app/a-very-long-folder-name/with/more/parts/that/must/wrap" />],
  ['keep chosen', <RemoveDialog size="1.4 GB" path="C:\\Users\\Someone\\AppData\\Local\\TheApp" initial="keep" />],
  ['delete chosen', <RemoveDialog size="320 MB" path="~/Library/Application Support/TheApp" initial="purge" />],
]);
