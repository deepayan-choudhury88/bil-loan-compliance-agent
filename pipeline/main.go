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
	"sync"
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

type SuggestionRequest struct {
	CompanyName  string  `json:"company_name"`
	LoanValue    float64 `json:"loan_value"`
	CurrentAsset string  `json:"current_asset"`
}

type SuggestionResponse struct {
	Status         string  `json:"status"`
	SuggestedAsset string  `json:"suggested_asset,omitempty"`
	AssetValue     float64 `json:"asset_value,omitempty"`
	Reason         string  `json:"reason"`
}

// LoanRecord is one row of the full portfolio report handed off to the
// Streamlit UI (app.py's load_data_from_custom_source() reads this back).
// Field names/types follow the EXPORT_COLUMNS schema documented in app.py.
type LoanRecord struct {
	LoanID        string  `json:"loan_id"`
	Company       string  `json:"company"`
	Country       string  `json:"country"`
	Currency      string  `json:"currency"`
	LoanValue     float64 `json:"loan_value"`
	LoanValueEUR  float64 `json:"loan_value_eur"`
	AssetType     string  `json:"asset_type"`
	AssetValue    float64 `json:"asset_value"`
	AssetValueEUR float64 `json:"asset_value_eur"`
	CoveragePct   float64 `json:"coverage_pct"`
	Rule1Pass     bool    `json:"rule1_pass"`
	Rule2Pass     bool    `json:"rule2_pass"`
	Rule3Pass     bool    `json:"rule3_pass"`
	OverallPass   bool    `json:"overall_pass"`
	ReviewState   string  `json:"review_state"`
	// ExpectedCurrency is the currency Rule 2 requires for this loan's HQ
	// country (see countryToCurrency). Deterministic - no AI call needed -
	// so the UI can show it as an instant "fix" hint for Rule 2 failures.
	ExpectedCurrency      string  `json:"expected_currency,omitempty"`
	AISuggestedAsset      string  `json:"ai_suggested_asset,omitempty"`
	AISuggestedAssetValue float64 `json:"ai_suggested_asset_value,omitempty"`
	AISuggestionReason    string  `json:"ai_suggestion_reason,omitempty"`
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

func hasRule3Violation(violations []string) bool {
	return violatesRule(violations, "Rule 3 Failed")
}

// violatesRule reports whether any violation message mentions the given
// rule label (e.g. "Rule 1 Failed").
func violatesRule(violations []string, ruleLabel string) bool {
	for _, violation := range violations {
		if strings.Contains(violation, ruleLabel) {
			return true
		}
	}
	return false
}

// reportOutputPath is where the full per-loan report is written for the
// Streamlit UI to read (see app.py's load_data_from_custom_source()).
const reportOutputPath = "../data/compliance_report.json"

func callSuggestionAPI(client *http.Client, loan LoanInput) (*SuggestionResponse, error) {
	apiURL := os.Getenv("SUGGESTION_API_URL")
	if apiURL == "" {
		apiURL = "http://127.0.0.1:8000/suggest"
	}

	reqBody := SuggestionRequest{
		CompanyName:  loan.CompanyName,
		LoanValue:    loan.LoanValue,
		CurrentAsset: loan.AssetDescription,
	}

	payload, err := json.Marshal(reqBody)
	if err != nil {
		return nil, err
	}

	resp, err := client.Post(apiURL, "application/json", bytes.NewBuffer(payload))
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("suggestion API status=%d body=%s", resp.StatusCode, string(body))
	}

	var out SuggestionResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return &out, nil
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
	var allLoans []LoanRecord

	// CONCURRENCY UPGRADES:
	var wg sync.WaitGroup
	var mu sync.Mutex
	// Semaphore to limit concurrent HTTP requests to 50 so we don't crash OPA
	sem := make(chan struct{}, 50)

	// Reusable HTTP client so we don't exhaust local ports
	client := &http.Client{
		Transport: &http.Transport{
			MaxIdleConnsPerHost: 50,
		},
		Timeout: 5 * time.Second,
	}

	// AI suggestions call a real LLM (Azure OpenAI) per Rule-3 failure, which
	// is far too slow to do in bulk for a live demo (thousands of real network
	// calls). Off by default so the pipeline stays fast; the Streamlit UI
	// fetches suggestions on-demand instead, one loan at a time. Set
	// ENABLE_AI_SUGGESTIONS=true to restore the old bulk behavior.
	enableAISuggestions := os.Getenv("ENABLE_AI_SUGGESTIONS") == "true"
	if enableAISuggestions {
		fmt.Println("⚠️  ENABLE_AI_SUGGESTIONS=true - calling the AI suggestion API for every Rule 3 failure (slow).")
	} else {
		fmt.Println("ℹ️  AI suggestions are fetched on-demand from the Streamlit UI (fast mode). Set ENABLE_AI_SUGGESTIONS=true to pre-compute them all in bulk.")
	}

	for {
		record, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			continue
		}

		// Parse row variables safely outside the goroutine
		loanID := record[0]
		companyName := record[1]
		hqCountry := record[2]
		assetDesc := record[3]
		assetValue, _ := strconv.ParseFloat(record[4], 64)
		assetOwner := record[5]
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

		// Asset value is expressed in the same currency as the loan (see
		// policy/compliance.rego's Rule 3 comment), so it converts with the
		// same FX rate.
		var assetValueEUR float64
		if currency == "EUR" {
			assetValueEUR = assetValue
		} else {
			assetValueEUR = assetValue / rates[currency]
		}

		expectedCurrency, exists := countryToCurrency[hqCountry]
		if !exists {
			expectedCurrency = "UNKNOWN"
		}

		// Start a Goroutine for this row
		wg.Add(1)
		sem <- struct{}{} // Claim a slot in the semaphore (max 50)

		go func(lID, cName, hq, aDesc, aOwner, cur, expCur string, aVal, lVal, lValEUR, aValEUR float64) {
			defer wg.Done()
			defer func() { <-sem }() // Release the slot when done

			loanInput := LoanInput{
				LoanID:           lID,
				CompanyName:      cName,
				HQCountry:        hq,
				AssetDescription: aDesc,
				AssetValue:       aVal,
				AssetOwner:       aOwner,
				LoanValue:        lVal,
				LoanCurrency:     cur,
				LoanValueEUR:     lValEUR,
				ExpectedCurrency: expCur,
			}

			reqBody := map[string]interface{}{"input": loanInput}
			jsonData, _ := json.Marshal(reqBody)

			resp, err := client.Post("http://localhost:8181/v1/data/compliance", "application/json", bytes.NewBuffer(jsonData))
			if err != nil {
				return
			}

			var opaResult OPAResponse
			if err := json.NewDecoder(resp.Body).Decode(&opaResult); err != nil {
				resp.Body.Close()
				return
			}
			resp.Body.Close()

			var suggestion *SuggestionResponse
			var suggestionErr error
			if enableAISuggestions && !opaResult.Result.Allow && hasRule3Violation(opaResult.Result.Violations) {
				suggestion, suggestionErr = callSuggestionAPI(client, loanInput)
			}

			rule1Pass := !violatesRule(opaResult.Result.Violations, "Rule 1")
			rule2Pass := !violatesRule(opaResult.Result.Violations, "Rule 2")
			rule3Pass := !violatesRule(opaResult.Result.Violations, "Rule 3")
			reviewState := "Unreviewed"
			if opaResult.Result.Allow {
				reviewState = "Clean / Passed"
			}

			loanRecord := LoanRecord{
				LoanID:           lID,
				Company:          cName,
				Country:          hq,
				Currency:         cur,
				LoanValue:        lVal,
				LoanValueEUR:     lValEUR,
				AssetType:        aDesc,
				AssetValue:       aVal,
				AssetValueEUR:    aValEUR,
				CoveragePct:      aValEUR / lValEUR * 100,
				Rule1Pass:        rule1Pass,
				Rule2Pass:        rule2Pass,
				Rule3Pass:        rule3Pass,
				OverallPass:      opaResult.Result.Allow,
				ReviewState:      reviewState,
				ExpectedCurrency: expCur,
			}
			if suggestion != nil && suggestion.Status == "success" {
				loanRecord.AISuggestedAsset = suggestion.SuggestedAsset
				loanRecord.AISuggestedAssetValue = suggestion.AssetValue
				loanRecord.AISuggestionReason = suggestion.Reason
			} else if suggestion != nil {
				loanRecord.AISuggestionReason = suggestion.Reason
			}

			// MUTEX LOCK: Safely update the shared report variables
			mu.Lock()
			report.Portfolio[cName] += lValEUR
			report.TotalLoansChecked++
			allLoans = append(allLoans, loanRecord)

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

				details := fmt.Sprintf("Loan Value: %.2f %s | Asset Value: %.2f %s | HQ: %s", lVal, cur, aVal, cur, hq)
				if suggestionErr != nil {
					details += fmt.Sprintf(" | Suggestion Error: %v", suggestionErr)
				} else if suggestion != nil {
					if suggestion.Status == "success" {
						details += fmt.Sprintf(
							" | Suggested Asset: %s (%.2f) | Suggestion Reason: %s",
							suggestion.SuggestedAsset,
							suggestion.AssetValue,
							suggestion.Reason,
						)
					} else {
						details += fmt.Sprintf(" | Suggested Asset: N/A | Suggestion Reason: %s", suggestion.Reason)
					}
				}

				report.FailedLoans = append(report.FailedLoans, FailedLoan{
					LoanID:      lID,
					Company:     cName,
					Violations:  violationsStr,
					LoanDetails: details,
				})
			}
			mu.Unlock() // MUTEX UNLOCK
		}(loanID, companyName, hqCountry, assetDesc, assetOwner, currency, expectedCurrency, assetValue, loanValue, loanValueEUR, assetValueEUR)
	}

	fmt.Println("Processing all rows concurrently... please wait.")
	wg.Wait() // Wait for all goroutines to finish

	reportJSON, err := json.MarshalIndent(allLoans, "", "  ")
	if err != nil {
		log.Fatalf("Failed to encode report: %v", err)
	}
	if err := os.WriteFile(reportOutputPath, reportJSON, 0o644); err != nil {
		log.Fatalf("Failed to write report: %v", err)
	}
	fmt.Printf("📄 Wrote %d loan records to %s (used by the Streamlit UI)\n", len(allLoans), reportOutputPath)

	fmt.Println("✅ Success! Compliance processing completed.")
}
