from django.apps import AppConfig


class WikiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'wiki'
    default_site = "wiki.sites.WikiSite"