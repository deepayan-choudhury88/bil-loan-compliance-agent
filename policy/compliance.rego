package compliance

import rego.v1

# By default, a loan is not allowed unless it has zero violations.
default allow := false

allow if {
    count(violations) == 0
}

# Rule 1: Minimum loan value must be > 25,000 EUR
violations contains msg if {
    input.loan_value_eur <= 25000
    msg := "Rule 1 Failed: Loan value is 25,000 EUR or less"
}

# Rule 2: Currency must match HQ Country
# (Our Go pipeline will compute 'expected_currency' and pass it in)
violations contains msg if {
    input.loan_currency != input.expected_currency
    msg := "Rule 2 Failed: Currency does not match HQ expected currency"
}

# Rule 3: Asset coverage must be >= 50% of loan value
# (No conversion needed here, they are in the same currency)
violations contains msg if {
    input.asset_value < (input.loan_value * 0.5)
    msg := "Rule 3 Failed: Asset value is less than 50% of the loan value"
}
