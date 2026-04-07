from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0010_fix_account_code_validation'),
    ]

    operations = [
        migrations.RenameField(
            model_name='accountingdocument',
            old_name='created_at',
            new_name='uploaded_at',
        ),
    ]
