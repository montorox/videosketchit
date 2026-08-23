module.exports = {
  daemon: true,
  run: [
    {
      method: "shell.run",
      params: {
        venv: "../.venv",
        path: "..",
        message: "python -m uvicorn webapp.server:app --host 127.0.0.1 --port 18775",
        on: [{
          event: "/(http:\\/\\/[0-9.:]+)/",
          done: true,
        }],
      },
    },
    {
      method: "shell.run",
      params: {
        path: "../web",
        message: "npm run start",
        on: [{
          event: "/(http:\\/\\/[0-9.:]+)/",
          done: true,
        }],
      },
    },
    {
      method: "local.set",
      params: {
        url: "{{input.event[1]}}",
      },
    },
  ],
};
