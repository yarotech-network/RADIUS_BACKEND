import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { Check } from 'lucide-react';
import dashboardPreview from '@/assets/images/dashboard-preview.jpg';
import { cn } from '@/lib/utilities/cn';
import { BrandMark } from './BrandMark';

/**
 * Two-sided authentication layout: form on the left, a branded panel with a
 * dashboard preview and feature highlights on the right (hidden on mobile,
 * where the form fills the screen). Used by the sign-in, registration and
 * email-verification pages.
 */
export function AuthSplitLayout({
  title,
  description,
  children,
  footer,
  className,
  panelTitle = 'Your hotspot business, one dashboard',
  panelDescription = 'Create vouchers, onboard routers, manage agents and take payments — every Wi-Fi operation in a single workspace.',
  panelPoints = [
    'Vouchers & access codes generated in seconds',
    'Live sessions, routers and devices at a glance',
    'Agents, wallets and Paystack payments built in',
  ],
}: {
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  panelTitle?: string;
  panelDescription?: string;
  panelPoints?: string[];
}) {
  return (
    <div className="flex min-h-dvh flex-col bg-canvas lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      {/* form side */}
      <div className="flex flex-1 flex-col">
        <header className="px-5 py-5 sm:px-10">
          <Link to="/" aria-label="Yarotech RADIUS home">
            <BrandMark />
          </Link>
        </header>
        <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-5 pb-12 sm:px-8">
          <div className={cn('rounded-card border border-border bg-surface p-6 sm:p-8', className)}>
            <h1 className="text-xl font-semibold text-brand-950">{title}</h1>
            {description && <p className="mt-1 text-sm text-ink-500">{description}</p>}
            <div className="mt-6">{children}</div>
          </div>
          {footer && <div className="mt-4 text-center text-sm text-ink-500">{footer}</div>}
        </main>
      </div>

      {/* brand side */}
      <aside className="relative hidden overflow-hidden bg-brand-950 lg:flex lg:flex-col lg:justify-center">
        <img
          src={dashboardPreview}
          alt="Preview of the Yarotech RADIUS workspace dashboard"
          className="absolute inset-0 size-full object-cover opacity-30"
          loading="lazy"
          decoding="async"
        />
        <div
          className="absolute inset-0 bg-gradient-to-t from-brand-950 via-brand-950/70 to-brand-950/40"
          aria-hidden
        />
        <div className="relative z-10 mx-auto w-full max-w-md px-10 py-16">
          <h2 className="text-2xl font-semibold tracking-tight text-white">{panelTitle}</h2>
          <p className="mt-3 text-sm leading-relaxed text-brand-100">{panelDescription}</p>
          <ul className="mt-8 space-y-3">
            {panelPoints.map((point) => (
              <li key={point} className="flex items-start gap-3 text-sm text-brand-50">
                <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-brand-500/30">
                  <Check className="size-3.5 text-brand-100" aria-hidden />
                </span>
                <span>{point}</span>
              </li>
            ))}
          </ul>
          <p className="mt-10 text-xs text-brand-200">
            © {new Date().getFullYear()} Yarotech Network
          </p>
        </div>
      </aside>
    </div>
  );
}
