"""Unit tests for Qt-free markdown + LaTeX rendering.

The renderer emits KaTeX placeholders (``data-katex-inline`` / ``data-katex-display``)
that the embedded web view renders in the browser; these tests only cover the
Python-side HTML, never Qt.
"""

from __future__ import annotations

from plugins.chat.src.markdown import render_markdown


def test_inline_dollar_math_becomes_a_katex_inline_placeholder() -> None:
    html = render_markdown("energy $E=mc^2$")

    assert '<span class="math-inline" data-katex-inline>' in html
    assert "E=mc^2" in html


def test_inline_paren_math_becomes_a_katex_inline_placeholder() -> None:
    html = render_markdown(r"energy \(E=mc^2\)")

    assert '<span class="math-inline" data-katex-inline>' in html
    assert "E=mc^2" in html


def test_display_dollar_math_becomes_a_katex_display_placeholder() -> None:
    html = render_markdown("$$\n\\frac{a}{b}\n$$")

    assert '<div class="math-display" data-katex-display>' in html
    assert "\\frac{a}{b}" in html


def test_display_bracket_math_becomes_a_katex_display_placeholder() -> None:
    html = render_markdown("before\n\n\\[\n\\frac{a}{b}\n\\]\n\nafter")

    assert '<div class="math-display" data-katex-display>' in html
    assert "\\frac{a}{b}" in html


def test_math_inside_code_fence_is_left_alone() -> None:
    html = render_markdown("```\n$$ x $$\n```")

    assert "data-katex" not in html
    assert "$$ x $$" in html


def test_literal_dollars_are_not_treated_as_math() -> None:
    html = render_markdown("It costs $5 and $10 total")

    assert "data-katex" not in html


def test_multiple_formulas_get_their_own_placeholders() -> None:
    html = render_markdown("$a$ and \\(b\\)")

    assert html.count("data-katex-inline") == 2


def test_malformed_math_is_still_emitted_for_katex() -> None:
    html = render_markdown("$\\frac{1}{$ and done")

    assert '<span class="math-inline" data-katex-inline>' in html
    assert "\\frac{1}{" in html


def test_raw_html_is_escaped() -> None:
    html = render_markdown("<script>alert(1)</script>")

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_remote_image_is_not_linked() -> None:
    html = render_markdown("![alt](http://example.com/x.png)")

    assert "[alt]" in html
    assert "http://example.com" not in html


def test_fenced_code_block_gets_a_copy_button() -> None:
    html = render_markdown("```python\nprint('hi')\n```")

    assert 'class="copy-btn"' in html
    assert "print('hi')" in html


def test_fenced_code_block_keeps_its_language_class() -> None:
    html = render_markdown("```python\nprint('hi')\n```")

    assert 'class="language-python"' in html
