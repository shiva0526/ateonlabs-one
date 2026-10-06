/**
 * Attendance API Service Layer.
 * Adapts FastAPI REST endpoints and contracts to the Next.js UI data structures.
 */

import { apiClient } from '@/lib/apiClient';
import type {
  FastAPIAttendanceStatusResponse,
  FastAPIAttendanceRecordResponse,
  FastAPIAttendanceHistoryResponse,
  AttendanceStatus,
  AttendanceRecord,
  AttendanceHistoryRecord,
  ClockInPayload,
  ClockOutPayload,
  BreakStartPayload,
  BreakEndPayload,
  AttendanceOverridePayload,
} from '@/types/attendance';

function mapRecord(res: FastAPIAttendanceRecordResponse): AttendanceRecord {
  return {
    id: res.id,
    employeeId: res.employee_id,
    date: res.date,
    status: res.status,
    checkIn: res.check_in,
    checkOut: res.check_out,
    onBreakSince: res.on_break_since,
    breakSeconds: res.break_seconds,
    elapsedSeconds: res.elapsed_seconds,
    createdAt: res.created_at,
    updatedAt: res.updated_at,
  };
}

/**
 * Fetch current live attendance state for the authenticated employee.
 */
export async function getAttendanceStatus(): Promise<AttendanceStatus> {
  const res = await apiClient.get<FastAPIAttendanceStatusResponse>('/api/v1/attendance/status');
  return {
    clockedIn: res.clocked_in,
    onBreak: res.on_break,
    checkInTime: res.check_in_time,
    elapsedSeconds: res.elapsed_seconds,
    breakSeconds: res.break_seconds,
    status: res.status,
    formattedDuration: res.formatted_duration,
  };
}

/**
 * Clock in for work session.
 */
export async function clockIn(payload?: ClockInPayload): Promise<AttendanceRecord> {
  const res = await apiClient.post<FastAPIAttendanceRecordResponse>('/api/v1/attendance/clock-in', payload || {});
  return mapRecord(res);
}

/**
 * Clock out of work session.
 */
export async function clockOut(payload?: ClockOutPayload): Promise<AttendanceRecord> {
  const res = await apiClient.post<FastAPIAttendanceRecordResponse>('/api/v1/attendance/clock-out', payload || {});
  return mapRecord(res);
}

/**
 * Start break during active work session.
 */
export async function startBreak(payload?: BreakStartPayload): Promise<AttendanceRecord> {
  const res = await apiClient.post<FastAPIAttendanceRecordResponse>('/api/v1/attendance/break/start', payload || {});
  return mapRecord(res);
}

/**
 * End ongoing break.
 */
export async function endBreak(payload?: BreakEndPayload): Promise<AttendanceRecord> {
  const res = await apiClient.post<FastAPIAttendanceRecordResponse>('/api/v1/attendance/break/end', payload || {});
  return mapRecord(res);
}

/**
 * Toggle attendance action compatibility function for WorkspacePage.
 * Maps: 'clock_in' | 'clock_out' | 'break_start' | 'break_end'.
 */
export async function toggleAttendance(
  action: 'clock_in' | 'clock_out' | 'break_start' | 'break_end'
): Promise<{ success: boolean; record: AttendanceRecord }> {
  const res = await apiClient.post<FastAPIAttendanceRecordResponse>('/api/v1/attendance/toggle', { action });
  return {
    success: true,
    record: mapRecord(res),
  };
}

/**
 * Fetch attendance history records for the authenticated employee within date range.
 * Formats date keys to ISO start-of-day strings (e.g. YYYY-MM-DDT00:00:00.000Z)
 * to maintain complete compatibility with the Workspace calendar and weekly widgets.
 */
export async function getAttendanceHistory(
  startDateStr?: string,
  endDateStr?: string
): Promise<AttendanceHistoryRecord[]> {
  const params = new URLSearchParams();

  if (startDateStr) {
    // If ISO string like "2026-09-01T00:00:00.000Z" was passed, extract "2026-09-01"
    const startFormatted = startDateStr.includes('T') ? startDateStr.split('T')[0] : startDateStr;
    params.set('start_date', startFormatted);
  }

  if (endDateStr) {
    const endFormatted = endDateStr.includes('T') ? endDateStr.split('T')[0] : endDateStr;
    params.set('end_date', endFormatted);
  }

  const queryString = params.toString() ? `?${params.toString()}` : '';
  const res = await apiClient.get<FastAPIAttendanceHistoryResponse>(`/api/v1/attendance/history${queryString}`);

  return (res.items || []).map((item) => {
    // Standardize to UTC start-of-day ISO string expected by Workspace calendar lookup:
    // e.g. "2026-09-01T00:00:00.000Z"
    const dateKey = item.date.includes('T') ? item.date : `${item.date}T00:00:00.000Z`;

    return {
      date: dateKey,
      checkIn: item.check_in,
      checkOut: item.check_out,
      elapsedSeconds: item.elapsed_seconds,
      breakSeconds: item.break_seconds,
      status: item.status,
    };
  });
}

/**
 * Admin manual override for employee attendance.
 */
export async function overrideAttendance(payload: AttendanceOverridePayload): Promise<AttendanceRecord> {
  const res = await apiClient.post<FastAPIAttendanceRecordResponse>('/api/v1/attendance/override', payload);
  return mapRecord(res);
}
