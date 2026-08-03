# BIL-red-pandas

Step 1: Start the OPA Server
Open a terminal window and spin up the Open Policy Agent container, mounting your local Rego compliance policies:

# Navigate to your policy directory or run OPA via Docker
docker run -d --name opa -p 8181:8181 openpolicyagent/opa:latest run --server --set=decision_logs.console=true

To load your specific compliance rules into OPA, ensure your compliance.rego is active or pushed to OPA's data endpoint : 

curl -X PUT --data-binary @compliance.rego http://localhost:8181/v1/policies/loan_compliance

Test with test payload : 

curl -X POST http://localhost:8181/v1/data/loan/compliance -H "Content-Type: application/json" -d '{
  "input": {
    "LoanID": "TEST-001",
    "LoanValueEUR": 20000.00
  }
}'

