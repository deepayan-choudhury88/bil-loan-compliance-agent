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
	"strings"
	"time"
)

var countryToCurrency = map[string]string{
	"Germany": "EUR", "Ireland": "EUR", "Spain": "EUR", "France": "EUR",
	"Italy": "EUR", "Netherlands": "EUR", "Portugal": "EUR", "Belgium": "EUR",
	"Austria": "EUR", "Finland": "EUR", "Luxembourg": "EUR",
	"United Kingdom": "GBP", "United States": "USD", "Switzerland": "CHF",
	"Sweden": "SEK", "Poland": "PLN", "Japan": "JPY", "Canada": "CAD",
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

type OPAResponse struct {
	Result struct {
		Allow      bool     `json:"allow"`
		Violations []string `json:"violations"`
	} `json:"result"`
}

type ReportData struct {
	TotalLoansChecked int
	TotalFailures     int
	Rule1Fails        int
	Rule2Fails        int
	Rule3Fails        int
	Portfolio         map[string]float64
	FailedLoans       []FailedLoan
}

type FailedLoan struct {
	LoanID      string
	Company     string
	Violations  string
	LoanDetails string
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

	file, err := os.Open("../data/loans.csv")
	if err != nil {
		log.Fatalf("Failed to open file: %v", err)
	}
	defer file.Close()

	reader := csv.NewReader(file)
	if _, err = reader.Read(); err != nil {
		log.Fatalf("Failed to read header: %v", err)
	}

	report := ReportData{
		Portfolio:   make(map[string]float64),
		FailedLoans: []FailedLoan{},
	}

	rowCount := 0
	for {
		record, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			continue
		}

		assetValue, _ := strconv.ParseFloat(record[4], 64)
		loanValue, _ := strconv.ParseFloat(record[6], 64)
		currency := record[7]
		hqCountry := record[2]
		companyName := record[1]

		var loanValueEUR float64
		if currency == "EUR" {
			loanValueEUR = loanValue
		} else {
			rate, exists := rates[currency]
			if !exists {
				continue
			}
			loanValueEUR = loanValue / rate
		}

		expectedCurrency, exists := countryToCurrency[hqCountry]
		if !exists {
			expectedCurrency = "UNKNOWN"
		}

		report.Portfolio[companyName] += loanValueEUR
		report.TotalLoansChecked++

		loanInput := LoanInput{
			LoanID:           record[0],
			CompanyName:      companyName,
			HQCountry:        hqCountry,
			AssetDescription: record[3],
			AssetValue:       assetValue,
			AssetOwner:       record[5],
			LoanValue:        loanValue,
			LoanCurrency:     currency,
			LoanValueEUR:     loanValueEUR,
			ExpectedCurrency: expectedCurrency,
		}

		reqBody := map[string]interface{}{"input": loanInput}
		jsonData, _ := json.Marshal(reqBody)

		resp, err := http.Post("http://localhost:8181/v1/data/compliance", "application/json", bytes.NewBuffer(jsonData))
		if err != nil {
			continue
		}

		var opaResult OPAResponse
		if err := json.NewDecoder(resp.Body).Decode(&opaResult); err != nil {
			resp.Body.Close()
			continue
		}
		resp.Body.Close()

		if !opaResult.Result.Allow {
			report.TotalFailures++
			violationsStr := strings.Join(opaResult.Result.Violations, "; ")

			if strings.Contains(violationsStr, "Rule 1") {
				report.Rule1Fails++
			}
			if strings.Contains(violationsStr, "Rule 2") {
				report.Rule2Fails++
			}
			if strings.Contains(violationsStr, "Rule 3") {
				report.Rule3Fails++
			}

			details := fmt.Sprintf("Loan Value: %.2f %s | Asset Value: %.2f %s | HQ: %s", loanValue, currency, assetValue, currency, hqCountry)

			report.FailedLoans = append(report.FailedLoans, FailedLoan{
				LoanID:      loanInput.LoanID,
				Company:     loanInput.CompanyName,
				Violations:  violationsStr,
				LoanDetails: details,
			})
		}

		rowCount++
	}

	fmt.Println("✅ Success! Compliance processing completed.")
}
