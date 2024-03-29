# Generated by Django 4.1.2 on 2023-03-06 05:08

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import mptt.fields


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('sites', '0002_alter_domain_unique'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('wiki', '0003_delete_urlpath'),
    ]

    operations = [
        migrations.CreateModel(
            name='ArticlePlugin',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('deleted', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AlterField(
            model_name='article',
            name='created',
            field=models.DateTimeField(auto_now_add=True, verbose_name='created'),
        ),
        migrations.AlterField(
            model_name='article',
            name='current_revision',
            field=models.OneToOneField(blank=True, help_text='The revision being displayed for this article. If you need to do a roll-back, simply change the value of this field.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='current_set', to='wiki.articlerevision', verbose_name='current revision'),
        ),
        migrations.AlterField(
            model_name='article',
            name='group',
            field=models.ForeignKey(blank=True, help_text='Like in a UNIX file system, permissions can be given to a user according to group membership. Groups are handled through the Django auth system.', null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.group', verbose_name='group'),
        ),
        migrations.AlterField(
            model_name='article',
            name='modified',
            field=models.DateTimeField(auto_now=True, help_text='Article properties last modified', verbose_name='modified'),
        ),
        migrations.AlterField(
            model_name='article',
            name='owner',
            field=models.ForeignKey(blank=True, help_text='The owner of the article, usually the creator. The owner always has both read and write access.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='owned_articles', to=settings.AUTH_USER_MODEL, verbose_name='owner'),
        ),
        migrations.CreateModel(
            name='RevisionPlugin',
            fields=[
                ('articleplugin_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='wiki.articleplugin')),
            ],
            bases=('wiki.articleplugin',),
        ),
        migrations.AddField(
            model_name='articleplugin',
            name='article',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='wiki.article', verbose_name='article'),
        ),
        migrations.CreateModel(
            name='URLPath',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(blank=True, null=True, verbose_name='slug')),
                ('lft', models.PositiveIntegerField(editable=False)),
                ('rght', models.PositiveIntegerField(editable=False)),
                ('tree_id', models.PositiveIntegerField(db_index=True, editable=False)),
                ('level', models.PositiveIntegerField(editable=False)),
                ('article', models.ForeignKey(help_text='This field is automatically updated, but you need to populate it when creating a new URL path.', on_delete=django.db.models.deletion.CASCADE, to='wiki.article', verbose_name='article')),
                ('moved_to', mptt.fields.TreeForeignKey(blank=True, help_text='Article path was moved to this location', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='moved_from', to='wiki.urlpath', verbose_name='Moved to')),
                ('parent', mptt.fields.TreeForeignKey(blank=True, help_text='Position of URL path in the tree.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='wiki.urlpath')),
                ('site', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='sites.site')),
            ],
            options={
                'verbose_name': 'URL path',
                'verbose_name_plural': 'URL paths',
                'unique_together': {('site', 'parent', 'slug')},
            },
        ),
        migrations.CreateModel(
            name='SimplePlugin',
            fields=[
                ('articleplugin_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='wiki.articleplugin')),
                ('article_revision', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='wiki.articlerevision')),
            ],
            bases=('wiki.articleplugin',),
        ),
        migrations.CreateModel(
            name='RevisionPluginRevision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('revision_number', models.IntegerField(editable=False, verbose_name='revision number')),
                ('user_message', models.TextField(blank=True)),
                ('automatic_log', models.TextField(blank=True, editable=False)),
                ('ip_address', models.GenericIPAddressField(blank=True, editable=False, null=True, verbose_name='IP address')),
                ('modified', models.DateTimeField(auto_now=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('deleted', models.BooleanField(default=False, verbose_name='deleted')),
                ('locked', models.BooleanField(default=False, verbose_name='locked')),
                ('previous_revision', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='wiki.revisionpluginrevision')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='user')),
                ('plugin', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='revision_set', to='wiki.revisionplugin')),
            ],
            options={
                'ordering': ('-created',),
                'get_latest_by': 'revision_number',
            },
        ),
        migrations.AddField(
            model_name='revisionplugin',
            name='current_revision',
            field=models.OneToOneField(blank=True, help_text='The revision being displayed for this plugin. If you need to do a roll-back, simply change the value of this field.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='plugin_set', to='wiki.revisionpluginrevision', verbose_name='current revision'),
        ),
        migrations.CreateModel(
            name='ReusablePlugin',
            fields=[
                ('articleplugin_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='wiki.articleplugin')),
                ('articles', models.ManyToManyField(related_name='shared_plugins_set', to='wiki.article')),
            ],
            bases=('wiki.articleplugin',),
        ),
    ]
