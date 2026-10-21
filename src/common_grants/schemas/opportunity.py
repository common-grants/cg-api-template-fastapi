"""
The single opportunity model this API serves.

Every route, response model, fixture parser and test reads `Opportunity` from
here, so this is the one place to add custom fields. See PORTING.md section 6.
"""

from common_grants_sdk.schemas.pydantic import OpportunityBase

Opportunity = OpportunityBase
