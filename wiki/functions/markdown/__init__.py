import bleach
import markdown

from wiki_test import settings
from wiki.functions import registry


class ArticleMarkdown(markdown.Markdown):
    def __init__(self, article, preview=False, user=None, *args, **kwargs):
        kwargs.update(settings.MARKDOWN_KWARGS)
        kwargs["extensions"] = self.get_markdown_extensions()
        super().__init__(*args, **kwargs)
        self.article = article
        self.preview = preview
        self.user = user

    def core_extensions(self):
        """List of functions extensions found in the mdx folder"""
        return [
            "markdown.extensions.footnotes",
        "markdown.extensions.attr_list",
        "markdown.extensions.footnotes",
        "markdown.extensions.attr_list",
        "markdown.extensions.def_list",
        "markdown.extensions.tables",
        "markdown.extensions.abbr",
        "markdown.extensions.sane_lists",
        "markdown.extensions.extra",
        "markdown.extensions.codehilite",
        "markdown.extensions.toc",
        "markdown.extensions.fenced_code",
        "markdown.extensions.admonition",
        "markdown.extensions.meta",
        "markdown.extensions.nl2br",
        "markdown.extensions.smarty",
        "markdown.extensions.wikilinks",
        ]

    def get_markdown_extensions(self):
        extensions = list(settings.MARKDOWN_KWARGS.get("extensions", []))
        extensions += self.core_extensions()
        extensions += registry.get_markdown_extensions()
        return extensions

    def convert(self, text, *args, **kwargs):
        html = super().convert(text, *args, **kwargs)
        if settings.MARKDOWN_SANITIZE_HTML:
            tags = (
                    settings.MARKDOWN_HTML_WHITELIST + registry.get_html_whitelist()
            )
            attrs = {}
            attrs.update(settings.MARKDOWN_HTML_ATTRIBUTES)
            attrs.update(registry.get_html_attributes().items())

            html = bleach.clean(
                html,
                tags=tags,
                attributes=attrs,
                strip=True,
            )
        return html


def article_markdown(text, article, *args, **kwargs):
    md = ArticleMarkdown(article, *args, **kwargs)
    return md.convert(text)


def add_to_registry(processor, key, value, location):
    if len(processor) == 0:
        # This is the first item. Set priority to 50.
        priority = 50
    elif location == "_begin":
        processor._sort()
        # Set priority 5 greater than highest existing priority
        priority = processor._priority[0].priority + 5
    elif location == "_end":
        processor._sort()
        # Set priority 5 less than lowest existing priority
        priority = processor._priority[-1].priority - 5
    elif location.startswith("<") or location.startswith(">"):
        # Set priority halfway between existing priorities.
        i = processor.get_index_for_name(location[1:])
        if location.startswith("<"):
            after = processor._priority[i].priority
            if i > 0:
                before = processor._priority[i - 1].priority
            else:
                # Location is first item`
                before = after + 10
        else:
            # location.startswith('>')
            before = processor._priority[i].priority
            if i < len(processor) - 1:
                after = processor._priority[i + 1].priority
            else:
                # location is last item
                after = before - 10
        priority = before - ((before - after) / 2)
    else:
        raise ValueError(
            'Not a valid location: "%s". Location key '
            'must start with a ">" or "<".' % location
        )
    processor.register(value, key, priority)
