import { cookies } from 'next/headers';
import { prisma } from '@/lib/prisma';

import { jwtVerify } from 'jose';

export const SESSION_COOKIE = 'ateon_session';

const FASTAPI_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
const secret = new TextEncoder().encode(process.env.NEXTAUTH_SECRET || 'dev-secret-key-ateon-one-2024-local');

/** Roles with elevated (admin-level) access across modules. */
export const ADMIN_ROLES = ['ceo', 'cfo', 'coo', 'cto', 'chro', 'legal', 'admin'];

export type SessionUser = {
  id: string;
  name: string;
  email: string;
  role: string;
  department: string;
  designation: string;
  avatar: string;
};

/**
 * Resolve the current user from the `ateon_session` cookie via FastAPI or JWT.
 * Returns null when unauthenticated / expired.
 */
export async function getSessionUser(): Promise<SessionUser | null> {
  try {
    const cookieStore = await cookies();
    const token = cookieStore.get(SESSION_COOKIE)?.value;
    if (!token) return null;

    // 1. Authenticate against FastAPI backend
    try {
      const res = await fetch(`${FASTAPI_URL}/api/v1/auth/me`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Cookie': `ateon_session=${token}`,
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
        };
      }
    } catch {
      // Backend temporarily unreachable, fall through to JWT
    }

    // 2. Verify JWT signature with shared secret
    try {
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
        };
      }
    } catch {
      // JWT verification failed
    }

    // 3. Fallback: check Prisma session if database is active
    try {
      const session = await prisma.session.findUnique({
        where: { token },
        include: { user: true },
      });
      if (session && session.expiresAt >= new Date()) {
        const { id, name, email, role, department, designation, avatar } = session.user;
        return { id, name, email, role, department, designation, avatar };
      }
    } catch {
      // Database session unavailable
    }

    return null;
  } catch (error) {
    console.warn('[auth] Unable to resolve session:', error instanceof Error ? error.message : error);
    return null;
  }
}

/** Like getSessionUser but throws for use in mutating server actions. */
export async function requireSession(): Promise<SessionUser> {
  const user = await getSessionUser();
  if (!user) throw new Error('Unauthorized');
  return user;
}

export function isAdmin(role: string): boolean {
  return ADMIN_ROLES.includes(role);
}

/** Require one of the given roles (or any admin role when roles omitted). */
export async function requireRole(roles?: string[]): Promise<SessionUser> {
  const user = await requireSession();
  const allowed = roles && roles.length > 0 ? roles : ADMIN_ROLES;
  if (!allowed.includes(user.role)) throw new Error('Forbidden: insufficient role');
  return user;
}

/** Fire-and-forget audit trail entry. Never throws. */
export async function logAudit(
  actor: SessionUser | null,
  action: string,
  entity: string,
  entityId?: string,
  details?: string
): Promise<void> {
  try {
    await prisma.auditLog.create({
      data: {
        actorId: actor?.id ?? null,
        actorName: actor?.name ?? 'system',
        action,
        entity,
        entityId: entityId ?? null,
        details: details ?? null,
      },
    });
  } catch (e) {
    console.error('audit log failed', e);
  }
}
