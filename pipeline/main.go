package main

import (
	"bytes"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"
)

// Static lookup table mapping HQ Country to Expected Currency
var countryToCurrency = map[string]string{
	"Germany":        "EUR",
	"Ireland":        "EUR",
	"Spain":          "EUR",
	"France":         "EUR",
	"Italy":          "EUR",
	"Netherlands":    "EUR",
	"Portugal":       "EUR",
	"Belgium":        "EUR",
	"Austria":        "EUR",
	"Finland":        "EUR",
	"Luxembourg":     "EUR",
	"United Kingdom": "GBP",
	"United States":  "USD",
	"Switzerland":    "CHF",
	"Sweden":         "SEK",
	"Poland":         "PLN",
	"Japan":          "JPY",
	"Canada":         "CAD",
}

type ExchangeRates struct {
	Rates map[string]float64 `json:"rates"`
}

type LoanInput struct {
	LoanID           string  `json:"loan_id"`
	CompanyName      string  `json:"company_name"`
	HQCountry        string  `json:"hq_country"`
	AssetDescription string  `json:"asset_description"`
	AssetValue       float64 `json:"asset_value"`
	AssetOwner       string  `json:"asset_owner"`
	LoanValue        float64 `json:"loan_value"`
	LoanCurrency     string  `json:"loan_currency"`
	LoanValueEUR     float64 `json:"loan_value_eur"`
	ExpectedCurrency string  `json:"expected_currency"`
}

// Updated to parse the 'allow' boolean and the 'violations' array from OPA
type OPAResponse struct {
	Result struct {
		Allow      bool     `json:"allow"`
		Violations []string `json:"violations"`
	} `json:"result"`
}

func fetchRates() (map[string]float64, error) {
	client := http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get("https://api.frankfurter.dev/v1/latest")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var data ExchangeRates
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return nil, err
	}
	return data.Rates, nil
}

func main() {
	rates, err := fetchRates()
	if err != nil {
		log.Fatalf("Failed to fetch exchange rates: %v", err)
	}
	rates["EUR"] = 1.0 
	fmt.Println("Successfully cached FX rates.")

	file, err := os.Open("../data/loans.csv")
	if err != nil {
		log.Fatalf("Failed to open file: %v", err)
	}
	defer file.Close()

	reader := csv.NewReader(file)
	if _, err = reader.Read(); err != nil { // Skip header
		log.Fatalf("Failed to read header: %v", err)
	}

	rowCount := 0
	for {
		record, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			log.Printf("Error reading row: %v", err)
			continue
		}

		assetValue, _ := strconv.ParseFloat(record[4], 64)
		loanValue, _ := strconv.ParseFloat(record[6], 64)
		currency := record[7]
		hqCountry := record[2]

		var loanValueEUR float64
		if currency == "EUR" {
			loanValueEUR = loanValue
		} else {
			rate, exists := rates[currency]
			if !exists {
				log.Printf("Warning: Exchange rate for %s not found. Skipping loan %s.", currency, record[0])
				continue
			}
			loanValueEUR = loanValue / rate 
		}

		// Look up expected currency, default to UNKNOWN if not in map
		expectedCurrency, exists := countryToCurrency[hqCountry]
		if !exists {
			expectedCurrency = "UNKNOWN"
		}

		loanInput := LoanInput{
			LoanID:           record[0],
			CompanyName:      record[1],
			HQCountry:        hqCountry,
			AssetDescription: record[3],
			AssetValue:       assetValue,
			AssetOwner:       record[5],
			LoanValue:        loanValue,
			LoanCurrency:     currency,
			LoanValueEUR:     loanValueEUR,
			ExpectedCurrency: expectedCurrency,
		}

		// 1. Wrap the loan in the "input" object OPA expects
		reqBody := map[string]interface{}{
			"input": loanInput,
		}
		jsonData, _ := json.Marshal(reqBody)

		// 2. Send the POST request to OPA (updated endpoint to match 'package compliance')
		resp, err := http.Post("http://localhost:8181/v1/data/compliance", "application/json", bytes.NewBuffer(jsonData))
		if err != nil {
			log.Printf("Failed to call OPA for LoanID %s: %v", loanInput.LoanID, err)
			continue
		}

		// 3. Parse the OPA result
		var opaResult OPAResponse
		if err := json.NewDecoder(resp.Body).Decode(&opaResult); err != nil {
			log.Printf("Failed to parse OPA response for LoanID %s: %v", loanInput.LoanID, err)
			resp.Body.Close()
			continue
		}
		resp.Body.Close()

		// 4. Print the result
		if opaResult.Result.Allow {
			fmt.Printf("LoanID: %s | Status: PASSED\n", loanInput.LoanID)
		} else {
			fmt.Printf("LoanID: %s | Status: FAILED | Violations: %v\n", loanInput.LoanID, opaResult.Result.Violations)
		}

		rowCount++
		// Stop after 10 rows for testing purposes
		if rowCount >= 10 {
			break
		}
	}
}
