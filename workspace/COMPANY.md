# COMPANY.md - Harbour Lane Trading Ltd (海港貿易有限公司)

Hong Kong trading company, 18 staff. Imports electronic components from Shenzhen/Dongguan, resells to HK and SE Asia.
Functional currency HKD (also RMB, USD). FY = calendar year. BR No. 63817254.
Office: Room 1203, 12/F, Wing Tat Commercial Centre, 88 Hoi Bun Road, Kwun Tong, Kowloon, Hong Kong. Warehouse: Unit 9A, 9/F, Oceanic Godown Centre, 21 Sheung Yuet Road, Kowloon Bay, Kowloon.
Bank: Victoria Harbour Bank Limited a/c 088-412-09375-1.

## People
- David Wong - Director / owner. Approves anything above HK$50,000.
- Anna Chan - Finance Manager. Month-end close, forecast, budget.
- Ken Lau - Accounts Clerk. Invoice entry, payments run.

## Conventions
- Account codes (ledger/chart_of_accounts.csv): 200 Sales, 310 COGS (all stock purchases), 425 Freight,
  469 Rent, 471 Building mgmt, 473 R&M, 445 Electricity, 485 Software. Facilities = 445 + 469 + 471 + 473.
- Invoice register: sheets/invoice_register.xlsx, one row per supplier invoice, amount_hkd = amount x month fx rate.
- Invoice PDFs filed under docs/invoices/YYYY-MM/; new ones arrive in docs/invoices/inbox/.

## Suppliers
| ID | Name | Ccy | Known domain | Terms | Contract |
|---|---|---|---|---|---|
| S01 | Shenzhen Parts Co., Ltd. 深圳市零件有限公司 | RMB | shenzhenparts.com | 60 days | docs/contracts/S01_supply_agreement_2026.pdf |
| S02 | Dongguan Precision Electronics Co., Ltd. 东莞精密电子有限公司 | USD | dg-precision.cn | 30 days | docs/contracts/S02_supply_agreement_2026.pdf |
| S03 | Pacific Freight Logistics Ltd  | HKD | pacfreight.com.hk | 30 days | docs/contracts/S03_freight_rate_card_2026.pdf |
| S04 | Kowloon Bay Properties Ltd 九龍灣置業有限公司 | HKD | kbproperties.com.hk | 7 days | docs/contracts/S04_lease_2024_2026.pdf |
| S05 | CloudDesk Inc.  | USD | clouddesk.io | 15 days | docs/contracts/S05_clouddesk_order_form.pdf |

## Policies
- Price tolerance: invoice unit price may not exceed the contract price by more than 1%. Otherwise hold.
- Approval: any invoice or payment above HK$50,000 needs D. Wong's approval.
- Payments only to bank accounts on the supplier master. Bank changes need written confirmation by the
  supplier's authorised signatory plus a call-back to a known number. Email alone is never enough.
- Duplicates: never enter an invoice whose number or supplier+amount matches an existing entry.

## Forecast assumptions (2027-2028)
- Rent assumed flat at HK$80,000 in 2027 pending lease renewal (D. Wong, Aug 2026).
- Revenue +4% p.a.; headcount flat at 18; FX USD 7.80, RMB 1.08.
- Source: docs/emails/2026-08-14_david_forecast_assumptions.eml
