/**
 * Services barrel export
 */
export { api, AthenaApiError } from './api';

export {
  QUERY_KEYS,
  STALE_TIMES,
  fetchDiagData,
  fetchFigureList,
  getFigureUrl,
  checkServerHealth,
} from './diagnostics';
export type { FigureListResponse } from './diagnostics';

export {
  openDiagStream,
  classifyLine,
  categoryColor,
} from './stream';
export type {
  StreamCallbacks,
  StreamController,
  LineCategory,
} from './stream';
