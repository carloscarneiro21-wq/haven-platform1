const path = require("path");

module.exports = {
  webpack: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
    configure: (webpackConfig) => {
      // Remove ForkTsCheckerWebpackPlugin (evita o erro AJV/keywords no build)
      webpackConfig.plugins = (webpackConfig.plugins || []).filter(
        (p) => p && p.constructor && p.constructor.name !== "ForkTsCheckerWebpackPlugin"
      );
      return webpackConfig;
    },
  },
};