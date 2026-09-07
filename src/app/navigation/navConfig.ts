import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  BadgeDollarSign,
  Building2,
  ClipboardList,
  CreditCard,
  Home,
  LayoutDashboard,
  ListChecks,
  Radio,
  Router,
  ScrollText,
  Settings,
  ShoppingBag,
  Smartphone,
  Store,
  Ticket,
  UserCircle,
  Users,
  Wallet,
} from 'lucide-react';
import type { Capability } from '@/services/auth/principal';
import { can, canAny, type Principal } from '@/services/auth/principal';

export interface NavItem {
  key: string;
  label: string;
  to: string;
  icon: LucideIcon;
  /** Any of these capabilities makes the item visible. Omit = always visible on the surface. */
  capabilities?: Capability[];
  /** Match nested routes (default true). */
  end?: boolean;
  /** Show in the mobile bottom bar (max 4 + "More"). */
  mobilePrimary?: boolean;
}

export interface NavGroup {
  key: string;
  label?: string;
  items: NavItem[];
}

export const WORKSPACE_NAV: NavGroup[] = [
  {
    key: 'overview',
    items: [
      {
        key: 'dashboard',
        label: 'Dashboard',
        to: '/dashboard',
        icon: LayoutDashboard,
        end: true,
        capabilities: ['dashboard.view'],
        mobilePrimary: true,
      },
      {
        key: 'sessions',
        label: 'Live sessions',
        to: '/sessions',
        icon: Activity,
        capabilities: ['sessions.view'],
      },
    ],
  },
  {
    key: 'sales',
    label: 'Sales',
    items: [
      {
        key: 'vouchers',
        label: 'Vouchers',
        to: '/vouchers',
        icon: Ticket,
        capabilities: ['vouchers.view', 'vouchers.generate'],
        mobilePrimary: true,
      },
      {
        key: 'plans',
        label: 'Plans',
        to: '/plans',
        icon: ListChecks,
        capabilities: ['plans.view'],
      },
      {
        key: 'payments',
        label: 'Payments',
        to: '/payments',
        icon: CreditCard,
        capabilities: ['payments.view'],
        mobilePrimary: true,
      },
      {
        key: 'agents',
        label: 'Agents',
        to: '/agents',
        icon: Store,
        capabilities: ['agents.manage'],
      },
    ],
  },
  {
    key: 'network',
    label: 'Network',
    items: [
      {
        key: 'routers',
        label: 'Routers',
        to: '/routers',
        icon: Router,
        capabilities: ['routers.view'],
        mobilePrimary: true,
      },
      {
        key: 'devices',
        label: 'Devices',
        to: '/devices',
        icon: Smartphone,
        capabilities: ['devices.view'],
      },
    ],
  },
  {
    key: 'admin',
    label: 'Administration',
    items: [
      {
        key: 'audit',
        label: 'Audit log',
        to: '/audit',
        icon: ScrollText,
        capabilities: ['audit.view'],
      },
      {
        key: 'settings',
        label: 'Settings',
        to: '/settings',
        icon: Settings,
        capabilities: ['settings.profile', 'team.view', 'subscription.view'],
      },
    ],
  },
];

export const PLATFORM_NAV: NavGroup[] = [
  {
    key: 'platform',
    items: [
      {
        key: 'overview',
        label: 'Overview',
        to: '/platform',
        icon: LayoutDashboard,
        end: true,
        mobilePrimary: true,
      },
      {
        key: 'tenants',
        label: 'Tenants',
        to: '/platform/tenants',
        icon: Building2,
        mobilePrimary: true,
      },
      {
        key: 'routers',
        label: 'Router fleet',
        to: '/platform/routers',
        icon: Radio,
        mobilePrimary: true,
      },
      {
        key: 'payments',
        label: 'Payments',
        to: '/platform/payments',
        icon: BadgeDollarSign,
        mobilePrimary: true,
      },
      { key: 'staff', label: 'Staff', to: '/platform/staff', icon: Users },
      { key: 'audit', label: 'Audit log', to: '/platform/audit', icon: ClipboardList },
    ],
  },
];

export const AGENT_NAV: NavItem[] = [
  { key: 'home', label: 'Home', to: '/agent', icon: Home, end: true },
  { key: 'sell', label: 'Sell', to: '/agent/sell', icon: ShoppingBag },
  { key: 'wallet', label: 'Wallet', to: '/agent/wallet', icon: Wallet },
  { key: 'vouchers', label: 'Vouchers', to: '/agent/vouchers', icon: Ticket },
  { key: 'profile', label: 'Profile', to: '/agent/profile', icon: UserCircle },
];

export function visibleGroups(groups: NavGroup[], principal: Principal | null): NavGroup[] {
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter(
        (item) => !item.capabilities || canAny(principal, item.capabilities),
      ),
    }))
    .filter((group) => group.items.length > 0);
}

export function visibleItems(groups: NavGroup[], principal: Principal | null): NavItem[] {
  return visibleGroups(groups, principal).flatMap((g) => g.items);
}

/** Mobile bottom bar: up to four primary items the principal can see. */
export function mobilePrimaryItems(groups: NavGroup[], principal: Principal | null): NavItem[] {
  const items = visibleItems(groups, principal);
  const primary = items.filter((i) => i.mobilePrimary);
  const picked = primary.length >= 2 ? primary : items;
  return picked.slice(0, 4);
}

export { can };
