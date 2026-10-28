# US federal archives: public-domain Vietnam War moving images (1945-1975), and how to find and download them programmatically

Research date: 2026-10-27. Some findings come from live API calls made that day. They are marked "live check" and cite the exact URL queried, so the report writer can reproduce them. Anything not directly supported by a source is listed under Inferences or Gaps.

---

## Q1. NARA Catalog API v2/v3: endpoints, API key, query parameters, restriction fields, download URLs (plus a bulk route that needs no key)

### Takeaway
The NARA Catalog API (v2, plus a newer v3 spec) needs a free API key in the `x-api-key` header. You get one by emailing Catalog_API@nara.gov, and the default limit is 10,000 queries a month. It supports filters such as `typeOfMaterials=Moving Images`, `recordGroupNumber`, `startDate`/`endDate` and `availableOnline`. Each record carries `useRestriction.status` and `accessRestriction.status`, and gives the file links in `digitalObjects[].objectUrl`.

There are also two routes with no key, both checked live on 2026-10-27:
- **The whole catalog as JSONL** on the AWS Open Data bucket `nara-national-archives-catalog`. Anonymous listing and reading work. Its `objectUrl`s (`s3.amazonaws.com/NARAprodstorage/lz/...`) are **stale** and return 403.
- **The catalog web app's internal proxy** for single-record lookups: `https://catalog.archives.gov/proxy/records/search?naId=N` returns JSON with the **current** `objectUrl` (`https://catalog.archives.gov/medialz/...`). Those media URLs download without a key (HTTP 200, video/mp4). Keyword or filter searches through the proxy returned an error page that day, and the endpoint is undocumented.

### Cited Findings
**API access and key**
- The API "requires the use of an API key". Pass it as header `x-api-key: API_KEY`, for example `curl 'https://catalog.archives.gov/api/v2/records/search?q=constitution' --header 'x-api-key: API_KEY'`. "Please contact O&M at Catalog_API@nara.gov for an API Key." (Swagger spec v2 `info.description`) — [NARA Catalog API v2 swagger.json](https://catalog.archives.gov/api/v2/swagger.json); [Swagger UI](https://catalog.archives.gov/api/v2/api-docs/)
- To request a key, email Catalog_API@nara.gov with your name and the email address to associate with it. Read-only keys query the data. Read-write keys (tags, transcriptions, comments) need a Catalog account. — [usnationalarchives/Catalog-API on GitHub](https://github.com/usnationalarchives/Catalog-API)
- Default rate limit is 10,000 queries per month per key. Going over blocks the key until the first of the next month, and higher limits can be requested by email. v2 was released in September 2022. — [GitHub Catalog-API](https://github.com/usnationalarchives/Catalog-API)
- A v3 spec also exists, with `GET /v3/records/search` and almost the same parameters. Its `info.version` is 0.3.0. — [NARA Catalog API v3 swagger.json](https://catalog.archives.gov/api/v3/swagger.json)
- **Live check:** `GET https://catalog.archives.gov/api/v2/records/search?q=vietnam&typeOfMaterials=Moving%20Images` with no key returned HTTP 200 but `text/html` (the catalog web app shell, "X-Cache: Error from cloudfront"), not JSON. A keyless call therefore fails without an obvious error, and code must check the Content-Type. — live check against [the search endpoint](https://catalog.archives.gov/api/v2/records/search?q=vietnam&typeOfMaterials=Moving%20Images)

**Search parameters** (exact names from the v2 spec `components.parameters`) — [v2 swagger.json](https://catalog.archives.gov/api/v2/swagger.json)
- `q`: query string; accepts AND/OR/NOT, wildcards `*` and exact phrases `""`.
- `typeOfMaterials`: one of `Photographs and other Graphic Materials`, `Moving Images`, `Textual Records`, `Architectural and Engineering Drawings`, `Data Files`, `Maps and Charts`, `Sound Recordings`, `Artifacts`.
- `availableOnline` (boolean): "records at the Item and File Unit levels which contain digital objects and can be viewed online".
- `levelOfDescription`: `recordGroup` | `collection` | `series` | `fileUnit` | `item`.
- `recordGroupNumber`: searches `record.recordGroupNumber` and `record.ancestors.recordGroupNumber`. `collectionIdentifier` works the same way.
- `ancestorNaId`: limits results to descendants of one series or file unit (the best way to scan a single series such as 428-NPC).
- `startDate` / `endDate`: YYYY-MM-DD, YYYY-MM or YYYY, and both must use the same format. They search `productionDates`, `copyrightDates`, `releaseDates`, etc. Only ancestors at **series** level have their dates searched. `exactDate` takes a single YYYY-MM-DD.
- `objectType`: matches `record.digitalObjects.objectType`; comma-separated values allowed.
- `localIdentifier`: e.g. "428-NPC-37149". `geographicReference` matches geographic subject headings. `creators` matches creator headings.
- `[fieldName]_exists=true|false`: works on any field, including nested ones (e.g. `ancestors.inclusiveEndDate_exists=true`). `[fieldName]_is_not=value` excludes a value.
- `page`, `limit`, `searchAfter` (deep paging past 10,000 results: start with `searchAfter=*`, then pass the sort array of the last item in `body.hits.hits`), `sourceIncludes` (trims `_source.record` to the fields you name), `abbreviated=true`.
- Other endpoints: `GET /records/parentNaId/{parentNaId}` (immediate children of a series or file unit), `GET /online-availability/naId/{naId}`, and `GET /extractedText/{naId}`.

**Restriction fields** (schema definitions in the v2 spec) — [v2 swagger.json](https://catalog.archives.gov/api/v2/swagger.json)
- `useRestriction`: `{status, note, specificUseRestrictions[]}`. The spec's examples for `status` are "Restricted - Fully" and "Unrestricted". Its example `note` is "Copyright held by RKO General Inc.". `specificUseRestriction` examples are "Copyright" and "Donor Restrictions".
- `accessRestriction`: `{status, note, specificAccessRestrictions[{restriction, securityClassification}]}`. Status examples are "Restricted - Partly", "Restricted - Possibly" and "Unrestricted".
- NARA defines five allowed Use Restriction Status values. "Restricted - Fully": *all* materials have a copyright, donor or other use restriction. "Restricted - Partly": *some* do. "Restricted - Possibly": materials "*may have* a use restriction". "Undetermined": "*unknown*". "Unrestricted": "no copyright, donor, or other use restrictions". — [NARA LCDRG Use Restriction Status authority list](https://www.archives.gov/research/catalog/lcdrg/authoritylists/uselist.html)
- NARA tells users to check the "Use Restrictions" heading in the **series** description, and says "The National Archives does not confirm the copyright status of photographs" and "It is the user's responsibility to obtain all necessary clearances". It also states "Copies of Federal records, as part of the public domain, are equally available to all." — [NARA "Publish photos" guidance](https://www.archives.gov/research/publish-photos)

**Digital objects / download URLs**
- `digitalObjects[]` items have `objectUrl` ("the file containing the access version"), `objectFilename`, `objectFileSize` (bytes), `objectType`, `objectId`, `thumbnailUrl` and `objectDesignator`. The spec's example host is `https://nara-media-001.s3.amazonaws.com/...`. — [v2 swagger.json](https://catalog.archives.gov/api/v2/swagger.json)
- **Live check (open data RG 428 JSONL):** Vietnam film items have `objectType: "Audio/Visual File (MP4)"` and objectUrls in the form `https://s3.amazonaws.com/NARAprodstorage/lz/mopix/428/NPC/428-npc-37149.mp4`. The median file size across 578 Vietnam MP4s was about 151 MB, and the largest about 463 MB. — live scan of [s3://nara-national-archives-catalog/descriptions/record-groups/rg_428/](https://nara-national-archives-catalog.s3.us-east-2.amazonaws.com/?list-type=2&prefix=descriptions/record-groups/rg_428/)
- **Live check:** an unauthenticated GET (also tried with a ranged request, a catalog Referer, and the `s3.us-east-1`, virtual-host and upper-case variants) on those `NARAprodstorage` URLs returned **403 AccessDenied** on 2026-10-27, for both video and still-image objectUrls. — live check on `https://s3.amazonaws.com/NARAprodstorage/lz/mopix/428/NPC/428-npc-37149.mp4`
- **Live check (current media URLs):** the same record (NAID 85342, 428-NPC-37149) read live gives `objectUrl` = `https://catalog.archives.gov/medialz/mopix/428/NPC/428-npc-37149.mp4`. A HEAD on it returned **200, video/mp4, 178,131,217 bytes**. Mapping the open-data prefix `https://s3.amazonaws.com/NARAprodstorage/lz/` to `https://catalog.archives.gov/medialz/` worked for 428-NPC-38401 (200, 42,826,820 bytes, the same size as in the export). The guess failed for 111-LC because the live path is lower-case `.../mopix/111/lc/111-lc-46157.mp4`, so always take `objectUrl` from a live record. Older digitisations use another form, e.g. `https://catalog.archives.gov/medialive/77/6531/653177/content/arcmedia/cs/001/30829.wmv` (WMV). — live check on [proxy naId=85342](https://catalog.archives.gov/proxy/records/search?naId=85342) and [medialz URL](https://catalog.archives.gov/medialz/mopix/428/NPC/428-npc-37149.mp4)
- **Live check (keyless proxy):** `https://catalog.archives.gov/proxy/records/search?naId=<NAID>`, sent with a plain User-Agent, returned `application/json` in the structure `body.hits.hits[]._source.record` (the same record schema as the API). Tested on NAIDs 85342, 28784, 71583, 653177 and 643344. The same proxy with `q=vietnam&typeOfMaterials=Moving Images&availableOnline=true`, with `q=tonkin&recordGroupNumber=428`, and with `localIdentifier=428-NPC-38401` returned the HTML error page ("X-Cache: Error from cloudfront") that day. This endpoint is what the catalog web app uses internally and is not documented in the API docs. — live check on [catalog proxy](https://catalog.archives.gov/proxy/records/search?naId=28784)
- The project's own module (`<repository>\editvideo\pd_sources.py`, docstring, written 2026-10-27 by another session) records that NARA's media server delivered about 830 KB/s against about 25 KB/s from the IA mirror for the same film. It uses the same keyless proxy for `nara_record()`/`nara_search()` and cites 36 C.F.R. 1254.62 for "NARA does not certify copyright". — `<repository>\editvideo\pd_sources.py` (local project file, not a public source)

**Bulk catalog dataset (no key)**
- The National Archives Catalog is on the AWS Registry of Open Data at bucket `arn:aws:s3:::nara-national-archives-catalog` (us-east-2). The dataset is over 261 GB, with URLs for over 148 million digital objects. It is updated twice a year, and the catalog content is current as of March 1, 2026. Access commands: `aws s3 ls s3://nara-national-archives-catalog/ --no-sign-request` and `aws s3 sync s3://nara-national-archives-catalog/descriptions/record-groups/rg_1/ [dest] --no-sign-request`. The descriptions zip is 202 GB. — [NARA developer page: National Archives Catalog dataset](https://www.archives.gov/developer/national-archives-catalog-dataset); [AWS Registry listing](https://registry.opendata.aws/nara-national-archives-catalog/)
- **Live check:** an anonymous HTTPS listing works. Top-level prefixes are `authority-records/`, `backups/`, `descriptions/` and `zip/`. Record-group folders contain files named `rg_NNN-K.jsonl`, one JSON record per line, wrapped as `{"record": {...}}`. Sizes: RG 111 has 400 files (about 1.58 GB), RG 342 has 400 (about 0.94 GB), RG 428 has 400 (about 117 MB). Record keys include `accessRestriction`, `ancestors`, `audiovisual`, `digitalObjects`, `generalRecordsTypes`, `levelOfDescription`, `localIdentifier`, `naId`, `physicalOccurrences`, `productionDates`, `shotList`, `subjects`, `title`, `useRestriction` and `variantControlNumbers`. — live listing of [the bucket](https://nara-national-archives-catalog.s3.us-east-2.amazonaws.com/?list-type=2&delimiter=/)
- Note: the S3 `zip/` listing showed descriptions zips up to `nac_export_descriptions_2024-09-12.zip` (about 73 GB) at the top level. The NARA page names a newer `nac_export_descriptions_2026-09-14.zip` (202 GB), which may sit under a subfolder. — [NARA developer page](https://www.archives.gov/developer/national-archives-catalog-dataset); live listing of `zip/`

### Inferences
- Recommended pipeline:
  1. **Discovery** without a key: stream the open-data JSONL for RG 111, 127, 200, 306, 330, 342, 428 and 263. Keep records whose `generalRecordsTypes` includes "Moving Images" and that have `digitalObjects`, and filter by `productionDates` from 1954 to 1975 and by keywords. For RG 127 (about 12 GB of JSONL), download once and cache.
  2. **Freshness**: re-read each chosen record by NAID, through the keyless proxy (`/proxy/records/search?naId=`) or the keyed API, to get the current `useRestriction` and `objectUrl`.
  3. **Media**: fetch from the live `catalog.archives.gov/medialz/...` URL. Fall back to the Internet Archive mirror with the same local identifier (see Q3).
  4. **Search**: if keyword search is still needed, use the keyed API, since proxy searches failed on 2026-10-27.
- Export sizes per record group (live listing): RG 111 about 1.6 GB, RG 127 about 12.0 GB, RG 306 about 0.47 GB, RG 330 about 1.7 GB, RG 342 about 0.94 GB, RG 428 about 0.12 GB. `rg_200` is about 1 MB, so the Universal Newsreel probably sits under `descriptions/collections/` rather than `rg_200` (an inference).
- Because only ancestors at series level have their dates searched, and many 428-NPC items have no `productionDates` (one example record had `[]`), a strict `startDate`/`endDate` filter will silently drop undated items. Keyword-based Vietnam filters should run alongside the date filter.
- The 403 on `NARAprodstorage` is most likely because NARA moved public media delivery behind `catalog.archives.gov/medialz/` and `/medialive/`, while the March 2026 export still carries the old S3 URLs. This is an inference: the live record for the same item gives the new URL, and that URL works.
- The keyless proxy is undocumented and its search half failed on the test day. Treat it as a convenience that can break, and keep the keyed API as the supported route.
- `useRestriction` is often set at **series** level, not item level. Code must check the item first and then fall back to the series ancestor's `useRestriction`. The ancestors in the open data carry only some fields, so an API call on the series `naId` may be needed.

### Gaps
- I could not run an authenticated API call (no key). The JSON path `body.hits.hits[]._source.record` was observed only through the keyless proxy, and I assume the keyed API returns the same thing.
- I could not confirm whether `[fieldName]_is_not` accepts a value with spaces such as `useRestriction.status_is_not=Restricted - Fully`.
- No public NARA statement found on retiring `NARAprodstorage` URLs, on the `/medialz/` host, or on rate limits for the proxy or media hosts.
- It is unclear why proxy searches with `q=` failed on 2026-10-27 (outage, blocking or a change) while `naId=` lookups worked.

---

## Q2. Which NARA record groups and series hold Vietnam-era film, and what quality to expect

### Takeaway
The main unedited combat and documentary footage is in **111-LC** (Army, 1964-75, about 7,000 items), **127-R/127-G** (Marine Corps, 1964-75, about 3,500), **342-USAF** (Air Force, 1964-75, about 6,000) and **428-NPC** (Navy, 1961-75, about 3,500). Edited productions are in **111-DD** (DoD news releases), the Army "Big Picture" series, **428** edited films and **306** (USIA). The donated **Universal Newsreel** collection (UN-UN releases and 200-UN outtakes) runs to 1967.

Copies online are mostly SD access MP4s (about 640-655 x 480). Some newer uploads are 1920 x 1080 HD transfers. For RG 428 Vietnam footage, item-level use status is mostly "Undetermined", not "Unrestricted".

### Cited Findings
- NARA Reference Information Paper 90, Part V (audiovisual) lists these Vietnam holdings — [RIP 90 Part V](https://www.archives.gov/publications/ref-info-papers/90/part-5.html):
  - RG 111 **111-LC**: unedited B&W and colour documentary footage, 1964-75, about 7,000 items.
  - RG 111 Army training and information films, 1961-80, about 2,000 items.
  - RG 111 **111-DD**: DoD documentary news release film, 1961-75, about 900 items.
  - RG 127 **127-R** (16mm) and **127-G** (35mm): unedited Marine combat camera film, 1964-75, about 3,500 items.
  - RG 306 USIA films and video, 1961-75, about 1,200 items, including **"North and South Vietnam productions and newsreels"**.
  - RG 330 OSD **network evening newscasts**: 16mm kinescopes of ABC, CBS and NBC, 1965-76, 574 items.
  - RG 342 **342-USAF**: unedited film including Operation Homecoming, 1964-75, about 6,000 items.
  - RG 428 Navy edited film and video, 1961-75, about 1,000 items.
  - RG 428 **428-NPC**: unedited film including POW handling, 1961-75, about 3,500 items.
  - RG 263 CIA: monitored foreign broadcast sound recordings, 1950-76.
- RIP 90 Part V also says the records are generally available for research and duplication, but "some of the material is protected by copyright". It lists donated material: Universal, Fox and Hearst newsreels up to 1967, the CBS News Collection (from 1974), MacNeil/Lehrer (1978-84), and the ABC Radio and NPR collections. — [RIP 90 Part V](https://www.archives.gov/publications/ref-info-papers/90/part-5.html)
- The Unwritten Record (NARA's special-media blog) points to Vietnam film including the Army Library Copy series in RG 111 (e.g. the Lawrence Joel Medal of Honor ceremony), Army Pictorial Center reels **342-APCCLI-7** and **342-APCCLI-10** (helicopter-mounted cameras showing napalm and phosphorus drops and strafing), and **111-DD-317-7** from the Filmed News Releases series. — [Unwritten Record, "Remembering the Vietnam War this Veterans Day" (2017)](https://unwritten-record.blogs.archives.gov/2017/11/09/remembering-the-vietnam-war-this-veterans-day/)
- RG 472 (US Forces in Southeast Asia) has a "Motion Pictures (General)" section, 472.12. — [Guide to Federal Records, RG 472](https://www.archives.gov/research/guide-fed-records/groups/472.html)
- Universal Newsreel at NARA: releases are **UN-UN** and outtakes **200-UN** (1929-1967). "MCA/Universal deeded the copyright to this collection to the US Government", but "individual reels may include content acquired and under copyright to a third party". Very few releases can be downloaded. — [NARA Newsreels page](https://www.archives.gov/research/motion-pictures/newsreels)
- March of Time **releases** (MT-MT) are restricted, and permission must be sought from the donor. March of Time **outtakes** (MT-MTT) are not restricted, but underlying IP issues may remain. Questions go to mopix@nara.gov. — [NARA Newsreels page](https://www.archives.gov/research/motion-pictures/newsreels)
- **Live check (RG 428 open-data scan, 2026-10-27):**
  - 16,419 moving-image descriptions; 5,824 have digital objects.
  - Item-level `useRestriction.status`: Undetermined 12,250; Restricted - Possibly 2,767; Unrestricted 1,401; Restricted - Partly 1.
  - 577 Vietnam-related items with digital objects (keyword match on viet/saigon/RVN/Da Nang/Khe Sanh/Hanoi/Tonkin/Yankee Station). Nearly all are in series naId **75284** "Moving Images Relating to Military Activities" (428-NPC).
  - Effective restriction (item, else series) for those 577: "Undetermined" 540, "Restricted - Possibly" with the note "Some or all of this material may be restricted by copyright or other intellectual property rights restrictions" about 34, "Unrestricted" 1.
  - Source: live scan of [rg_428 JSONL](https://nara-national-archives-catalog.s3.us-east-2.amazonaws.com/?list-type=2&prefix=descriptions/record-groups/rg_428/)
- **Live check (resolution of IA mirrors, via `archive.org/metadata/{id}`):**
  - 428-NPC, 342-USAF and Universal Newsreel mirrors are **655 x 480 MP4**: [428-npc-42085](https://archive.org/metadata/428-npc-42085), [342-usaf-47451](https://archive.org/metadata/342-usaf-47451), [un-un-v40-r86](https://archive.org/metadata/un-un-v40-r86).
  - Some newer 111-LC and 306 mirrors are **1920 x 1080 MP4**: [111-lc-46157](https://archive.org/metadata/111-lc-46157) (about 161 MB for 9.8 min), [306-3287](https://archive.org/metadata/306-3287).
  - Older Public.Resource.Org "gov.archives.arc" and "gov.dod.dimoc" items are **640 x 480 MPEG-2** DVD transfers. Their descriptions say e.g. "DVD Copied by IASL Scanner": [gov.archives.arc.653177](https://archive.org/metadata/gov.archives.arc.653177), [gov.dod.dimoc.20051](https://archive.org/metadata/gov.dod.dimoc.20051).
- **Live check (NARA's own access files):**
  - `ffprobe` on `https://catalog.archives.gov/medialz/mopix/428/NPC/428-npc-37149.mp4` reports h264, **720 x 480**, 653.8 s, about 2.18 Mb/s (the reported `r_frame_rate` is 60/1).
  - NARA's 111-LC-46157 object is 161,322,736 bytes, essentially the same as the IA mirror's 1920 x 1080 file (161,322,735 bytes). So NARA's own access copy for that 111-LC reel is **HD 1080p**, and the IA mirror is a straight copy.
  - Source: [NARA medialz 428-npc-37149](https://catalog.archives.gov/medialz/mopix/428/NPC/428-npc-37149.mp4); [proxy naId=28784](https://catalog.archives.gov/proxy/records/search?naId=28784); [IA 111-lc-46157](https://archive.org/metadata/111-lc-46157)
- **Live check (record-level rights on sample NAIDs):**
  - NAID 28784 (111-LC-46157, series "Motion Picture Films from the Army Library Copy Collection", creator the Army Audiovisual Center): `useRestriction.status` = **Unrestricted**.
  - NAID 71583 (342-USAF-47451, series "Moving Images Relating to Military Aviation Activities", creator the Department of the Air Force): **Unrestricted**.
  - NAID 85342 (428-NPC-37149): use **Undetermined**, access **Unrestricted**.
  - Source: [catalog proxy lookups](https://catalog.archives.gov/proxy/records/search?naId=71583)

### Inferences
- For 1954-1975 combat footage, the useful automated targets are, in order: 428-NPC (most material online), 111-LC, 342-USAF and 127-R/G (unedited, no music, no narration), then the edited 111-DD, Big Picture and 330/DIMOC productions (these have narration and music, see Q5).
- HD transfers exist for at least part of 111-LC and 306. To find them, prefer the newest IA mirrors (uploaded 2025) and read the `width`/`height` of the original file in `archive.org/metadata`. In NARA's own records the only proxy for quality is `objectFileSize`. Bytes per second of runtime (when the runtime is in the description) roughly separates SD from HD.
- In the rough Vietnam keyword scan of RG 428, the one item with "Unrestricted" status was a 1945 film ("Bombing Japanese ships off Saigon"). This suggests NARA's item-level status cannot by itself act as a positive "public domain" flag for Navy Vietnam footage (see Q5).

### Gaps
- I did not finish scanning RG 111, 127 and 342. I stopped those scans for time: their JSONL exports are about 1.6, 12.0 and 0.94 GB. Item counts for those groups come only from RIP 90, and the share of "Unrestricted" vs "Undetermined" there is unknown.
- I found no NARA page describing a systematic 2K/4K rescan programme for Vietnam film, and no way to request HD through an API. HD availability must be checked item by item, using `objectFileSize` against runtime or an `ffprobe` on the medialz URL.
- Only one 111-LC item (46157) was confirmed as a 1080p NARA access file. It is unknown how many other 111-LC or 342-USAF reels are HD.

---

## Q3. NARA material mirrored on the Internet Archive: search syntax, download URLs, rights fields and how reliable they are

### Takeaway
The Internet Archive (IA) holds several families of NARA and DoD film mirrors in the `usgovfilms` and `FedFlix` collections. They can be searched without a key through `advancedsearch.php` and the cursor-based `services/search/v1/scrape` endpoint. File lists and resolutions come from `archive.org/metadata/{id}`, and files download from `archive.org/download/{id}/{file}`.

IA rights fields (`licenseurl`) are **set by the uploader and inconsistent**: CC0, the Public Domain Mark, blank, or even CC BY-NC-ND on commercial re-uploads. They must not be treated as proof of public-domain status. Prove PD from the NARA catalog record and the producing agency instead.

### Cited Findings
- **Advanced search (live):** `https://archive.org/advancedsearch.php?q=...&fl[]=identifier&fl[]=title&fl[]=date&fl[]=licenseurl&fl[]=rights&fl[]=collection&rows=N&output=json` returns `response.numFound` and `docs`. Lucene syntax works, e.g. `identifier:gov.archives.arc.* AND vietnam AND mediatype:movies` (81 hits) or `collection:(usgovfilms OR FedFlix)`. — live query on [advancedsearch.php](https://archive.org/advancedsearch.php?q=identifier%3Agov.archives.arc.*+AND+vietnam+AND+mediatype%3Amovies&fl%5B%5D=identifier&fl%5B%5D=title&fl%5B%5D=licenseurl&rows=40&output=json)
- **Scrape API:** `/services/search/v1/scrape` takes `q`, `fields`, `sorts`, `count` (minimum 100), `cursor` and `total_only`, and returns `items`, `total`, `count` and `cursor` for the next page. The older advancedsearch caps paged results at 10,000. — [IA Item Search APIs docs (readthedocs mirror)](https://doc-tools.readthedocs.io/en/ia-test-gsod/item-search-apis.html)
- **Live check:** `scrape?q=collection:usgovfilms AND mediatype:movies AND (vietnam OR "south vietnam" OR saigon OR RVN)&fields=identifier,title,date,licenseurl&count=100` returned `total: 277` and a cursor. However, `total_only=true` returned 277 for *every* query, unrelated ones included, so the count is unreliable. Use advancedsearch with `rows=0` for counts. — live query on [scrape endpoint](https://archive.org/services/search/v1/scrape?q=collection:usgovfilms&total_only=true)
- **Live identifier-family counts** (advancedsearch `numFound`, 2026-10-27):

  | Query | Items |
  |---|---|
  | `collection:usgovfilms` | 24,873 |
  | `collection:FedFlix` | 13,556 |
  | `identifier:gov.archives.arc.*` | 2,108 (Public.Resource.Org DVD transfers, "ARC" = old NARA ID) |
  | `identifier:gov.dod.dimoc.*` | 917 (DoD DIMOC "PIN" films) |
  | `identifier:428-npc-*` | 1,523 |
  | `identifier:111-lc-*` | 235 |
  | `identifier:342-usaf-*` | 43 |
  | `identifier:330-dimoc-*` | 16 |
  | `identifier:un-un-*` | 109 (Universal Newsreel) |
  | `identifier:306-*` | 323 |
  | `collection:prelinger` | 10,468 |

  Source: live queries on [advancedsearch.php](https://archive.org/advancedsearch.php)
- **Item metadata and download (live):** `https://archive.org/metadata/{identifier}` returns `metadata` (title, date, creator, collection, licenseurl, uploader, description) and `files[]` with `name`, `format`, `source` (original/derivative), `size`, `width`, `height` and `length`. Files download from `https://archive.org/download/{identifier}/{name}`.
  - Example: [gov.dod.dimoc.30200](https://archive.org/metadata/gov.dod.dimoc.30200) ("Vietnam Village Reborn") has an original `gov.dod.dimoc.30200.mpeg` (MPEG2, 640x480, 902 MB, 27.6 min) plus derivative `.ogv` and `_512kb.mp4`.
- **Provenance strings in IA descriptions (live):**
  - Public.Resource.Org items cite NARA IDs, e.g. "ARC 653177 / LI 263.2408" ([gov.archives.arc.653177](https://archive.org/details/gov.archives.arc.653177)), or DoD PIN numbers ([gov.dod.dimoc.20051](https://archive.org/details/gov.dod.dimoc.20051)).
  - Newer mirrors uploaded by skip@avgeeks.com and robertvale07 include `https://catalog.archives.gov/id/{naId}` links, e.g. [111-lc-46157](https://archive.org/details/111-lc-46157) → NAID 28784 and [428-npc-8345](https://archive.org/details/428-npc-8345) → NAID 78450.
- **Rights-field reliability (live):** of the first 100 `usgovfilms` Vietnam results from the scrape API, **77 had no `licenseurl`**. The 23 that had one were all `gov.archives.arc.*` with CC0 (`http://creativecommons.org/publicdomain/zero/1.0/`), a dedication set by the uploader (carl@media.org / Public.Resource.Org). Newer `un-un-*` and `306-*` mirrors use the Public Domain Mark 1.0, and many 428-npc and 111-lc mirrors have no licence at all. — live scrape on [usgovfilms Vietnam query](https://archive.org/services/search/v1/scrape?q=collection:usgovfilms%20AND%20mediatype:movies%20AND%20vietnam&fields=identifier,licenseurl&count=100)
- One uploader of a 342-USAF mirror writes that the NARA Catalog "Use" field reads "Unrestricted" rather than "Possibly Restricted", "so use it at your own risk (not legal advice)". The IA rights metadata is the uploader's own judgement. — [342-usaf-47451 on IA](https://archive.org/details/342-usaf-47451)
- A commercial uploader (Periscope Film, IA collection `PeriscopeFilm`/`ephemera`) published an Army "Big Picture" episode with `licenseurl` **CC BY-NC-ND 4.0**, a licence claim on a federal production. — [50224-material-readiness-vwr](https://archive.org/details/50224-material-readiness-vwr)
- **IA and NARA disagree (live):** the IA mirror [gov.archives.arc.653177](https://archive.org/details/gov.archives.arc.653177) ("The Battle of Ia Drang Valley") and [gov.archives.arc.643344](https://archive.org/details/gov.archives.arc.643344) ("Bomb Damage in Hanoi") carry **CC0** `licenseurl`. NARA's records for NAIDs 653177 and 643344 say **"Restricted - Possibly"**, with the note "Some or all of this material may be restricted by copyright or other intellectual property right restrictions." They belong to the CIA series "Moving Images Relating to Intelligence and International Relations". — [proxy naId=653177](https://catalog.archives.gov/proxy/records/search?naId=653177); [proxy naId=643344](https://catalog.archives.gov/proxy/records/search?naId=643344)

### Inferences
- Treat any IA `licenseurl`/`rights` value only as a hint. Proof of PD should be: (a) a NARA `naId` or a DoD PIN / local identifier pulled from the description; (b) the NARA record's producing agency and `useRestriction` (Q1); (c) the IA file checksum and URL saved as the source copy.
- The `gov.archives.arc.N` number equals the NARA NAID. This was confirmed live for 653177 and 643344, which both resolve by `naId=` through the catalog proxy to the same titles. The local identifiers there are "263.2408" and "263.234" (the "LI" in the IA description). IA identifiers such as `428-npc-37149` map to the NARA local identifier `428-NPC-37149`. For `un-un-v40-r86` the IA description carries NAID 234275177 directly.
- When an IA mirror and NARA both exist, the IA copy is the practical download (no key, no 403). Keep the NARA naId as the citation.

### Gaps
- I could not reach archive.org's official API pages directly (only a readthedocs mirror), so `scrape` behaviour beyond what was tested (sort keys, limits) is unverified.
- I found no IA-wide policy statement on how `licenseurl` is set for `usgovfilms` items.

---

## Q4. Other US government and US-hosted sources: DVIDS, service history centres, presidential libraries, Library of Congress, Prelinger

### Takeaway
DVIDS has a JSON API that needs a free key, but its library is overwhelmingly post-2000 and I found no evidence of systematic Vietnam-era film there. Presidential libraries hold Vietnam-era White House film; LBJ's White House Naval Photographic Center films are catalogued as public domain, but most are viewed or copied on site or through YouTube and partners, with no download API. The Library of Congress site blocked scripted access (a Cloudflare challenge) in this test.

Prelinger Archives on IA is mainly *sponsored and ephemeral* films, not federal ones. About 65% is PD, reuse is unrestricted for the PD titles, credit is requested, and Getty sells HD masters.

### Cited Findings
- **DVIDS:** the API is "currently open". Get a key via the sign-up or login link on the site; access questions go to dvidsservicedesk@dvidshub.net. The API searches more than 1.8 million assets as JSON over HTTP. — [DVIDS API docs](https://api.dvidshub.net/docs)
- **Live check:** `https://api.dvidshub.net/search?q=vietnam&type=video` without a key returns `{"errors":["Bad Request - No API key was provided"]}`. — live check on [api.dvidshub.net/search](https://api.dvidshub.net/search?q=vietnam&type=video)
- **LBJ Library:** the White House Naval Photographic Center Films (December 1963 to January 1969; 77 films, each with unfinished footage, audio and finished film) are catalogued as **public domain**. They include monthly "Reports on the Activities of the President" (June 1966 to January 1968). Some are on the LBJ Library YouTube channel and through the Texas Archive of the Moving Image partnership. — [Discover LBJ, AV film](https://discoverlbj.org/loh/av/av-film)
- The LBJ Library's own guide says most materials are viewed on site and most AV material can be reproduced for purchase. — [Hofstra guide to LBJ Library online research (2014, PDF)](https://www.hofstra.edu/pdf/academics/colleges/hclas/prssty/presidential-guidetoonlineresearchonlbjlibrary-spring2014.pdf)
- **JFK Library** Naval Photographic Center / White House films carry a generic warning that some materials "may be subject to copyright or other intellectual property restrictions". — [JFK Library moving image record](https://www.jfklibrary.org/asset-viewer/archives/jfkwhf-whn15)
- **Prelinger Archives** (IA collection `prelinger`): founded in 1983. In 2002 its film collection (60,000+ ephemeral, advertising, educational, industrial and amateur films) was acquired by the Library of Congress. About 8,800 items are on IA, and Getty Images represents the collection for stock sales. "Since 2012 … newer and higher-quality versions" have been uploaded, and "the highest quality" is usually the most recent upload. — [IA Prelinger collection metadata](https://archive.org/metadata/prelinger/metadata)
- About 65% of Prelinger is PD in the US (expired or no notice). The PD films are available "for download and unrestricted reuse", users "do not need to notify" IA or Prelinger, and credit is requested. Physical or higher-quality access for commercial users goes through Getty. — [IA Help: Prelinger Archive](https://help.archive.org/help/prelinger-archive/); [Wikipedia: Prelinger Archives](https://en.wikipedia.org/wiki/Prelinger_Archives)
- **Live check:** a `prelinger` + vietnam search finds 79 items, mostly home movies of US anti-war marches (e.g. `000432`, an anti-Vietnam War demonstration in San Francisco, 15 April 1967) and Cold War films such as "Red Chinese Battle Plan" (1964) and "Brink of Disaster" (1972), not combat footage. — live query on [advancedsearch](https://archive.org/advancedsearch.php?q=collection%3Aprelinger+AND+vietnam&fl%5B%5D=identifier&fl%5B%5D=title&rows=20&output=json)
- **Library of Congress:** `https://www.loc.gov/search/?q=vietnam&fa=original-format:film,+video&fo=json` returned HTTP 403 with a Cloudflare "Just a moment…" challenge when scripted from this machine. — live check on [loc.gov search JSON](https://www.loc.gov/search/?q=vietnam&fa=original-format:film,+video&fo=json)
- **Australian War Memorial** (a non-US mirror of a USAF film): F10258, "Khe Sanh: victory for air power" (1968, about 15 min, 600th Photographic Squadron USAF) is listed with copyright status "unlicensed". — [AWM F10258](https://www.awm.gov.au/collection/C190912)
- Lookout Mountain Laboratory / 1352nd Photographic Group archive lists a "Battle of Khe Sanh" (about 14:49) linked to an archive.org item. — [Lookout America item 106](https://lookoutamerica.org/items/show/106)

### Inferences
- For automated video sourcing, DVIDS is low priority for 1954-75. Its API key is free, but its holdings are contemporary. Worth a one-off check with the key for "Vietnam War 50th Commemoration" uploads, which may reuse NARA footage at higher resolution.
- The Army Center of Military History, USMC History Division, Naval History and Heritage Command and the Air Force film units mostly hold *publications and photos*. Their wartime film went to NARA (RG 111/127/428/342) and DIMOC (`gov.dod.dimoc.*` on IA). That makes NARA plus IA the practical film source.
- LBJ/Nixon White House film (WHNPC, WHCA) is federal work and likely PD, but there is no bulk download API, so treat it as manual or YouTube-sourced, with provenance recorded by hand.

### Gaps
- No primary source found on whether the CMH, USMC History Division or NHHC host downloadable Vietnam *motion pictures*. I did not search these sites in depth.
- No rights statement found for Nixon Library moving images (WHCA).
- I could not test the LoC JSON API (blocked) and did not find its Vietnam moving-image rights advisories.
- DVIDS Vietnam-era holdings were not counted (no key).

---

## Q5. Known traps: footage in federal custody that is not PD, Content ID claims, and documenting provenance

### Takeaway
"In NARA" does not mean "public domain". The main traps for Vietnam-era film:
1. Network news in federal record groups: RG 330's 574 ABC/CBS/NBC kinescopes and the donated CBS News Collection.
2. Donated commercial newsreels other than Universal (March of Time releases restricted; Fox and Hearst donated).
3. Foreign productions captured or collected by the CIA and USIA, e.g. the North Vietnamese-language "Bomb Damage in Hanoi" in the CIA collection.
4. Third-party content inside edited government films: music, network clips, and stories acquired for Universal Newsreel.
5. Commercial re-uploads asserting licences or Content ID over PD footage.

Defend a PD claim with a provenance record: NARA naId, local ID, series, producing agency, `useRestriction` snapshot, source URL and checksum.

### Cited Findings
- RG 330 (Office of the Secretary of Defense) holds **16mm kinescopes of ABC, CBS and NBC evening newscasts, 1965-76 (574 items)**. The donated material includes the **CBS News Collection (from 1974)** and the Universal, Fox and Hearst newsreels. "Some of the material is protected by copyright." — [RIP 90 Part V](https://www.archives.gov/publications/ref-info-papers/90/part-5.html)
- RG 306 USIA holdings include "North and South Vietnam productions and newsreels". — [RIP 90 Part V](https://www.archives.gov/publications/ref-info-papers/90/part-5.html)
- Universal Newsreel: copyright deeded to the US Government, but "individual reels may include content acquired and under copyright to a third party". March of Time releases need donor permission. — [NARA Newsreels page](https://www.archives.gov/research/motion-pictures/newsreels); MCA/Universal gave the collection in 1970 and transferred rights in 1974, though some stories may carry underlying IP — [Wikipedia: Universal Newsreel](https://en.wikipedia.org/wiki/Universal_Newsreel)
- NARA's model motion-picture restriction record reads "Restricted - Fully" with the note "Copyright held by RKO General Inc." This shows that copyrighted commercial films sit in the catalog with explicit flags. — [NARA LCDRG / v2 spec examples](https://catalog.archives.gov/api/v2/swagger.json)
- "Restricted - Possibly" is defined as "may have a use restriction", and "Undetermined" as "unknown". — [NARA Use Restriction Status list](https://www.archives.gov/research/catalog/lcdrg/authoritylists/uselist.html)
- **Live examples of foreign or third-party material in IA "gov.archives" mirrors:**
  - [gov.archives.arc.643344](https://archive.org/details/gov.archives.arc.643344) "Bomb Damage in Hanoi" (1972). Its description reads: "National Security Council. Central Intelligence Agency … This film is in Vietnamese and shows victims of bomb damage in Hanoi … ARC 643344 / LI 263.234". It still carries a CC0 `licenseurl` from the uploader.
  - [gov.archives.arc.653177](https://archive.org/details/gov.archives.arc.653177) "The Battle of Ia Drang Valley" (1965) is also from the CIA file series (LI 263.2408), so its producer is not stated.
  - NARA marks both NAIDs **"Restricted - Possibly"** (copyright/IP note), while the IA mirrors say CC0. — [proxy naId=653177](https://catalog.archives.gov/proxy/records/search?naId=653177); [proxy naId=643344](https://catalog.archives.gov/proxy/records/search?naId=643344)
- **Content ID:** in 2011, companies including NBC Universal, Al Jazeera and Discovery used YouTube Content ID to claim **FedFlix** public-domain government videos. The only dispute grounds available were false match, written permission, or fair use. — [Boing Boing / Cory Doctorow (2011)](https://boingboing.net/2011/12/12/youtubes-real-pirates-multi.html); a dispute log reports 250 of 326 matches cleared (secondary source) — [Nexa mailing list thread](https://server-nexa.polito.it/hyperkitty/list/nexa@server-nexa.polito.it/thread/ELOQ5VGO2J6PV3Z5G6EY6NJO56YWB4NN/)
- Commercial archives re-upload federal films with their own catalogue numbers and terms. Examples: Periscope Film IA items such as [21794B52FromGuamToNamMosVwr](https://archive.org/details/21794B52FromGuamToNamMosVwr) ("B-52 Bomber Operation Arc Light 1965 Guam to Vietnam") and [56284-american-navy-in-vietnam-vwr](https://archive.org/details/56284-american-navy-in-vietnam-vwr), and one Big Picture episode labelled CC BY-NC-ND 4.0 ([50224-material-readiness-vwr](https://archive.org/details/50224-material-readiness-vwr)). — live IA queries
- NARA: "Proper credit lines are encouraged". Example form: "Credit National Archives (photo no. 306-NT-186000)". NARA "does not grant exclusive or non-exclusive publication privileges". — [NARA Publish photos](https://www.archives.gov/research/publish-photos)

### Inferences
- **Automated PD gate (proposed):**
  - **Pass** only if (a) the record group or creator is a US federal unit (Army Signal Corps / APC, Navy Photographic Center, USAF photo squadrons, USMC combat camera, DoD/DIMOC, USIA *own* productions), AND (b) `useRestriction.status` is not "Restricted - Fully/Partly", AND (c) no `useRestriction.note` or title or description mentions CBS, NBC, ABC, Movietone, Hearst, Paramount, March of Time, Pathé, Grinberg, Vietnamese-language, "captured", "North Vietnam(ese) film", "Liberation", or a foreign studio.
  - Items marked "Restricted - Possibly" or with the generic "may be restricted by copyright" note go to **manual review**, not auto-reject. In RG 428 the note is boilerplate on many unedited Navy reels.
  - "Undetermined" plus a federal-unit origin plus an unedited reel (`428-NPC`, `111-LC`, `342-USAF`, `127-R/G`) is the strongest automated PD case.
- **Edited** government films (Big Picture, DIMOC "Staff Film Report") may contain commercial music or licensed network clips. Prefer unedited reels (silent or wild sound) for an automated pipeline, or strip the audio and rebuild sound from your own layers.
- Footage of North Vietnamese origin (CIA/USIA collected) is a separate legal question. A foreign work could have had US copyright restored (URAA / 17 U.S.C. §104A) if it was protected in its source country. This is an inference that needs legal confirmation, and I did not fetch a source for it. Exclude such items automatically.
- **Provenance record per clip:** NARA naId and catalog URL, `localIdentifier` (e.g. 428-NPC-37149), series naId and title, record group, creator, a JSON snapshot of `useRestriction` and `accessRestriction` with the access date, IA identifier, file name, size and SHA-1 (`files[].sha1` in IA metadata), the download URL, and the extract timecodes. This answers a Content ID dispute or a stock-site claim with NARA's own record.

### Gaps
- No current (2024-2026) source found on how YouTube handles Content ID disputes over NARA footage, or on specific stock companies that claim NARA Vietnam clips.
- No primary legal source fetched on the copyright status of North Vietnamese or NLF films held by US agencies (URAA restoration). This needs counsel.
- I could not confirm whether NARA flags music inside edited DoD films anywhere in the metadata.

---

## Q6. Concrete Vietnam-era films and footage with identifiers and links

### Takeaway
Dozens of concrete, downloadable Vietnam-era federal films exist on IA with NARA or DoD identifiers, and NARA's catalog lists 500+ digitised Navy 428-NPC Vietnam reels. Some titles from the brief were not found under those exact names: "Air Power at Khe Sanh", "Operation Starlite", and Da Nang 1965 landing-specific reels. The nearest equivalents are listed below.

### Cited Findings (all live checks via archive.org advancedsearch/metadata, 2026-10-27, unless another source is noted)
**Edited DoD and Army films (narrated; check music)**
- "THE BATTLE OF KHE SANH", DoD PIN 20051. Photographed "by all the services", it covers tactical and strategic air power (including B-52s) and airlift. 640x480 MPEG2, 28.5 min, CC0 per uploader. — [gov.dod.dimoc.20051](https://archive.org/details/gov.dod.dimoc.20051)
- Nearest to "Air Power at Khe Sanh": USAF 600th Photo Squadron, "Khe Sanh: victory for air power" (1968, AWM F10258). — [AWM](https://www.awm.gov.au/collection/C190912)
- "VIETNAM VILLAGE REBORN" (1967), DoD PIN 30200: Operation Lam Son II, US 1st Infantry Division and ARVN 5th Division. 640x480 MPEG2, 27.6 min. — [gov.dod.dimoc.30200](https://archive.org/details/gov.dod.dimoc.30200)
- Army "The Big Picture" Vietnam-related episodes:
  - "Why Vietnam?" — [gov.archives.arc.2569861](https://archive.org/details/gov.archives.arc.2569861)
  - "World Trouble Spots" — [2569843](https://archive.org/details/gov.archives.arc.2569843)
  - "Not for Conquest" — [2569868](https://archive.org/details/gov.archives.arc.2569868)
  - "Stay Alert, Stay Alive" — [2569886](https://archive.org/details/gov.archives.arc.2569886)
  - "Shotgun Rider" — [2569887](https://archive.org/details/gov.archives.arc.2569887)
  - "Your Army Reports" Nos. 6, 13, 14 — [2569875](https://archive.org/details/gov.archives.arc.2569875), [2569896](https://archive.org/details/gov.archives.arc.2569896), [2569898](https://archive.org/details/gov.archives.arc.2569898)
- "Why Vietnam?" (1965, DoD), NTIS copy — [gov.ntis.ava08194vnb1](https://archive.org/details/gov.ntis.ava08194vnb1)
- "MARINES 65" (1966) — [gov.dod.dimoc.23436](https://archive.org/details/gov.dod.dimoc.23436)
- "THE BATTLE" (1965) — [gov.dod.dimoc.23421](https://archive.org/details/gov.dod.dimoc.23421)
- "FULL BLADE" (1965) — [gov.dod.dimoc.23420](https://archive.org/details/gov.dod.dimoc.23420)
- DoD "Staff Film Report" 66-12A, 66-19A, 66-27A, 66-28A, 67-2 — [26961](https://archive.org/details/gov.dod.dimoc.26961), [26968](https://archive.org/details/gov.dod.dimoc.26968), [26979](https://archive.org/details/gov.dod.dimoc.26979), [26980](https://archive.org/details/gov.dod.dimoc.26980), [27015](https://archive.org/details/gov.dod.dimoc.27015)
- "The Battle of Ia Drang Valley" (1965; CIA series, LI 263.2408, NARA title "The Battle of La Drang Valley" [sic]; NARA use "Restricted - Possibly"; producer unclear; **do not auto-use**) — [gov.archives.arc.653177](https://archive.org/details/gov.archives.arc.653177), [NARA 653177](https://catalog.archives.gov/id/653177)
- "Task Force Oregon" (1967) — [gov.archives.arc.31254](https://archive.org/details/gov.archives.arc.31254)
- "Vietnam Special" (1967, origin to verify) — [gov.archives.arc.653071](https://archive.org/details/gov.archives.arc.653071)
- "This Is Saigon" (1967) — [gov.archives.arc.616381](https://archive.org/details/gov.archives.arc.616381)
- "Saigon, Target Zero" (psychological warfare film, 1968) — [gov.archives.arc.32416](https://archive.org/details/gov.archives.arc.32416)

**Air Force / B-52 / Arc Light**
- "Strategic Air Command Semiannual Film Report" (1968) — [gov.dod.dimoc.20791](https://archive.org/details/gov.dod.dimoc.20791)
- "History of the Air Force: From Vietnam to Present, 1965-1977" — [gov.dod.dimoc.38380](https://archive.org/details/gov.dod.dimoc.38380)
- "342-USAF-47451 Street Scenes in Saigon" (1972, NAID 71583, 2 reels, 655x480) — [342-usaf-47451](https://archive.org/details/342-usaf-47451)
- Arc Light: the only titled hit was a commercial Periscope re-upload — [21794B52FromGuamToNamMosVwr](https://archive.org/details/21794B52FromGuamToNamMosVwr). Search NARA 342-USAF for originals.

**Tet 1968**
- "Vietcong attacks during Tet; Saigon" (1968) — [gov.archives.arc.31793](https://archive.org/details/gov.archives.arc.31793)
- "Tet Offensive Footage (Hue, RVN)" (1968; unedited Navy footage with shot list; 655x480, 5.8 min) — [428-npc-42085](https://archive.org/details/428-npc-42085)
- "Tet Offensive – Stock Footage" (1968) — [428-npc-42090](https://archive.org/details/428-npc-42090)
- "Vietnamese 'Tet' Celebration 1967 Saigon" — [428-npc-39355](https://archive.org/details/428-npc-39355)

**Navy / carriers / riverine** (NARA naIds from the open-data scan; IA mirror where it exists)
- 428-NPC-37149 "Air Strike – South Viet Nam" (1966-07-09), NAID 85342 (use Undetermined; 720x480 MP4, 10.9 min, 178 MB at `https://catalog.archives.gov/medialz/mopix/428/NPC/428-npc-37149.mp4`) — [catalog](https://catalog.archives.gov/id/85342)
- 428-NPC-38401 "Air Strike Recovery aboard USS Bon Homme Richard (CVA-31), Gulf of Tonkin" (1967-06-16), NAID 85745 — [catalog](https://catalog.archives.gov/id/85745)
- 428-NPC-36144 "Swift Boats, An Thoi, RVN" (1966), NAID 84811 — [catalog](https://catalog.archives.gov/id/84811)
- 428-NPC-38752 "River Assault Flot One, Mekong Delta" (1967), NAID 85851 — [catalog](https://catalog.archives.gov/id/85851)
- 428-NPC-42307 "USS New Jersey last line period off Vietnamese coast", NAID 87167 — [catalog](https://catalog.archives.gov/id/87167)
- "McNamara visits USS Oriskany (CVA-34), Yankee Station, Gulf of Tonkin, 10-1966" (community upload, PD Mark) — [NPC-37453](https://archive.org/details/NPC-37453)

**Army ground / pacification** (111-LC and others)
- "Village Resettlement Program, Quang Ngai Province" (1967) — [gov.archives.arc.31762](https://archive.org/details/gov.archives.arc.31762)
- "A-1-5 1st Air Cavalry, Binh Tuy Province" (1971) — [gov.archives.arc.34265](https://archive.org/details/gov.archives.arc.34265)
- "Operations of 1/5 Mech. Inf. along the DMZ, Phu Bai" (1971) — [gov.archives.arc.34325](https://archive.org/details/gov.archives.arc.34325)
- "'C' Co 2/22 25th Inf. Div. in Cambodia" (1970) — [gov.archives.arc.33723](https://archive.org/details/gov.archives.arc.33723)
- "Documentary of XXIV Corps" (1971) — [gov.archives.arc.33997](https://archive.org/details/gov.archives.arc.33997)
- "Vietnamese 7th Independence Day celebration, Saigon" (Oct 1962; **1920x1080**; NAID 28784; NARA use **Unrestricted**; NARA file `https://catalog.archives.gov/medialz/mopix/111/lc/111-lc-46157.mp4`) — [111-lc-46157](https://archive.org/details/111-lc-46157), [NARA 28784](https://catalog.archives.gov/id/28784)
- "USIS officer visits New Life Hamlet" (1964) — [111-lc-48194](https://archive.org/details/111-lc-48194)
- "Stock Footage of Saigon" (1955) — [gov.archives.arc.27343](https://archive.org/details/gov.archives.arc.27343)

**Hanoi 1972** (provenance trap; see Q5)
- "Bomb Damage in Hanoi" (1972; CIA collection, Vietnamese-language) — [gov.archives.arc.643344](https://archive.org/details/gov.archives.arc.643344), [gov.archives.arc.647192](https://archive.org/details/gov.archives.arc.647192)
- "Carpet Bombing of Hanoi" (1972) — [gov.archives.arc.644905](https://archive.org/details/gov.archives.arc.644905)

**POW return 1973**
- "Homecoming" (1973) — [330-dimoc-dnbaf870206-r40](https://archive.org/details/330-dimoc-dnbaf870206-r40)

**Newsreel and USIA**
- Universal Newsreel Vol. 40 Rel. 86 (24 Oct 1967; NAID 234275177; PD Mark per uploader) — [un-un-v40-r86](https://archive.org/details/un-un-v40-r86)
- USIA "Seven Nations' Summit Conference, Manila" (1966; NAID 49634; 1920x1080) — [306-3287](https://archive.org/details/306-3287)

**Unwritten Record picks:** 342-APCCLI-7 and 342-APCCLI-10 (helicopter-mounted camera: napalm and strafing), and 111-DD-317-7. — [Unwritten Record (2017)](https://unwritten-record.blogs.archives.gov/2017/11/09/remembering-the-vietnam-war-this-veterans-day/)

### Inferences
- For "Marine Corps landing at Da Nang 1965" and "Operation Starlite" (August 1965), the likely originals are USMC combat camera reels in **127-R/127-G** and DoD edited films such as "MARINES 65". An `ancestorNaId` search on the 127 series with q="Da Nang" or "Starlite" (API key needed) or a scan of the `rg_127` open-data JSONL is the route. This is inferred from RIP 90's description of 127-R/G as 1964-75 unedited combat film.
- Carrier operations 1965-68 are best covered by 428-NPC (Yankee Station, Gulf of Tonkin, CVA recovery reels). The open-data scan found these titles directly.

### Gaps
- No item titled exactly "Air Power at Khe Sanh" was found on IA or in web search. An AWM-held USAF film "Khe Sanh: victory for air power" exists, and its NARA identifier was not located.
- "Operation Starlite" footage was not found by title on IA. The NARA RG 127 scan was not finished at the time of writing.
- Durations, resolutions and restriction status were checked only for the items whose metadata was opened (listed in Q2). The others are unverified beyond title, date and licenseurl.
