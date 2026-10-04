# COMPANY.md - Lantau Peak Family Office Ltd (大嶼峰家族辦公室有限公司)

Hong Kong single-family office for the Cheung family. Manages about US$350M for the Cheung Family Trust: a listed
portfolio at Lion Rock Private Bank (custodian), four private fund commitments, two rental flats in Hong Kong,
an art collection and the family's expenses (staff, school fees, travel and aviation, insurance).
Functional currency HKD (also USD, RMB). FY = calendar year. BR No. 74120583.
Office: Suite 3802, 38/F, Harbour Crest Tower, 1 Harbour View Street, Central, Hong Kong.
Bank: Victoria Harbour Bank Limited a/c 088-517-22046-8 (operating account; fund calls, fees and family bills are paid from here).
Email domain: lantaupeak.com.hk

## People
- Victoria Cheung - Principal (family member). Approves anything above HK$500,000.
- Raymond Ho - CFO. Forecast, budget, investment reporting.
- Grace Lam - Fund Accountant. Month-end close, fund capital accounts, invoice register.
- Jason Yip - Accounts Clerk. Document intake, payments run.

## Conventions
- Account codes (ledger/chart_of_accounts.csv): capital calls -> 150 (Investments - Private Funds);
  fund management fee notices -> 455 (Fund management fees); 260 Rental income; 433 Insurance; 471 Property management;
  473 Repairs; 475 Building management & rates. Property = 471 + 473 + 475.
- Invoice register: sheets/invoice_register.xlsx, one row per payable document (capital call, fee notice, invoice),
  amount_hkd = amount x month fx rate.
- Fund commitments: sheets/commitments.xlsx (commitment, called to date, unfunded).
- Payable PDFs filed under docs/invoices/YYYY-MM/; new ones arrive in docs/invoices/inbox/.

## Counterparties
| ID | Name | Ccy | Known domain | Terms | Contract |
|---|---|---|---|---|---|
| S01 | Pearl River Growth Fund II LP 珠江成长基金二期 | RMB | prgfund.com | 14 days | docs/contracts/S01_subscription_agreement_2024.pdf |
| S02 | Harbourview Capital Partners III LP  | USD | harbourviewcap.com | 10 days | docs/contracts/S02_side_letter_2024.pdf |
| S03 | Peak Estates Property Management Ltd 峰譽物業管理有限公司 | HKD | peakestates.com.hk | 30 days | docs/contracts/S03_property_management_agreement_2026.pdf |
| S04 | Halcyon Re Asia Ltd  | HKD | halcyonre.com.hk | 0 days | docs/contracts/S04_lease_2024_2026.pdf |
| S05 | Meridian Fine Art Insurance Ltd  | USD | meridianfineart.com | 15 days | docs/contracts/S05_art_insurance_policy_2025.pdf |

## Policies
- Price tolerance: an invoice unit price or fee rate may not exceed the contract or side-letter rate by more than 1%. Otherwise hold.
- Approval: any payment above HK$500,000 needs V. Cheung's approval.
- Payments only to bank accounts on the counterparty master. Wire-instruction changes need a signed letter from the
  counterparty's authorised signatory plus a call-back to a number on file. Email alone is never enough.
- Duplicates: never enter a document whose number or counterparty+amount matches an existing entry.

## Forecast assumptions (2027-2028)
- Rental income for Flat 12A Repulse Bay (Halcyon Re lease) assumed flat at HK$95,000/month in 2027-2028 pending lease renewal (R. Ho, Aug 2026).
- Forecast rent cells: named range RENT_INCOME_FORECAST in sheets/forecast_2027_2028.xlsx.
- Portfolio income +3% in 2028; staff flat (4 office + 6 household); FX USD 7.80, RMB 1.08.
- Source: docs/emails/2026-08-14_raymond_forecast_assumptions.eml
