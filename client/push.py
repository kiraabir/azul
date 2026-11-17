"""Web Push Notification Service for AZUL."""
import json
import base64
import hashlib
import time
import os
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import requests


class VAPID:
    """VAPID key generation and signing for Web Push."""

    def __init__(self, private_key=None, public_key=None):
        if private_key is None:
            self.private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        else:
            self.private_key = serialization.load_pem_private_key(
                private_key, password=None, backend=default_backend()
            )
        self.public_key = self.private_key.public_key()

    @property
    def public_key_pem(self):
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )

    @property
    def private_key_pem(self):
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PKCS8,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

    def sign(self, payload):
        """Sign a push message with VAPID."""
        # Create JWT for VAPID authentication
        jwt_payload = {
            'aud': 'https://fcm.googleapis.com',
            'exp': int(time.time()) + 43200,  # 12 hours
            'sub': 'mailto:admin@azul.ma'
        }
        jwt_header = {'typ': 'JWT', 'alg': 'ES256'}
        jwt_base = base64.urlsafe_b64encode(
            json.dumps(jwt_header).encode()
        ).rstrip(b'=') + b'.' + base64.urlsafe_b64encode(
            json.dumps(jwt_payload).encode()
        ).rstrip(b'=')

        # Sign with ECDSA
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
        signature = self.private_key.sign(
            jwt_base.encode(),
            ec.ECDSA(hashes.SHA256())
        )
        r, s = decode_dss_signature(signature)
        r_bytes = r.to_bytes(32, 'big')
        s_bytes = s.to_bytes(32, 'big')
        sig = base64.urlsafe_b64encode(r_bytes + s_bytes).rstrip(b'=')

        return jwt_base + b'.' + sig


class PushNotificationService:
    """Service for sending Web Push notifications."""

    def __init__(self, vapid_private_key=None, vapid_public_key=None):
        self.vapid = VAPID(
            private_key=vapid_private_key,
            public_key=vapid_public_key
        ) if vapid_private_key else None

    def send_push(self, subscription, title, body, data=None):
        """Send a push notification to a subscription."""
        endpoint = subscription['endpoint']
        p256dh_key = subscription['keys']['p256dh']
        auth_key = subscription['keys']['auth']

        # Build the encrypted payload
        payload = json.dumps({
            'title': title,
            'body': body,
            'data': data or {}
        })

        # Encrypt payload for delivery
        # In production, this would use the proper Web Push encryption
        # For now, we'll send a simple notification
        headers = {
            'Content-Type': 'application/json',
            'TTL': '86400',
            'Urgency': 'normal'
        }

        if self.vapid:
            vapid_jwt = self.vapid.sign(payload)
            headers['Authorization'] = 'Bearer ' + vapid_jwt.decode()
            headers['VAPID'] = base64.urlsafe_b64encode(
                self.vapid.public_key_pem
            ).rstrip(b'=').decode()

        try:
            response = requests.post(endpoint, data=payload, headers=headers, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"Push notification failed: {e}")
            return False


def generate_vapid_keys():
    """Generate VAPID keys for Web Push."""
    vapid = VAPID()
    return {
        'public_key': base64.urlsafe_b64encode(vapid.public_key_pem).rstrip(b'=').decode(),
        'private_key': base64.urlsafe_b64encode(vapid.private_key_pem).rstrip(b'=').decode()
    }


def create_push_subscription(customer_id, endpoint, p256dh, auth):
    """Store a push subscription for a customer."""
    from .models import Customer
    customer = Customer.query.get(customer_id)
    if customer:
        customer.device_token = json.dumps({
            'endpoint': endpoint,
            'keys': {
                'p256dh': p256dh,
                'auth': auth
            }
        })
        customer.push_opt_in = True
        from . import db
        db.session.commit()
        return True
    return False


def send_push_to_customer(customer_id, title, body, data=None):
    """Send a push notification to a specific customer."""
    from .models import Customer
    customer = Customer.query.get(customer_id)
    if not customer or not customer.device_token:
        return False

    try:
        subscription = json.loads(customer.device_token)
    except (json.JSONDecodeError, TypeError):
        return False

    service = PushNotificationService()
    return service.send_push(subscription, title, body, data)


def send_push_to_customers(customer_ids, title, body, data=None):
    """Send push notifications to multiple customers."""
    results = []
    for customer_id in customer_ids:
        results.append(send_push_to_customer(customer_id, title, body, data))
    return all(results)