import { withAuth } from "next-auth/middleware";

const authSecret = process.env.NEXTAUTH_SECRET ?? "dev-auth-secret";

export default withAuth({
  callbacks: {
    authorized: ({ token }) => !!token,
  },
  pages: {
    signIn: "/login",
  },
  secret: authSecret,
});

export const config = {
  matcher: ["/dashboard/:path*", "/analytics/:path*", "/signals/:path*", "/settings/:path*"],
};

