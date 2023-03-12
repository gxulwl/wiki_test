import logging
import warnings

from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.urls import reverse
from mptt.fields import TreeForeignKey
from mptt.models import MPTTModel
from wiki import queryset
from wiki_test import settings
from wiki.functions.exceptions import MultipleRootURLs
from wiki.functions.exceptions import NoRootURL
from wiki.decorators import disable_signal_for_loaddata
from wiki.models.article import Article
from wiki.models.article import ArticleForObject
from wiki.models.article import ArticleRevision

log = logging.getLogger(__name__)


class URLPath(MPTTModel):
    INHERIT_PERMISSIONS = True

    objects = queryset.URLPathManager()

    articles = GenericRelation(
        ArticleForObject,
        content_type_field="content_type",
        object_id_field="object_id",
    )

    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        verbose_name=("文章"),
        help_text=(
            "此字段会自动更新，但需要在创建新的URL路径时填充它。"
        ),
    )

    SLUG_MAX_LENGTH = 50

    slug = models.SlugField(
        verbose_name=("slug"), null=True, blank=True, max_length=SLUG_MAX_LENGTH
    )
    site = models.ForeignKey(Site, on_delete=models.CASCADE)
    parent = TreeForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    moved_to = TreeForeignKey(
        "self",
        verbose_name=("移动到"),
        help_text=("文章路径被移动到该路径"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="moved_from",
    )

    def __cached_ancestors(self):
        if not self.pk or not self.get_ancestors().exists():
            self._cached_ancestors = []
        if not hasattr(self, "_cached_ancestors"):
            self._cached_ancestors = list(self.get_ancestors().select_related_common())

        return self._cached_ancestors

    def __cached_ancestors_setter(self, ancestors):
        self._cached_ancestors = ancestors

    # Python 2.5 compatible property constructor
    cached_ancestors = property(__cached_ancestors, __cached_ancestors_setter)

    def set_cached_ancestors_from_parent(self, parent):
        self.cached_ancestors = parent.cached_ancestors + [parent]

    @property
    def path(self):
        if not self.parent:
            return ""

        # All ancestors except roots
        ancestors = list(
            filter(lambda ancestor: ancestor.parent is not None, self.cached_ancestors)
        )
        slugs = [obj.slug if obj.slug else "" for obj in ancestors + [self]]

        return "/".join(slugs) + "/"

    def is_deleted(self):

        return self.first_deleted_ancestor() is not None

    def first_deleted_ancestor(self):
        for ancestor in self.cached_ancestors + [self]:
            if ancestor.article.current_revision.deleted:
                return ancestor
        return None

    @transaction.atomic
    def _delete_subtree(self):
        for descendant in self.get_descendants(include_self=True).order_by("-level"):
            descendant.article.delete()

    def delete_subtree(self):

        self._delete_subtree()

    @classmethod
    def root(cls):
        site = Site.objects.get_current()
        root_nodes = cls.objects.root_nodes().filter(site=site).select_related_common()
        # We fetch the nodes as a list and use len(), not count() because we need
        # to get the result out anyway. This only takes one sql query
        no_paths = len(root_nodes)
        if no_paths == 0:
            raise NoRootURL("您需要在站点上创建根文章 '%s'" % site)
        if no_paths > 1:
            raise MultipleRootURLs("你在 %s 上有多个根" % site)
        return root_nodes[0]

    class MPTTMeta:
        pass

    def __str__(self):
        path = self.path
        return path if path else ("(root)")

    def delete(self, *args, **kwargs):
        assert not (
                self.parent and self.get_children()
        ), "不能删除包含子项的根项目。"
        super().delete(*args, **kwargs)

    class Meta:
        verbose_name = ("URL path")
        verbose_name_plural = ("URL paths")
        unique_together = ("site", "parent", "slug")

    def clean(self, *args, **kwargs):
        if self.slug and not self.parent:
            raise ValidationError(
                ("很抱歉，你不能有一篇带有slug的根文章。")
            )
        if not self.slug and self.parent:
            raise ValidationError(("非根注释应该有一个slug"))
        if not self.parent:
            if URLPath.objects.root_nodes().filter(site=self.site).exclude(id=self.id):
                raise ValidationError(
                    ("%s上已存在根节点") % self.site
                )

    @classmethod
    def get_by_path(cls, path, select_related=False):

        path = path.lstrip("/")
        path = path.rstrip("/")

        # Root page requested
        if not path:
            return cls.root()

        slugs = path.split("/")
        level = 1
        parent = cls.root()
        for slug in slugs:
            if settings.URL_CASE_SENSITIVE:
                child = parent.get_children().select_related_common().get(slug=slug)
                child.cached_ancestors = parent.cached_ancestors + [parent]
                parent = child
            else:
                child = (
                    parent.get_children().select_related_common().get(slug__iexact=slug)
                )
                child.cached_ancestors = parent.cached_ancestors + [parent]
                parent = child
            level += 1

        return parent

    def get_absolute_url(self):
        return reverse("wiki:get", kwargs={"path": self.path})

    @classmethod
    def create_root(cls, site=None, title="Root", request=None, **kwargs):
        if not site:
            site = Site.objects.get_current()
        root_nodes = cls.objects.root_nodes().filter(site=site)
        if not root_nodes:
            article = Article()
            revision = ArticleRevision(title=title, **kwargs)
            if request:
                revision.set_from_request(request)
            article.add_revision(revision, save=True)
            article.save()
            root = cls.objects.create(site=site, article=article)
            article.add_object_relation(root)
        else:
            root = root_nodes[0]
        return root

    @classmethod
    @transaction.atomic
    def create_urlpath(
            cls,
            parent,
            slug,
            site=None,
            title="Root",
            article_kwargs={},
            request=None,
            article_w_permissions=None,
            **revision_kwargs
    ):
        if not site:
            site = Site.objects.get_current()
        article = Article(**article_kwargs)
        article.add_revision(ArticleRevision(title=title, **revision_kwargs), save=True)
        article.save()
        newpath = cls.objects.create(
            site=site, parent=parent, slug=slug, article=article
        )
        article.add_object_relation(newpath)
        return newpath

    @classmethod
    def _create_urlpath_from_request(
            cls, request, perm_article, parent_urlpath, slug, title, content, summary
    ):
        user = None
        ip_address = None
        if not request.user.is_anonymous:
            user = request.user
            if settings.LOG_IPS_USERS:
                ip_address = request.META.get("REMOTE_ADDR", None)
        elif settings.LOG_IPS_ANONYMOUS:
            ip_address = request.META.get("REMOTE_ADDR", None)

        return cls.create_urlpath(
            parent_urlpath,
            slug,
            title=title,
            content=content,
            user_message=summary,
            user=user,
            ip_address=ip_address,
            article_kwargs={
                "owner": user,
                "group": perm_article.group,
                "group_read": perm_article.group_read,
                "group_write": perm_article.group_write,
                "other_read": perm_article.other_read,
                "other_write": perm_article.other_write,
            },
        )

    @classmethod
    def create_article(cls, *args, **kwargs):
        warnings.warn(
            "URLPath.create_article 重命名为 create_urlpath",
            DeprecationWarning,
        )
        return cls.create_urlpath(*args, **kwargs)

    def get_ordered_children(self):
        return self.children.order_by("slug")


######################################################
# SIGNAL HANDLERS
######################################################

# Just get this once
urlpath_content_type = None


@disable_signal_for_loaddata
def on_article_relation_save(**kwargs):
    global urlpath_content_type
    instance = kwargs["instance"]
    if not urlpath_content_type:
        urlpath_content_type = ContentType.objects.get_for_model(URLPath)
    if instance.content_type == urlpath_content_type:
        URLPath.objects.filter(id=instance.object_id).update(article=instance.article)


post_save.connect(on_article_relation_save, ArticleForObject)


class Namespace:
    # An instance of Namespace simulates "nonlocal variable_name" declaration
    # in any nested function, that is possible in Python 3. It allows assigning
    # to non local variable without rebinding it local. See PEP 3104.
    pass


def on_article_delete(instance, *args, **kwargs):

    site = Site.objects.get_current()

    ns = Namespace()
    ns.lost_and_found = None

    def get_lost_and_found():
        if ns.lost_and_found:
            return ns.lost_and_found
        try:
            ns.lost_and_found = URLPath.objects.get(
                slug=settings.LOST_AND_FOUND_SLUG, parent=URLPath.root(), site=site
            )
        except URLPath.DoesNotExist:
            article = Article(
                group_read=True, group_write=False, other_read=False, other_write=False
            )
            article.add_revision(
                ArticleRevision(
                    content=(
                        "文章丢失了父项目\n"
                        "===============================\n\n"
                        "这篇文章的子项目的父项目被删除了。你应该为他们找一个新的父项目。"
                    ),
                    title=("页面丢失了"),
                )
            )
            ns.lost_and_found = URLPath.objects.create(
                slug=settings.LOST_AND_FOUND_SLUG,
                parent=URLPath.root(),
                site=site,
                article=article,
            )
            article.add_object_relation(ns.lost_and_found)
        return ns.lost_and_found

    for urlpath in URLPath.objects.filter(articles__article=instance, site=site):
        # Delete the children
        for child in urlpath.get_children():
            child.move_to(get_lost_and_found())
        # ...and finally delete the path itself


pre_delete.connect(on_article_delete, Article)
