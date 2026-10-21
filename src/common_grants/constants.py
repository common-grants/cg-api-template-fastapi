"""
Constants to customize for your implementation.

`OPPORTUNITY_NAMESPACE` gives records keyed by integers or strings a stable UUID:
`uuid.uuid5(OPPORTUNITY_NAMESPACE, str(key))` returns the same id for the same
key every time. See PORTING.md section 2.
"""

import uuid

# CUSTOMIZE: your organization's domain, so your ids never collide with another API's.
ORGANIZATION_DOMAIN = "example.com"

OPPORTUNITY_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, ORGANIZATION_DOMAIN)
