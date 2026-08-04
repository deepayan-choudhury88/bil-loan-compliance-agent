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

type ExchangeRates struct {
	Rates map[string]float64 `json:"rates"`
}

type LoanRecord struct {
	LoanID           string  `json:"LoanID"`
	CompanyName      string  `json:"CompanyName"`
	HQCountry        string  `json:"HQCountry"`
	AssetDescription string  `json:"AssetDescription"`
	AssetValue       float64 `json:"AssetValue"`
	AssetOwner       string  `json:"AssetOwner"`
	LoanValue        float64 `json:"LoanValue"`
	LoanCurrency     string  `json:"LoanCurrency"`
	LoanValueEUR     float64 `json:"LoanValueEUR"`
}

type OPAResponse struct {
	Result struct {
		Rule1Pass bool `json:"rule1_pass"`
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
	if _, err = reader.Read(); err != nil {
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

		loan := LoanRecord{
			LoanID:           record[0],
			CompanyName:      record[1],
			HQCountry:        record[2],
			AssetDescription: record[3],
			AssetValue:       assetValue,
			AssetOwner:       record[5],
			LoanValue:        loanValue,
			LoanCurrency:     currency,
			LoanValueEUR:     loanValueEUR,
		}

		// 1. Wrap the loan in the "input" object OPA expects
		reqBody := map[string]interface{}{
			"input": loan,
		}
		jsonData, _ := json.Marshal(reqBody)

		// 2. Send the POST request to OPA
		resp, err := http.Post("http://localhost:8181/v1/data/loan/compliance", "application/json", bytes.NewBuffer(jsonData))
		if err != nil {
			log.Printf("Failed to call OPA for LoanID %s: %v", loan.LoanID, err)
			continue
		}

		// 3. Parse the OPA result
		var opaResult OPAResponse
		if err := json.NewDecoder(resp.Body).Decode(&opaResult); err != nil {
			log.Printf("Failed to parse OPA response: %v", err)
		}
		resp.Body.Close()

		// Print the result
		fmt.Printf("LoanID: %s | EUR Value: %.2f | Rule 1 Pass: %v\n", loan.LoanID, loan.LoanValueEUR, opaResult.Result.Rule1Pass)

		rowCount++
		// Stop after 5 rows for testing purposes
		if rowCount >= 10 {
			break
		}
	}
}
