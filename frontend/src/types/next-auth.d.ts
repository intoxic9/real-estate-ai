import "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  interface Session {
    user?: {
      name?: string | null;
      email?: string | null;
      role?: "admin" | "agent" | "viewer";
    };
  }

  interface User {
    role?: "admin" | "agent" | "viewer";
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    role?: "admin" | "agent" | "viewer";
    name?: string | null;
  }
}

