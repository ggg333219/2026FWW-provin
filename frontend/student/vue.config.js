const { defineConfig } = require('@vue/cli-service')
module.exports = defineConfig({
  transpileDependencies: true,
  devServer: {
    host: '0.0.0.0',
    port: 8080,
  }
  ,
  chainWebpack: (config) => {
    // Prevent copy-webpack-plugin from emitting public/index.html (HtmlWebpackPlugin owns it).
    config.plugin('copy').tap((args) => {
      const options = args && args[0] ? args[0] : {}
      const patterns = Array.isArray(options) ? options : (options.patterns || [])

      for (const pattern of patterns) {
        if (!pattern || typeof pattern !== 'object') continue
        pattern.globOptions = pattern.globOptions || {}
        const ignore = pattern.globOptions.ignore || []
        pattern.globOptions.ignore = Array.from(new Set([...(Array.isArray(ignore) ? ignore : [ignore]), '**/index.html']))
      }

      if (Array.isArray(options)) {
        return [patterns]
      }
      return [{ ...options, patterns }]
    })
  }
})
