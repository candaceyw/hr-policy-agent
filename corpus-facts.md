# Northwind Robotics — canonical policy facts

Internal reference (not part of the policy corpus). Every concrete number that
appears in `corpus/` is listed here so the documents stay consistent with each
other and with `mock_data/`. Use this file when writing evaluation gold answers.

## Company
- Northwind Robotics, Inc. — ~650 employees, robotics hardware + software.
- US HQ: Austin, TX. US offices: Austin, Seattle, New York, San Francisco, Denver, Chicago, Miami.
- International entity: Northwind Robotics Ireland (Dublin).
- Legal entities: "Northwind Robotics US", "Northwind Robotics Ireland".
- Standard workweek: 40 hours. Standard business hours: 09:00–17:00 local.
- Core collaboration hours (meetings/availability): 10:00–15:00 local.
- People Operations owns HR policy. Escalation lead: Director of People Operations.

## PTO and sick time (doc 02)
- Full-time accrual: **10.0 hours/month** (15 days/year). Begins on day one.
- Part-time accrual: prorated by schedule; a half-time schedule accrues **5.0 hours/month**.
- Not eligible: contractors, interns, temporary workers (unless engagement says so).
- Year-end carryover cap: **40 hours** full-time / **20 hours** part-time. Excess is forfeited unless local law requires otherwise.
- Minimum increment: **4 hours** (half day).
- Notice: **2 weeks** for 3+ consecutive days; **30 days** for 5+ consecutive days.
- Manager decision target: **3 business days** after the request.
- Unused PTO is paid out on separation only where state law requires it.
- Sick time: where a state/city sick-leave law applies it is tracked separately; otherwise sick time is drawn from the PTO balance.

## Holidays (doc 03)
- **9 paid company holidays/year**: New Year's Day, Martin Luther King Jr. Day, Memorial Day, Juneteenth, Independence Day, Labor Day, Thanksgiving Day, Day after Thanksgiving, Christmas Day.
- **2 floating holidays/year**, prorated by hire date, no carryover, no payout.
- Company closure days (weather/emergency) are paid for scheduled employees.

## Remote and hybrid work (docs 04, 05)
- Hybrid default for office-assigned roles: **minimum 2 days/week onsite**.
- Fully remote requires **Director-level approval**; re-reviewed every **12 months**.
- Minimum home internet: **25 Mbps** down.
- Company-managed device + MFA required; see doc 06.
- Domestic out-of-state: trips **≤ 30 days** need manager notice only. **31+ days** need People Ops + Payroll review before travel.
- A new work state is established after **30 days** in that state → triggers payroll registration.
- International incidental work: **≤ 10 business days/year** with manager + People Ops approval. More requires Legal + entity review.
- Restricted-country list is maintained by Legal/Security; no company work from those locations.

## Expenses and travel (docs 07, 08)
- Submit expense reports within **30 days** of the expense date.
- Itemized receipt required for any expense **≥ $25**.
- Meal per diem: **$75/day** standard US cities, **$100/day** designated high-cost cities. No alcohol.
- Personal-vehicle mileage: **IRS standard rate (70¢/mile for the current year)**.
- Airfare: economy for flights **under 6 hours**; premium economy allowed for **6+ hour** flights with manager approval. No first/business class without VP approval.
- Lodging cap: **$250/night** standard, **$350/night** high-cost cities.
- Advance written approval required for: any single purchase **≥ $500**, and any trip with total cost **≥ $1,000**.
- Reimbursements are paid with the next regular payroll run after approval.

## Equipment and onboarding (doc 11)
- Standard new-hire kit: laptop, external monitor, keyboard, mouse, headset, docking station.
- One-time home-office setup stipend for approved remote/hybrid employees: **$500** (chair, desk accessories, etc.).
- Monthly connectivity stipend for fully remote employees: **$50**.
- Laptop refresh cycle: **every 3 years**.
- Equipment return on separation: within **10 business days**.
- Onboarding must be completed within the first **5 business days** (policy acknowledgment, security setup, payroll, benefits).

## Data security (doc 06) and information classification (doc 17)
- MFA mandatory on all company systems. Password manager required. No password reuse.
- Full-disk encryption required. Screen auto-lock: **10 minutes**.
- Report suspected incidents to security@northwindrobotics.example within **1 hour**.
- Classification tiers: **Public, Internal, Confidential, Restricted**.
- Confidential/Restricted data may only be handled on company-managed devices and approved systems. No company data in personal cloud storage.
- Restricted data (e.g. customer PII, security keys, unreleased financials) requires named-approver access and encryption in transit and at rest.

## Benefits (doc 09)
- Eligible: employees working **30+ hours/week**. Part-time under 30 hrs generally ineligible except where law requires. Contractors/interns ineligible.
- Coverage effective: **first of the month after 30 days** of employment.
- Open enrollment: every **November**, elections effective **January 1**.
- Qualifying life event: **30 days** to make changes.
- Medical plans: **PPO** and **HDHP** (HDHP pairs with an HSA). Dental and vision optional.
- 401(k): eligible after **90 days**. Company match: **100% of the first 4%** of pay. Immediate vesting.
- FSA: elect up to the **IRS annual maximum ($3,200 for the current plan year)**.
- `eligibility_status` values in mock data: `eligible`, `pending`, `ineligible`.

## Leave of absence (doc 10) and parental leave (doc 15)
- Job-protected unpaid leave: up to **12 weeks** for employees who have worked **12 months and 1,250 hours**.
- Company paid parental leave: **12 weeks** for birth, adoption, or foster placement; same for primary and secondary caregivers; after **6 months** of service. Must be taken within **12 months** of the event.
- Short-term disability: **60% of pay**, up to **12 weeks**, after a **7-day** waiting period.
- Medical documentation due within **15 days** of a leave request.
- Bereavement: up to **5 days** immediate family, up to **2 days** extended family.
- Jury duty: paid up to **10 days/year**.
- Military leave: per USERRA.

## Compensation and payroll (doc 13)
- Pay schedule: **semi-monthly** (15th and last day of the month).
- Non-exempt overtime: **1.5×** for hours over **40/week**, manager pre-approval required.
- Timesheets due by **10:00 the business day after** the pay period closes.
- Annual merit cycle: increases effective **April 1**.
- Referral bonus: **$2,000**, paid after the referred hire completes **90 days**.
- `exempt_status` in mock data: `exempt` (no overtime) / `non_exempt` (overtime eligible).

## Performance and development (doc 14)
- Reviews: **mid-year check-in in June**, **annual review in December**. Rating scale **1–5**.
- Performance improvement plan (PIP): **30–60 days** minimum.
- Tuition / professional development reimbursement: up to **$2,000/year** with manager approval; prorated for part-time.
- One company-paid domestic conference per year with approval.

## Workplace conduct and grievance (doc 12)
- Report acknowledged within **2 business days**.
- Investigation target: **30 days**.
- Appeal of an outcome: within **10 business days** to the Director of People Operations.

## Health and safety (doc 16)
- Report a workplace injury within **24 hours**.
- Ergonomic assessment available on request; remote workspace self-check **annually**.
- Workers' compensation covers work-related injury regardless of location.

## mock_data alignment notes
- `office_locations.json` must include `chicago-hq` (E-1005, IL) and `miami-hq` (E-1013, FL) — added.
- `E-1013` is `full_time`; PTO accrual corrected to `10.0`/month to match the full-time rate.
- Part-time example: `E-1006` accrues `5.0`/month — consistent with the prorated part-time rate.
