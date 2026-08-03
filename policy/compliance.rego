package loan.compliance

import rego.v1

# Default state: assume no violations
default rule1_pass := false

# Rule 1: Pass if the EUR-converted value is strictly greater than 25,000
rule1_pass if {
    input.LoanValueEUR > 25000
}
