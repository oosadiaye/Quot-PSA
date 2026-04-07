# Migration: move TenantModule and Role to per-tenant schemas (core app).
# Each tenant's PostgreSQL schema will contain its own core_tenantmodule
# and core_role tables — no tenant FK needed; schema isolation is the key.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_rename_core_logina_usernam_idx_core_logina_usernam_de1067_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='TenantModule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('module_name', models.CharField(max_length=50, unique=True)),
                ('module_title', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['module_title'],
            },
        ),
        migrations.CreateModel(
            name='Role',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('code', models.CharField(max_length=50, unique=True)),
                ('module', models.CharField(
                    choices=[
                        ('accounting', 'Accounting'),
                        ('sales', 'Sales'),
                        ('procurement', 'Procurement'),
                        ('inventory', 'Inventory'),
                        ('hrm', 'Human Resources'),
                        ('budget', 'Budget'),
                        ('production', 'Production'),
                        ('quality', 'Quality'),
                        ('service', 'Service'),
                        ('technical', 'Technical'),
                        ('admin', 'Administration'),
                    ],
                    max_length=20,
                )),
                ('role_type', models.CharField(
                    choices=[('manager', 'Manager'), ('officer', 'Officer')],
                    max_length=20,
                )),
                ('can_view', models.BooleanField(default=True)),
                ('can_add', models.BooleanField(default=False)),
                ('can_change', models.BooleanField(default=False)),
                ('can_delete', models.BooleanField(default=False)),
                ('can_approve', models.BooleanField(default=False)),
                ('can_post', models.BooleanField(default=False)),
                ('is_active', models.BooleanField(default=True)),
                ('is_default', models.BooleanField(
                    default=False,
                    help_text='Default role assigned to new users in this module',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['module', 'role_type', 'name'],
            },
        ),
    ]
