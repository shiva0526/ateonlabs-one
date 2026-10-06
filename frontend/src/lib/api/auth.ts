/**
 * Auth API Service Layer.
 * Connects frontend to the FastAPI Auth endpoints.
 */

import { apiClient } from '@/lib/apiClient';

export interface UserProfile {
  id: string;
  name: string;
  email: string;
  role: string;
  department: string;
  designation: string;
  avatar: string;
  twoFactorEnabled?: boolean;
}

export interface LoginApiResponse {
  success: boolean;
  token?: string;
  user?: {
    id: string;
    name: string;
    email: string;
    role: string;
    department?: string;
    designation?: string;
    avatar?: string;
    two_factor_enabled?: boolean;
  };
  require_otp?: boolean;
  error?: string;
}

export async function loginApi(email: string, password: string, otpCode?: string): Promise<LoginApiResponse> {
  return apiClient.post<LoginApiResponse>('/api/v1/auth/login', {
    email,
    password,
    otp_code: otpCode || null,
  });
}

export async function getMeApi(): Promise<UserProfile | null> {
  try {
    const res = await apiClient.get<any>('/api/v1/auth/me');
    if (!res || !res.id) return null;
    return {
      id: res.id,
      name: res.name,
      email: res.email,
      role: res.role,
      department: res.department || '',
      designation: res.designation || '',
      avatar: res.avatar || '',
      twoFactorEnabled: res.two_factor_enabled || false,
    };
  } catch {
    return null;
  }
}

export async function logoutApi(): Promise<{ success: boolean }> {
  try {
    return await apiClient.post<{ success: boolean }>('/api/v1/auth/logout', {});
  } catch {
    return { success: true };
  }
}
