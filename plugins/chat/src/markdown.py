"""Qt-free Markdown + LaTeX rendering for the chat view.

Markdown is parsed with ``markdown-it-py`` (raw HTML is disabled, so model output
cannot inject markup). Inline ``$...$`` / ``\\(...\\)`` and display ``$$...$$`` /
``\\[...\\]`` math spans are emitted as KaTeX placeholder elements carrying the raw
LaTeX as their text: the embedded web view calls ``katex.render`` on each
``[data-katex-inline]`` / ``[data-katex-display]`` node. Fenced code blocks gain a
copy-button wrapper. Remote images are neutralized. Nothing here touches Qt.
"""

from __future__ import annotations

import html as html_module

from markdown_it import MarkdownIt
from markdown_it.common.utils import escapeHtml
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.texmath import texmath_plugin


def _math_rule(*, block: bool):
    tag = "div" if block else "span"
    css_class = "math-display" if block else "math-inline"
    data_attr = "data-katex-display" if block else "data-katex-inline"
    suffix = "\n" if block else ""

    def rule(renderer, tokens, index, options, env) -> str:
        latex = escapeHtml(tokens[index].content)
        return f'<{tag} class="{css_class}" {data_attr}>{latex}</{tag}>{suffix}'

    return rule


def _fence_rule(renderer, tokens, index, options, env) -> str:
    token = tokens[index]
    language = (token.info.strip().split() or [""])[0] if token.info else ""
    class_attr = (
        f' class="language-{html_module.escape(language, quote=True)}"' if language else ""
    )
    return (
        '<div class="code-block">'
        '<button class="copy-btn" type="button">Copy</button>'
        f"<pre><code{class_attr}>{escapeHtml(token.content)}</code></pre>"
        "</div>"
    )


def _image_rule(renderer, tokens, index, options, env) -> str:
    # Never let model output trigger a network fetch: show remote images as text.
    return f"<span>[{escapeHtml(tokens[index].content)}]</span>"


def _build_markdown() -> MarkdownIt:
    markdown = MarkdownIt("commonmark", {"html": False})
    markdown.use(dollarmath_plugin, allow_digits=False)
    markdown.use(texmath_plugin, delimiters="brackets")
    markdown.add_render_rule("math_inline", _math_rule(block=False))
    markdown.add_render_rule("math_block", _math_rule(block=True))
    markdown.add_render_rule("math_block_eqno", _math_rule(block=True))
    markdown.add_render_rule("fence", _fence_rule)
    markdown.add_render_rule("image", _image_rule)
    return markdown


_MARKDOWN = _build_markdown()


def render_markdown(text: str) -> str:
    """Render ``text`` to an HTML fragment for the chat web view."""
    return _MARKDOWN.render(text)
