// Chat log front-end. `window.render` is driven from Python (the ChatWidget).
// The block list is diffed by index and html so only the changed block is
// re-rendered, which keeps streaming cheap (KaTeX runs on one block per tick).

(function () {
  "use strict";

  var container = document.getElementById("conversation");
  var bridge = null;

  if (typeof QWebChannel !== "undefined" && typeof qt !== "undefined") {
    new QWebChannel(qt.webChannelTransport, function (channel) {
      bridge = channel.objects.kuestionBridge;
    });
  }

  function renderMath(root) {
    root.querySelectorAll("[data-katex-inline]").forEach(function (el) {
      renderFormula(el, false);
    });
    root.querySelectorAll("[data-katex-display]").forEach(function (el) {
      renderFormula(el, true);
    });
  }

  function renderFormula(el, displayMode) {
    var latex = el.textContent;
    try {
      katex.render(latex, el, {
        displayMode: displayMode,
        throwOnError: false,
        strict: false,
      });
    } catch (err) {
      el.classList.add("math-error");
      el.textContent = latex;
    }
  }

  function applyPalette(vars) {
    var root = document.documentElement;
    Object.keys(vars).forEach(function (key) {
      if (key === "color-scheme") {
        root.style.colorScheme = vars[key];
        root.setAttribute("data-theme", vars[key]);
      } else {
        root.style.setProperty(key, vars[key]);
      }
    });
  }

  function ensureBlock(index, role) {
    var el = container.children[index];
    if (!el) {
      el = document.createElement("div");
      el.innerHTML = '<div class="role"></div><div class="content"></div>';
      container.appendChild(el);
    }
    el.className = "block " + role;
    el.querySelector(".role").textContent = role === "user" ? "You" : "Assistant";
    return el.querySelector(".content");
  }

  function render(payload) {
    var blocks = payload.blocks || [];
    while (container.children.length > blocks.length) {
      container.removeChild(container.lastElementChild);
    }
    blocks.forEach(function (block, index) {
      var content = ensureBlock(index, block.role);
      if (content.dataset.html !== block.html) {
        content.innerHTML = block.html;
        content.dataset.html = block.html;
        renderMath(content);
      }
    });
    scrollToBottom();
  }

  function scrollToBottom() {
    document.documentElement.scrollTop = document.documentElement.scrollHeight;
    document.body.scrollTop = document.body.scrollHeight;
  }

  function copyCode(button) {
    var block = button.closest(".code-block");
    var code = block ? block.querySelector("code") : null;
    if (!code) {
      return;
    }
    var text = code.textContent;
    if (bridge) {
      bridge.copy(text);
    } else {
      legacyCopy(text);
    }
    button.textContent = "Copied!";
    window.setTimeout(function () {
      button.textContent = "Copy";
    }, 1200);
  }

  function legacyCopy(text) {
    var textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    try {
      document.execCommand("copy");
    } catch (err) {
      /* no clipboard available */
    }
    document.body.removeChild(textarea);
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest(".copy-btn");
    if (button) {
      copyCode(button);
    }
  });

  window.render = render;
  window.applyPalette = applyPalette;
})();
