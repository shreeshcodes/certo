/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    const api = process.env.CERTO_API_URL || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
};
export default nextConfig;
