import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Routes that require an authenticated session.
const PROTECTED_PREFIXES = [
  "/dashboard",
  "/documents",
  "/analysis",
  "/reviews",
  "/regulatory",
  "/settings",
];

// Auth pages — an already-authenticated user is redirected away from these.
const AUTH_PREFIXES = ["/login", "/register"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  // The auth store mirrors the access token into this cookie so the
  // server-side middleware can read it (localStorage is client-only).
  const token = request.cookies.get("access_token")?.value;

  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
  const isAuthPage = AUTH_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );

  if (isProtected && !token) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (isAuthPage && token) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/documents/:path*",
    "/analysis/:path*",
    "/reviews/:path*",
    "/regulatory/:path*",
    "/settings/:path*",
    "/login",
    "/register",
  ],
};
