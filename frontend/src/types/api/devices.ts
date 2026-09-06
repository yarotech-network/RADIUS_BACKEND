import type { IsoDateTime, PageParams } from './common';

export interface MacDevice {
  id: number;
  /** Normalised to XX:XX:XX:XX:XX:XX by the server. */
  mac_address: string;
  device_name: string;
  plan: number;
  plan_name: string;
  tenant: number;
  is_active: boolean;
  expires_at: IsoDateTime;
  created_at: IsoDateTime;
}

export interface MacDeviceWrite {
  mac_address: string;
  device_name: string;
  plan: number;
  is_active?: boolean;
  expires_at: IsoDateTime;
}

export interface DeviceListParams extends PageParams {
  is_active?: boolean;
  plan?: number;
}

/** `access_token_encrypted` is write-only. One route per tenant. */
export interface WhatsAppRoute {
  id: number;
  tenant: number;
  phone_number_id: string;
  is_active: boolean;
  created_at: IsoDateTime;
}

export interface WhatsAppRouteWrite {
  phone_number_id: string;
  access_token_encrypted?: string;
  is_active?: boolean;
}
