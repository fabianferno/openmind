// pm2 process config for the openmind backend.
//   pm2 start ecosystem.config.js --only openmind-api   # API only
//   pm2 start ecosystem.config.js                        # API + worker
// `cwd` resolves to this file's directory, so it works wherever you clone the repo.
module.exports = {
  apps: [
    {
      name: "openmind-api",
      cwd: __dirname,
      script: ".venv/bin/uvicorn",
      args: "agent.api.server:app --host 0.0.0.0 --port 8000",
      interpreter: "none", // run the venv entrypoint directly, not via node
      autorestart: true,
      max_restarts: 10,
      env: { PORT: "8000" },
    },
    {
      // Autonomous agent loop (mode controlled by AGENT_MODE in .env).
      // Start only when you actually want it cycling.
      name: "openmind-worker",
      cwd: __dirname,
      script: ".venv/bin/python",
      args: "-m agent loop",
      interpreter: "none",
      autorestart: true,
    },
  ],
};
