/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 生产部署时可切换为静态导出（output: 'export'）随 Rust 服务分发
};

export default nextConfig;
