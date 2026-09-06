import { useMemo } from 'react';
import { PageHeader } from '@/components/layout';
import { useListParams } from '@/components/data';
import { usePrincipal } from '@/app/auth/useAuth';
import { useDebouncedValue } from '@/lib/utilities/useDebouncedValue';
import type { AuditListParams } from '@/types/api';
import { useAuditEvents } from '../queries';
import { resourceLink } from '../auditVocabulary';
import { AuditLogView } from '../components/AuditLogView';

const FILTERS = ['action', 'actor'] as const;

/** `/audit` — the signed-in workspace's own audit trail. */
export default function AuditPage() {
  const principal = usePrincipal();
  const list = useListParams(FILTERS, { ordering: '-created_at' });
  const debouncedSearch = useDebouncedValue(list.state.search);
  const debouncedActor = useDebouncedValue(list.state.filters.actor ?? '');
  const query = useAuditEvents(
    useMemo(() => {
      const p: AuditListParams = { page: list.state.page, page_size: list.state.page_size };
      if (debouncedSearch) p.search = debouncedSearch;
      if (list.state.ordering) p.ordering = list.state.ordering;
      if (list.state.filters.action) p.action = list.state.filters.action;
      const actor = Number(debouncedActor);
      if (debouncedActor && Number.isInteger(actor) && actor > 0) p.actor = actor;
      return p;
    }, [list.state, debouncedSearch, debouncedActor]),
  );

  return (
    <>
      <PageHeader
        title="Audit log"
        description="Who did what in your workspace — voucher batches, router changes, team updates and payment recovery."
      />
      <AuditLogView
        query={query}
        list={list}
        debouncedSearch={debouncedSearch}
        currentUserId={principal?.user.id}
        linkFor={resourceLink}
        emptyDescription="Actions taken by your team will appear here."
      />
    </>
  );
}
