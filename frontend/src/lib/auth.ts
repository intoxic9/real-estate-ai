import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";

export type AppUserRole = "admin" | "agent" | "viewer";

const PASSWORD = "admin";

const USERS: Array<{
  id: string;
  email: string;
  name: string;
  role: AppUserRole;
}> = [
  { id: "1", email: "vedant@admin.com", name: "Vedant", role: "admin" },
  { id: "2", email: "vedant@agent.com", name: "Vedant", role: "agent" },
  { id: "3", email: "rashi@admin.com", name: "Rashi", role: "admin" },
  { id: "4", email: "rashi@agent.com", name: "Rashi", role: "agent" },
  { id: "5", email: "abhishek@agent.com", name: "Abhishek", role: "agent" },
  { id: "6", email: "abhishek@admin.com", name: "Abhishek", role: "admin" },
  { id: "7", email: "demo@demo.com", name: "Demo", role: "viewer" },
];

export const authOptions: NextAuthOptions = {
  session: { strategy: "jwt" },
  secret: process.env.NEXTAUTH_SECRET ?? "dev-auth-secret",
  providers: [
    CredentialsProvider({
      name: "Credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const email = credentials?.email?.toString().trim().toLowerCase();
        const password = credentials?.password?.toString().trim();
        if (!email || !password) return null;

        // Hardcoded credential set for now.
        if (password !== PASSWORD) return null;

        const user = USERS.find((u) => u.email === email);
        if (!user) return null;

        return {
          id: user.id,
          email: user.email,
          name: user.name,
          role: user.role,
        } as const;
      },
    }),
  ],
  pages: {
    signIn: "/login",
  },
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.role = (user as any).role;
        token.name = (user as any).name;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.role = token.role as any;
        session.user.name = token.name as any;
      }
      return session;
    },
  },
};

