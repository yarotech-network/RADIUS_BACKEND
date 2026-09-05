# YAROTECH RADIUS SYSTEM — React.js Frontend Prompts

> **Purpose:** This file contains 15 detailed, step-by-step prompts to rebuild the entire YAROTECH RADIUS SYSTEM frontend using **React.js** with modern UI/UX, **Tailwind CSS**, **React Router v6**, **TanStack Query (React Query)**, **Zustand** for state management, and **shadcn/ui** component library. Each prompt is self-contained and builds on the previous one.

---

## Table of Contents

1. [Project Scaffolding & Dependencies](#prompt-1-project-scaffolding--dependencies)
2. [Authentication System (Login/Register/Password Reset)](#prompt-2-authentication-system)
3. [Dashboard & Layout Shell](#prompt-3-dashboard--layout-shell)
4. [Voucher Management Module](#prompt-4-voucher-management-module)
5. [Voucher Generation & PDF Export](#prompt-5-voucher-generation--pdf-export)
6. [Router Management Module](#prompt-6-router-management-module)
7. [Router Onboarding & Deployment](#prompt-7-router-onboarding--deployment)
8. [Agent Portal (Login/Dashboard/Wallet)](#prompt-8-agent-portal)
9. [Agent Voucher Generation & Sales](#prompt-9-agent-voucher-generation--sales)
10. [Payment & Billing Module](#prompt-10-payment--billing-module)
11. [Subscription & Pricing Page](#prompt-11-subscription--pricing-page)
12. [Platform Admin Panel](#prompt-12-platform-admin-panel)
13. [WhatsApp Management & Orders](#prompt-13-whatsapp-management--orders)
14. [MAC Device (IoT) Management](#prompt-14-mac-device-iot-management)
15. [Live Users, Debug & Settings](#prompt-15-live-users-debug--settings)

---

## Prompt 1: Project Scaffolding & Dependencies

### What to Build
Initialize the React project with all necessary tooling, folder structure, and base configuration.

### Commands to Run
```bash
# Create React app with Vite
npx create-vite@latest yarotech-radius-frontend --template react-ts
cd yarotech-radius-frontend

# Install core dependencies
npm install react-router-dom@6 @tanstack/react-query axios zustand
npm install @tanstack/react-query-devtools

# Install UI library (shadcn/ui)
npm install -D tailwindcss @tailwindcss/vite
npx shadcn@latest init

# Install shadcn components
npx shadcn@latest add button card dialog dropdown-menu input label select table tabs toast form badge separator avatar sheet command popover calendar textarea switch tooltip

# Install utility libraries
npm install date-fns clsx tailwind-merge lucide-react
npm install react-hook-form @hookform/resolvers zod
npm install recharts                    # For dashboard charts
npm install qrcode.react                # For QR codes on vouchers
npm install @react-pdf/renderer         # For PDF generation
npm install input-otp                   # For OTP input fields

# Install dev dependencies
npm install -D @types/node prettier eslint-config-prettier
```

### Folder Structure to Create
```
src/
├── api/                    # API client, interceptors, endpoints
│   ├── client.ts           # Axios instance with auth interceptor
│   ├── endpoints.ts        # All API endpoint constants
│   └── types.ts            # TypeScript interfaces for all API responses
├── components/             # Reusable UI components
│   ├── ui/                 # shadcn/ui components (auto-generated)
│   ├── layout/             # Sidebar, Navbar, Footer, PageWrapper
│   ├── vouchers/           # VoucherCard, VoucherTable, VoucherPrintPreview
│   ├── routers/            # RouterCard, RouterStatusBadge, DeploymentTimeline
│   ├── agents/             # AgentCard, WalletBalance, CommissionTable
│   ├── payments/           # PaymentCard, PaystackButton, TransactionRow
│   ├── charts/             # RevenueChart, UserChart, UsageChart
│   └── shared/             # DataTable, EmptyState, LoadingSpinner, ErrorBoundary
├── hooks/                  # Custom React hooks
│   ├── useAuth.ts
│   ├── useVouchers.ts
│   ├── useRouters.ts
│   ├── useAgents.ts
│   ├── usePayments.ts
│   └── useDashboard.ts
├── pages/                  # Page components (route targets)
│   ├── auth/               # LoginPage, RegisterPage, PasswordResetPage
│   ├── dashboard/          # DashboardPage, LiveUsersPage
│   ├── vouchers/           # VoucherListPage, VoucherGeneratePage, VoucherPrintPage
│   ├── routers/            # RouterListPage, RouterCreatePage, RouterDeploymentPage
│   ├── agents/             # AgentLoginPage, AgentDashboardPage, AgentWalletPage
│   ├── payments/           # PaymentCallbackPage, PaymentStatusPage
│   ├── subscriptions/      # PricingPage, BillingPage
│   ├── platform/           # PlatformDashboardPage, TenantsPage, ReconciliationPage
│   ├── whatsapp/           # WhatsAppOrdersPage, WhatsAppConfigPage
│   ├── iot/                # IoTDeviceListPage, IoTDeviceAddPage
│   └── settings/           # TenantSettingsPage, ProfilePage
├── store/                  # Zustand stores
│   ├── authStore.ts        # Auth state (user, token, tenant, role)
│   ├── uiStore.ts          # UI state (sidebar open, theme, modals)
│   └── voucherStore.ts     # Voucher filter/sort state
├── lib/                    # Utility functions
│   ├── utils.ts            # cn(), formatKobo(), formatDate(), etc.
│   ├── constants.ts        # App-wide constants
│   └── validations.ts      # Zod schemas for forms
├── routes/                 # Route definitions
│   ├── index.tsx           # Main router setup
│   ├── ProtectedRoute.tsx  # Auth guard component
│   ├── AgentRoute.tsx      # Agent-specific guard
│   └── PlatformRoute.tsx   # Platform admin guard
├── App.tsx
├── main.tsx
└── index.css               # Tailwind imports + custom CSS variables
```

### Files to Create

**`src/api/client.ts`**
```typescript
import axios from "axios";

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1",
  headers: { "Content-Type": "application/json" },
});

// Request interceptor: attach JWT token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: handle 401, refresh token
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      const refreshToken = localStorage.getItem("refresh_token");
      if (refreshToken) {
        try {
          const res = await axios.post(
            `${apiClient.defaults.baseURL}/auth/token/refresh/`,
            { refresh: refreshToken }
          );
          localStorage.setItem("access_token", res.data.access);
          originalRequest.headers.Authorization = `Bearer ${res.data.access}`;
          return apiClient(originalRequest);
        } catch {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;
```

**`src/api/endpoints.ts`**
```typescript
export const API_ENDPOINTS = {
  // Auth
  LOGIN: "/auth/login/",
  REGISTER: "/auth/register/",
  PASSWORD_RESET: "/auth/password-reset/",
  PASSWORD_RESET_CONFIRM: "/auth/password-reset/confirm/",
  TOKEN_REFRESH: "/auth/token/refresh/",
  CURRENT_USER: "/auth/user/",

  // Dashboard
  DASHBOARD_STATS: "/dashboard/stats/",
  DASHBOARD_REVENUE: "/dashboard/revenue/",
  LIVE_USERS: "/dashboard/live-users/",

  // Tenants
  TENANTS: "/tenants/",
  TENANT_DETAIL: (id: number) => `/tenants/${id}/`,
  TENANT_SETTINGS: (id: number) => `/tenants/${id}/settings/`,

  // Vouchers
  VOUCHERS: "/vouchers/",
  VOUCHER_DETAIL: (id: number) => `/vouchers/${id}/`,
  VOUCHER_GENERATE: "/vouchers/generate/",
  VOUCHER_PRINT: (id: number) => `/vouchers/${id}/print/`,
  VOUCHER_PDF: (id: number) => `/vouchers/${id}/pdf/`,
  VOUCHER_DISABLE: (id: number) => `/vouchers/${id}/disable/`,

  // Internet Plans
  PLANS: "/plans/",
  PLAN_DETAIL: (id: number) => `/plans/${id}/`,

  // Routers
  ROUTERS: "/routers/",
  ROUTER_DETAIL: (id: number) => `/routers/${id}/`,
  ROUTER_CREATE: "/routers/create/",
  ROUTER_DEPLOYMENT: (id: number) => `/routers/${id}/deployment/`,
  ROUTER_TEST: (id: number) => `/routers/${id}/test/`,
  ROUTER_STATUS: (id: number) => `/routers/${id}/status/`,

  // Agents
  AGENT_LOGIN: "/agent/login/",
  AGENT_DASHBOARD: "/agent/dashboard/",
  AGENT_VOUCHERS: "/agent/vouchers/",
  AGENT_GENERATE: "/agent/generate/",
  AGENT_WALLET: "/agent/wallet/",
  AGENT_WALLET_FUND: "/agent/wallet/fund/",
  AGENT_WEBHOOK: "/agent/webhook/",

  // Payments
  BUY_VOUCHER: "/buy/",
  PAYMENT_CALLBACK: "/payments/callback/",
  PAYSTACK_WEBHOOK: (token: string) => `/payments/paystack/webhook/${token}/`,

  // Subscriptions
  PRICING: "/pricing/",
  SUBSCRIPTIONS: "/subscriptions/",
  SUBSCRIPTION_DETAIL: (id: number) => `/subscriptions/${id}/`,
  BILLING: "/billing/",
  BILLING_WEBHOOK: "/billing/webhook/",

  // Platform Admin
  PLATFORM_DASHBOARD: "/platform/",
  PLATFORM_TENANTS: "/platform/tenants/",
  PLATFORM_ROUTERS: "/platform/routers/",
  PLATFORM_RECONCILIATION: "/platform/reconciliation/",

  // WhatsApp
  WHATSAPP_CONFIG: "/whatsapp/config/",
  WHATSAPP_ORDERS: "/whatsapp/orders/",
  WHATSAPP_CONVERSATIONS: "/whatsapp/conversations/",

  // IoT / MAC Devices
  IOT_DEVICES: "/iot-devices/",
  IOT_DEVICE_ADD: "/iot-devices/add/",
  IOT_DEVICE_DETAIL: (id: number) => `/iot-devices/${id}/`,
} as const;
```

**`src/api/types.ts`**
```typescript
// === Auth Types ===
export interface User {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_staff: boolean;
}

export interface AuthResponse {
  access: string;
  refresh: string;
  user: User;
}

export interface TenantMembership {
  id: number;
  tenant: Tenant;
  role: "owner" | "manager" | "staff";
  user: User;
}

// === Tenant Types ===
export interface Tenant {
  id: number;
  name: string;
  slug: string;
  phone: string;
  email: string;
  address: string;
  is_active: boolean;
  created_at: string;
}

export interface TenantSetting {
  id: number;
  tenant: number;
  paystack_secret_key: string;
  paystack_public_key: string;
  agent_commission_percent: number;
  voucher_prefix: string;
  max_funding_amount: number;
}

// === Voucher Types ===
export type VoucherStatus = "unused" | "active" | "expired" | "disabled";

export interface InternetPlan {
  id: number;
  name: string;
  price: number;          // in kobo
  duration_hours: number;
  rate_limit: string;     // e.g., "5M/10M"
  data_limit: number;     // in MB, 0 = unlimited
  voucher_prefix: string;
  is_active: boolean;
}

export interface Voucher {
  id: number;
  username: string;
  password: string;
  plan: InternetPlan;
  status: VoucherStatus;
  created_at: string;
  expires_at: string | null;
  activated_at: string | null;
  device_limit: number;
  tenant: number;
  agent: number | null;
  generation_source: "admin" | "agent" | "customer";
}

export interface VoucherGeneratePayload {
  plan_id: number;
  quantity: number;
  prefix?: string;
}

export interface PaymentTransaction {
  id: number;
  reference: string;
  amount: number;
  status: "pending" | "success" | "failed" | "abandoned";
  customer_email: string;
  customer_name: string;
  voucher: Voucher | null;
  created_at: string;
  paid_at: string | null;
}

// === Router Types ===
export type OnboardingState =
  | "pending"
  | "reviewed"
  | "approved"
  | "waiting_for_vpn"
  | "vpn_failed"
  | "testing_radius"
  | "radius_failed"
  | "accounting_failed"
  | "active"
  | "suspended";

export type DeploymentStatus = "not_deployed" | "deploying" | "deployed" | "failed";

export interface NASDevice {
  id: number;
  name: string;
  ip_address: string;
  nas_secret: string;
  wireguard_ip: string;
  wireguard_public_key: string;
  wireguard_port: number;
  onboarding_state: OnboardingState;
  deployment_status: DeploymentStatus;
  routeros_username: string;
  routeros_password: string;
  location: string;
  is_active: boolean;
  created_at: string;
  last_seen_at: string | null;
}

export interface RouterAuditEvent {
  id: number;
  router: number;
  action: string;
  from_state: OnboardingState | null;
  to_state: OnboardingState | null;
  correlation_id: string;
  details: string;
  created_at: string;
}

// === Agent Types ===
export type AgentStatus = "pending" | "active" | "suspended";

export interface AgentProfile {
  id: number;
  user: User;
  phone: string;
  shop_name: string;
  status: AgentStatus;
  commission_rate: number;
  tenant: Tenant;
  created_at: string;
}

export interface AgentWallet {
  id: number;
  agent: AgentProfile;
  balance: number;  // in kobo
  updated_at: string;
}

export interface AgentWalletFundingPayment {
  id: number;
  wallet: AgentWallet;
  amount: number;
  reference: string;
  status: "pending" | "success" | "failed";
  created_at: string;
}

export interface AgentVoucherAllocation {
  id: number;
  agent: AgentProfile;
  voucher: Voucher;
  allocation_type: "wallet" | "credit" | "complimentary";
  amount_charged: number;
  created_at: string;
}

// === Subscription Types ===
export interface SubscriptionPlan {
  id: number;
  name: string;
  price: number;
  duration_days: number;
  features: string[];
  is_active: boolean;
}

export interface TenantSubscription {
  id: number;
  tenant: Tenant;
  plan: SubscriptionPlan;
  status: "trial" | "active" | "expired" | "cancelled";
  started_at: string;
  expires_at: string;
  is_trial: boolean;
}

// === WhatsApp Types ===
export interface WhatsAppConversation {
  id: number;
  phone_number: string;
  tenant: number;
  state: "greeting" | "plan_selected" | "payment_pending" | "fulfilled";
  created_at: string;
  updated_at: string;
}

export interface WhatsAppOrder {
  id: number;
  conversation: WhatsAppConversation;
  voucher: Voucher | null;
  plan: InternetPlan;
  paystack_reference: string;
  payment_status: "pending" | "success" | "failed";
  fulfilment_status: "pending" | "fulfilled" | "failed";
  delivery_status: "pending" | "delivered" | "failed";
  created_at: string;
}

// === IoT / MAC Device Types ===
export interface MacDevice {
  id: number;
  mac_address: string;
  device_name: string;
  plan: InternetPlan;
  tenant: number;
  is_active: boolean;
  expires_at: string;
  created_at: string;
}

// === Dashboard Types ===
export interface DashboardStats {
  total_vouchers: number;
  active_vouchers: number;
  total_revenue: number;
  total_agents: number;
  total_routers: number;
  active_routers: number;
  online_users: number;
  pending_payments: number;
}

export interface RevenueDataPoint {
  date: string;
  revenue: number;
  vouchers_sold: number;
}

export interface LiveUser {
  username: string;
  ip_address: string;
  router: string;
  session_time: string;
  bytes_in: number;
  bytes_out: number;
  connected_at: string;
}
```

**`src/lib/utils.ts`**
```typescript
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatKobo(kobo: number): string {
  return new Intl.NumberFormat("en-NG", {
    style: "currency",
    currency: "NGN",
  }).format(kobo / 100);
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

export function formatDuration(hours: number): string {
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  return remainingHours > 0 ? `${days}d ${remainingHours}h` : `${days}d`;
}

export function formatDate(date: string): string {
  return new Date(date).toLocaleDateString("en-NG", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(date: string): string {
  return new Date(date).toLocaleString("en-NG", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    active: "bg-green-100 text-green-800",
    unused: "bg-blue-100 text-blue-800",
    expired: "bg-yellow-100 text-yellow-800",
    disabled: "bg-red-100 text-red-800",
    pending: "bg-orange-100 text-orange-800",
    success: "bg-green-100 text-green-800",
    failed: "bg-red-100 text-red-800",
    suspended: "bg-red-100 text-red-800",
    deploying: "bg-blue-100 text-blue-800",
    deployed: "bg-green-100 text-green-800",
  };
  return colors[status] || "bg-gray-100 text-gray-800";
}
```

**`src/lib/validations.ts`**
```typescript
import { z } from "zod";

export const loginSchema = z.object({
  username: z.string().min(3, "Username must be at least 3 characters"),
  password: z.string().min(6, "Password must be at least 6 characters"),
});

export const registerSchema = z.object({
  username: z.string().min(3),
  email: z.string().email(),
  password: z.string().min(8),
  password_confirm: z.string(),
  tenant_name: z.string().min(2),
  phone: z.string().min(10),
}).refine((data) => data.password === data.password_confirm, {
  message: "Passwords don't match",
  path: ["password_confirm"],
});

export const voucherGenerateSchema = z.object({
  plan_id: z.number().min(1, "Select a plan"),
  quantity: z.number().min(1, "At least 1 voucher").max(100, "Max 100 per batch"),
  prefix: z.string().optional(),
});

export const routerCreateSchema = z.object({
  name: z.string().min(2),
  ip_address: z.string().ip(),
  nas_secret: z.string().min(8),
  location: z.string().min(2),
  routeros_username: z.string().min(1),
  routeros_password: z.string().min(1),
});

export const internetPlanSchema = z.object({
  name: z.string().min(2),
  price: z.number().min(100, "Minimum price is ₦100"),
  duration_hours: z.number().min(1),
  rate_limit: z.string().regex(/^\d+M\/\d+M$/, "Format: 5M/10M"),
  data_limit: z.number().min(0),
  voucher_prefix: z.string().max(10),
  is_active: z.boolean(),
});

export const agentRegisterSchema = z.object({
  phone: z.string().min(10),
  shop_name: z.string().min(2),
});

export const walletFundSchema = z.object({
  amount: z.number().min(500, "Minimum funding is ₦500"),
});
```

### Verify
```bash
npm run dev
# Should open at http://localhost:5173 with Tailwind working
npx tsc --noEmit
# Should compile with no TypeScript errors
```

---

## Prompt 2: Authentication System

### What to Build
Complete authentication flow: Login, Register (tenant + user), Password Reset, OTP verification, and JWT token management.

### API Endpoints to Consume
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/auth/login/` | POST | Username + password → JWT tokens |
| `/api/v1/auth/register/` | POST | Create tenant + user account |
| `/api/v1/auth/password-reset/` | POST | Request password reset email |
| `/api/v1/auth/password-reset/confirm/` | POST | Confirm reset with token |
| `/api/v1/auth/token/refresh/` | POST | Refresh access token |
| `/api/v1/auth/user/` | GET | Get current authenticated user |

### Files to Create

**`src/store/authStore.ts`**
```typescript
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { User, TenantMembership } from "@/api/types";

interface AuthState {
  user: User | null;
  membership: TenantMembership | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;

  setAuth: (user: User, membership: TenantMembership, access: string, refresh: string) => void;
  logout: () => void;
  setLoading: (loading: boolean) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      membership: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: true,

      setAuth: (user, membership, access, refresh) =>
        set({
          user,
          membership,
          accessToken: access,
          refreshToken: refresh,
          isAuthenticated: true,
          isLoading: false,
        }),

      logout: () => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        set({
          user: null,
          membership: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          isLoading: false,
        });
      },

      setLoading: (loading) => set({ isLoading: loading }),
    }),
    { name: "yarotech-auth" }
  )
);
```

**`src/hooks/useAuth.ts`**
```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import apiClient from "@/api/client";
import { API_ENDPOINTS } from "@/api/endpoints";
import { useAuthStore } from "@/store/authStore";
import { AuthResponse, User, TenantMembership } from "@/api/types";
import { loginSchema, registerSchema } from "@/lib/validations";
import { z } from "zod";

export function useLogin() {
  const navigate = useNavigate();
  const { setAuth } = useAuthStore();

  return useMutation({
    mutationFn: async (data: z.infer<typeof loginSchema>) => {
      const res = await apiClient.post<AuthResponse>(API_ENDPOINTS.LOGIN, data);
      return res.data;
    },
    onSuccess: (data) => {
      localStorage.setItem("access_token", data.access);
      localStorage.setItem("refresh_token", data.refresh);
      // Fetch membership after login
      apiClient
        .get<TenantMembership>("/auth/membership/")
        .then((res) => {
          setAuth(data.user, res.data, data.access, data.refresh);
          const role = res.data.role;
          if (role === "owner" || role === "manager") {
            navigate("/dashboard");
          } else {
            navigate("/dashboard");
          }
        });
    },
  });
}

export function useRegister() {
  const navigate = useNavigate();

  return useMutation({
    mutationFn: async (data: z.infer<typeof registerSchema>) => {
      const res = await apiClient.post(API_ENDPOINTS.REGISTER, data);
      return res.data;
    },
    onSuccess: () => {
      navigate("/login?registered=true");
    },
  });
}

export function useCurrentUser() {
  const { isAuthenticated, setAuth, logout } = useAuthStore();

  return useQuery({
    queryKey: ["currentUser"],
    queryFn: async () => {
      const res = await apiClient.get<User>(API_ENDPOINTS.CURRENT_USER);
      return res.data;
    },
    enabled: isAuthenticated,
    onError: () => {
      logout();
    },
  });
}

export function useLogout() {
  const navigate = useNavigate();
  const { logout } = useAuthStore();
  const queryClient = useQueryClient();

  return () => {
    logout();
    queryClient.clear();
    navigate("/login");
  };
}
```

**`src/pages/auth/LoginPage.tsx`**
```tsx
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Wifi, Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useLogin } from "@/hooks/useAuth";
import { loginSchema } from "@/lib/validations";
import { z } from "zod";

export default function LoginPage() {
  const [searchParams] = useSearchParams();
  const [showPassword, setShowPassword] = useState(false);
  const loginMutation = useLogin();

  const form = useForm<z.infer<typeof loginSchema>>({
    resolver: zodResolver(loginSchema),
    defaultValues: { username: "", password: "" },
  });

  const onSubmit = (data: z.infer<typeof loginSchema>) => {
    loginMutation.mutate(data);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 via-white to-cyan-50">
      <div className="w-full max-w-md px-4">
        {/* Logo */}
        <div className="flex items-center justify-center gap-2 mb-8">
          <div className="w-12 h-12 bg-blue-600 rounded-xl flex items-center justify-center">
            <Wifi className="w-7 h-7 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">YAROTECH</h1>
            <p className="text-sm text-gray-500">RADIUS Management</p>
          </div>
        </div>

        <Card className="shadow-lg border-0">
          <CardHeader className="text-center">
            <CardTitle className="text-xl">Welcome back</CardTitle>
            <CardDescription>Sign in to your account</CardDescription>
          </CardHeader>
          <CardContent>
            {searchParams.get("registered") && (
              <Alert className="mb-4 bg-green-50 border-green-200">
                <AlertDescription className="text-green-800">
                  Account created successfully. Please sign in.
                </AlertDescription>
              </Alert>
            )}

            {loginMutation.isError && (
              <Alert className="mb-4 bg-red-50 border-red-200">
                <AlertDescription className="text-red-800">
                  Invalid username or password. Please try again.
                </AlertDescription>
              </Alert>
            )}

            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  placeholder="Enter your username"
                  {...form.register("username")}
                  className="h-11"
                />
                {form.formState.errors.username && (
                  <p className="text-sm text-red-500">
                    {form.formState.errors.username.message}
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    placeholder="Enter your password"
                    {...form.register("password")}
                    className="h-11 pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                {form.formState.errors.password && (
                  <p className="text-sm text-red-500">
                    {form.formState.errors.password.message}
                  </p>
                )}
              </div>

              <div className="flex items-center justify-between">
                <Link to="/password-reset" className="text-sm text-blue-600 hover:underline">
                  Forgot password?
                </Link>
              </div>

              <Button
                type="submit"
                className="w-full h-11 bg-blue-600 hover:bg-blue-700"
                disabled={loginMutation.isPending}
              >
                {loginMutation.isPending ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Signing in...
                  </>
                ) : (
                  "Sign In"
                )}
              </Button>
            </form>

            <div className="mt-6 text-center">
              <p className="text-sm text-gray-500">
                Don't have an account?{" "}
                <Link to="/register" className="text-blue-600 font-medium hover:underline">
                  Sign up
                </Link>
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
```

**`src/pages/auth/RegisterPage.tsx`**
```tsx
import { useState } from "react";
import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Wifi, Eye, EyeOff, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { useRegister } from "@/hooks/useAuth";
import { registerSchema } from "@/lib/validations";
import { z } from "zod";

export default function RegisterPage() {
  const [showPassword, setShowPassword] = useState(false);
  const registerMutation = useRegister();

  const form = useForm<z.infer<typeof registerSchema>>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      username: "",
      email: "",
      password: "",
      password_confirm: "",
      tenant_name: "",
      phone: "",
    },
  });

  const onSubmit = (data: z.infer<typeof registerSchema>) => {
    registerMutation.mutate(data);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 via-white to-cyan-50 py-8">
      <div className="w-full max-w-lg px-4">
        <div className="flex items-center justify-center gap-2 mb-8">
          <div className="w-12 h-12 bg-blue-600 rounded-xl flex items-center justify-center">
            <Wifi className="w-7 h-7 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">YAROTECH</h1>
            <p className="text-sm text-gray-500">RADIUS Management</p>
          </div>
        </div>

        <Card className="shadow-lg border-0">
          <CardHeader className="text-center">
            <CardTitle className="text-xl">Create your account</CardTitle>
            <CardDescription>Start managing your WiFi hotspot</CardDescription>
          </CardHeader>
          <CardContent>
            {registerMutation.isError && (
              <Alert className="mb-4 bg-red-50 border-red-200">
                <AlertDescription className="text-red-800">
                  Registration failed. Please check your details and try again.
                </AlertDescription>
              </Alert>
            )}

            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              {/* Business Info */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">Business Information</h3>
                <div className="grid grid-cols-1 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="tenant_name">Business Name</Label>
                    <Input id="tenant_name" placeholder="e.g., StarNet WiFi" {...form.register("tenant_name")} className="h-11" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="phone">Phone Number</Label>
                    <Input id="phone" placeholder="e.g., 08012345678" {...form.register("phone")} className="h-11" />
                  </div>
                </div>
              </div>

              <Separator />

              {/* Login Credentials */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">Login Credentials</h3>
                <div className="grid grid-cols-1 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="username">Username</Label>
                    <Input id="username" placeholder="Choose a username" {...form.register("username")} className="h-11" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="email">Email Address</Label>
                    <Input id="email" type="email" placeholder="you@business.com" {...form.register("email")} className="h-11" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password">Password</Label>
                    <div className="relative">
                      <Input
                        id="password"
                        type={showPassword ? "text" : "password"}
                        placeholder="Min. 8 characters"
                        {...form.register("password")}
                        className="h-11 pr-10"
                      />
                      <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400">
                        {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password_confirm">Confirm Password</Label>
                    <Input id="password_confirm" type="password" placeholder="Repeat your password" {...form.register("password_confirm")} className="h-11" />
                  </div>
                </div>
              </div>

              {/* Benefits */}
              <div className="bg-blue-50 rounded-lg p-3 space-y-2">
                {["30-day free trial", "Unlimited vouchers", "Full router management", "WhatsApp agent included"].map((feature) => (
                  <div key={feature} className="flex items-center gap-2 text-sm text-blue-800">
                    <CheckCircle2 className="w-4 h-4 text-blue-600" />
                    {feature}
                  </div>
                ))}
              </div>

              <Button type="submit" className="w-full h-11 bg-blue-600 hover:bg-blue-700" disabled={registerMutation.isPending}>
                {registerMutation.isPending ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Creating account...</>
                ) : (
                  "Create Account"
                )}
              </Button>
            </form>

            <div className="mt-6 text-center">
              <p className="text-sm text-gray-500">
                Already have an account?{" "}
                <Link to="/login" className="text-blue-600 font-medium hover:underline">Sign in</Link>
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
```

**`src/routes/ProtectedRoute.tsx`**
```tsx
import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { Loader2 } from "lucide-react";

export function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuthStore();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}

export function AgentRoute() {
  const { isAuthenticated, membership } = useAuthStore();

  if (!isAuthenticated) return <Navigate to="/agent/login" replace />;
  // Agent portal has its own auth flow
  return <Outlet />;
}

export function PlatformRoute() {
  const { isAuthenticated, membership } = useAuthStore();

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (membership?.role !== "owner") return <Navigate to="/dashboard" replace />;

  return <Outlet />;
}
```

### Verify
```bash
npm run dev
# Navigate to /login — should render the login page
# Navigate to /register — should render the register page
# Navigate to /dashboard without login — should redirect to /login
```

---

## Prompt 3: Dashboard & Layout Shell

### What to Build
Main layout (sidebar + navbar + content area), dashboard with stats cards, revenue chart, and quick actions.

### API Endpoints to Consume
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/dashboard/stats/` | GET | Dashboard statistics |
| `/api/v1/dashboard/revenue/` | GET | Revenue chart data (30 days) |
| `/api/v1/dashboard/live-users/` | GET | Currently connected users |

### Files to Create

**`src/components/layout/Sidebar.tsx`** — Collapsible sidebar with navigation items, role-based menu items, active state highlighting, mobile sheet overlay.

**`src/components/layout/Navbar.tsx`** — Top navbar with search, notifications bell, user avatar dropdown (profile, settings, logout).

**`src/components/layout/PageWrapper.tsx`** — Page container with title, breadcrumbs, optional action buttons.

**`src/components/layout/AppLayout.tsx`** — Combines Sidebar + Navbar + `<Outlet />` for nested routes.

**`src/pages/dashboard/DashboardPage.tsx`** — Stats cards (total vouchers, active users, revenue, routers), revenue line chart (Recharts), recent activity, quick action buttons.

**`src/pages/dashboard/LiveUsersPage.tsx`** — Real-time table of connected users with session time, data usage, disconnect action.

**`src/hooks/useDashboard.ts`** — React Query hooks for `useDashboardStats()`, `useRevenueChart()`, `useLiveUsers()`.

### Verify
```bash
npm run dev
# Login → should see dashboard with stats and charts
# Sidebar should show role-appropriate menu items
# Mobile: sidebar should collapse to sheet overlay
```

---

## Prompt 4: Voucher Management Module

### What to Build
Voucher list with filtering, sorting, pagination, status badges, bulk actions, and individual voucher details.

### API Endpoints to Consume
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/vouchers/` | GET | List vouchers (query params: status, plan, search, page) |
| `/api/v1/vouchers/:id/` | GET | Voucher detail |
| `/api/v1/vouchers/:id/disable/` | POST | Disable a voucher |
| `/api/v1/plans/` | GET | List internet plans |

### Files to Create

**`src/hooks/useVouchers.ts`**
```typescript
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/api/client";
import { API_ENDPOINTS } from "@/api/endpoints";
import { Voucher, InternetPlan } from "@/api/types";

interface VoucherListParams {
  status?: string;
  plan?: number;
  search?: string;
  page?: number;
  page_size?: number;
  ordering?: string;
}

export function useVouchers(params: VoucherListParams) {
  return useQuery({
    queryKey: ["vouchers", params],
    queryFn: async () => {
      const res = await apiClient.get(API_ENDPOINTS.VOUCHERS, { params });
      return res.data; // { results: Voucher[], count: number }
    },
  });
}

export function useVoucherDetail(id: number) {
  return useQuery({
    queryKey: ["voucher", id],
    queryFn: async () => {
      const res = await apiClient.get<Voucher>(API_ENDPOINTS.VOUCHER_DETAIL(id));
      return res.data;
    },
    enabled: !!id,
  });
}

export function useDisableVoucher() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await apiClient.post(API_ENDPOINTS.VOUCHER_DISABLE(id));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vouchers"] });
    },
  });
}

export function useInternetPlans() {
  return useQuery({
    queryKey: ["plans"],
    queryFn: async () => {
      const res = await apiClient.get<InternetPlan[]>(API_ENDPOINTS.PLANS);
      return res.data;
    },
  });
}
```

**`src/pages/vouchers/VoucherListPage.tsx`**
```tsx
// Full page with:
// - Filter bar: status dropdown, plan dropdown, search input, date range picker
// - DataTable with columns: Username, Plan, Status (badge), Created, Expires, Actions
// - Pagination component
// - Row click → navigate to voucher detail
// - Bulk select → bulk disable action
// - Empty state when no vouchers
// - Loading skeleton while fetching
```

**`src/components/vouchers/VoucherTable.tsx`** — Reusable data table with sortable columns.

**`src/components/vouchers/VoucherStatusBadge.tsx`** — Color-coded badge for voucher status.

**`src/components/vouchers/VoucherCard.tsx`** — Card view for voucher (used in agent portal).

### Verify
```bash
npm run dev
# Navigate to /vouchers — should show voucher list
# Filter by status — should update list
# Click voucher — should show detail
# Disable voucher — should update status
```

---

## Prompt 5: Voucher Generation & PDF Export

### What to Build
Voucher generation form, print preview, PDF download with QR codes, batch generation.

### API Endpoints to Consume
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/vouchers/generate/` | POST | Generate vouchers (plan_id, quantity, prefix) |
| `/api/v1/vouchers/:id/print/` | GET | Print-ready HTML view |
| `/api/v1/vouchers/:id/pdf/` | GET | PDF download |
| `/api/v1/plans/` | GET | Available plans |

### Files to Create

**`src/pages/vouchers/VoucherGeneratePage.tsx`**
```tsx
// Form with:
// - Plan selector (cards showing plan name, price, duration, speed)
// - Quantity input (1-100 with +/- buttons)
// - Optional prefix input
// - Preview card showing what voucher will look like
// - Generate button with loading state
// - Success state showing generated vouchers with print/download actions
```

**`src/pages/vouchers/VoucherPrintPage.tsx`**
```tsx
// Print-optimized layout:
// - Voucher cards arranged for A4 paper
// - Each card shows: SSID, username, password, QR code, duration, price
// - Print button triggers window.print()
// - Auto-hides navbar/sidebar for clean print
```

**`src/components/vouchers/VoucherPrintCard.tsx`**
```tsx
// Individual voucher card for printing:
// - Business name/logo at top
// - WiFi network name (SSID)
// - Username and password (large, readable)
// - QR code encoding WiFi credentials
// - Plan details (speed, duration, price)
// - Terms/conditions footer
```

**`src/hooks/useVoucherGenerate.ts`**
```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/api/client";
import { API_ENDPOINTS } from "@/api/endpoints";
import { VoucherGeneratePayload, Voucher } from "@/api/types";

export function useVoucherGenerate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: VoucherGeneratePayload) => {
      const res = await apiClient.post<{ vouchers: Voucher[] }>(API_ENDPOINTS.VOUCHER_GENERATE, payload);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vouchers"] });
    },
  });
}
```

### Verify
```bash
npm run dev
# Navigate to /vouchers/generate
# Select plan, enter quantity → generate
# Should show generated vouchers
# Click print → opens print preview
# Click PDF → downloads PDF
```

---

## Prompt 6: Router Management Module

### What to Build
Router list, create form, status monitoring, deployment timeline, health checks.

### API Endpoints to Consume
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/routers/` | GET | List all routers |
| `/api/v1/routers/:id/` | GET | Router detail |
| `/api/v1/routers/create/` | POST | Create new router |
| `/api/v1/routers/:id/deployment/` | GET | Deployment status |
| `/api/v1/routers/:id/test/` | POST | Test router connectivity |
| `/api/v1/routers/:id/status/` | GET | Live router status |

### Files to Create

**`src/hooks/useRouters.ts`** — React Query hooks for CRUD, deployment status, health checks.

**`src/pages/routers/RouterListPage.tsx`**
```tsx
// Grid layout of router cards with:
// - Status indicator (green dot = online, red = offline, yellow = provisioning)
// - Router name, IP, location
// - Onboarding state badge
// - Deployment status
// - Last seen timestamp
// - Quick actions: View, Test, Restart
```

**`src/pages/routers/RouterCreatePage.tsx`**
```tsx
// Multi-step form:
// Step 1: Basic info (name, IP, location)
// Step 2: RouterOS credentials (username, password, secret)
// Step 3: WireGuard config (auto-generated or manual)
// Step 4: Review & submit
```

**`src/pages/routers/RouterDetailPage.tsx`**
```tsx
// Router detail with tabs:
// Tab 1: Overview (status, IP, location, WireGuard info)
// Tab 2: Deployment (timeline of onboarding states)
// Tab 3: Sessions (active RADIUS sessions)
// Tab 4: Audit Log (state transition history)
// Tab 5: Actions (test, suspend, decommission)
```

**`src/components/routers/RouterStatusBadge.tsx`** — Animated status indicator.

**`src/components/routers/DeploymentTimeline.tsx`** — Visual timeline showing onboarding state progression.

### Verify
```bash
npm run dev
# Navigate to /routers — should show router cards
# Click Create — should show multi-step form
# Click router card — should show detail with tabs
```

---

## Prompt 7: Router Onboarding & Deployment

### What to Build
Visual onboarding workflow, WireGuard status, provisioning progress, real-time status updates.

### API Endpoints to Consume
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/routers/:id/deployment/` | GET | Deployment state machine status |
| `/api/v1/routers/:id/test/` | POST | Test RADIUS through router |
| `/api/v1/routers/:id/provision/` | POST | Trigger provisioning |
| `/api/v1/routers/:id/wireguard/` | GET | WireGuard peer status |

### Files to Create

**`src/components/routers/ProvisioningProgress.tsx`**
```tsx
// Visual progress stepper:
// 1. Router Registered ✓
// 2. WireGuard Configured ✓
// 3. VPN Tunnel Active (pending...)
// 4. RADIUS Tested
// 5. Accounting Verified
// 6. Active ✓
// Each step shows: icon, title, timestamp, error message if failed
// Retry button on failed steps
```

**`src/components/routers/WireGuardStatus.tsx`**
```tsx
// WireGuard connection info:
// - Tunnel IP address
// - Public key
// - Peer status (connected/disconnected)
// - Latency
// - Data transferred (in/out)
// - Last handshake time
```

**`src/components/routers/OnboardingChecklist.tsx`**
```tsx
// Checklist of required onboarding checks:
// □ Router pingable
// □ RouterOS API accessible
// □ WireGuard peer created
// □ RADIUS shared secret configured
// □ Firewall rules applied
// □ Test authentication successful
// □ Accounting data received
// Each item shows pass/fail with details
```

### Verify
```bash
npm run dev
# Navigate to /routers/:id/deployment
# Should show provisioning progress stepper
# Should show WireGuard status
# Should show onboarding checklist
```

---

## Prompt 8: Agent Portal

### What to Build
Separate agent portal with its own login, dashboard, wallet management, and voucher generation.

### API Endpoints to Consume
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/agent/login/` | POST | Agent authentication |
| `/api/v1/agent/dashboard/` | GET | Agent stats |
| `/api/v1/agent/wallet/` | GET | Wallet balance & history |
| `/api/v1/agent/wallet/fund/` | POST | Initialize wallet funding |
| `/api/v1/agent/vouchers/` | GET | Agent's vouchers |

### Files to Create

**`src/pages/agents/AgentLoginPage.tsx`** — Separate login page for agents (phone + password).

**`src/pages/agents/AgentDashboardPage.tsx`**
```tsx
// Agent-specific dashboard:
// - Wallet balance card (large, prominent)
// - Vouchers generated today
// - Commission earned this month
// - Quick generate button
// - Recent sales list
// - Fund wallet button
```

**`src/pages/agents/AgentWalletPage.tsx`**
```tsx
// Wallet management:
// - Current balance (large display)
// - Fund wallet button → Paystack payment
// - Transaction history table
// - Credit account info (if applicable)
// - Commission summary
```

**`src/hooks/useAgent.ts`** — React Query hooks for agent operations.

### Verify
```bash
npm run dev
# Navigate to /agent/login — should show agent login
# Login → should show agent dashboard
# Navigate to /agent/wallet — should show wallet page
```

---

## Prompt 9: Agent Voucher Generation & Sales

### What to Build
Agent voucher generation (wallet-funded), sales tracking, commission reports.

### API Endpoints to Consume
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/agent/generate/` | POST | Generate voucher from wallet |
| `/api/v1/agent/vouchers/` | GET | Agent's voucher history |
| `/api/v1/agent/vouchers/:id/sell/` | POST | Mark voucher as sold |

### Files to Create

**`src/pages/agents/AgentGeneratePage.tsx`**
```tsx
// Simplified generation for agents:
// - Plan selector (only active plans)
// - Wallet balance display (shows if sufficient)
// - Quantity selector
// - Cost preview (shows wallet deduction)
// - Generate button (disabled if insufficient balance)
// - Success: shows voucher credentials for sharing
```

**`src/components/agents/VoucherShareCard.tsx`**
```tsx
// Shareable voucher card:
// - Copy username/password buttons
// - WhatsApp share button
// - SMS share button
// - QR code for easy scanning
// - Voucher expiry timer
```

### Verify
```bash
npm run dev
# Navigate to /agent/generate
# Should show plan selection and wallet balance
# Generate voucher → should deduct from wallet
# Should show shareable voucher card
```

---

## Prompt 10: Payment & Billing Module

### What to Build
Customer-facing payment flow, Paystack integration, payment callback handling, transaction history.

### API Endpoints to Consume
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/buy/` | POST | Initialize voucher purchase |
| `/api/v1/payments/callback/` | GET | Payment callback (Paystack redirect) |
| `/api/v1/payments/transactions/` | GET | Transaction history |

### Files to Create

**`src/pages/payments/BuyVoucherPage.tsx`**
```tsx
// Public voucher purchase page:
// - Plan selection (cards with pricing)
// - Customer info form (name, email, phone)
// - Payment summary
// - Paystack payment button (inline or redirect)
// - Loading state during payment
```

**`src/pages/payments/PaymentCallbackPage.tsx`**
```tsx
// Payment callback handler:
// - Reads Paystack reference from URL
// - Calls verification endpoint
// - Shows success/failure state
// - Displays voucher credentials on success
// - Download/print voucher options
```

**`src/pages/payments/TransactionHistoryPage.tsx`**
```tsx
// Transaction list:
// - Table with: Reference, Amount, Status, Voucher, Date
// - Filter by status, date range
// - Export to CSV
```

### Verify
```bash
npm run dev
# Navigate to /buy — should show purchase flow
# Complete payment → should redirect to callback
# Callback → should show voucher credentials
```

---

## Prompt 11: Subscription & Pricing Page

### What to Build
Pricing page, subscription management, billing history, Paystack subscription payments.

### API Endpoints to Consume
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/pricing/` | GET | Available subscription plans |
| `/api/v1/subscriptions/` | GET | Current subscription |
| `/api/v1/billing/` | GET | Billing history |

### Files to Create

**`src/pages/subscriptions/PricingPage.tsx`**
```tsx
// Pricing comparison page:
// - Plan cards (Free Trial, Starter, Professional, Enterprise)
// - Feature comparison table
// - Current plan indicator
// - Upgrade/Downgrade buttons
// - Paystack payment integration
```

**`src/pages/subscriptions/BillingPage.tsx`**
```tsx
// Billing management:
// - Current plan info
// - Next billing date
// - Payment method
// - Billing history table
// - Cancel subscription option
```

### Verify
```bash
npm run dev
# Navigate to /pricing — should show plan cards
# Click upgrade — should init Paystack payment
```

---

## Prompt 12: Platform Admin Panel

### What to Build
Platform-wide admin dashboard: tenant management, router overview, reconciliation, system health.

### API Endpoints to Consume
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/platform/` | GET | Platform stats |
| `/api/v1/platform/tenants/` | GET | All tenants |
| `/api/v1/platform/routers/` | GET | All routers across tenants |
| `/api/v1/platform/reconciliation/` | GET | Financial reconciliation |

### Files to Create

**`src/pages/platform/PlatformDashboardPage.tsx`**
```tsx
// Platform-wide stats:
// - Total tenants, active tenants
// - Total revenue across all tenants
// - Total vouchers generated
// - System health indicators
// - Revenue by tenant chart
```

**`src/pages/platform/TenantsPage.tsx`**
```tsx
// Tenant management:
// - Tenant list with search/filter
// - Tenant detail modal (expand row)
// - Actions: Activate, Suspend, View Details
// - Subscription status per tenant
```

**`src/pages/platform/ReconciliationPage.tsx`**
```tsx
// Financial reconciliation:
// - Revenue vs. Paystack settlements
// - Discrepancy detection
// - Manual adjustment tools
// - Export reports
```

### Verify
```bash
npm run dev
# Navigate to /platform (owner role only)
# Should show platform stats
# Click tenants → should list all tenants
```

---

## Prompt 13: WhatsApp Management & Orders

### What to Build
WhatsApp order monitoring, conversation tracking, configuration management.

### API Endpoints to Consume
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/whatsapp/orders/` | GET | WhatsApp orders |
| `/api/v1/whatsapp/conversations/` | GET | Active conversations |
| `/api/v1/whatsapp/config/` | GET/PUT | WhatsApp API configuration |

### Files to Create

**`src/pages/whatsapp/WhatsAppOrdersPage.tsx`**
```tsx
// WhatsApp order monitoring:
// - Orders table: Customer, Plan, Amount, Status, Date
// - Status filters: pending, fulfilled, failed
// - Order detail drawer (payment, fulfilment, delivery status)
// - Retry failed deliveries
```

**`src/pages/whatsapp/WhatsAppConfigPage.tsx`**
```tsx
// WhatsApp API configuration:
// - API credentials form (phone number ID, access token)
// - Webhook URL display (for copy)
// - Test message button
// - Route token management
```

### Verify
```bash
npm run dev
# Navigate to /whatsapp/orders — should show order list
# Navigate to /whatsapp/config — should show config form
```

---

## Prompt 14: MAC Device (IoT) Management

### What to Build
IoT device registration, MAC-based authentication management, device listing.

### API Endpoints to Consume
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/iot-devices/` | GET | List IoT devices |
| `/api/v1/iot-devices/add/` | POST | Register new device |
| `/api/v1/iot-devices/:id/` | GET/PUT/DELETE | Device CRUD |

### Files to Create

**`src/pages/iot/IoTDeviceListPage.tsx`**
```tsx
// Device list:
// - Table: MAC Address, Device Name, Plan, Status, Expires
// - Search by MAC/device name
// - Actions: Edit, Disable, Remove
```

**`src/pages/iot/IoTDeviceAddPage.tsx`**
```tsx
// Device registration form:
// - MAC address input (with normalization)
// - Device name
// - Plan selection
// - Expiry date
// - Submit → creates MAC device entry
```

### Verify
```bash
npm run dev
# Navigate to /iot-devices — should show device list
# Click Add — should show registration form
```

---

## Prompt 15: Live Users, Debug & Settings

### What to Build
Real-time connected users monitor, debug information page, tenant settings, profile management.

### API Endpoints to Consume
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/dashboard/live-users/` | GET | Current RADIUS sessions |
| `/api/v1/debug/` | GET | System debug info |
| `/api/v1/tenants/:id/settings/` | GET/PUT | Tenant settings |
| `/api/v1/auth/profile/` | GET/PUT | User profile |

### Files to Create

**`src/pages/dashboard/LiveUsersPage.tsx`**
```tsx
// Real-time user monitor:
// - Table: Username, IP, Router, Session Time, Data Usage
// - Auto-refresh every 30 seconds
// - Disconnect button per user
// - Filter by router
// - Total online count
```

**`src/pages/settings/TenantSettingsPage.tsx`**
```tsx
// Tenant settings:
// - Business info (name, phone, email, address)
// - Paystack keys (masked, with reveal toggle)
// - Agent commission settings
// - Voucher prefix settings
// - WhatsApp configuration link
```

**`src/pages/settings/ProfilePage.tsx`**
```tsx
// User profile:
// - Name, email, username
// - Change password form
// - Two-factor authentication (if enabled)
```

### Verify
```bash
npm run dev
# Navigate to /dashboard/live-users — should show connected users
# Navigate to /settings — should show tenant settings
# Navigate to /profile — should show user profile
```

---

## Final Integration Checklist

After completing all 15 prompts, verify:

```bash
# TypeScript compilation
npx tsc --noEmit

# Linting
npm run lint

# Build for production
npm run build

# Run dev server
npm run dev
```

### Route Map
| Path | Component | Role |
|------|-----------|------|
| `/login` | LoginPage | Public |
| `/register` | RegisterPage | Public |
| `/password-reset` | PasswordResetPage | Public |
| `/dashboard` | DashboardPage | Owner/Manager/Staff |
| `/dashboard/live-users` | LiveUsersPage | Owner/Manager |
| `/vouchers` | VoucherListPage | Owner/Manager/Staff |
| `/vouchers/generate` | VoucherGeneratePage | Owner/Manager |
| `/vouchers/:id` | VoucherDetailPage | Owner/Manager/Staff |
| `/vouchers/:id/print` | VoucherPrintPage | Owner/Manager |
| `/routers` | RouterListPage | Owner/Manager |
| `/routers/create` | RouterCreatePage | Owner |
| `/routers/:id` | RouterDetailPage | Owner/Manager |
| `/routers/:id/deployment` | RouterDeploymentPage | Owner |
| `/agent/login` | AgentLoginPage | Agent |
| `/agent/dashboard` | AgentDashboardPage | Agent |
| `/agent/generate` | AgentGeneratePage | Agent |
| `/agent/wallet` | AgentWalletPage | Agent |
| `/buy` | BuyVoucherPage | Public |
| `/payments/callback` | PaymentCallbackPage | Public |
| `/pricing` | PricingPage | Public |
| `/billing` | BillingPage | Owner |
| `/platform` | PlatformDashboardPage | Platform Admin |
| `/platform/tenants` | TenantsPage | Platform Admin |
| `/platform/routers` | PlatformRoutersPage | Platform Admin |
| `/whatsapp/orders` | WhatsAppOrdersPage | Owner/Manager |
| `/iot-devices` | IoTDeviceListPage | Owner/Manager |
| `/settings` | TenantSettingsPage | Owner |
| `/profile` | ProfilePage | All |
