/** Static export: the deployed demo is plain files reading public/data/. */
const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
