# SNEC PV+ 2026 — Web Research Summary

**Official site:** [https://pv.snec.org.cn/](https://pv.snec.org.cn/)  
**Edition:** 19th SNEC PV+ International Photovoltaic Power Generation and Smart Energy Exhibition & Conference  
**Dates (public):** 3–5 June 2026 (visitor hours 09:00–17:00 / last day until 14:00)  
**Venue:** National Exhibition and Convention Center (NECC), Shanghai — “four-leaf clover” layout, 14 halls  
**Build / move-in:** 31 May – 2 June 2026 | **Teardown:** 5 June from 14:00  

---

## Floor plan (展位图)

### What is published today

| Asset | Status | Local path |
| :--- | :--- | :--- |
| **Overview map (NECC clover)** | Official **2025** layout image on 2026 site | `floor_plans/00_overview_NECC_clover.jpg` |
| **Per-hall booth layouts (1.1H–8.2H, GC)** | Official **2025** hall PDFs-as-JPG (June 2025 upload) | `floor_plans/1.1H.jpg` … `floor_plans/8.2H.jpg`, `GC_central_plaza.jpg` |
| **Interactive map popup** on [企业展厅 list](https://pv.snec.org.cn/hallIndex/companyList) | Still uses **2024** image set | See `floor_plans/README` note below |
| **2026 hall/company list table** on same page | **Empty** (“暂无数据”, 0 rows) | Booth assignments not loaded server-side yet |
| **Official PDFs** | 2026 exhibitor handbook + venue entry guide | `official_SNEC2026_exhibitor_handbook.pdf`, `official_2026_venue_guide.pdf`, `official_commercial_guide.pdf` |

### Official web sources

- **展位图 channel:** [pv.snec.org.cn/channel/d97fecea-5bef-efad-a767-a5f2e217f55e](https://pv.snec.org.cn/channel/d97fecea-5bef-efad-a767-a5f2e217f55e) — overview + per-hall images (2025-dated CDN files, valid for NECC geometry).
- **Download center:** [展览项目相关文件](https://pv.snec.org.cn/channel/fef8ef54-7320-2cdf-b312-5bdcdd1213bb) — includes *SNEC2026参展手册*, *2026进馆指南*, transport guide.
- **Times & venue:** [时间与地点](https://pv.snec.org.cn/channel/Time_venue)

### Hall list (NECC)

Ground (0 m): **1.1H, 2.1H, 3H, 4.1H, 5.1H, 6.1H, 7.1H, 8.1H**, NH, **GC** (central plaza)  
Upper (16 m): **1.2H, 2.2H, 4.2H, 5.2H, 6.2H, 7.2H, 8.2H**

See `expo_map_guide.md` for sector-to-hall orientation (equipment, materials, trackers, inverters/ESS, tier-1 modules, etc.) and metro/taxi entry tips.

---

## Exhibitor list

### Dataset in this folder

| File | Records | Source API |
| :--- | ---: | :--- |
| `exhibitors_list.csv` | **2,341** companies | `POST https://pv.snec.org.cn/api/getInviteCompanyList` |

**Columns:** `company_name_cn`, `company_name_en`, `hall`, `booth`, `booth_display`, `invite_company_id`, `invite_company_info_id`, `exb_contract_id`, `company_logo_url`, `source`, `year`

### Important limitation (May 2026)

- All **2,341** rows were returned with **empty `PavilionCode` and `BoothNo`** from the public API (`ExamineStateCode: audited`, `Year: 2026`).
- The [hallIndex/companyList](https://pv.snec.org.cn/hallIndex/companyList) printable table also shows **0 rows**.
- **Booth numbers on the online 企业展厅** (e.g. “1.2H A110”) appear only on featured/homepage cards, not yet in the bulk export.
- **Next step when organizers publish stands:** re-pull `getInviteCompanyList` or scrape `hallIndex/companyList`; cross-reference per-hall JPGs in `floor_plans/`.

### Other useful directories on the site

- **Searchable online directory:** [exHallList?type=company](https://pv.snec.org.cn/exHallList?type=company) — same backend as CSV.
- **Company detail pages:** `https://pv.snec.org.cn/companyDetail/{invite_company_info_id}`
- **Products:** ~2,046 audited products via `/api/getAllProductInfoList` (separate from booth map).

---

## Co-located / related events (from homepage)

- **SNEC ES+** (storage & battery) — co-located June 2026 at NECC  
- **SNEC H2+** (hydrogen) — dedicated show October 2026 at SNIEC  
- Scale cited on site / press: **300,000+ m²**, **3,500+** exhibitors (marketing figures)

---

## Files in `g:\SNEC-RESEARCH`

| Path | Description |
| :--- | :--- |
| `SNEC_2026_RESEARCH.md` | This summary |
| `expo_map_guide.md` | Venue layout, hall sectors, transport |
| `sections_analysis.md` | PV / battery / hydrogen sector notes |
| `floor_plans/` | Downloaded official hall maps (2025 CDN, NECC layout) |
| `exhibitors_list.csv` | Full 2026 exhibitor names (2,341) |
| `official_*.pdf` | Handbook, venue guide, commercial guide |
| `snec_expo_floor_plan.pdf` | Earlier placeholder (homepage HTML export — not a real PDF) |

---

*Research date: 18 May 2026. Data pulled from public endpoints on pv.snec.org.cn; no login required.*
