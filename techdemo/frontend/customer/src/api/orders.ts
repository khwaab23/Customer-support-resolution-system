import { apiRequest } from "./client";

export type CustomerOrder = {
  order_id: string;
  ordered_at: string;
  status: string;
  currency: string;
  total_minor: number;
};

type CustomerOrderListResponse = {
  orders: CustomerOrder[];
};

function validLimit(limit: number): number {
  if (!Number.isInteger(limit) || limit < 1 || limit > 50) {
    throw new Error("Order limit must be an integer between 1 and 50.");
  }
  return limit;
}

export function getCustomerOrders(limit = 10): Promise<CustomerOrderListResponse> {
  const query = new URLSearchParams({ limit: String(validLimit(limit)) });
  return apiRequest<CustomerOrderListResponse>(`/v1/customer/orders?${query}`);
}

export function getCustomerOrder(orderId: string): Promise<CustomerOrder> {
  return apiRequest<CustomerOrder>(
    `/v1/customer/orders/${encodeURIComponent(orderId)}`,
  );
}
