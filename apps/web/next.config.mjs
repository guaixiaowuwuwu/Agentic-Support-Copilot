/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  transpilePackages: ["@support-copilot/shared"]
};

export default nextConfig;
