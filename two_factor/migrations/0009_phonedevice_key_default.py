from django.db import migrations, models

import two_factor.models


class Migration(migrations.Migration):

    dependencies = [
        ('two_factor', '0006_auto_20190408_1044'),
    ]

    operations = [
        migrations.AlterField(
            model_name='phonedevice',
            name='key',
            field=models.CharField(default=two_factor.models.random_hex_str, help_text='Hex-encoded secret key', max_length=40, validators=[two_factor.models.key_validator]),
        ),
    ]
