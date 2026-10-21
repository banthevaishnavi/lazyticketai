"""12 realistic synthetic support tickets (fictional people, example.com emails)."""
from datetime import datetime, timedelta

from . import db

SEED_TICKETS = [
    ("Priya Sharma", "Email", "Charged twice for my monthly subscription",
     "Hi, I just checked my bank statement and I was charged $49 twice on October 3rd for the Pro plan. "
     "I only have one account. Please refund the duplicate charge, this is really frustrating."),
    ("Marcus Lee", "Chat", "App crashes when uploading a PDF",
     "Every time I try to upload a PDF larger than 10MB in the Android app, it crashes immediately. "
     "Version 4.2.1 on a Pixel 7. Smaller files work fine. I need this for a client meeting tomorrow."),
    ("Elena Rossi", "Email", "Cannot log in after password reset",
     "I reset my password yesterday but now the login page says 'invalid credentials' with the new one. "
     "I have tried three times and now my account seems locked. Please help, I cannot access my invoices."),
    ("Tom Okafor", "Web Form", "Package marked delivered but never arrived",
     "Order #88231 shows as delivered on Monday but nothing arrived. I checked with neighbours and the "
     "building reception. The tracking number is 1Z999AA10123456784."),
    ("Aiko Tanaka", "Email", "Please add a dark mode to the dashboard",
     "Love the product! It would be great if the web dashboard had a dark mode. I work late and the "
     "bright white screen is hard on the eyes. Thanks for considering it."),
    ("David Novak", "Phone", "URGENT: API returning 500 errors in production",
     "Since 09:40 UTC all calls to /v2/orders return HTTP 500. Our checkout is down and we are losing "
     "sales. This is an outage for us. Please escalate immediately."),
    ("Sofia Martinez", "Chat", "How do I export my reports to Excel?",
     "Hello, I would like to export the monthly sales report to Excel or CSV. I could not find the "
     "option in the Reports tab. Is this possible?"),
    ("Priya Sharma", "Web Form", "Double charge on subscription - still no refund",
     "I was billed twice ($49 x2) for my Pro subscription this month on October 3rd. I emailed already "
     "but have not heard back. Please refund the duplicate payment."),
    ("James Whitaker", "Email", "Suspicious login from another country",
     "I received an alert about a login from Brazil, but I am in Canada. I did not do this. I think my "
     "account was hacked. Please secure my account and tell me what was accessed."),
    ("Fatima Zahra", "Email", "Invoice shows wrong company address",
     "Our invoices for September and October show our old company address. We updated it in settings "
     "last month. Our accounting team needs corrected invoices for the audit."),
    ("Lucas Weber", "Chat", "Data sync between mobile and web is very slow",
     "Changes I make on the mobile app take 20-30 minutes to show up on the web version. It used to be "
     "instant. Is there a known issue with sync?"),
    ("Grace Kim", "Email", "Thank you for the quick help last week",
     "Just wanted to say thanks to Daniel from your support team who fixed my calendar integration "
     "issue last week. Great service, keep it up!"),
]


def seed(db_path, reset=False):
    """Insert the seed tickets. With reset=True, wipes existing data first. Returns count inserted."""
    if reset:
        db.delete_all(db_path)
    elif db.count_tickets(db_path):
        return 0
    base = datetime.now() - timedelta(hours=len(SEED_TICKETS) * 3)
    for i, (name, channel, subject, description) in enumerate(SEED_TICKETS):
        db.insert_ticket(db_path, {
            "customer_name": name,
            "customer_email": name.lower().replace(" ", ".") + "@example.com",
            "channel": channel,
            "subject": subject,
            "description": description,
            "created_at": (base + timedelta(hours=i * 3)).isoformat(timespec="seconds"),
        })
    db.log_activity(db_path, "Seed data", f"Inserted {len(SEED_TICKETS)} synthetic tickets")
    return len(SEED_TICKETS)
