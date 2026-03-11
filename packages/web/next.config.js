/** @type {import('next').NextConfig} */
const nextConfig = {
  // NOT: standalone kullanmiyoruz — rewrites ile API proxy lazim
  // Server-side rewrite: tarayicidan gelen /api/* isteklerini FastAPI'ye yonlendir
  async rewrites() {
    const apiUrl = process.env.API_BACKEND_URL || "http://localhost:8470";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
