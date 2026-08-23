module.exports = {
  run: [
    {
      method: "fs.rm",
      params: {
        path: "../.venv",
      },
    },
    {
      method: "fs.rm",
      params: {
        path: "../web/node_modules",
      },
    },
    {
      method: "fs.rm",
      params: {
        path: "../video_renderer/node_modules",
      },
    },
  ],
};
