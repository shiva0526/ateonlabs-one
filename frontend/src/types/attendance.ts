/**
 * Attendance type definitions mapping between FastAPI backend and Next.js frontend.
 */

// ─── FastAPI Raw Response Schemas (snake_case) ───

export interface FastAPIAttendanceStatusResponse {
  clocked_in: boolean;
  on_break: boolean;
  check_in_time: string | null;
  elapsed_seconds: number;
  break_seconds: number;
  status: string;
  formatted_duration: string;
}

export interface FastAPIAttendanceRecordResponse {
  id: string;
  employee_id: string;
  date: string;
  status: string;
  check_in: string | null;
  check_out: string | null;
  on_break_since: string | null;
  break_seconds: number;
  elapsed_seconds: number;
  created_at: string;
  updated_at: string;
}

export interface FastAPIAttendanceHistoryItem {
  date: string;
  check_in: string | null;
  check_out: string | null;
  elapsed_seconds: number;
  break_seconds: number;
  status: string;
}

export interface FastAPIAttendanceHistoryResponse {
  items: FastAPIAttendanceHistoryItem[];
  total_count: number;
}

// ─── FastAPI Request Payloads ───

export interface ClockInPayload {
  notes?: string;
  lat?: number;
  lng?: number;
}

export interface ClockOutPayload {
  notes?: string;
}

export interface BreakStartPayload {
  notes?: string;
}

export interface BreakEndPayload {
  notes?: string;
}

export interface AttendanceTogglePayload {
  action: 'clock_in' | 'clock_out' | 'break_start' | 'break_end';
}

export interface AttendanceOverridePayload {
  employee_id: string;
  date: string; // YYYY-MM-DD
  status: 'present' | 'absent' | 'leave' | 'wfh' | 'holiday';
  check_in?: string;
  check_out?: string;
}

// ─── Frontend UI Domain Types (camelCase) ───

export interface AttendanceStatus {
  clockedIn: boolean;
  onBreak: boolean;
  elapsedSeconds: number;
  breakSeconds: number;
  checkInTime?: string | null;
  status?: string;
  formattedDuration?: string;
}

export interface AttendanceHistoryRecord {
  date: string; // ISO string matching "YYYY-MM-DDT00:00:00.000Z"
  checkIn: string | null;
  checkOut: string | null;
  elapsedSeconds: number;
  breakSeconds: number;
  status: string;
}

export interface AttendanceRecord {
  id: string;
  employeeId: string;
  date: string;
  status: string;
  checkIn: string | null;
  checkOut: string | null;
  onBreakSince: string | null;
  breakSeconds: number;
  elapsedSeconds: number;
  createdAt: string;
  updatedAt: string;
}
