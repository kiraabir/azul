"""Debug test to verify customer creation with proper authentication."""
import sys
sys.path.insert(0, '.')
from client import create_app, db
from client.models import Customer, Merchant, User
from client.auth import hash_password

app = create_app({
    'TESTING': True,
    'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
})
with app.app_context():
    db.create_all()

    # Create merchant
    m = Merchant(id=1, name='Test', email='t@t.com', business_type='cafe')
    db.session.add(m)
    db.session.commit()

    # Create user
    u = User(merchant_id=1, email='user@t.com', password_hash=hash_password('password123'), role='owner', is_active=True)
    db.session.add(u)
    db.session.commit()

    # Store user ID as primitive (int), not ORM object
    user_id = u.id

c = app.test_client()

# Set both merchant_id AND user_id in session (required for login_required)
with c.session_transaction() as sess:
    sess['merchant_id'] = 1
    sess['user_id'] = user_id

# Test customer creation
r = c.post('/customers/new', data={'name': 'Youssef', 'phone': '06 44 44 44 44'}, follow_redirects=True)
print('Status:', r.status_code)
print('Contains Youssef:', b'Youssef' in r.data)

with app.app_context():
    cust = Customer.query.filter_by(merchant_id=1, name='Youssef').first()
    print('Customer found:', cust is not None)
    if cust:
        print('has_phone:', cust.has_phone)
        print('phone:', cust.phone)