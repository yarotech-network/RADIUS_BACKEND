import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import UiGalleryPage from '@/features/dev/UiGalleryPage';

describe('UI gallery smoke', () => {
  it('renders every section and opens overlays without crashing', async () => {
    renderWithProviders(<UiGalleryPage />);
    expect(screen.getByRole('heading', { name: 'UI gallery' })).toBeInTheDocument();
    for (const name of ['Buttons', 'Form controls', 'Status vocabulary', 'Stats', 'Feedback', 'Overlays', 'Data table', 'Formatters']) {
      expect(screen.getByRole('heading', { name })).toBeInTheDocument();
    }
    await userEvent.click(screen.getByRole('button', { name: 'Open dialog' }));
    expect(screen.getByRole('heading', { name: 'Generate vouchers' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Close' }));
    await userEvent.click(screen.getByRole('button', { name: 'Success toast' }));
    expect(screen.getByText('Vouchers generated')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Menu' }));
    expect(screen.getByRole('menu')).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });
});
