import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX } from '@/app/config/constants';

export interface ListState {
  page: number;
  page_size: number;
  search: string;
  ordering: string | undefined;
  filters: Record<string, string>;
}

/**
 * URL-backed list state (page, page_size, search, ordering + arbitrary filters) so list views are
 * shareable and survive refresh. Any filter change resets to page 1.
 */
const NO_FILTERS: readonly string[] = [];

export interface ListDefaults {
  page_size?: number;
  ordering?: string;
}

/**
 * NOTE: pass a module-level constant for `filterKeys` (e.g. `const FILTERS = ['status', 'plan'] as const`)
 * so the memoised state is stable between renders.
 */
export function useListParams(filterKeys: readonly string[] = NO_FILTERS, defaults?: ListDefaults) {
  const [params, setParams] = useSearchParams();
  const defaultPageSize = defaults?.page_size ?? PAGE_SIZE_DEFAULT;
  const defaultOrdering = defaults?.ordering;

  const state = useMemo<ListState>(() => {
    const filters: Record<string, string> = {};
    for (const key of filterKeys) {
      const value = params.get(key);
      if (value) filters[key] = value;
    }
    const pageSize = Number(params.get('page_size')) || defaultPageSize;
    return {
      page: Math.max(1, Number(params.get('page')) || 1),
      page_size: Math.min(PAGE_SIZE_MAX, Math.max(1, pageSize)),
      search: params.get('search') ?? '',
      ordering: params.get('ordering') ?? defaultOrdering,
      filters,
    };
  }, [params, filterKeys, defaultPageSize, defaultOrdering]);

  const update = useCallback(
    (
      patch: Partial<Record<string, string | number | undefined>>,
      options: { resetPage?: boolean } = { resetPage: true },
    ) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          for (const [key, value] of Object.entries(patch)) {
            if (value === undefined || value === '' || value === null) next.delete(key);
            else next.set(key, String(value));
          }
          if (options.resetPage !== false && !('page' in patch)) next.delete('page');
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const setPage = useCallback(
    (page: number) => update({ page: page > 1 ? page : undefined }, { resetPage: false }),
    [update],
  );
  const setPageSize = useCallback(
    (size: number) => update({ page_size: size === PAGE_SIZE_DEFAULT ? undefined : size }),
    [update],
  );
  const setSearch = useCallback((search: string) => update({ search }), [update]);
  const setOrdering = useCallback((ordering: string | undefined) => update({ ordering }), [update]);
  const setFilter = useCallback(
    (key: string, value: string | undefined) => update({ [key]: value }),
    [update],
  );
  const clearFilters = useCallback(() => {
    const patch: Record<string, undefined> = { search: undefined };
    for (const key of filterKeys) patch[key] = undefined;
    update(patch);
  }, [filterKeys, update]);

  const activeFilterCount = Object.keys(state.filters).length + (state.search ? 1 : 0);

  /** Query object ready for the API service (drops empty values). */
  const query = useMemo(
    () => ({
      page: state.page,
      page_size: state.page_size,
      ...(state.search ? { search: state.search } : {}),
      ...(state.ordering ? { ordering: state.ordering } : {}),
      ...state.filters,
    }),
    [state],
  );

  return {
    state,
    query,
    setPage,
    setPageSize,
    setSearch,
    setOrdering,
    setFilter,
    clearFilters,
    activeFilterCount,
  };
}
