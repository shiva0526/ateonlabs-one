/**
 * Centralized API Client for FastAPI backend communication.
 * Automatically handles baseURL, headers, credentials (cookies), and error normalization.
 */

export class ApiError extends Error {
  public status: number;
  public data: any;

  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

async function parseResponseBody(response: Response): Promise<any> {
  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    try {
      return await response.json();
    } catch {
      return null;
    }
  }
  try {
    return await response.text();
  } catch {
    return null;
  }
}

function extractErrorMessage(status: number, data: any, statusText: string): string {
  if (typeof data === 'string' && data.trim()) {
    return data;
  }

  if (data && typeof data === 'object') {
    // FastAPI standard error format: { "detail": "message" } or { "detail": [...] }
    if (data.detail) {
      if (typeof data.detail === 'string') {
        return data.detail;
      }
      if (Array.isArray(data.detail)) {
        // Pydantic 422 validation errors
        return data.detail
          .map((err: any) => `${err.loc ? err.loc.join('.') : 'field'}: ${err.msg || 'Invalid'}`)
          .join('; ');
      }
    }
    if (data.message && typeof data.message === 'string') {
      return data.message;
    }
    if (data.error && typeof data.error === 'string') {
      return data.error;
    }
  }

  switch (status) {
    case 400:
      return 'Bad Request';
    case 401:
      return 'Unauthorized: Session expired or invalid';
    case 403:
      return 'Forbidden: You do not have permission to perform this action';
    case 404:
      return 'Resource not found';
    case 409:
      return 'Conflict: Operation cannot be performed due to state conflict';
    case 422:
      return 'Unprocessable Entity: Validation failed';
    case 500:
      return 'Internal Server Error';
    default:
      return statusText || `HTTP error ${status}`;
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = endpoint.startsWith('http://') || endpoint.startsWith('https://')
    ? endpoint
    : `${API_BASE_URL}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;

  const defaultHeaders: Record<string, string> = {};

  if (options.body && typeof options.body === 'string') {
    defaultHeaders['Content-Type'] = 'application/json';
  }

  const mergedHeaders = {
    ...defaultHeaders,
    ...(options.headers as Record<string, string> || {}),
  };

  const config: RequestInit = {
    ...options,
    headers: mergedHeaders,
    // REQUIRED: automatically forwards httpOnly 'ateon_session' cookie across CORS
    credentials: 'include',
  };

  let response: Response;
  try {
    response = await fetch(url, config);
  } catch (networkError: any) {
    throw new ApiError(
      networkError?.message || 'Network error: Failed to connect to FastAPI backend.',
      0,
      networkError
    );
  }

  const responseData = await parseResponseBody(response);

  if (!response.ok) {
    const errorMessage = extractErrorMessage(response.status, responseData, response.statusText);
    throw new ApiError(errorMessage, response.status, responseData);
  }

  return responseData as T;
}

export const apiClient = {
  get<T>(endpoint: string, options?: RequestInit): Promise<T> {
    return request<T>(endpoint, { ...options, method: 'GET' });
  },

  post<T>(endpoint: string, body?: any, options?: RequestInit): Promise<T> {
    return request<T>(endpoint, {
      ...options,
      method: 'POST',
      body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined,
    });
  },

  put<T>(endpoint: string, body?: any, options?: RequestInit): Promise<T> {
    return request<T>(endpoint, {
      ...options,
      method: 'PUT',
      body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined,
    });
  },

  patch<T>(endpoint: string, body?: any, options?: RequestInit): Promise<T> {
    return request<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined,
    });
  },

  delete<T>(endpoint: string, options?: RequestInit): Promise<T> {
    return request<T>(endpoint, { ...options, method: 'DELETE' });
  },
};
