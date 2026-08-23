module.exports = {
  version: "5.0",
  title: "CS Board · Codex Edition",
  description: "Create narrated whiteboard and infographic videos with your ChatGPT/Codex subscription.",
  icon: "../web/public/brand-mark.png",
  pre: [{
    title: "ChatGPT or Codex",
    description: "Install ChatGPT desktop or Codex CLI, then sign in with ChatGPT.",
    href: "https://chatgpt.com/",
  }],
  menu: async (kernel, info) => {
    const installed = info.exists("../.venv") && info.exists("../web/node_modules");
    const running = {
      install: info.running("install.js"),
      start: info.running("start.js"),
      update: info.running("update.js"),
      reset: info.running("reset.js"),
    };
    if (running.install) {
      return [{ default: true, icon: "fa-solid fa-plug", text: "Installing", href: "install.js" }];
    }
    if (!installed) {
      return [{ default: true, icon: "fa-solid fa-plug", text: "Install", href: "install.js" }];
    }
    if (running.start) {
      const local = info.local("start.js");
      if (local && local.url) {
        return [
          { default: true, icon: "fa-solid fa-rocket", text: "Open Codex Edition", href: local.url },
          { icon: "fa-solid fa-terminal", text: "Terminal", href: "start.js" },
        ];
      }
      return [{ default: true, icon: "fa-solid fa-terminal", text: "Starting", href: "start.js" }];
    }
    if (running.update) {
      return [{ default: true, icon: "fa-solid fa-terminal", text: "Updating", href: "update.js" }];
    }
    if (running.reset) {
      return [{ default: true, icon: "fa-solid fa-terminal", text: "Resetting dependencies", href: "reset.js" }];
    }
    return [
      { default: true, icon: "fa-solid fa-power-off", text: "Start", href: "start.js" },
      { icon: "fa-solid fa-rotate", text: "Update dependencies", href: "update.js" },
      { icon: "fa-solid fa-plug", text: "Reinstall", href: "install.js" },
      { icon: "fa-regular fa-circle-xmark", text: "Reset dependencies", href: "reset.js" },
    ];
  },
};
