module.exports = {
  run: [
    {
      method: "shell.run",
      params: {
        venv: "../.venv",
        path: "..",
        message: [
          "uv pip install -r webapp/requirements.txt",
        ],
      },
    },
    {
      method: "shell.run",
      params: {
        path: "../web",
        message: ["npm install", "npm run build"],
      },
    },
    {
      method: "shell.run",
      params: {
        path: "../video_renderer",
        message: "npm install",
      },
    },
    {
      method: "shell.run",
      params: {
        path: "..",
        message: "python scripts/prepare_env.py --check",
      },
    },
  ],
};
