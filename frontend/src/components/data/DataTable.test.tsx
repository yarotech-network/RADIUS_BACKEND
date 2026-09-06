import { describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { DataTable, type Column } from './DataTable';
import { ApiError } from '@/services/api/errors';

interface Row {
  id: number;
  name: string;
  status: string;
}
const columns: Column<Row>[] = [
  { key: 'name', header: 'Name', primary: true, cell: (r) => r.name },
  { key: 'status', header: 'Status', sortField: 'status', cell: (r) => r.status },
];
const rows: Row[] = [
  { id: 1, name: 'Alpha', status: 'active' },
  { id: 2, name: 'Beta', status: 'unused' },
];

describe('DataTable', () => {
  it('renders rows, sorts via backend ordering and handles clicks', async () => {
    const onOrderingChange = vi.fn();
    const onRowClick = vi.fn();
    renderWithProviders(
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        onOrderingChange={onOrderingChange}
        onRowClick={onRowClick}
        mobileCards={false}
      />,
    );
    const table = screen.getByRole('table');
    expect(within(table).getAllByRole('row')).toHaveLength(3);
    await userEvent.click(within(table).getByRole('button', { name: /status/i }));
    expect(onOrderingChange).toHaveBeenCalledWith('status');
    await userEvent.click(within(table).getByText('Alpha'));
    expect(onRowClick).toHaveBeenCalledWith(rows[0]);
  });

  it('cycles ordering asc → desc → none', async () => {
    const onOrderingChange = vi.fn();
    const { rerender } = renderWithProviders(
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        ordering="status"
        onOrderingChange={onOrderingChange}
        mobileCards={false}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /status/i }));
    expect(onOrderingChange).toHaveBeenLastCalledWith('-status');
    rerender(
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        ordering="-status"
        onOrderingChange={onOrderingChange}
        mobileCards={false}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /status/i }));
    expect(onOrderingChange).toHaveBeenLastCalledWith(undefined);
  });

  it('shows skeleton, empty and error states', () => {
    const { rerender } = renderWithProviders(
      <DataTable
        columns={columns}
        rows={undefined}
        loading
        rowKey={(r) => r.id}
        mobileCards={false}
      />,
    );
    expect(screen.queryByText('Alpha')).not.toBeInTheDocument();
    rerender(
      <DataTable
        columns={columns}
        rows={[]}
        rowKey={(r) => r.id}
        empty={<p>No records</p>}
        mobileCards={false}
      />,
    );
    expect(screen.getByText('No records')).toBeInTheDocument();
    const onRetry = vi.fn();
    rerender(
      <DataTable
        columns={columns}
        rows={undefined}
        error={new ApiError({ status: 503, message: 'RADIUS unavailable' })}
        onRetry={onRetry}
        rowKey={(r) => r.id}
        mobileCards={false}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('RADIUS unavailable');
  });
});
