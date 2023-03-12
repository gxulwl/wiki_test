
from datetime import timedelta

from django import forms
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core import validators
from django.core.validators import RegexValidator
from django.forms.widgets import HiddenInput
from django.shortcuts import get_object_or_404
from django.urls import Resolver404, resolve
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, gettext_lazy as _, pgettext_lazy
from wiki import models
from wiki_test import settings
from wiki.functions import permissions
from wiki.functions.diff import simple_merge
from wiki.functions.base import PluginSettingsFormMixin
from wiki.functions.markdown.editors  import getEditor

from .account_form import UserCreationForm, UserUpdateForm

validate_slug_numbers = RegexValidator(
    r"^[0-9]+$",
    _("A 'slug' cannot consist solely of numbers."),
    "invalid",
    inverse_match=True,
)


class WikiSlugField(forms.CharField):

    default_validators = [validators.validate_slug, validate_slug_numbers]

    def __init__(self, *args, **kwargs):
        self.allow_unicode = kwargs.pop("allow_unicode", False)
        if self.allow_unicode:
            self.default_validators = [
                validators.validate_unicode_slug,
                validate_slug_numbers,
            ]
        super().__init__(*args, **kwargs)


def _clean_slug(slug, urlpath):
    if slug.startswith("_"):
        raise forms.ValidationError(gettext("地址不能以_开头"))
    if slug == "admin":
        raise forms.ValidationError(gettext("“admin”不是允许的地址名称。"))

    if settings.URL_CASE_SENSITIVE:
        already_existing_slug = models.URLPath.objects.filter(slug=slug, parent=urlpath)
    else:
        slug = slug.lower()
        already_existing_slug = models.URLPath.objects.filter(
            slug__iexact=slug, parent=urlpath
        )
    if already_existing_slug:
        already_urlpath = already_existing_slug[0]
        if already_urlpath.article and already_urlpath.article.current_revision.deleted:
            raise forms.ValidationError(
                gettext('已存在带有地址为“%s”的已删除文章。')
                % already_urlpath.slug
            )
        else:
            raise forms.ValidationError(
                gettext('已存在带有地址为“%s”的已删除文章。') % already_urlpath.slug
            )

    if settings.CHECK_SLUG_URL_AVAILABLE:
        try:
            # Fail validation if URL resolves to non-wiki app
            match = resolve(urlpath.path + "/" + slug + "/")
            if match.app_name != "wiki":
                raise forms.ValidationError(
                    gettext("此地址与现有URL冲突。")
                )
        except Resolver404:
            pass

    return slug


User = get_user_model()
Group = apps.get_model(settings.GROUP_MODEL)


class SpamProtectionMixin:


    revision_model = models.ArticleRevision

    # TODO: This method is too complex (C901)
    def check_spam(self):  # noqa
        request = self.request
        user = None
        ip_address = None
        if request.user.is_authenticated:
            user = request.user
        else:
            ip_address = request.META.get("HTTP_X_REAL_IP", None) or request.META.get(
                "REMOTE_ADDR", None
            )

        if not (user or ip_address):
            raise forms.ValidationError(
                gettext(
                    "无法找到登录用户和IP地址。"
                )
            )

        def check_interval(from_time, max_count, interval_name):
            from_time = timezone.now() - timedelta(
                minutes=settings.REVISIONS_MINUTES_LOOKBACK
            )
            revisions = self.revision_model.objects.filter(
                created__gte=from_time,
            )
            if user:
                revisions = revisions.filter(user=user)
            if ip_address:
                revisions = revisions.filter(ip_address=ip_address)
            revisions = revisions.count()
            if revisions >= max_count:
                raise forms.ValidationError(
                    gettext(
                        "您只能按%(interval_name)创建或编辑%(修订版)d篇文章。"
                    )
                    % {"revisions": max_count, "interval_name": interval_name}
                )

        if not settings.LOG_IPS_ANONYMOUS:
            return
        if request.user.has_perm("wiki.moderator"):
            return

        from_time = timezone.now() - timedelta(
            minutes=settings.REVISIONS_MINUTES_LOOKBACK
        )
        if request.user.is_authenticated:
            per_minute = settings.REVISIONS_PER_MINUTES
        else:
            per_minute = settings.REVISIONS_PER_MINUTES_ANONYMOUS
        check_interval(
            from_time,
            per_minute,
            _("minute")
            if settings.REVISIONS_MINUTES_LOOKBACK == 1
            else (_("%d minutes") % settings.REVISIONS_MINUTES_LOOKBACK),
        )

        from_time = timezone.now() - timedelta(minutes=60)
        if request.user.is_authenticated:
            per_hour = settings.REVISIONS_PER_MINUTES
        else:
            per_hour = settings.REVISIONS_PER_MINUTES_ANONYMOUS
        check_interval(from_time, per_hour, _("hour"))


class CreateRootForm(forms.Form):

    title = forms.CharField(
        label=_("Title"),
        help_text=_(
            "文章的初始标题。可以用修订标题覆盖。"
        ),
    )
    content = forms.CharField(
        label=_("Type in some contents"),
        help_text=_(
            "这只是你文章的最初内容。创建后，您可以使用更复杂的功能，如添加插件、元数据、相关文章等..."
        ),
        required=False,
        widget=getEditor().get_widget(),
    )  # @UndefinedVariable


class MoveForm(forms.Form):

    destination = forms.CharField(label=_("Destination"))
    slug = WikiSlugField(max_length=models.URLPath.SLUG_MAX_LENGTH)
    redirect = forms.BooleanField(
        label=_("Redirect pages"),
        help_text=_("为每个移动的文章创建重定向页面？"),
        required=False,
    )

    def clean(self):
        cd = super().clean()
        if cd.get("slug"):
            dest_path = get_object_or_404(
                models.URLPath, pk=self.cleaned_data["destination"]
            )
            cd["slug"] = _clean_slug(cd["slug"], dest_path)
        return cd


class EditForm(forms.Form, SpamProtectionMixin):

    title = forms.CharField(
        label=_("Title"),
    )
    content = forms.CharField(
        label=_("Contents"), required=False, widget=getEditor().get_widget()
    )  # @UndefinedVariable

    summary = forms.CharField(
        label=pgettext_lazy("Revision comment", "Summary"),
        help_text=_(
            "简介，并在日志中显示"
        ),
        required=False,
    )

    current_revision = forms.IntegerField(required=False, widget=forms.HiddenInput())

    def __init__(self, request, current_revision, *args, **kwargs):

        self.request = request
        self.no_clean = kwargs.pop("no_clean", False)
        self.preview = kwargs.pop("preview", False)
        self.initial_revision = current_revision
        self.presumed_revision = None
        if current_revision:
            # For e.g. editing a section of the text: The content provided by the caller is used.
            #      Otherwise use the content of the revision.
            provided_content = True
            content = kwargs.pop("content", None)
            if content is None:
                provided_content = False
                content = current_revision.content
            initial = {
                "content": content,
                "title": current_revision.title,
                "current_revision": current_revision.id,
            }
            initial.update(kwargs.get("initial", {}))

            # Manipulate any data put in args[0] such that the current_revision
            # is reset to match the actual current revision.
            data = None
            if len(args) > 0:
                data = args[0]
                args = args[1:]
            if data is None:
                data = kwargs.get("data", None)
            if data:
                self.presumed_revision = data.get("current_revision", None)
                if not str(self.presumed_revision) == str(self.initial_revision.id):
                    newdata = {}
                    for k, v in data.items():
                        newdata[k] = v
                    newdata["current_revision"] = self.initial_revision.id
                    # Don't merge if content comes from the caller
                    if provided_content:
                        self.presumed_revision = self.initial_revision.id
                    else:
                        newdata["content"] = simple_merge(
                            content, data.get("content", "")
                        )
                    newdata["title"] = current_revision.title
                    kwargs["data"] = newdata
                else:
                    # Always pass as kwarg
                    kwargs["data"] = data

            kwargs["initial"] = initial

        super().__init__(*args, **kwargs)

    def clean_title(self):
        title = self.cleaned_data.get("title", None)
        title = (title or "").strip()
        if not title:
            raise forms.ValidationError(
                gettext("文章缺少标题或标题无效")
            )
        return title

    def clean(self):
        """
        通过检查以下内容验证表单数据自用户尝试编辑后，未创建任何新修订修订标题或内容已更改
        """
        if self.no_clean or self.preview:
            return self.cleaned_data
        if not str(self.initial_revision.id) == str(self.presumed_revision):
            raise forms.ValidationError(
                gettext(
                    "在您编辑时，其他人更改了修订。您的内容已自动与新内容合并。请查看以下文本。"
                )
            )
        if (
            "title" in self.cleaned_data
            and self.cleaned_data["title"] == self.initial_revision.title
            and self.cleaned_data["content"] == self.initial_revision.content
        ):
            raise forms.ValidationError(gettext("No changes made. Nothing to save."))
        self.check_spam()
        return self.cleaned_data


class SelectWidgetBootstrap(forms.Select):

    def __init__(self, attrs=None, choices=()):
        if attrs is None:
            attrs = {"class": ""}
        elif "class" not in attrs:
            attrs["class"] = ""
        attrs["class"] += " form-control"

        super().__init__(attrs, choices)


class TextInputPrepend(forms.TextInput):
    template_name = "wiki/forms/text.html"

    def __init__(self, *args, **kwargs):
        self.prepend = kwargs.pop("prepend", "")
        super().__init__(*args, **kwargs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["prepend"] = mark_safe(self.prepend)
        return context


class CreateForm(forms.Form, SpamProtectionMixin):
    def __init__(self, request, urlpath_parent, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.urlpath_parent = urlpath_parent

    title = forms.CharField(
        label=_("Title"),
    )
    slug = WikiSlugField(
        label=_("Slug"),
        help_text=_(
            "这将是您可以找到文章的地址。仅使用字母数字字符和-或_<br>注意：如果稍后更改slug，指向本文的链接将不会更新。"
        ),
        max_length=models.URLPath.SLUG_MAX_LENGTH,
    )
    content = forms.CharField(
        label=_("Contents"), required=False, widget=getEditor().get_widget()
    )  # @UndefinedVariable

    summary = forms.CharField(
        label=pgettext_lazy("Revision comment", "Summary"),
        help_text=_("为文章的历史日志写一条简介。"),
        required=False,
    )

    def clean_slug(self):
        return _clean_slug(self.cleaned_data["slug"], self.urlpath_parent)

    def clean(self):
        self.check_spam()
        return self.cleaned_data


class DeleteForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.article = kwargs.pop("article")
        self.has_children = kwargs.pop("has_children")
        super().__init__(*args, **kwargs)

    confirm = forms.BooleanField(required=False, label=_("Yes, I am sure"))
    purge = forms.BooleanField(
        widget=HiddenInput(),
        required=False,
        label=_("Purge"),
        help_text=_(
            "清除文章：完全删除它（及其所有内容），不要撤消。如果您想释放slug，以便用户可以在其位置创建新文章，那么清除是一个好主意。"
        ),
    )
    revision = forms.ModelChoiceField(
        models.ArticleRevision.objects.all(), widget=HiddenInput(), required=False
    )

    def clean(self):
        if not self.cleaned_data["confirm"]:
            raise forms.ValidationError(gettext("你还不够肯定！"))
        if self.cleaned_data["revision"] != self.article.current_revision:
            raise forms.ValidationError(
                gettext(
                    "当您尝试删除此文章时，它已被修改。"
                )
            )
        return self.cleaned_data


class PermissionsForm(PluginSettingsFormMixin, forms.ModelForm):

    locked = forms.BooleanField(
        label=_("锁定文章"),
        help_text=_("拒绝所有用户编辑此文章的权限。"),
        required=False,

    )

    settings_form_headline = _("Permissions")
    settings_order = 5
    settings_write_access = False

    owner_username = forms.CharField(
        required=False,
        label=_("创建者"),
        help_text=_("输入创建者的用户名。"),
    )
    group = forms.ModelChoiceField(
        Group.objects.all(),
        empty_label=_("无"),
        label=_("组"),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    if settings.USE_BOOTSTRAP_SELECT_WIDGET:
        group.widget = SelectWidgetBootstrap()

    recursive = forms.BooleanField(
        label=_("继承权限"),
        help_text=_(
            "选中此处可将上述权限（不包括文章的组和所有者）递归应用于此权限以下的文章。"
        ),
        required=False,
    )

    recursive_owner = forms.BooleanField(
        label=_("继承所有者"),
        help_text=_(
            "选中此处可将所有权设置递归地应用于此项目之下的项目。"
        ),
        required=False,
    )

    recursive_group = forms.BooleanField(
        label=_("继承组"),
        help_text=_(
            "选中此处可将组设置递归地应用于此项目下的项目。"
        ),
        required=False,
    )

    def get_usermessage(self):
        if self.changed_data:
            return _("已更新项目的权限设置。")
        else:
            return _("您的权限设置未更改，因此未保存任何内容。")

    def __init__(self, article, request, *args, **kwargs):
        self.article = article
        self.user = request.user
        self.request = request
        kwargs["instance"] = article
        kwargs["initial"] = {"locked": article.current_revision.locked}

        super().__init__(*args, **kwargs)

        self.can_change_groups = False
        self.can_assign = False

        if permissions.can_assign(article, request.user):
            self.can_assign = True
            self.can_change_groups = True
            self.fields["group"].queryset = Group.objects.all()
        elif permissions.can_assign_owner(article, request.user):
            self.fields["group"].queryset = Group.objects.filter(user=request.user)
            self.can_change_groups = True
        else:
            # Quick-fix...
            # Set the group dropdown to readonly and with the current
            # group as only selectable option
            self.fields["group"] = forms.ModelChoiceField(
                queryset=Group.objects.filter(id=self.instance.group.id)
                if self.instance.group
                else Group.objects.none(),
                empty_label=_("(none)"),
                required=False,
                widget=SelectWidgetBootstrap(attrs={"disabled": True})
                if settings.USE_BOOTSTRAP_SELECT_WIDGET
                else forms.Select(attrs={"disabled": True}),
            )
            self.fields["group_read"].widget = forms.HiddenInput()
            self.fields["group_write"].widget = forms.HiddenInput()

        if not self.can_assign:
            self.fields["owner_username"].widget = forms.TextInput(
                attrs={"readonly": "true"}
            )
            self.fields["recursive"].widget = forms.HiddenInput()
            self.fields["recursive_group"].widget = forms.HiddenInput()
            self.fields["recursive_owner"].widget = forms.HiddenInput()
            self.fields["locked"].widget = forms.HiddenInput()

        self.fields["owner_username"].initial = (
            getattr(article.owner, User.USERNAME_FIELD) if article.owner else ""
        )

    def clean_owner_username(self):
        if self.can_assign:
            username = self.cleaned_data["owner_username"]
            if username:
                try:
                    kwargs = {User.USERNAME_FIELD: username}
                    user = User.objects.get(**kwargs)
                except User.DoesNotExist:
                    raise forms.ValidationError(gettext("No user with that username"))
            else:
                user = None
        else:
            user = self.article.owner
        return user

    def save(self, commit=True):
        article = super().save(commit=False)

        # Alter the owner according to the form field owner_username
        # TODO: Why not rename this field to 'owner' so this happens
        # automatically?
        article.owner = self.cleaned_data["owner_username"]

        # Revert any changes to group permissions if the
        # current user is not allowed (see __init__)
        # TODO: Write clean methods for this instead!
        if not self.can_change_groups:
            article.group = self.article.group
            article.group_read = self.article.group_read
            article.group_write = self.article.group_write

        if self.can_assign:
            if self.cleaned_data["recursive"]:
                article.set_permissions_recursive()
            if self.cleaned_data["recursive_owner"]:
                article.set_owner_recursive()
            if self.cleaned_data["recursive_group"]:
                article.set_group_recursive()
            if self.cleaned_data["locked"] and not article.current_revision.locked:
                revision = models.ArticleRevision()
                revision.inherit_predecessor(self.article)
                revision.set_from_request(self.request)
                revision.automatic_log = _("Article locked for editing")
                revision.locked = True
                self.article.add_revision(revision)
            elif not self.cleaned_data["locked"] and article.current_revision.locked:
                revision = models.ArticleRevision()
                revision.inherit_predecessor(self.article)
                revision.set_from_request(self.request)
                revision.automatic_log = _("Article unlocked for editing")
                revision.locked = False
                self.article.add_revision(revision)

        article.save()

    class Meta:
        model = models.Article
        fields = (
            "locked",
            "owner_username",
            "recursive_owner",
            "group",
            "recursive_group",
            "group_read",
            "group_write",
            "other_read",
            "other_write",
            "recursive",
        )
        widgets = {}


class DirFilterForm(forms.Form):

    query = forms.CharField(
        widget=forms.TextInput(
            attrs={"placeholder": _("Filter..."), "class": "search-query"}
        ),
        required=False,
    )


class SearchForm(forms.Form):

    q = forms.CharField(
        widget=forms.TextInput(
            attrs={"placeholder": _("Search..."), "class": "search-query"}
        ),
        required=False,
    )
