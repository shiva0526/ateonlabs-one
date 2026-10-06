'use server';

import { cookies } from 'next/headers';
import bcrypt from 'bcryptjs';
import { SignJWT } from 'jose';
import nodemailer from 'nodemailer';
import { prisma } from '@/lib/prisma';
import { randomBytes } from 'crypto';
import { getRoleConfig, ROLES, rankOf } from '@/data/roles';
import { requireSession, logAudit } from '@/lib/auth';
const secret = new TextEncoder().encode(process.env.NEXTAUTH_SECRET || 'dev-secret-key-ateon-one-2024-local');

/** Module list for a role, preferring the DB-defined role over the built-in one. */
async function getModulesForRole(roleKey: string): Promise<string[]> {
  try {
    const row = await prisma.role.findUnique({ where: { key: roleKey } });
    if (row?.modules) {
      const parsed = JSON.parse(row.modules);
      if (Array.isArray(parsed)) return parsed.filter((m: unknown) => typeof m === 'string');
    }
  } catch {
    // Role table not ready yet — fall through to the built-in set.
  }
  return getRoleConfig(roleKey).modules;
}

/**
 * Mail transport, built per-call so a missing SMTP_HOST is reported clearly
 * instead of nodemailer silently defaulting to localhost (which surfaces as a
 * baffling `ECONNREFUSED ::1:465`).
 */
function getTransporter() {
  const host = process.env.SMTP_HOST;
  const user = process.env.SMTP_USER;
  const pass = process.env.SMTP_PASSWORD;
  if (!host || !user || !pass) {
    throw new Error(
      'Email is not configured on this server. Set SMTP_HOST, SMTP_PORT, SMTP_USER and SMTP_PASSWORD.'
    );
  }
  const port = Number(process.env.SMTP_PORT) || 465;
  return nodemailer.createTransport({
    host,
    port,
    secure: port === 465,
    auth: { user, pass },
  });
}

const FASTAPI_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

export interface LoginActionResult {
  success?: boolean;
  requireOtp?: boolean;
  emailSent?: boolean;
  error?: string | null;
  user?: {
    id: string;
    name: string;
    role: string;
    email: string;
  };
}

export async function login(email: string, password: string, otpCode?: string): Promise<LoginActionResult> {
  const cleanEmail = email.trim().toLowerCase();

  // Try FastAPI backend first if available
  try {
    const res = await fetch(`${FASTAPI_URL}/api/v1/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        email: cleanEmail,
        password,
        otp_code: otpCode || null,
      }),
      cache: 'no-store',
    });

    const data = await res.json();

    if (res.ok && data.success && data.token) {
      const cookieStore = await cookies();
      cookieStore.set('ateon_session', data.token, {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax',
        path: '/',
        maxAge: 24 * 60 * 60,
      });

      return {
        success: true,
        user: {
          id: data.user.id,
          name: data.user.name,
          role: data.user.role,
          email: data.user.email,
        },
      };
    }

    if (res.ok && data.require_otp) {
      return {
        requireOtp: true,
        emailSent: Boolean(data.email_sent),
      };
    }

    if (!res.ok && data.detail && !data.detail.includes('connect')) {
      const errMsg = typeof data.detail === 'string' ? data.detail : (data.detail?.[0]?.msg || data.message || 'Invalid credentials');
      return { error: errMsg };
    }
  } catch {
    // Backend unreachable (e.g., in Hostinger production without standalone backend) -> fall through to database
  }

  // Fallback to direct database authentication (Hostinger production)
  try {
    const user = await prisma.user.findUnique({ where: { email: cleanEmail } });
    if (!user) return { error: 'Invalid credentials' };

    const valid = await bcrypt.compare(password, user.passwordHash);
    if (!valid) return { error: 'Invalid credentials' };

    const modules = await getModulesForRole(user.role);
    const jwt = await new SignJWT({ id: user.id, email: user.email, role: user.role, modules })
      .setProtectedHeader({ alg: 'HS256' })
      .setIssuedAt()
      .setExpirationTime('24h')
      .sign(secret);

    try {
      await prisma.session.create({
        data: {
          userId: user.id,
          token: jwt,
          expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000),
        },
      });
    } catch (sErr) {
      console.warn('Session write non-critical error:', sErr);
    }

    const cookieStore = await cookies();
    cookieStore.set('ateon_session', jwt, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      path: '/',
      maxAge: 24 * 60 * 60,
    });

    return {
      success: true,
      user: {
        id: user.id,
        name: user.name,
        role: user.role,
        email: user.email,
      },
    };
  } catch (dbErr: any) {
    return { error: dbErr?.message || 'Authentication failed' };
  }
}

export async function logout() {
  const cookieStore = await cookies();
  const token = cookieStore.get('ateon_session')?.value;

  if (token) {
    try {
      await fetch(`${FASTAPI_URL}/api/v1/auth/logout`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        cache: 'no-store',
      });
    } catch {
      // Ignore network errors on logout
    }
  }

  cookieStore.delete('ateon_session');
  return { success: true };
}

export async function revokeAllSessions() {
  const user = await requireSession();
  const cookieStore = await cookies();
  const token = cookieStore.get('ateon_session')?.value;

  await prisma.session.deleteMany(
    token ? { userId: user.id, NOT: { token } } : { userId: user.id }
  );
  return { success: true };
}

export async function changePassword(current: string, newPass: string) {
  const sessionUser = await requireSession();
  if (!newPass || newPass.length < 8) {
    return { error: 'New password must be at least 8 characters' };
  }

  const dbUser = await prisma.user.findUnique({ where: { id: sessionUser.id } });
  if (!dbUser) return { error: 'Unauthorized' };

  const valid = await bcrypt.compare(current, dbUser.passwordHash);
  if (!valid) return { error: 'Current password incorrect' };

  const hash = await bcrypt.hash(newPass, 10);
  await prisma.user.update({
    where: { id: dbUser.id },
    data: { passwordHash: hash }
  });

  // A password change should invalidate everything except the current session.
  const cookieStore = await cookies();
  const token = cookieStore.get('ateon_session')?.value;
  await prisma.session.deleteMany(
    token ? { userId: dbUser.id, NOT: { token } } : { userId: dbUser.id }
  );

  return { success: true };
}

export async function toggle2FA(enabled: boolean) {
  const user = await requireSession();
  await prisma.user.update({
    where: { id: user.id },
    data: { twoFactorEnabled: enabled }
  });
  return { success: true };
}

export async function generateInviteEmail(email: string, role: string, name: string, phone: string = '') {
  const cookieStore = await cookies();
  const token = cookieStore.get('ateon_session')?.value;

  if (!token) {
    return { error: 'Unauthorized' };
  }

  try {
    const res = await fetch(`${FASTAPI_URL}/api/v1/auth/invite`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        'Cookie': `ateon_session=${token}`,
      },
      body: JSON.stringify({ email, name, role, phone }),
      cache: 'no-store',
    });

    const data = await res.json();

    if (data.error) {
      return { error: data.error };
    }

    return { success: true };
  } catch (err: any) {
    return { error: `Failed to send invite: ${err.message}` };
  }
}

export async function getMe() {
  const cookieStore = await cookies();
  const token = cookieStore.get('ateon_session')?.value;
  if (!token) return null;

  try {
    const res = await fetch(`${FASTAPI_URL}/api/v1/auth/me`, {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
      cache: 'no-store',
    });

    if (res.ok) {
      const data = await res.json();
      return {
        id: data.id,
        name: data.name,
        email: data.email,
        role: data.role,
        department: data.department || '',
        designation: data.designation || '',
        avatar: data.avatar || '',
        twoFactorEnabled: data.two_factor_enabled || false,
      };
    }
  } catch {
    // Fallback if FastAPI is temporarily unreachable
  }

  try {
    const { jwtVerify } = await import('jose');
    const { payload } = await jwtVerify(token, secret);
    if (payload && payload.id) {
      return {
        id: String(payload.id),
        name: (payload.name as string) || (payload.email as string)?.split('@')[0] || 'User',
        email: (payload.email as string) || '',
        role: (payload.role as string) || 'employee',
        department: (payload.department as string) || '',
        designation: (payload.designation as string) || '',
        avatar: (payload.avatar as string) || '',
        twoFactorEnabled: false,
      };
    }
  } catch {
    // JWT verification failed
  }

  try {
    const session = await prisma.session.findUnique({
      where: { token },
      include: { user: {
        select: {
          id: true, name: true, email: true, role: true, department: true, designation: true, avatar: true, twoFactorEnabled: true
        }
      } }
    });
    if (!session) return null;
    if (new Date(session.expiresAt) < new Date()) return null;
    return session.user;
  } catch {
    return null;
  }
}

export async function getUserMetrics() {
  await requireSession();
  const cookieStore = await cookies();
  const token = cookieStore.get('ateon_session')?.value;
  if (token) {
    try {
      const res = await fetch(`${FASTAPI_URL}/api/v1/auth/users`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Cookie': `ateon_session=${token}`,
        },
        cache: 'no-store',
      });
      if (res.ok) {
        const users = await res.json();
        const depts = new Set(users.map((u: any) => u.department).filter(Boolean));
        return { usersCount: users.length, deptsCount: depts.size || 1 };
      }
    } catch {
      // Fallback
    }
  }

  const [usersCount, deptsCount] = await Promise.all([
    prisma.user.count(),
    prisma.department.count()
  ]);

  return { usersCount, deptsCount };
}

/**
 * Directory of colleagues. Requires a session — these are real names, emails
 * and roles, and this action is reachable as an HTTP endpoint.
 */
export async function listUsers() {
  await requireSession();
  const cookieStore = await cookies();
  const token = cookieStore.get('ateon_session')?.value;
  if (token) {
    try {
      const res = await fetch(`${FASTAPI_URL}/api/v1/auth/users`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Cookie': `ateon_session=${token}`,
        },
        cache: 'no-store',
      });
      if (res.ok) {
        return await res.json();
      }
    } catch {
      // Fallback
    }
  }

  return prisma.user.findMany({
    select: { id: true, name: true, email: true, role: true, department: true, designation: true },
    orderBy: { name: 'asc' }
  });
}
