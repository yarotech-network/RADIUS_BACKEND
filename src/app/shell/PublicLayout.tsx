import { Link, Outlet } from 'react-router';
import { BrandMark } from './BrandMark';

/** Minimal centred layout for sign-in, registration, reset, invitation and public pages. */
export function PublicLayout() {
  return (
    <div className="flex min-h-dvh flex-col bg-canvas">
      <header className="mx-auto flex w-full max-w-5xl items-center justify-between px-4 py-4 sm:px-6">
        <Link to="/" aria-label="Home">
          <BrandMark />
        </Link>
      </header>
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-4 pb-10 sm:px-6">
        <Outlet />
      </main>
      <footer className="mx-auto w-full max-w-5xl px-4 py-4 text-xs text-ink-400 sm:px-6">
        © {new Date().getFullYear()} Yarotech Network
      </footer>
    </div>
  );
}
