#!/usr/bin/env python
"""Test security code extraction from email formats."""

import re

def extract_security_code(email_text: str) -> str:
    """Test the security code extraction logic."""
    combined = email_text.lower()
    
    # Enhanced extraction patterns
    patterns = [
        # Pattern 1: "# CODE" (Greenhouse email format with hash)
        r'#\s*([A-Za-z0-9]{6,10})',
        # Pattern 2: "code: CODE" or "verification: CODE"
        r'(?:code|verification|security)[:\s]+([A-Za-z0-9]{6,10})',
        # Pattern 3: "Copy and paste this code" followed by code
        r'copy and paste[^:]*:\s*([A-Za-z0-9]{6,10})',
        # Pattern 4: Standalone alphanumeric codes
        r'\b([A-Z0-9a-z]{6,10})\b',
        # Pattern 5: Pure numeric codes
        r'\b(\d{6,10})\b',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            code = match.group(1).strip()
            if len(code) >= 6 and code.lower() not in ("security", "verify", "confirm", "greenhouse", "application", "code"):
                return code
    
    return None

# Test cases
test_emails = [
    """
    Hi Ranjan,
    
    Copy and paste this code into the security code field on your application:
    
    # d8odDGqG
    After you enter the code, resubmit your application.
    """,
    """
    Your verification code is: ABC12345
    """,
    """
    <h1>XY2Z9876</h1>
    Please enter this code
    """,
]

print("Testing Security Code Extraction\n" + "="*50)
for i, email in enumerate(test_emails, 1):
    code = extract_security_code(email)
    print(f"Test {i}: {code}")

print("="*50)
