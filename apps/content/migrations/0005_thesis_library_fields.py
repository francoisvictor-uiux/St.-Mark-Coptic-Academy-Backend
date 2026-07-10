import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0004_article_is_featured_article_tags_article_views_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='thesis',
            name='category',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='theses',
                to='content.category',
            ),
        ),
        migrations.AddField(
            model_name='thesis',
            name='abstract_ar',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='thesis',
            name='abstract_en',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='thesis',
            name='keywords',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='thesis',
            name='file_url',
            field=models.URLField(blank=True, default=''),
        ),
        migrations.AddIndex(
            model_name='thesis',
            index=models.Index(fields=['is_published', '-year'], name='theses_pub_year_idx'),
        ),
    ]
