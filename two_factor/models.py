from __future__ import absolute_import, division, unicode_literals

import logging
from binascii import unhexlify

from django.conf import settings
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django_otp.models import Device
from django_otp.oath import totp
from django_otp.util import hex_validator, random_hex
from phonenumber_field.modelfields import PhoneNumberField

from .gateways import make_call, send_sms

try:
    import yubiotp
except ImportError:
    yubiotp = None


logger = logging.getLogger(__name__)

PHONE_METHODS = (
    ('call', _('Phone Call')),
    ('sms', _('Text Message')),
)


def get_available_phone_methods():
    methods = []
    if getattr(settings, 'TWO_FACTOR_CALL_GATEWAY', None):
        methods.append(('call', _('Phone call')))
    if getattr(settings, 'TWO_FACTOR_SMS_GATEWAY', None):
        methods.append(('sms', _('Text message')))
    return methods


def get_available_yubikey_methods():
    methods = []
    if yubiotp and 'otp_yubikey' in settings.INSTALLED_APPS:
        methods.append(('yubikey', _('YubiKey')))
    return methods


def get_available_methods():
    methods = [('generator', _('Token generator')), ('u2f', _('FIDO U2F'))]
    methods.extend(get_available_phone_methods())
    methods.extend(get_available_yubikey_methods())
    return methods


def key_validator(*args, **kwargs):
    """Wraps hex_validator generator, to keep makemigrations happy."""
    return hex_validator()(*args, **kwargs)


def random_hex_str():
    return random_hex().decode('utf-8')


class PhoneDevice(Device):
    """
    Model with phone number and token seed linked to a user.
    """
    class Meta:
        app_label = 'two_factor'

    number = PhoneNumberField()
    key = models.CharField(max_length=40,
                           validators=[key_validator],
                           default=random_hex_str,
                           help_text="Hex-encoded secret key")
    method = models.CharField(max_length=4, choices=PHONE_METHODS,
                              verbose_name=_('method'))

    def __repr__(self):
        return '<PhoneDevice(number={!r}, method={!r}>'.format(
            self.number,
            self.method,
        )

    def __eq__(self, other):
        if not isinstance(other, PhoneDevice):
            return False
        return self.number == other.number \
            and self.method == other.method \
            and self.key == other.key

    @property
    def bin_key(self):
        return unhexlify(self.key.encode())

    def verify_token(self, token):
        # local import to avoid circular import
        from two_factor.utils import totp_digits

        try:
            token = int(token)
        except ValueError:
            return False

        for drift in range(-5, 1):
            if totp(self.bin_key, drift=drift, digits=totp_digits()) == token:
                return True
        return False

    def generate_challenge(self):
        # local import to avoid circular import
        from two_factor.utils import totp_digits

        """
        Sends the current TOTP token to `self.number` using `self.method`.
        """
        no_digits = totp_digits()
        token = str(totp(self.bin_key, digits=no_digits)).zfill(no_digits)
        if self.method == 'call':
            make_call(device=self, token=token)
        else:
            send_sms(device=self, token=token)


class U2FDevice(Device):
    """
    Model for U2F authentication
    """
    class Meta:
        app_label = 'two_factor'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='u2f_keys')
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True)

    public_key = models.TextField(unique=True)
    key_handle = models.TextField()
    app_id = models.TextField()

    def to_json(self):
        return {
            'publicKey': self.public_key,
            'keyHandle': self.key_handle,
            'appId': self.app_id,
            'version': 'U2F_V2',
        }
